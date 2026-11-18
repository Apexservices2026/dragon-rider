#include "DragonFlightPawn.h"

#include "Camera/CameraComponent.h"
#include "Components/SkeletalMeshComponent.h"
#include "Components/SphereComponent.h"
#include "Components/StaticMeshComponent.h"
#include "EnhancedInputComponent.h"
#include "EnhancedInputSubsystems.h"
#include "Engine/LocalPlayer.h"
#include "Engine/StaticMesh.h"
#include "Animation/AnimSequence.h"
#include "GameFramework/PlayerController.h"
#include "GameFramework/SpringArmComponent.h"
#include "InputAction.h"
#include "InputMappingContext.h"
#include "InputModifiers.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "UObject/ConstructorHelpers.h"
#include "UnrealClient.h"
#include "Misc/CommandLine.h"

namespace
{
	enum EDragonSlot : int32 { Scales = 0, Membrane = 1, Horn = 2, Glow = 3, Belly = 4 };

	float Smooth01(float X) { X = FMath::Clamp(X, 0.f, 1.f); return X * X * (3.f - 2.f * X); }
	float ExpAlpha(float Rate, float Dt) { return 1.f - FMath::Exp(-Rate * Dt); }
}

ADragonFlightPawn::ADragonFlightPawn()
{
	PrimaryActorTick.bCanEverTick = true;
	bUseControllerRotationPitch = false;
	bUseControllerRotationYaw = false;
	bUseControllerRotationRoll = false;
	AutoPossessPlayer = EAutoReceiveInput::Disabled;

	Collision = CreateDefaultSubobject<USphereComponent>(TEXT("Collision"));
	Collision->InitSphereRadius(330.f);
	Collision->SetCollisionProfileName(TEXT("Pawn"));
	RootComponent = Collision;

	BodyRoot = CreateDefaultSubobject<USceneComponent>(TEXT("BodyRoot"));
	BodyRoot->SetupAttachment(Collision);

	static ConstructorHelpers::FObjectFinder<UMaterialInterface> ShapeMat(TEXT("/Engine/BasicShapes/BasicShapeMaterial.BasicShapeMaterial"));
	BaseShapeMaterial = ShapeMat.Object;

	BuildDragonBody();

	Rider = CreateDefaultSubobject<USkeletalMeshComponent>(TEXT("Rider"));
	Rider->SetupAttachment(BodyRoot);
	Rider->SetRelativeLocation(FVector(95.f, 0.f, 62.f));
	Rider->SetRelativeRotation(FRotator(0.f, -90.f, 0.f)); // UE mannequins face +Y
	Rider->SetRelativeScale3D(FVector(1.05f));
	Rider->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	static ConstructorHelpers::FObjectFinder<USkeletalMesh> RiderMesh(TEXT("/Game/Characters/Mannequins/Meshes/SKM_Manny_Simple.SKM_Manny_Simple"));
	static ConstructorHelpers::FObjectFinder<UAnimSequence> RiderIdle(TEXT("/Game/Characters/Mannequins/Anims/Unarmed/MM_Idle.MM_Idle"));
	if (RiderMesh.Succeeded()) { Rider->SetSkeletalMesh(RiderMesh.Object); }
	if (RiderIdle.Succeeded())
	{
		Rider->SetAnimationMode(EAnimationMode::AnimationSingleNode);
		Rider->AnimationData.AnimToPlay = RiderIdle.Object;
		Rider->AnimationData.bSavedLooping = true;
		Rider->AnimationData.bSavedPlaying = true;
	}

	CameraBoom = CreateDefaultSubobject<USpringArmComponent>(TEXT("CameraBoom"));
	CameraBoom->SetupAttachment(Collision);
	CameraBoom->TargetArmLength = BaseArmLength;
	CameraBoom->SocketOffset = FVector(0.f, 0.f, 560.f);
	CameraBoom->bUsePawnControlRotation = true;
	CameraBoom->bInheritRoll = false;
	CameraBoom->bEnableCameraLag = true;
	CameraBoom->CameraLagSpeed = 9.f;
	CameraBoom->CameraLagMaxDistance = 900.f;
	CameraBoom->bEnableCameraRotationLag = true;
	CameraBoom->CameraRotationLagSpeed = 11.f;
	CameraBoom->ProbeSize = 40.f;

	Camera = CreateDefaultSubobject<UCameraComponent>(TEXT("Camera"));
	Camera->SetupAttachment(CameraBoom, USpringArmComponent::SocketName);
	Camera->SetFieldOfView(BaseFOV);
	Camera->PostProcessSettings.bOverride_MotionBlurAmount = true;
	Camera->PostProcessSettings.MotionBlurAmount = 0.35f;
	Camera->PostProcessSettings.bOverride_VignetteIntensity = true;
	Camera->PostProcessSettings.VignetteIntensity = 0.45f;
}

