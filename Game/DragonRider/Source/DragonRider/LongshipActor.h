#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "LongshipActor.generated.h"

class UStaticMeshComponent;
class UStaticMesh;
class UMaterialInterface;
class UPrimitiveComponent;

/**
 * Viking longship assembled from the world kit (tools/import_world_kit.py): hull + sail + 32 oars at the
 * manifest's oar ports. It sails along its facing at SailSpeed, bobs and rolls on the swell, rows its oars
 * in a sine stroke, billows the sail, and leaves a cheap foam wake (flattened engine spheres).
 * When terrain shows up just ahead it loops back LoopDistance along its track so a fleet never runs out.
 * With SailSpeed = 0 it is moored: it only bobs, oars resting.
 * Ship origin = waterline, hull centre, +X = bow (as exported).
 */
UCLASS()
class DRAGONRIDER_API ALongshipActor : public AActor
{
	GENERATED_BODY()

public:
	ALongshipActor();
	virtual void Tick(float DeltaSeconds) override;
	virtual void OnConstruction(const FTransform& Transform) override;

	/** false = ClanA (red/white), true = ClanB (blue/ochre). */
	UPROPERTY(EditAnywhere, Category = "Longship") bool bClanB = false;
	/** cm/s along the ship's facing. 0 = moored. */
	UPROPERTY(EditAnywhere, Category = "Longship") float SailSpeed = 500.f;
	/** Seconds per oar stroke. */
	UPROPERTY(EditAnywhere, Category = "Longship") float StrokePeriod = 2.8f;
	/** How far back along its track (cm) the ship jumps when it nears land. */
	UPROPERTY(EditAnywhere, Category = "Longship") float LoopDistance = 520000.f;
	/** true: when it nears land, return to where it started (a route between two islands) instead of jumping back LoopDistance. */
	UPROPERTY(EditAnywhere, Category = "Longship") bool bReturnToStart = false;
	/** Look-ahead (cm) for the "near land" check. */
	UPROPERTY(EditAnywhere, Category = "Longship") float LandCheckAhead = 9000.f;
	UPROPERTY(EditAnywhere, Category = "Longship") float BobHeight = 22.f;
	UPROPERTY(EditAnywhere, Category = "Longship") float RollDegrees = 2.2f;
	UPROPERTY(EditAnywhere, Category = "Longship") float PitchDegrees = 1.1f;
	UPROPERTY(EditAnywhere, Category = "Longship") bool bWake = true;

protected:
	virtual void BeginPlay() override;

	UPROPERTY(VisibleAnywhere, Category = "Components") TObjectPtr<USceneComponent> Root;
	UPROPERTY(VisibleAnywhere, Category = "Components") TObjectPtr<USceneComponent> Deck;   // bobbing frame
	UPROPERTY(VisibleAnywhere, Category = "Components") TObjectPtr<UStaticMeshComponent> Hull;
	UPROPERTY(VisibleAnywhere, Category = "Components") TObjectPtr<UStaticMeshComponent> Sail;
	UPROPERTY(VisibleAnywhere, Category = "Components") TArray<TObjectPtr<UStaticMeshComponent>> Oars;
	UPROPERTY(VisibleAnywhere, Category = "Components") TArray<TObjectPtr<UStaticMeshComponent>> WakeParts;
	UPROPERTY(VisibleAnywhere, Category = "Components") TArray<TObjectPtr<UStaticMeshComponent>> BowWave;

private:
	void ApplyClan();
	void UpdateOars(float Time);
	void UpdateWake(float Dt);
	bool LandAhead() const;

	UPROPERTY() TObjectPtr<UStaticMesh> HullA;
	UPROPERTY() TObjectPtr<UStaticMesh> HullB;
	UPROPERTY() TObjectPtr<UStaticMesh> SailA;
	UPROPERTY() TObjectPtr<UStaticMesh> SailB;
	UPROPERTY() TObjectPtr<UMaterialInterface> FoamBase;
	UPROPERTY() TObjectPtr<UPrimitiveComponent> WaterComponent;
	UPROPERTY() TArray<TObjectPtr<UPrimitiveComponent>> SeaPlanes;

	struct FWakeBlob { FVector Pos = FVector::ZeroVector; float Age = 100.f; float Yaw = 0.f; float Side = 1.f; };
	TArray<FWakeBlob> Wake;
	TArray<FQuat> OarBase;
	TArray<float> OarSide;
	float Time = 0.f;
	float Phase = 0.f;
	float WakeTimer = 0.f;
	float LandCheckTimer = 0.f;
	int32 NextWake = 0;
	FVector StartLocation = FVector::ZeroVector;
};
