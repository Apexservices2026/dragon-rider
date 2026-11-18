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
class UPrimitiveComponent;
class UExponentialHeightFogComponent;
struct FInputActionValue;

/**
 * Arcade-cinematic dragon. The player aims with the mouse/right stick (the camera),
 * and the dragon smoothly chases that aim, banking into turns. Diving trades
 * altitude for speed, climbing bleeds it off. Shift boosts, Space beats the wings,
 * Q/E barrel-roll. Ctrl/RMB power-dives (wings tucked, gravity-driven speed past the normal cap).
 * A steep, fast water hit plunges the dragon under the sea; it bursts back out with a speed/lift boost.
 * All tuning values are editable in the Blueprint/Details panel.
 *
 * Animation is driven by plain state values (FlapPhase/FlapIntensity, DiveAmount, UnderwaterAmount,
 * BurstAmount) so a future rigged model's Anim Blueprint can read the same getters.
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
	/** 0..1 how far into the power-dive pose/physics the dragon is (wings fully tucked at 1). */
	UFUNCTION(BlueprintPure, Category = "Dragon|State") float GetDiveAmount() const { return DiveAmount; }
	UFUNCTION(BlueprintPure, Category = "Dragon|State") bool IsPowerDiving() const { return bDiveHeld && !bUnderwater; }
	UFUNCTION(BlueprintPure, Category = "Dragon|State") bool IsUnderwater() const { return bUnderwater; }
	/** 0..1 blend of the underwater (swimming, wings half-tucked) pose. */
	UFUNCTION(BlueprintPure, Category = "Dragon|State") float GetUnderwaterAmount() const { return UnderwaterAmount; }
	/** 0..1 spike right after bursting out of the water (wings flung open). */
	UFUNCTION(BlueprintPure, Category = "Dragon|State") float GetBurstAmount() const { return BurstAmount; }
	// --- Read by UDragonAnimInstance ---
	UFUNCTION(BlueprintPure, Category = "Dragon|State") float GetFlightPitch() const { return FlightPitch; }
	UFUNCTION(BlueprintPure, Category = "Dragon|State") float GetThrottle() const { return ThrottleInput; }
	UFUNCTION(BlueprintPure, Category = "Dragon|State") float GetYawRate() const { return YawRate; }
	UFUNCTION(BlueprintPure, Category = "Dragon|State") bool IsWingBeating() const { return WingBeatTimer > 0.f; }
	/** Increments on every wing beat and water burst (anim instance restarts the WingBeatStrong one-shot). */
	UFUNCTION(BlueprintPure, Category = "Dragon|State") int32 GetWingBeatCount() const { return WingBeatCount; }
	UFUNCTION(BlueprintPure, Category = "Dragon|State") float GetDepthMeters() const { return FMath::Max(0.f, -GetActorLocation().Z / 100.f); }
	/** 1 = full breath, 0 = forced to the surface. */
	UFUNCTION(BlueprintPure, Category = "Dragon|State") float GetBreath01() const { return bUnderwater ? FMath::Clamp(1.f - UnderwaterTime / MaxUnderwaterTime, 0.f, 1.f) : 1.f; }

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

	// --- Power dive (hold Ctrl / RMB / left trigger) ---
	/** Nose is pulled toward this pitch while diving, unless the player already aims steeper. */
	UPROPERTY(EditAnywhere, Category = "Dragon|PowerDive") float PowerDivePitch = -65.f;
	/** Multiplies DiveAcceleration (gravity pull) at full dive. */
	UPROPERTY(EditAnywhere, Category = "Dragon|PowerDive") float PowerDiveGravityScale = 4.0f;
	/** Multiplies SpeedRecovery (drag back toward throttle speed) at full dive. */
	UPROPERTY(EditAnywhere, Category = "Dragon|PowerDive") float PowerDiveDragScale = 0.12f;
	/** Speed cap while diving (cm/s). 22200 = ~800 km/h. Speed above MaxSpeed is kept after release and bleeds off. */
	UPROPERTY(EditAnywhere, Category = "Dragon|PowerDive") float PowerDiveMaxSpeed = 22200.f;
	UPROPERTY(EditAnywhere, Category = "Dragon|PowerDive") float PowerDiveSteerScale = 0.6f;
	/** How fast the wings tuck / the dive blends in (1/s). */
	UPROPERTY(EditAnywhere, Category = "Dragon|PowerDive") float PowerDiveBlendRate = 4.f;
	/** After release the aim eases up to this pitch (unless the player moves the mouse) so the dive slingshots out. */
	UPROPERTY(EditAnywhere, Category = "Dragon|PowerDive") float PullOutPitch = 12.f;
	UPROPERTY(EditAnywhere, Category = "Dragon|PowerDive") float PullOutDuration = 1.3f;

	// --- Water plunge / burst ---
	/** Hitting the water with pitch below this AND speed above PlungeMinSpeed (or while power-diving) plunges under. */
	UPROPERTY(EditAnywhere, Category = "Dragon|Water") float PlungeMaxPitch = -25.f;
	UPROPERTY(EditAnywhere, Category = "Dragon|Water") float PlungeMinSpeed = 5500.f;
	/** Underwater speed decays toward UnderwaterSwimSpeed at this rate (1/s). */
	UPROPERTY(EditAnywhere, Category = "Dragon|Water") float UnderwaterDrag = 3.4f;
	UPROPERTY(EditAnywhere, Category = "Dragon|Water") float UnderwaterSwimSpeed = 2600.f;
	/** Upward acceleration under water (cm/s^2). */
	UPROPERTY(EditAnywhere, Category = "Dragon|Water") float Buoyancy = 2300.f;
	UPROPERTY(EditAnywhere, Category = "Dragon|Water") float MaxUnderwaterTime = 2.5f;
	/** Speed added on bursting out, and the minimum exit speed (cm/s). */
	UPROPERTY(EditAnywhere, Category = "Dragon|Water") float BurstSpeedGain = 3200.f;
	UPROPERTY(EditAnywhere, Category = "Dragon|Water") float BurstMinSpeed = 9000.f;
	/** Extra vertical launch velocity on exit (cm/s). */
	UPROPERTY(EditAnywhere, Category = "Dragon|Water") float BurstLift = 6000.f;
	UPROPERTY(EditAnywhere, Category = "Dragon|Water") float BurstExitPitch = 38.f;

	// --- Camera tuning ---
	UPROPERTY(EditAnywhere, Category = "Dragon|Camera") float BaseFOV = 78.f;
	UPROPERTY(EditAnywhere, Category = "Dragon|Camera") float MaxFOV = 104.f;
	UPROPERTY(EditAnywhere, Category = "Dragon|Camera") float BaseArmLength = 1500.f;
	UPROPERTY(EditAnywhere, Category = "Dragon|Camera") float SpeedArmExtra = 700.f;
	UPROPERTY(EditAnywhere, Category = "Dragon|Camera") float MouseSensitivity = 1.0f;
	UPROPERTY(EditAnywhere, Category = "Dragon|Camera") float PowerDiveFOVExtra = 14.f;
	/** Extra rider rotation on the Saddle, in the dragon's body frame (the bone's own rest frame is undone in code). */
	UPROPERTY(EditAnywhere, Category = "Dragon|Rig") FRotator SaddleRiderRotation = FRotator::ZeroRotator;
	/** Arm length multiplier at full dive (pulls the camera in). */
	UPROPERTY(EditAnywhere, Category = "Dragon|Camera") float PowerDiveArmScale = 0.78f;

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
	/** Rigged dragon from tools/import_dragon.py; when its asset is missing the primitive placeholder is shown instead. */
	UPROPERTY(VisibleAnywhere, Category = "Components") TObjectPtr<USkeletalMeshComponent> DragonMesh;
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
	void OnDiveStart(const FInputActionValue& Value);
	void OnDiveStop(const FInputActionValue& Value);

	void EnterWater(const FVector& ImpactPoint);
	void ExitWater();
	bool IsWaterComponent(const UPrimitiveComponent* Comp);
	void FindWorldWaterAndFog();
	void SetupRiggedDragon();
	void UpdateUnderwaterView(float Dt);

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
	UPROPERTY() TObjectPtr<UInputAction> DiveAction;

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
	float LastLookInputTime = -10.f;
	int32 WingBeatCount = 0;
	bool bRigged = false;
	UPROPERTY() TArray<TObjectPtr<class UAnimSequence>> DragonAnims; // Glide, Flap, DiveTuck, WingBeatStrong, Hover

	// Power dive state
	bool bDiveHeld = false;
	float DiveAmount = 0.f;
	float PullOutTime = 0.f;

	// Water state
	UPROPERTY() TObjectPtr<UPrimitiveComponent> WaterComponent;
	UPROPERTY() TObjectPtr<UExponentialHeightFogComponent> WorldFog;
	bool bUnderwater = false;
	bool bSubmerged = false;     // centre has actually gone below Z=0 during this plunge
	bool bBurstRising = false;   // Space pressed / out of breath: drive hard for the surface
	float UnderwaterTime = 0.f;
	float BuoyancyVelocity = 0.f;
	float WaterIgnoreTime = 0.f; // keep ignoring the sea plane briefly after the exit so we clear it
	float UnderwaterAmount = 0.f;
	float BurstAmount = 0.f;
	float UnderwaterView = 0.f;  // camera-below-surface blend for post-process + fog
	float CamLagHoldTime = 0.f, CamLagHoldSpeed = 9.f, CamLagHoldMaxDistance = 900.f; // short camera-lag overrides on plunge/burst
	bool bFogSaved = false;
	float SavedFogDensity = 0.f, SavedFogStart = 0.f, SavedFogMaxOpacity = 1.f, SavedFogFalloff = 0.2f;
	FLinearColor SavedFogColor = FLinearColor::White, SavedFogDirColor = FLinearColor::White;
	bool bSavedVolumetricFog = false;

	// Automated review mode (-DragonShots): scripted flight + screenshots, then quit.
	void UpdateReviewMode(float Dt);
	bool bReviewMode = false;
	float ReviewTime = 0.f;
	int32 ReviewShot = 0;
	int32 ReviewPhase = 0;
	float ReviewEventTime = 0.f;
	int32 ReviewPass = 0; // review-only teleports: 1 = Skerholm, 2 = Innvik, 3 = fleet
	void ReviewScreenshot(const TCHAR* What);

	// Data-driven review (Lvl_Archipelago): the level holds actors tagged "ReviewLeg:<n>" (tools/build_archipelago.py).
	// Each leg teleports the dragon to that actor's transform, flies it for Dur seconds and takes shots at the listed
	// times. Tags: Dur:<s> Shots:<t>|<t> Name:<text> Pitch:<deg> Speed:<km/h> Boost Dive:<t> Orbit:<yaw>,<pitch> AimAt:<x>,<y>,<z>
	// FollowShip:<back>,<side>,<alt> (cm) starts the leg beside the nearest rowing longship, wherever it has got to.
	struct FReviewLeg
	{
		FVector Location = FVector::ZeroVector;
		FRotator Rotation = FRotator::ZeroRotator;
		float Duration = 6.f, Pitch = -4.f, SpeedKmh = 0.f, DiveAt = -1.f, OrbitYaw = 0.f, OrbitPitch = 0.f;
		bool bBoost = false, bOrbit = false, bAimAt = false, bFollowShip = false;
		FVector FollowOffset = FVector::ZeroVector;
		FVector AimAt = FVector::ZeroVector;
		TArray<float> Shots;
		FString Name;
	};
	TArray<FReviewLeg> ReviewLegs;
	int32 ReviewLeg = -1;
	int32 ReviewLegShot = 0;
	float ReviewLegTime = 0.f;
	bool CollectReviewLegs();
	void StartReviewLeg(int32 Index);
	void UpdateLegReview(float Dt);

	// Animation state
	float FlapPhase = 0.f;
	float FlapIntensity = 1.f;
	float AnimTime = 0.f;
	float ShakeTime = 0.f;
};