UStaticMeshComponent* ADragonFlightPawn::AddPart(const TCHAR* Name, USceneComponent* Parent, UStaticMesh* Mesh,
	const FVector& Location, const FRotator& Rotation, const FVector& Scale, int32 MaterialSlot)
{
	UStaticMeshComponent* Part = CreateDefaultSubobject<UStaticMeshComponent>(Name);
	Part->SetupAttachment(Parent);
	Part->SetStaticMesh(Mesh);
	Part->SetRelativeLocation(Location);
	Part->SetRelativeRotation(Rotation);
	Part->SetRelativeScale3D(Scale);
	Part->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	Part->SetGenerateOverlapEvents(false);
	Part->CastShadow = true;
	switch (MaterialSlot)
	{
	case Membrane: MembraneParts.Add(Part); break;
	case Horn: HornParts.Add(Part); break;
	case Glow: GlowParts.Add(Part); break;
	default: ScaleParts.Add(Part); break;
	}
	return Part;
}

void ADragonFlightPawn::BuildDragonBody()
{
	// Placeholder dragon assembled from engine primitives. It reads as a dragon silhouette in flight
	// and is replaced later by a rigged dragon model; gameplay code does not depend on these parts.
	static ConstructorHelpers::FObjectFinder<UStaticMesh> SphereF(TEXT("/Engine/BasicShapes/Sphere.Sphere"));
	static ConstructorHelpers::FObjectFinder<UStaticMesh> CubeF(TEXT("/Engine/BasicShapes/Cube.Cube"));
	static ConstructorHelpers::FObjectFinder<UStaticMesh> CylF(TEXT("/Engine/BasicShapes/Cylinder.Cylinder"));
	static ConstructorHelpers::FObjectFinder<UStaticMesh> ConeF(TEXT("/Engine/BasicShapes/Cone.Cone"));
	UStaticMesh* Sphere = SphereF.Object;
	UStaticMesh* Cube = CubeF.Object;
	UStaticMesh* Cyl = CylF.Object;
	UStaticMesh* Cone = ConeF.Object;

	// Torso
	AddPart(TEXT("Torso"), BodyRoot, Sphere, FVector(0, 0, 0), FRotator::ZeroRotator, FVector(4.4f, 1.75f, 1.5f), Scales);
	AddPart(TEXT("Chest"), BodyRoot, Sphere, FVector(130, 0, -12), FRotator(-8, 0, 0), FVector(2.4f, 2.0f, 1.75f), Scales);
	AddPart(TEXT("Hips"), BodyRoot, Sphere, FVector(-160, 0, 0), FRotator::ZeroRotator, FVector(2.1f, 1.55f, 1.35f), Scales);
	AddPart(TEXT("Belly"), BodyRoot, Sphere, FVector(20, 0, -40), FRotator::ZeroRotator, FVector(3.6f, 1.35f, 0.9f), Horn);
	for (int32 i = 0; i < 8; ++i)
	{
		const float X = 200.f - i * 55.f;
		AddPart(*FString::Printf(TEXT("Ridge%d"), i), BodyRoot, Cone, FVector(X, 0, 78.f - FMath::Abs(X) * 0.05f),
			FRotator(28, 0, 0), FVector(0.22f, 0.1f, 0.5f - i * 0.03f), Horn);
	}
	// Saddle
	AddPart(TEXT("Saddle"), BodyRoot, Cube, FVector(95, 0, 68), FRotator::ZeroRotator, FVector(0.9f, 1.1f, 0.12f), Belly);

	// Legs (tucked for flight)
	for (int32 Side = -1; Side <= 1; Side += 2)
	{
		const TCHAR* S = Side < 0 ? TEXT("L") : TEXT("R");
		AddPart(*FString::Printf(TEXT("FrontLeg%s"), S), BodyRoot, Sphere, FVector(120, 62.f * Side, -78), FRotator(-35, 0, 0), FVector(0.55f, 0.4f, 1.0f), Scales);
		AddPart(*FString::Printf(TEXT("BackLeg%s"), S), BodyRoot, Sphere, FVector(-150, 66.f * Side, -62), FRotator(-55, 0, 0), FVector(0.85f, 0.55f, 1.2f), Scales);
		AddPart(*FString::Printf(TEXT("BackClaw%s"), S), BodyRoot, Cone, FVector(-215, 66.f * Side, -105), FRotator(90, 0, 0), FVector(0.25f, 0.25f, 0.5f), Horn);
	}

	// Neck and head
	NeckPivot = CreateDefaultSubobject<USceneComponent>(TEXT("NeckPivot"));
	NeckPivot->SetupAttachment(BodyRoot);
	NeckPivot->SetRelativeLocation(FVector(200, 0, 25));
	AddPart(TEXT("Neck1"), NeckPivot, Sphere, FVector(70, 0, 30), FRotator(30, 0, 0), FVector(1.6f, 1.05f, 1.05f), Scales);
	AddPart(TEXT("Neck2"), NeckPivot, Sphere, FVector(160, 0, 80), FRotator(25, 0, 0), FVector(1.5f, 0.9f, 0.9f), Scales);
	AddPart(TEXT("Neck3"), NeckPivot, Sphere, FVector(245, 0, 115), FRotator(12, 0, 0), FVector(1.3f, 0.8f, 0.8f), Scales);
	AddPart(TEXT("Skull"), NeckPivot, Sphere, FVector(335, 0, 130), FRotator(-5, 0, 0), FVector(1.55f, 0.9f, 0.75f), Scales);
	AddPart(TEXT("Snout"), NeckPivot, Cube, FVector(425, 0, 118), FRotator(-9, 0, 0), FVector(1.25f, 0.55f, 0.38f), Scales);
	AddPart(TEXT("Jaw"), NeckPivot, Cube, FVector(405, 0, 92), FRotator(-4, 0, 0), FVector(1.15f, 0.48f, 0.14f), Belly);
	for (int32 Side = -1; Side <= 1; Side += 2)
	{
		const TCHAR* S = Side < 0 ? TEXT("L") : TEXT("R");
		AddPart(*FString::Printf(TEXT("Horn%s"), S), NeckPivot, Cone, FVector(300, 30.f * Side, 170), FRotator(62, 0, -18.f * Side), FVector(0.18f, 0.18f, 1.0f), Horn);
		AddPart(*FString::Printf(TEXT("HornSmall%s"), S), NeckPivot, Cone, FVector(320, 40.f * Side, 150), FRotator(75, 0, -40.f * Side), FVector(0.12f, 0.12f, 0.55f), Horn);
		AddPart(*FString::Printf(TEXT("Eye%s"), S), NeckPivot, Sphere, FVector(385, 34.f * Side, 148), FRotator::ZeroRotator, FVector(0.13f, 0.09f, 0.08f), Glow);
	}

	// Tail: chained pivots so it curls with a travelling wave
	TailPivot = CreateDefaultSubobject<USceneComponent>(TEXT("TailPivot"));
	TailPivot->SetupAttachment(BodyRoot);
	TailPivot->SetRelativeLocation(FVector(-250, 0, 5));
	USceneComponent* Parent = TailPivot;
	for (int32 i = 0; i < 7; ++i)
	{
		const float W = 0.95f - i * 0.12f;
		UStaticMeshComponent* Seg = AddPart(*FString::Printf(TEXT("Tail%d"), i), Parent, Sphere,
			FVector(i == 0 ? -60.f : -85.f, 0, 0), FRotator::ZeroRotator, FVector(1.5f, W, W * 0.9f), Scales);
		Seg->SetAbsolute(false, false, true); // keep scale from compounding down the chain
		TailSegments.Add(Seg);
		Parent = Seg;
	}
	AddPart(TEXT("TailBlade"), Parent, Cube, FVector(-80, 0, 0), FRotator(0, 45, 0), FVector(0.9f, 0.9f, 0.06f), Membrane);

	// Wings: shoulder pivot + wrist pivot so the outer wing lags the beat
	auto BuildWing = [&](int32 Side, TObjectPtr<USceneComponent>& Pivot, TObjectPtr<USceneComponent>& TipPivot)
	{
		const TCHAR* S = Side < 0 ? TEXT("L") : TEXT("R");
		const float Y = static_cast<float>(Side);
		Pivot = CreateDefaultSubobject<USceneComponent>(*FString::Printf(TEXT("WingPivot%s"), S));
		Pivot->SetupAttachment(BodyRoot);
		Pivot->SetRelativeLocation(FVector(85, 75.f * Y, 55));
		AddPart(*FString::Printf(TEXT("WingArm%s"), S), Pivot, Cyl, FVector(0, 210.f * Y, 0), FRotator(0, 0, 90), FVector(0.24f, 0.24f, 4.2f), Scales);
		AddPart(*FString::Printf(TEXT("WingInner%s"), S), Pivot, Cube, FVector(-175, 210.f * Y, 0), FRotator::ZeroRotator, FVector(3.4f, 4.2f, 0.05f), Membrane);
		AddPart(*FString::Printf(TEXT("WingRoot%s"), S), Pivot, Cube, FVector(-260, 70.f * Y, 0), FRotator(0, 30.f * Y, 0), FVector(2.4f, 1.4f, 0.05f), Membrane);

		TipPivot = CreateDefaultSubobject<USceneComponent>(*FString::Printf(TEXT("WingTipPivot%s"), S));
		TipPivot->SetupAttachment(Pivot);
		TipPivot->SetRelativeLocation(FVector(0, 420.f * Y, 0));
		AddPart(*FString::Printf(TEXT("WingFinger%s"), S), TipPivot, Cyl, FVector(-40, 230.f * Y, 0), FRotator(0, -10.f * Y, 90), FVector(0.16f, 0.16f, 4.7f), Scales);
		AddPart(*FString::Printf(TEXT("WingOuter%s"), S), TipPivot, Cube, FVector(-150, 210.f * Y, 0), FRotator(0, 8.f * Y, 0), FVector(2.9f, 4.4f, 0.04f), Membrane);
		AddPart(*FString::Printf(TEXT("WingClaw%s"), S), TipPivot, Cone, FVector(0, 0, 25), FRotator::ZeroRotator, FVector(0.12f, 0.12f, 0.4f), Horn);
		for (int32 j = 0; j < 3; ++j)
		{
			AddPart(*FString::Printf(TEXT("WingScallop%s%d"), S, j), TipPivot, Cube, FVector(-300, (70.f + j * 140.f) * Y, 0),
				FRotator(0, 45, 0), FVector(1.0f, 1.0f, 0.035f), Membrane);
		}
	};
	BuildWing(-1, LeftWingPivot, LeftWingTipPivot);
	BuildWing(1, RightWingPivot, RightWingTipPivot);
}

