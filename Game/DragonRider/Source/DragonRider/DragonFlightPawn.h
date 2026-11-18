#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Pawn.h"
#include "DragonFlightPawn.generated.h"

class USphereComponent;
class USpringArmComponent;
class UCameraComponent;
class UStaticMeshComponent;
class USkeletalMeshComponent;
class UInputAction;
class UInputMappingContext;
class UMaterialInterface;
struct FInputActionValue;

/**
 * Arcade-cinematic dragon. The player aims with the mouse/right stick (the camera),
 * and the dragon smoothly chases that aim, banking into turns. Diving trades
 * altitude for speed, climbing bleeds it off. Shift boosts, Space beats the wings,
 * Q/E barrel-roll. All tuning values are editable in the Blueprint/Details panel.
 */
UCLASS()
class DRAGONRIDER_API ADragonFlightPawn : public APawn
{
	GENERATED_BODY()

public:
	ADragonFlightPawn();

	virtual void Tick(float DeltaSeconds) override;
	virtual void SetupPlayerInputComponent(UInputComponent* PlayerInputComponent) override;
	virtual void PossessedBy(AController* NewController) override;

	// --- Read by the HUD ---
	UFUNCTION(BlueprintPure, Category = "Dragon|State") float GetSpeedKmh() const { return Speed * 0.036f; }
	UFUNCTION(BlueprintPure, Category = "Dragon|State") float GetAltitudeMeters() const { return GetActorLocation().Z / 100.f; }
	UFUNCTION(BlueprintPure, Category = "Dragon|State") float GetStamina01() const { return Stamina / MaxStamina; }
	UFUNCTION(BlueprintPure, Category = "Dragon|State") bool IsBoosting() const { return bBoosting; }

	// --- Flight tuning (cm/s, degrees) ---
	UPROPERTY(EditAnywhere, Category = "Dragon|Flight") float CruiseSpeed = 4200.f;
	UPROPERTY(EditAnywhere, Category = "Dragon|Flight") float FastSpeed = 6500.f;
	UPROPERTY(EditAnywhere, Category = "Dragon|Flight") float SlowSpeed = 1800.f;
	UPROPERTY(EditAnywhere, Category = "Dragon|Flight") float BoostSpeed = 10500.f;
	UPROPERTY(EditAnywhere, Category = "Dragon|Flight") float MinSpeed = 1200.f;
	UPROPERTY(EditAnywhere, Category = "Dragon|Flight") float MaxSpeed = 15000.f;
	/** How strongly speed is pulled back toward the throttle target (1/s). Lower = dives keep momentum longer. */
	UPROPERTY(EditAnywhere, Category = "Dragon|Flight") float SpeedRecovery = 0.55f;
	/** Speed gained per second when diving straight down (scaled by sin of pitch). */
	UPROPERTY(EditAnywhere, Category = "Dragon|Flight") float DiveAcceleration = 2600.f;
	/** How fast the dragon's heading chases the camera aim. */
	UPROPERTY(EditAnywhere, Category = "Dragon|Flight") float TurnResponsiveness = 2.6f;
	UPROPERTY(EditAnywhere, Category = "Dragon|Flight") float MaxBankAngle = 70.f;
	UPROPERTY(EditAnywhere, Category = "Dragon|Flight") float BankPerYawRate = 0.75f;
	UPROPERTY(EditAnywhere, Category = "Dragon|Flight") float StrafeYawRate = 55.f;
	UPROPERTY(EditAnywhere, Category = "Dragon|Flight") float WingBeatSpeedGain = 900.f;
	UPROPERTY(EditAnywhere, Category = "Dragon|Flight") float WingBeatLift = 1600.f;
	UPROPERTY(EditAnywhere, Category = "Dragon|Flight") float BarrelRollDuration = 0.65f;
	UPROPERTY(EditAnywhere, Category = "Dragon|Flight") float MaxStamina = 100.f;
	UPROPERTY(EditAnywhere, Category = "Dragon|Flight") float BoostDrainPerSecond = 22.f;
	UPROPERTY(EditAnywhere, Category = "Dragon|Flight") float StaminaRegenPerSecond = 14.f;

	// --- Camera tuning ---
	UPROPERTY(EditAnywhere, Category = "Dragon|Camera") float BaseFOV = 78.f;
	UPROPERTY(EditAnywhere, Category = "Dragon|Camera") float MaxFOV = 104.f;
	UPROPERTY(EditAnywhere, Category = "Dragon|Camera") float BaseArmLength = 1500.f;
	UPROPERTY(EditAnywhere, Category = "Dragon|Camera") float SpeedArmExtra = 700.f;
	UPROPERTY(EditAnywhere, Category = "Dragon|Camera") float MouseSensitivity = 1.0f;

protected:
	virtual void BeginPlay() override;

