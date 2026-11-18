#pragma once

#include "CoreMinimal.h"
#include "Kismet/BlueprintFunctionLibrary.h"
#include "DragonLandscapeLibrary.generated.h"

class ALandscape;
class UMaterialInterface;

/**
 * Landscape creation for the archipelago build (tools/build_archipelago.py). Python can't create a landscape
 * with height data in a commandlet, so this wraps ALandscape::Import, the same call the editor's "New Landscape"
 * tool makes, and splits the result into World Partition streaming proxies.
 */
UCLASS()
class DRAGONRIDEREDITOR_API UDragonLandscapeLibrary : public UBlueprintFunctionLibrary
{
	GENERATED_BODY()

public:
	/**
	 * Create a landscape in the current editor world from a raw little-endian uint16 heightmap (SizePx x SizePx,
	 * row = +Y). SizePx - 1 must be a multiple of 126 (components of 2x2 sections of 63 quads).
	 * LocationCm is the world position of vertex (0, 0); Scale is the actor scale (X/Y = cm per sample,
	 * Z = height scale: Z_cm = (value - 32768) * Scale.Z / 128).
	 * In a World Partition world the landscape is split into streaming proxies of GridSize x GridSize components.
	 * bSpatiallyLoaded = false keeps every proxy loaded (the whole archipelago is visible from the air).
	 */
	UFUNCTION(BlueprintCallable, Category = "DragonRider|Landscape")
	static ALandscape* ImportHeightmapLandscape(const FString& RawHeightmapPath, int32 SizePx, FVector LocationCm, FVector Scale,
		UMaterialInterface* Material, const FString& Label, int32 GridSize = 8, bool bSpatiallyLoaded = false);

	/** Flush pending edit-layer merges on every landscape in the editor world (so heights are final before saving). */
	UFUNCTION(BlueprintCallable, Category = "DragonRider|Landscape")
	static int32 FlushLandscapes();

	/** Landscape collision height (cm) at a world XY in the editor world; returns false where no landscape is. */
	UFUNCTION(BlueprintCallable, Category = "DragonRider|Landscape")
	static bool SampleLandscapeHeight(FVector LocationCm, float& OutHeightCm);
};