void ADragonFlightPawn::ApplyBodyColors()
{
	if (!BaseShapeMaterial) { return; }
	auto Make = [this](const FLinearColor& Color)
	{
		UMaterialInstanceDynamic* M = UMaterialInstanceDynamic::Create(BaseShapeMaterial, this);
		M->SetVectorParameterValue(TEXT("Color"), Color);
		return M;
	};
	UMaterialInstanceDynamic* ScaleMat = Make(FLinearColor(0.035f, 0.03f, 0.032f));   // obsidian scales
	UMaterialInstanceDynamic* MembraneMat = Make(FLinearColor(0.22f, 0.025f, 0.015f)); // ember-red wings
	UMaterialInstanceDynamic* HornMat = Make(FLinearColor(0.55f, 0.48f, 0.36f));       // bone
	UMaterialInstanceDynamic* GlowMat = Make(FLinearColor(1.0f, 0.45f, 0.02f));        // molten eyes
	for (UStaticMeshComponent* P : ScaleParts) { P->SetMaterial(0, ScaleMat); }
	for (UStaticMeshComponent* P : MembraneParts) { P->SetMaterial(0, MembraneMat); }
	for (UStaticMeshComponent* P : HornParts) { P->SetMaterial(0, HornMat); }
	for (UStaticMeshComponent* P : GlowParts) { P->SetMaterial(0, GlowMat); }
}