	UPROPERTY(VisibleAnywhere, Category = "Components") TObjectPtr<USphereComponent> Collision;
	UPROPERTY(VisibleAnywhere, Category = "Components") TObjectPtr<USceneComponent> BodyRoot;
	UPROPERTY(VisibleAnywhere, Category = "Components") TObjectPtr<USceneComponent> LeftWingPivot;
	UPROPERTY(VisibleAnywhere, Category = "Components") TObjectPtr<USceneComponent> RightWingPivot;
	UPROPERTY(VisibleAnywhere, Category = "Components") TObjectPtr<USceneComponent> LeftWingTipPivot;
	UPROPERTY(VisibleAnywhere, Category = "Components") TObjectPtr<USceneComponent> RightWingTipPivot;
	UPROPERTY(VisibleAnywhere, Category = "Components") TObjectPtr<USceneComponent> NeckPivot;
	UPROPERTY(VisibleAnywhere, Category = "Components") TObjectPtr<USceneComponent> TailPivot;
	UPROPERTY(VisibleAnywhere, Category = "Components") TObjectPtr<USkeletalMeshComponent> Rider;
	UPROPERTY(VisibleAnywhere, Category = "Components") TObjectPtr<USpringArmComponent> CameraBoom;
	UPROPERTY(VisibleAnywhere, Category = "Components") TObjectPtr<UCameraComponent> Camera;

private:
	UStaticMeshComponent* AddPart(const TCHAR* Name, USceneComponent* Parent, UStaticMesh* Mesh,
		const FVector& Location, const FRotator& Rotation, const FVector& Scale, int32 MaterialSlot);
	void BuildDragonBody();
	void ApplyBodyColors();

	void OnLook(const FInputActionValue& Value);
	void OnBank(const FInputActionValue& Value);
	void OnThrottle(const FInputActionValue& Value);
	void OnBoostStart(const FInputActionValue& Value);
	void OnBoostStop(const FInputActionValue& Value);
	void OnWingBeat(const FInputActionValue& Value);
	void OnRoll(const FInputActionValue& Value);

	void UpdateFlight(float Dt);
	void UpdateAnimation(float Dt);
	void UpdateCamera(float Dt);

	UPROPERTY() TObjectPtr<UInputMappingContext> FlightContext;
	UPROPERTY() TObjectPtr<UInputAction> LookAction;
	UPROPERTY() TObjectPtr<UInputAction> BankAction;
	UPROPERTY() TObjectPtr<UInputAction> ThrottleAction;
	UPROPERTY() TObjectPtr<UInputAction> BoostAction;
	UPROPERTY() TObjectPtr<UInputAction> WingBeatAction;
	UPROPERTY() TObjectPtr<UInputAction> RollAction;

	UPROPERTY() TArray<TObjectPtr<UStaticMeshComponent>> ScaleParts;
	UPROPERTY() TArray<TObjectPtr<UStaticMeshComponent>> MembraneParts;
	UPROPERTY() TArray<TObjectPtr<UStaticMeshComponent>> HornParts;
	UPROPERTY() TArray<TObjectPtr<UStaticMeshComponent>> GlowParts;
	UPROPERTY() TArray<TObjectPtr<UStaticMeshComponent>> TailSegments;
	UPROPERTY() TObjectPtr<UMaterialInterface> BaseShapeMaterial;

	// Flight state
	float Speed = 0.f;
	float FlightYaw = 0.f;
	float FlightPitch = 0.f;
	float Bank = 0.f;
	float RollOffset = 0.f;
	float RollDirection = 0.f;
	float RollTimeLeft = 0.f;
	float VerticalBoost = 0.f;
	float Stamina = 100.f;
	float BankInput = 0.f;
	float ThrottleInput = 0.f;
	bool bBoosting = false;
	float WingBeatTimer = 0.f;
	float ImpactCooldown = 0.f;
	float YawRate = 0.f;

	// Automated review mode (-DragonShots): scripted flight + screenshots, then quit.
	void UpdateReviewMode(float Dt);
	bool bReviewMode = false;
	float ReviewTime = 0.f;
	int32 ReviewShot = 0;

	// Animation state
	float FlapPhase = 0.f;
	float FlapIntensity = 1.f;
	float AnimTime = 0.f;
	float ShakeTime = 0.f;
};
