#pragma once

#include "CoreMinimal.h"
#include "Kismet/BlueprintFunctionLibrary.h"
class UStaticMesh;
#include "DragonAssetLibrary.generated.h"

/** Asset hygiene for the import scripts (tools/scrub_import_paths.py). */
UCLASS()
class DRAGONRIDEREDITOR_API UDragonAssetLibrary : public UBlueprintFunctionLibrary
{
	GENERATED_BODY()

public:
	/**
	 * Replace an asset's import data (its "AssetImportData" property, e.g. Interchange's import graph, which is keyed by
	 * the absolute source path and so embeds the importing user's folder) with a plain UAssetImportData holding only
	 * SourceFile, stored relative to the package. Pixels, geometry and all other settings are untouched.
	 * Returns false when the asset has no import data property.
	 */
	UFUNCTION(BlueprintCallable, Category = "DragonRider|Assets")
	static bool ResetImportData(UObject* Asset, const FString& SourceFile);

	/** Number of simple collision primitives (boxes, spheres, capsules, convex hulls) on a static mesh. */
	UFUNCTION(BlueprintCallable, Category = "DragonRider|Assets")
	static int32 GetCollisionPrimitiveCount(UStaticMesh* Mesh);

	/**
	 * Replace a static mesh's simple collision. Shape: "box" (one bounding box), "kdop" (one 26-sided hull) or
	 * "hulls" (convex decomposition into HullCount hulls, keeps arches and rings open). Returns the primitive count.
	 * (The Python StaticMeshEditorSubsystem calls do nothing inside a commandlet, so the import scripts use this.)
	 */
	UFUNCTION(BlueprintCallable, Category = "DragonRider|Assets")
	static int32 SetCollision(UStaticMesh* Mesh, const FString& Shape, int32 HullCount = 8, int32 MaxHullVerts = 16);
};