void ADragonFlightPawn::BeginPlay()
{
	Super::BeginPlay();
	ApplyBodyColors();
	const FRotator Start = GetActorRotation();
	FlightYaw = Start.Yaw;
	FlightPitch = FRotator::NormalizeAxis(Start.Pitch);
	Speed = CruiseSpeed;
	Stamina = MaxStamina;
	bReviewMode = FParse::Param(FCommandLine::Get(), TEXT("DragonShots"));
}

void ADragonFlightPawn::UpdateReviewMode(float Dt)
{
	ReviewTime += Dt;
	AController* C = GetController();
	if (!C) { return; }
	const float T = ReviewTime;
	FRotator Aim = C->GetControlRotation();

	// Script: cruise -> beauty orbit shots -> right turn -> boosted dive -> climb with wing beats.
	if (T > 4.f && T < 11.f)
	{
		CameraBoom->SetUsingAbsoluteRotation(true);
		const float OrbitYaw = T < 7.5f ? 150.f : 95.f;
		CameraBoom->SetWorldRotation(FRotator(T < 7.5f ? -8.f : -22.f, FlightYaw + OrbitYaw, 0.f));
	}
	else if (CameraBoom->IsUsingAbsoluteRotation())
	{
		CameraBoom->SetUsingAbsoluteRotation(false);
	}
	if (T > 11.f && T < 17.f) { Aim.Yaw += 28.f * Dt; Aim.Pitch = -6.f; }
	if (T > 17.f && T < 23.f) { bBoosting = true; Aim.Pitch = -32.f; }
	if (T >= 23.f && T < 24.f) { bBoosting = false; }
	if (T > 23.f && T < 30.f) { Aim.Pitch = 22.f; OnWingBeat(FInputActionValue()); }
	C->SetControlRotation(Aim);

	static const float ShotTimes[] = { 3.f, 6.8f, 10.3f, 15.f, 21.5f, 27.f };
	if (ReviewShot < UE_ARRAY_COUNT(ShotTimes) && T >= ShotTimes[ReviewShot])
	{
		FScreenshotRequest::RequestScreenshot(FString::Printf(TEXT("DragonReview_%02d"), ReviewShot), true, false);
		UE_LOG(LogTemp, Display, TEXT("DRAGON_REVIEW shot %d t=%.1f speed=%.0fkmh alt=%.0fm pitch=%.1f bank=%.1f loc=%s"),
			ReviewShot, T, GetSpeedKmh(), GetAltitudeMeters(), FlightPitch, Bank, *GetActorLocation().ToString());
		++ReviewShot;
	}
	if (T > 30.f)
	{
		if (APlayerController* PC = Cast<APlayerController>(C)) { PC->ConsoleCommand(TEXT("quit")); }
	}
}

