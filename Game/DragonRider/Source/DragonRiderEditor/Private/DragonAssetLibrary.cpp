#include "DragonAssetLibrary.h"

#include "EditorFramework/AssetImportData.h"
#include "UObject/UnrealType.h"
#include "ConvexDecompTool.h"
#include "Engine/StaticMesh.h"
#include "PhysicsEngine/BodySetup.h"
#include "StaticMeshResources.h"

// From UnrealEd's private GeomFitUtils.h (exported, but the header isn't public).
UNREALED_API int32 GenerateKDopAsSimpleCollision(UStaticMesh* StaticMesh, const TArray<FVector>& dirs, bool bUpdate);
UNREALED_API int32 GenerateBoxAsSimpleCollision(UStaticMesh* StaticMesh, bool bUpdate);

bool UDragonAssetLibrary::ResetImportData(UObject* Asset, const FString& SourceFile)
{
	if (!Asset) { return false; }
	FObjectPropertyBase* Prop = CastField<FObjectPropertyBase>(Asset->GetClass()->FindPropertyByName(TEXT("AssetImportData")));
	if (!Prop) { return false; }
	UAssetImportData* Clean = NewObject<UAssetImportData>(Asset, NAME_None, RF_Transactional);
	if (!SourceFile.IsEmpty())
	{
		Clean->Update(SourceFile);   // stores the path relative to the package, plus timestamp and MD5
	}
	Asset->Modify();
	Prop->SetObjectPropertyValue(Prop->ContainerPtrToValuePtr<void>(Asset), Clean);
	Asset->MarkPackageDirty();
	return true;
}

int32 UDragonAssetLibrary::GetCollisionPrimitiveCount(UStaticMesh* Mesh)
{
	const UBodySetup* Body = Mesh ? Mesh->GetBodySetup() : nullptr;
	if (!Body) { return 0; }
	const FKAggregateGeom& G = Body->AggGeom;
	return G.BoxElems.Num() + G.SphereElems.Num() + G.SphylElems.Num() + G.ConvexElems.Num() + G.TaperedCapsuleElems.Num();
}

int32 UDragonAssetLibrary::SetCollision(UStaticMesh* Mesh, const FString& Shape, int32 HullCount, int32 MaxHullVerts)
{
	if (!Mesh) { return 0; }
	if (!Mesh->GetBodySetup()) { Mesh->CreateBodySetup(); }
	UBodySetup* Body = Mesh->GetBodySetup();
	Body->Modify();
	Body->RemoveSimpleCollision();
	if (Shape == TEXT("box"))
	{
		GenerateBoxAsSimpleCollision(Mesh, false);
	}
	else if (Shape == TEXT("kdop"))
	{
		const float S2 = UE_INV_SQRT_2, S3 = 0.57735026919f;
		const TArray<FVector> Dirs = {
			FVector(1, 0, 0), FVector(-1, 0, 0), FVector(0, 1, 0), FVector(0, -1, 0), FVector(0, 0, 1), FVector(0, 0, -1),
			FVector(0, S2, S2), FVector(0, -S2, -S2), FVector(0, S2, -S2), FVector(0, -S2, S2),
			FVector(S2, 0, S2), FVector(-S2, 0, -S2), FVector(S2, 0, -S2), FVector(-S2, 0, S2),
			FVector(S2, S2, 0), FVector(-S2, -S2, 0), FVector(S2, -S2, 0), FVector(-S2, S2, 0),
			FVector(S3, S3, S3), FVector(S3, S3, -S3), FVector(S3, -S3, S3), FVector(S3, -S3, -S3),
			FVector(-S3, S3, S3), FVector(-S3, S3, -S3), FVector(-S3, -S3, S3), FVector(-S3, -S3, -S3) };
		GenerateKDopAsSimpleCollision(Mesh, Dirs, false);
	}
	else if (Shape == TEXT("hulls"))
	{
		if (!Mesh->GetRenderData()) { Mesh->CacheDerivedData(); }
		const FStaticMeshLODResources& LOD = Mesh->GetRenderData()->LODResources[0];
		TArray<FVector3f> Verts;
		for (uint32 i = 0; i < LOD.VertexBuffers.PositionVertexBuffer.GetNumVertices(); ++i)
		{
			Verts.Add(LOD.VertexBuffers.PositionVertexBuffer.VertexPosition(i));
		}
		TArray<uint32> Indices;
		LOD.IndexBuffer.GetCopy(Indices);
		if (Verts.Num() >= 3 && Indices.Num() >= 3)
		{
			DecomposeMeshToHulls(Body, Verts, Indices, FMath::Max(1, HullCount), FMath::Clamp(MaxHullVerts, 6, 32), 100000);
		}
	}
	Mesh->SetCustomizedCollision(true);
	Body->InvalidatePhysicsData();
	Body->CreatePhysicsMeshes();
	Mesh->MarkPackageDirty();
	Mesh->PostEditChange();
	return GetCollisionPrimitiveCount(Mesh);
}
