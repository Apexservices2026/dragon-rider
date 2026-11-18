#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "DragonSplash.generated.h"

class UStaticMeshComponent;
class UMaterialInterface;

/**
 * Cheap procedural water splash built from /Engine/BasicShapes (no Niagara assets exist yet):
 * a rising white column, a crown of droplets thrown up and out under gravity, fine spray, and a
 * foam ring that spreads across the surface. Lives ~1.8 s and destroys itself.
 * Spawn it at the impact point on the water (Z=0) and call Init with a strength (1 = ~400 km/h hit).
 */
UCLASS()
class DRAGONRIDER_API ADragonSplash : public AActor
{
	GENERATED_BODY()

public:
	ADragonSplash();
	virtual void Tick(float DeltaSeconds) override;

	/** Strength scales size and throw speed. bExit = burst out of the water (taller, narrower column). */
	void Init(float InStrength, bool bExit, const FVector& Travel);

	static ADragonSplash* Spawn(UWorld* World, const FVector& Location, float Strength, bool bExit, const FVector& Travel);

private:
	struct FDrop
	{
		FVector Pos = FVector::ZeroVector;
		FVector Vel = FVector::ZeroVector;
		float Size = 1.f;
		float Delay = 0.f;
	};

	UPROPERTY() TArray<TObjectPtr<UStaticMeshComponent>> DropParts;
	UPROPERTY() TArray<TObjectPtr<UStaticMeshComponent>> RingParts;
	UPROPERTY() TArray<TObjectPtr<UStaticMeshComponent>> ColumnParts;
	UPROPERTY() TObjectPtr<UStaticMeshComponent> FoamDisk;
	UPROPERTY() TObjectPtr<UMaterialInterface> BaseMaterial;

	TArray<FDrop> Drops;
	float Strength = 1.f;
	float Age = 0.f;
	float Life = 1.8f;
	bool bIsExit = false;
	float RingRadiusMax = 1400.f;
};