void ADragonFlightPawn::PossessedBy(AController* NewController)
{
	Super::PossessedBy(NewController);
	if (NewController) { NewController->SetControlRotation(FRotator(-8.f, GetActorRotation().Yaw, 0.f)); }
	if (APlayerController* PC = Cast<APlayerController>(NewController)) { PC->ConsoleCommand(TEXT("DisableAllScreenMessages")); }
}

void ADragonFlightPawn::SetupPlayerInputComponent(UInputComponent* PlayerInputComponent)
{
	Super::SetupPlayerInputComponent(PlayerInputComponent);

	auto MakeAction = [this](const TCHAR* Name, EInputActionValueType Type)
	{
		UInputAction* A = NewObject<UInputAction>(this, Name);
		A->ValueType = Type;
		return A;
	};
	LookAction = MakeAction(TEXT("IA_DragonLook"), EInputActionValueType::Axis2D);
	BankAction = MakeAction(TEXT("IA_DragonBank"), EInputActionValueType::Axis1D);
	ThrottleAction = MakeAction(TEXT("IA_DragonThrottle"), EInputActionValueType::Axis1D);
	BoostAction = MakeAction(TEXT("IA_DragonBoost"), EInputActionValueType::Boolean);
	WingBeatAction = MakeAction(TEXT("IA_DragonWingBeat"), EInputActionValueType::Boolean);
	RollAction = MakeAction(TEXT("IA_DragonRoll"), EInputActionValueType::Axis1D);

	FlightContext = NewObject<UInputMappingContext>(this, TEXT("IMC_DragonFlight"));
	UInputMappingContext* C = FlightContext;
	auto Negate = [C](FEnhancedActionKeyMapping& M) { M.Modifiers.Add(NewObject<UInputModifierNegate>(C)); };

	C->MapKey(LookAction, EKeys::Mouse2D);
	{
		FEnhancedActionKeyMapping& Pad = C->MapKey(LookAction, EKeys::Gamepad_Right2D);
		Pad.Modifiers.Add(NewObject<UInputModifierDeadZone>(C));
		Pad.Modifiers.Add(NewObject<UInputModifierScaleByDeltaTime>(C));
		UInputModifierScalar* Scale = NewObject<UInputModifierScalar>(C);
		Scale->Scalar = FVector(55.f, 40.f, 1.f);
		Pad.Modifiers.Add(Scale);
	}
	C->MapKey(BankAction, EKeys::D);
	Negate(C->MapKey(BankAction, EKeys::A));
	C->MapKey(BankAction, EKeys::Gamepad_LeftX).Modifiers.Add(NewObject<UInputModifierDeadZone>(C));
	C->MapKey(ThrottleAction, EKeys::W);
	Negate(C->MapKey(ThrottleAction, EKeys::S));
	C->MapKey(ThrottleAction, EKeys::Gamepad_LeftY).Modifiers.Add(NewObject<UInputModifierDeadZone>(C));
	C->MapKey(BoostAction, EKeys::LeftShift);
	C->MapKey(BoostAction, EKeys::Gamepad_RightTrigger);
	C->MapKey(WingBeatAction, EKeys::SpaceBar);
	C->MapKey(WingBeatAction, EKeys::Gamepad_FaceButton_Bottom);
	C->MapKey(RollAction, EKeys::E);
	Negate(C->MapKey(RollAction, EKeys::Q));
	C->MapKey(RollAction, EKeys::Gamepad_RightShoulder);
	Negate(C->MapKey(RollAction, EKeys::Gamepad_LeftShoulder));

	if (APlayerController* PC = Cast<APlayerController>(GetController()))
	{
		if (UEnhancedInputLocalPlayerSubsystem* Sub = ULocalPlayer::GetSubsystem<UEnhancedInputLocalPlayerSubsystem>(PC->GetLocalPlayer()))
		{
			Sub->ClearAllMappings();
			Sub->AddMappingContext(FlightContext, 0);
		}
	}

	if (UEnhancedInputComponent* EIC = Cast<UEnhancedInputComponent>(PlayerInputComponent))
	{
		EIC->BindAction(LookAction, ETriggerEvent::Triggered, this, &ADragonFlightPawn::OnLook);
		EIC->BindAction(BankAction, ETriggerEvent::Triggered, this, &ADragonFlightPawn::OnBank);
		EIC->BindAction(BankAction, ETriggerEvent::Completed, this, &ADragonFlightPawn::OnBank);
		EIC->BindAction(ThrottleAction, ETriggerEvent::Triggered, this, &ADragonFlightPawn::OnThrottle);
		EIC->BindAction(ThrottleAction, ETriggerEvent::Completed, this, &ADragonFlightPawn::OnThrottle);
		EIC->BindAction(BoostAction, ETriggerEvent::Started, this, &ADragonFlightPawn::OnBoostStart);
		EIC->BindAction(BoostAction, ETriggerEvent::Completed, this, &ADragonFlightPawn::OnBoostStop);
		EIC->BindAction(WingBeatAction, ETriggerEvent::Triggered, this, &ADragonFlightPawn::OnWingBeat);
		EIC->BindAction(RollAction, ETriggerEvent::Started, this, &ADragonFlightPawn::OnRoll);
	}
}

