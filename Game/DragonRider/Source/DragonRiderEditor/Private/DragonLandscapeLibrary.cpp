#include "DragonLandscapeLibrary.h"

#include "Editor.h"
#include "EngineUtils.h"
#include "Landscape.h"
#include "LandscapeInfo.h"
#include "LandscapeProxy.h"
#include "LandscapeSubsystem.h"
#include "Materials/MaterialInterface.h"
#include "Misc/App.h"
#include "RenderingThread.h"
#include "Misc/FileHelper.h"

DEFINE_LOG_CATEGORY_STATIC(LogDragonLandscape, Log, All);

ALandscape* UDragonLandscapeLibrary::ImportHeightmapLandscape(const FString& RawHeightmapPath, int32 SizePx, FVector LocationCm, FVector Scale,
	UMaterialInterface* Material, const FString& Label, int32 GridSize, bool bSpatiallyLoaded)
{
	constexpr int32 QuadsPerSection = 63;
	constexpr int32 SectionsPerComponent = 2;
	constexpr int32 QuadsPerComponent = QuadsPerSection * SectionsPerComponent;

	UWorld* World = GEditor ? GEditor->GetEditorWorldContext().World() : nullptr;
	if (!World)
	{
		UE_LOG(LogDragonLandscape, Error, TEXT("No editor world"));
		return nullptr;
	}
	if (SizePx < QuadsPerComponent + 1 || (SizePx - 1) % QuadsPerComponent != 0)
	{
		UE_LOG(LogDragonLandscape, Error, TEXT("%s: size %d is not 126*k + 1"), *Label, SizePx);
		return nullptr;
	}
	TArray<uint8> Bytes;
	if (!FFileHelper::LoadFileToArray(Bytes, *RawHeightmapPath) || Bytes.Num() != SizePx * SizePx * 2)
	{
		UE_LOG(LogDragonLandscape, Error, TEXT("%s: could not read %d x %d uint16 from %s (%d bytes)"), *Label, SizePx, SizePx, *RawHeightmapPath, Bytes.Num());
		return nullptr;
	}
	TArray<uint16> Heights;
	Heights.SetNumUninitialized(SizePx * SizePx);
	FMemory::Memcpy(Heights.GetData(), Bytes.GetData(), Bytes.Num()); // little-endian on Windows

	ALandscape* Landscape = World->SpawnActor<ALandscape>(LocationCm, FRotator::ZeroRotator);
	if (!Landscape)
	{
		return nullptr;
	}
	Landscape->LandscapeMaterial = Material;
	Landscape->SetActorRelativeScale3D(Scale);
	Landscape->StaticLightingLOD = FMath::DivideAndRoundUp(FMath::CeilLogTwo((SizePx * SizePx) / (2048 * 2048) + 1), (uint32)2);

	TMap<FGuid, TArray<uint16>> HeightDataPerLayer;
	HeightDataPerLayer.Add(FGuid(), MoveTemp(Heights));
	TMap<FGuid, TArray<FLandscapeImportLayerInfo>> MaterialLayersPerLayer;
	MaterialLayersPerLayer.Add(FGuid(), TArray<FLandscapeImportLayerInfo>());
	Landscape->Import(FGuid::NewGuid(), 0, 0, SizePx - 1, SizePx - 1, SectionsPerComponent, QuadsPerSection, HeightDataPerLayer,
		*RawHeightmapPath, MaterialLayersPerLayer, ELandscapeImportAlphamapType::Additive, TArrayView<const FLandscapeLayer>());
	Landscape->SetActorLabel(Label);

	ULandscapeInfo* Info = Landscape->GetLandscapeInfo();
	if (!Info)
	{
		UE_LOG(LogDragonLandscape, Error, TEXT("%s: import produced no landscape info"), *Label);
		return Landscape;
	}
	Info->UpdateLayerInfoMap(Landscape);

	ULandscapeSubsystem* Subsystem = World->GetSubsystem<ULandscapeSubsystem>();
	int32 NumProxies = 0;
	if (Subsystem && Subsystem->IsGridBased())
	{
		Subsystem->ChangeGridSize(Info, static_cast<uint32>(FMath::Max(1, GridSize)));
	}
	Info->ForEachLandscapeProxy([&NumProxies, bSpatiallyLoaded, &Label](ALandscapeProxy* Proxy)
	{
		if (Proxy != nullptr && !Proxy->IsA<ALandscape>())
		{
			Proxy->SetIsSpatiallyLoaded(bSpatiallyLoaded);
			Proxy->SetFolderPath(*FString::Printf(TEXT("Archipelago/Landscape/%s"), *Label));
			++NumProxies;
		}
		return true;
	});
	Landscape->SetFolderPath(*FString::Printf(TEXT("Archipelago/Landscape/%s"), *Label));
	// The heights were written into the default edit layer; the final heightmap is a GPU merge of the layers.
	// It needs a renderer: run the commandlet with -AllowCommandletRendering.
	if (!FApp::CanEverRender())
	{
		UE_LOG(LogDragonLandscape, Error, TEXT("%s: no renderer, so the edit layers can't be merged (run the commandlet with -AllowCommandletRendering)"), *Label);
	}
	Landscape->ForceLayersFullUpdate();
	UE_LOG(LogDragonLandscape, Display, TEXT("DRAGON_LANDSCAPE %s: %dx%d, %d components, %d streaming proxies, scale %s"),
		*Label, SizePx, SizePx, Info->XYtoComponentMap.Num(), NumProxies, *Scale.ToString());
	return Landscape;
}

int32 UDragonLandscapeLibrary::FlushLandscapes()
{
	UWorld* World = GEditor ? GEditor->GetEditorWorldContext().World() : nullptr;
	if (!World) { return 0; }
	// The edit-layer merge and its GPU readback into the heightmaps (what gets saved, and what collision uses) run
	// over several updates; a single update leaves some components flat. Keep updating until every landscape
	// reports up to date.
	int32 N = 0, Pass = 0;
	for (TActorIterator<ALandscape> It(World); It; ++It) { It->ForceLayersFullUpdate(); ++N; }
	for (; Pass < 400; ++Pass)
	{
		bool bAllDone = true;
		for (TActorIterator<ALandscape> It(World); It; ++It)
		{
			if (!It->IsUpToDate())
			{
				bAllDone = false;
				It->ForceUpdateLayersContent();
			}
		}
		FlushRenderingCommands();
		if (bAllDone) { break; }
	}
	UE_LOG(LogDragonLandscape, Display, TEXT("DRAGON_LANDSCAPE flushed %d landscapes in %d passes"), N, Pass);
	return N;
}

bool UDragonLandscapeLibrary::SampleLandscapeHeight(FVector LocationCm, float& OutHeightCm)
{
	UWorld* World = GEditor ? GEditor->GetEditorWorldContext().World() : nullptr;
	OutHeightCm = 0.f;
	if (!World) { return false; }
	bool bFound = false;
	for (TActorIterator<ALandscapeProxy> It(World); It; ++It)
	{
		const TOptional<float> H = It->GetHeightAtLocation(LocationCm, EHeightfieldSource::Complex);
		if (H.IsSet() && (!bFound || H.GetValue() > OutHeightCm))
		{
			OutHeightCm = H.GetValue();
			bFound = true;
		}
	}
	return bFound;
}