void ADragonFlightPawn::OnLook(const FInputActionValue& Value)
{
	const FVector2D V = Value.Get<FVector2D>();
	AddControllerYawInput(V.X * MouseSensitivity);
	AddControllerPitchInput(-V.Y * MouseSensitivity);
}

void ADragonFlightPawn::OnBank(const FInputActionValue& Value) { BankInput = Value.Get<float>(); }
void ADragonFlightPawn::OnThrottle(const FInputActionValue& Value) { ThrottleInput = Value.Get<float>(); }
void ADragonFlightPawn::OnBoostStart(const FInputActionValue&) { bBoosting = Stamina > 5.f; }
void ADragonFlightPawn::OnBoostStop(const FInputActionValue&) { bBoosting = false; }

void ADragonFlightPawn::OnWingBeat(const FInputActionValue&)
{
	if (WingBeatTimer > 0.f || Stamina < 3.f) { return; }
	WingBeatTimer = 0.42f;
	Speed += WingBeatSpeedGain;
	VerticalBoost = FMath::Min(VerticalBoost + WingBeatLift, WingBeatLift * 1.6f);
	Stamina -= 3.f;
	FlapIntensity = 1.7f;
	FlapPhase = HALF_PI; // start the visible downstroke now
}

void ADragonFlightPawn::OnRoll(const FInputActionValue& Value)
{
	const float Dir = Value.Get<float>();
	if (RollTimeLeft > 0.f || FMath::IsNearlyZero(Dir)) { return; }
	RollDirection = FMath::Sign(Dir);
	RollTimeLeft = BarrelRollDuration;
	ShakeTime = 0.15f;
}

void ADragonFlightPawn::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);
	const float Dt = FMath::Min(DeltaSeconds, 0.05f);
	if (bReviewMode) { UpdateReviewMode(Dt); }
	UpdateFlight(Dt);
	UpdateAnimation(Dt);
	UpdateCamera(Dt);
}

void ADragonFlightPawn::UpdateFlight(float Dt)
{
	AController* C = GetController();

	// A/D steer the aim sideways so keyboard-only players can turn without the mouse.
	if (C && !FMath::IsNearlyZero(BankInput))
	{
		FRotator Aim = C->GetControlRotation();
		Aim.Yaw += BankInput * StrafeYawRate * Dt;
		C->SetControlRotation(Aim);
	}

	FRotator Aim = C ? C->GetControlRotation() : GetActorRotation();
	const float AimPitch = FMath::Clamp(FRotator::NormalizeAxis(Aim.Pitch), -80.f, 80.f);

	// Heading chases the camera aim; heavier when boosting.
	const float Resp = TurnResponsiveness * (bBoosting ? 0.7f : 1.f) * FMath::Lerp(0.75f, 1.15f, Smooth01((Speed - MinSpeed) / CruiseSpeed));
	const float A = ExpAlpha(Resp, Dt);
	const float YawStep = FMath::FindDeltaAngleDegrees(FlightYaw, Aim.Yaw) * A;
	FlightYaw = FRotator::NormalizeAxis(FlightYaw + YawStep);
	FlightPitch += (AimPitch - FlightPitch) * A;
	YawRate = FMath::FInterpTo(YawRate, YawStep / Dt, Dt, 8.f);

	const float TargetBank = FMath::Clamp(YawRate * BankPerYawRate + BankInput * 25.f, -MaxBankAngle, MaxBankAngle);
	Bank = FMath::FInterpTo(Bank, TargetBank, Dt, 4.f);

	// Speed: throttle target + dive/climb energy exchange.
	float Target = ThrottleInput >= 0.f ? FMath::Lerp(CruiseSpeed, FastSpeed, ThrottleInput) : FMath::Lerp(CruiseSpeed, SlowSpeed, -ThrottleInput);
	float Recovery = SpeedRecovery;
	if (bBoosting)
	{
		Stamina -= BoostDrainPerSecond * Dt;
		if (Stamina <= 0.f) { Stamina = 0.f; bBoosting = false; }
		Target = BoostSpeed;
		Recovery *= 2.2f;
	}
	else
	{
		Stamina = FMath::Min(MaxStamina, Stamina + StaminaRegenPerSecond * Dt);
	}
	if (Speed < Target || bBoosting) { Speed += (Target - Speed) * Recovery * Dt; }
	else { Speed += (Target - Speed) * Recovery * 0.6f * Dt; } // bleed excess dive speed slowly

	const float PitchSin = FMath::Sin(FMath::DegreesToRadians(FlightPitch));
	Speed -= PitchSin * DiveAcceleration * (PitchSin > 0.f ? 0.55f : 1.f) * Dt;
	Speed = FMath::Clamp(Speed, MinSpeed, MaxSpeed);

	WingBeatTimer = FMath::Max(0.f, WingBeatTimer - Dt);
	VerticalBoost = FMath::FInterpTo(VerticalBoost, 0.f, Dt, 2.2f);
	ImpactCooldown = FMath::Max(0.f, ImpactCooldown - Dt);

	// Barrel roll: eased full rotation plus a sideways dodge.
	FVector Dodge = FVector::ZeroVector;
	if (RollTimeLeft > 0.f)
	{
		RollTimeLeft = FMath::Max(0.f, RollTimeLeft - Dt);
		const float T = 1.f - RollTimeLeft / BarrelRollDuration;
		RollOffset = RollDirection * 360.f * Smooth01(T);
		Dodge = FRotator(0.f, FlightYaw, 0.f).RotateVector(FVector::RightVector) * RollDirection * 2600.f * FMath::Sin(T * PI);
		if (RollTimeLeft <= 0.f) { RollOffset = 0.f; }
	}

	const FRotator FlightRot(FlightPitch, FlightYaw, 0.f);
	const FVector Velocity = FlightRot.Vector() * Speed + FVector::UpVector * VerticalBoost + Dodge;

	FHitResult Hit;
	AddActorWorldOffset(Velocity * Dt, true, &Hit);
	if (Hit.bBlockingHit)
	{
		const FVector N = Hit.ImpactNormal;
		const FVector Slide = FVector::VectorPlaneProject(Velocity * Dt * (1.f - Hit.Time), N);
		AddActorWorldOffset(Slide + N * 8.f, true);

		// Deflect heading along the surface and nose up off the ground so the dragon skims instead of sticking.
		FVector NewDir = (FVector::VectorPlaneProject(FlightRot.Vector(), N).GetSafeNormal() + N * 0.4f).GetSafeNormal();
		const FRotator NewRot = NewDir.Rotation();
		FlightYaw = NewRot.Yaw;
		FlightPitch = FMath::Max(NewRot.Pitch, N.Z > 0.5f ? 6.f : NewRot.Pitch);
		if (C)
		{
			FRotator CR = C->GetControlRotation();
			CR.Yaw = FlightYaw;
			CR.Pitch = FMath::Max(FRotator::NormalizeAxis(CR.Pitch), FlightPitch + 4.f);
			C->SetControlRotation(CR);
		}
		if (ImpactCooldown <= 0.f)
		{
			Speed *= 0.8f;
			ShakeTime = 0.5f;
			ImpactCooldown = 0.4f;
		}
	}

	SetActorRotation(FRotator(FlightPitch, FlightYaw, Bank + RollOffset));
}

void ADragonFlightPawn::UpdateAnimation(float Dt)
{
	AnimTime += Dt;
	const bool bDiving = FlightPitch < -18.f && ThrottleInput <= 0.f && !bBoosting;
	float Rate = 0.85f, Intensity = 0.8f;
	if (ThrottleInput > 0.1f) { Rate = 1.25f; Intensity = 1.0f; }
	if (FlightPitch > 15.f) { Rate = 1.35f; Intensity = 1.1f; }
	if (bBoosting) { Rate = 1.9f; Intensity = 1.15f; }
	if (bDiving) { Intensity = 0.08f; }
	if (WingBeatTimer > 0.f) { Rate = 2.3f; }

	FlapIntensity = FMath::FInterpTo(FlapIntensity, Intensity, Dt, WingBeatTimer > 0.f ? 1.0f : 2.5f);
	FlapPhase = FMath::Fmod(FlapPhase + 2.f * PI * Rate * Dt, 2.f * PI);

	const float Flap = FMath::Sin(FlapPhase);
	const float Sweep = FMath::Lerp(0.f, 38.f, Smooth01((Speed - FastSpeed) / (BoostSpeed - FastSpeed)) + (bDiving ? 0.7f : 0.f));
	const float Shoulder = 6.f + Flap * 40.f * FlapIntensity;
	const float Wrist = (bDiving ? -10.f : 4.f) + FMath::Sin(FlapPhase - 1.0f) * 30.f * FlapIntensity;

	RightWingPivot->SetRelativeRotation(FRotator(0.f, FMath::Min(Sweep, 45.f), Shoulder));
	LeftWingPivot->SetRelativeRotation(FRotator(0.f, -FMath::Min(Sweep, 45.f), -Shoulder));
	RightWingTipPivot->SetRelativeRotation(FRotator(0.f, Sweep * 0.4f, Wrist));
	LeftWingTipPivot->SetRelativeRotation(FRotator(0.f, -Sweep * 0.4f, -Wrist));

	// Body rises on the downstroke, settles on the upstroke.
	BodyRoot->SetRelativeLocation(FVector(0.f, 0.f, -FMath::Cos(FlapPhase) * 22.f * FlapIntensity));
	BodyRoot->SetRelativeRotation(FRotator(FMath::Cos(FlapPhase) * 2.f * FlapIntensity, 0.f, 0.f));

	// Head looks into turns; tail counter-swings with a travelling wave.
	NeckPivot->SetRelativeRotation(FRotator(FMath::Sin(AnimTime * 0.9f) * 3.f - FlightPitch * 0.08f, FMath::Clamp(YawRate * 0.12f, -18.f, 18.f), 0.f));
	for (int32 i = 0; i < TailSegments.Num(); ++i)
	{
		const float Wave = FMath::Sin(AnimTime * 1.6f - i * 0.6f);
		const float YawAmt = Wave * (3.f + i * 1.2f) - FMath::Clamp(YawRate * 0.05f, -8.f, 8.f);
		const float PitchAmt = FMath::Sin(AnimTime * 1.1f - i * 0.5f) * 2.5f + FlightPitch * 0.04f;
		TailSegments[i]->SetRelativeRotation(FRotator(PitchAmt, YawAmt, 0.f));
	}
}

void ADragonFlightPawn::UpdateCamera(float Dt)
{
	const float Speed01 = Smooth01((Speed - SlowSpeed) / (BoostSpeed - SlowSpeed));
	Camera->SetFieldOfView(FMath::FInterpTo(Camera->FieldOfView, FMath::Lerp(BaseFOV, MaxFOV, FMath::Pow(Speed01, 1.3f)), Dt, 2.5f));
	CameraBoom->TargetArmLength = FMath::FInterpTo(CameraBoom->TargetArmLength, BaseArmLength + SpeedArmExtra * Speed01, Dt, 2.f);

	ShakeTime = FMath::Max(0.f, ShakeTime - Dt);
	const float Amp = Speed01 * Speed01 * 5.f + ShakeTime * 45.f;
	const float T = AnimTime;
	Camera->SetRelativeLocation(FVector(0.f, (FMath::Sin(T * 31.f) + 0.5f * FMath::Sin(T * 17.3f)) * Amp, FMath::Cos(T * 27.f) * Amp));
	Camera->SetRelativeRotation(FRotator(-9.f, 0.f, Bank * 0.12f)); // look down onto the dragon's back
}
