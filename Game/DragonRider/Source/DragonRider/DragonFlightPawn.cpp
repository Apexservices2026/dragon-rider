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
#include "DragonSplash.h"
#include "LongshipActor.h"
#include "DragonAnimInstance.h"
#include "Animation/AnimSequence.h"
#include "EngineUtils.h"
#include "Engine/StaticMeshActor.h"
#include "Engine/ExponentialHeightFog.h"
#include "Components/ExponentialHeightFogComponent.h"

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

	// Rigged dragon + Viking rider (tools/import_dragon.py) are loaded at BeginPlay, so editor commandlets that
	// rebuild those assets never hold them. Until then (or if they're missing) the primitive placeholder and the
	// UE mannequin rider below are used, so the game never breaks.
	DragonMesh = CreateDefaultSubobject<USkeletalMeshComponent>(TEXT("DragonMesh"));
	DragonMesh->SetupAttachment(Collision);
	DragonMesh->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	DragonMesh->SetGenerateOverlapEvents(false);
	DragonMesh->VisibilityBasedAnimTickOption = EVisibilityBasedAnimTickOption::AlwaysTickPoseAndRefreshBones;

	Rider = CreateDefaultSubobject<USkeletalMeshComponent>(TEXT("Rider"));
	Rider->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	Rider->SetupAttachment(BodyRoot);
	Rider->SetRelativeLocation(FVector(95.f, 0.f, 62.f));
	// The rider mesh (SK_Rider, from tools/import_dragon.py) is assigned in BeginPlay. There is no
	// template-mannequin fallback any more: Epic's template content is not part of this repository.

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
	SetupRiggedDragon();
	const FRotator Start = GetActorRotation();
	FlightYaw = Start.Yaw;
	FlightPitch = FRotator::NormalizeAxis(Start.Pitch);
	Speed = CruiseSpeed;
	Stamina = MaxStamina;
	bReviewMode = FParse::Param(FCommandLine::Get(), TEXT("DragonShots"));
	FindWorldWaterAndFog();
	if (bReviewMode) { CollectReviewLegs(); }
}

void ADragonFlightPawn::SetupRiggedDragon()
{
	const TCHAR* Dir = TEXT("/Game/DragonRider/Characters/");
	USkeletalMesh* DragonSK = LoadObject<USkeletalMesh>(nullptr, *FString::Printf(TEXT("%sSK_Dragon.SK_Dragon"), Dir), nullptr, LOAD_NoWarn | LOAD_Quiet);
	USkeletalMesh* RiderSK = LoadObject<USkeletalMesh>(nullptr, *FString::Printf(TEXT("%sSK_Rider.SK_Rider"), Dir), nullptr, LOAD_NoWarn | LOAD_Quiet);
	bRigged = DragonSK != nullptr;
	if (!bRigged) { DragonMesh->SetVisibility(false); return; }

	DragonMesh->SetAnimInstanceClass(UDragonAnimInstance::StaticClass());
	DragonMesh->SetSkeletalMesh(DragonSK);
	// Material instances by slot (also set on the asset by the import; this keeps the game right if that was lost).
	auto ApplyMI = [Dir](USkeletalMeshComponent* C)
	{
		const TArray<FName> Slots = C->GetMaterialSlotNames();
		for (int32 i = 0; i < Slots.Num(); ++i)
		{
			const FString S = Slots[i].ToString();
			const TCHAR* MI = S.Contains(TEXT("Wing")) ? TEXT("MI_Dragon_Wings_TwoSided") : S.Contains(TEXT("Rider")) ? TEXT("MI_Rider") : TEXT("MI_Dragon_Body");
			if (UMaterialInterface* M = LoadObject<UMaterialInterface>(nullptr, *FString::Printf(TEXT("%sMaterials/%s.%s"), Dir, MI, MI), nullptr, LOAD_NoWarn | LOAD_Quiet))
			{
				C->SetMaterial(C->GetMaterialIndex(Slots[i]), M);
			}
		}
	};
	ApplyMI(DragonMesh);
	BodyRoot->SetVisibility(false, true); // hide the primitive placeholder
	BodyRoot->SetRelativeLocationAndRotation(FVector::ZeroVector, FRotator::ZeroRotator);

	static const TCHAR* Takes[] = { TEXT("Glide"), TEXT("Flap"), TEXT("DiveTuck"), TEXT("WingBeatStrong"), TEXT("Hover") };
	DragonAnims.Reset();
	for (const TCHAR* T : Takes)
	{
		DragonAnims.Add(LoadObject<UAnimSequence>(nullptr, *FString::Printf(TEXT("%sSK_DragonDragonRig_%s.SK_DragonDragonRig_%s"), Dir, T, T), nullptr, LOAD_NoWarn | LOAD_Quiet));
	}
	if (UDragonAnimInstance* Anim = Cast<UDragonAnimInstance>(DragonMesh->GetAnimInstance()))
	{
		Anim->GlideSeq = DragonAnims[0]; Anim->FlapSeq = DragonAnims[1]; Anim->DiveSeq = DragonAnims[2];
		Anim->WingBeatSeq = DragonAnims[3]; Anim->HoverSeq = DragonAnims[4];
		const FReferenceSkeleton& Ref = DragonSK->GetRefSkeleton();
		for (int32 i = 0; i < Ref.GetNum(); ++i)
		{
			const FString N = Ref.GetBoneName(i).ToString();
			if (N.StartsWith(TEXT("Neck")) || N == TEXT("Head")) { Anim->NeckBones.Add(Ref.GetBoneName(i)); }
		}
	}

	if (RiderSK)
	{
		// Rider origin = seat point; the Saddle bone carries Blender's -90 deg X rest roll, undone by SaddleRiderRotation.
		Rider->AttachToComponent(DragonMesh, FAttachmentTransformRules::SnapToTargetNotIncludingScale, TEXT("Saddle"));
		// Undo the Saddle bone's rest frame (Blender bone axes, -90 deg roll): align the rider with the dragon's body
		// axes (+X forward, +Z up) in the bind pose, plus an optional trim. The saddle still carries body motion.
		DragonMesh->RefreshBoneTransforms();
		const FQuat SaddleCS = DragonMesh->GetSocketTransform(TEXT("Saddle"), RTS_Component).GetRotation();
		Rider->SetRelativeLocationAndRotation(FVector::ZeroVector, SaddleCS.Inverse() * SaddleRiderRotation.Quaternion());
		Rider->SetUsingAbsoluteScale(true); // don't inherit the Saddle bone's scale
		Rider->SetWorldScale3D(FVector(1.f));
		Rider->SetVisibility(true);
		Rider->SetSkeletalMesh(RiderSK);
		ApplyMI(Rider);
		if (UAnimSequence* Idle = LoadObject<UAnimSequence>(nullptr, *FString::Printf(TEXT("%sSK_Rider_Anim.SK_Rider_Anim"), Dir), nullptr, LOAD_NoWarn | LOAD_Quiet))
		{
			Rider->PlayAnimation(Idle, true);
		}
	}
	int32 Valid = 0;
	for (UAnimSequence* A : DragonAnims) { Valid += A && A->GetSkeleton() ? 1 : 0; }
	UE_LOG(LogTemp, Display, TEXT("DRAGON_RIG bones=%d anims=%d/5 rider=%d"), DragonSK->GetRefSkeleton().GetNum(), Valid, RiderSK ? 1 : 0);
	const int32 SaddleIdx = DragonSK->GetRefSkeleton().FindBoneIndex(TEXT("Saddle"));
	if (SaddleIdx != INDEX_NONE)
	{
		UE_LOG(LogTemp, Display, TEXT("DRAGON_RIG saddle ref local=%s socketscale=%s"), *DragonSK->GetRefSkeleton().GetRefBonePose()[SaddleIdx].ToString(),
			*DragonMesh->GetSocketTransform(TEXT("Saddle")).GetScale3D().ToString());
	}
}

void ADragonFlightPawn::FindWorldWaterAndFog()
{
	// The sea is a huge /Engine/BasicShapes/Plane static mesh actor at Z=0 (tools/build_opening_level.py).
	for (TActorIterator<AStaticMeshActor> It(GetWorld()); It; ++It)
	{
		UStaticMeshComponent* SM = It->GetStaticMeshComponent();
		if (SM && IsWaterComponent(SM)) { break; }
	}
	// The archipelago's far-ocean skirt lies 0.8 m under the sea plane. It is scenery only: if the dragon's sweep hits
	// it, a plunge bounces off it at the surface instead of going under.
	for (TActorIterator<AStaticMeshActor> It(GetWorld()); It; ++It)
	{
		UStaticMeshComponent* SM = It->GetStaticMeshComponent();
		if (SM && SM != WaterComponent && SM->GetStaticMesh() && SM->GetStaticMesh()->GetName() == TEXT("Plane")
			&& It->GetActorLocation().Z < -10.f && It->GetActorLocation().Z > -500.f && SM->GetComponentScale().X > 100.f)
		{
			Collision->IgnoreComponentWhenMoving(SM, true);
		}
	}
	for (TActorIterator<AExponentialHeightFog> It(GetWorld()); It; ++It)
	{
		WorldFog = It->GetComponent();
		break;
	}
}

bool ADragonFlightPawn::IsWaterComponent(const UPrimitiveComponent* Comp)
{
	if (!Comp) { return false; }
	if (Comp == WaterComponent) { return true; }
	const UStaticMeshComponent* SM = Cast<UStaticMeshComponent>(Comp);
	if (SM && SM->GetStaticMesh() && SM->GetStaticMesh()->GetName() == TEXT("Plane")
		&& FMath::Abs(SM->GetComponentLocation().Z) < 50.f && SM->GetComponentScale().X > 100.f)
	{
		WaterComponent = const_cast<UStaticMeshComponent*>(SM);
		return true;
	}
	return false;
}

void ADragonFlightPawn::EnterWater(const FVector& ImpactPoint)
{
	bUnderwater = true;
	bSubmerged = false;
	bBurstRising = false;
	UnderwaterTime = 0.f;
	BuoyancyVelocity = 0.f;
	VerticalBoost = 0.f;
	PullOutTime = 0.f;
	bBoosting = false;
	WaterIgnoreTime = 0.f;
	if (WaterComponent) { Collision->IgnoreComponentWhenMoving(WaterComponent, true); }
	CameraBoom->bDoCollisionTest = false; // the camera probe would otherwise pin the camera to the sea plane
	// Let the camera hang above the surface for a beat so the splash is seen before it follows the dragon under.
	CamLagHoldTime = 0.45f; CamLagHoldSpeed = 0.5f; CamLagHoldMaxDistance = 3500.f;

	const FVector Dir = FRotator(FlightPitch, FlightYaw, 0.f).Vector();
	ADragonSplash::Spawn(GetWorld(), ImpactPoint, Speed / 8500.f, false, Dir);
	ShakeTime = 0.7f;
	Speed *= 0.82f;
	UE_LOG(LogTemp, Display, TEXT("DRAGON_REVIEW plunge speed=%.0fkmh pitch=%.1f"), GetSpeedKmh(), FlightPitch);
}

void ADragonFlightPawn::ExitWater()
{
	bUnderwater = false;
	bBurstRising = false;
	Speed = FMath::Max(Speed + BurstSpeedGain, BurstMinSpeed);
	FlightPitch = FMath::Max(FlightPitch, BurstExitPitch);
	VerticalBoost = BurstLift + FMath::Max(0.f, BuoyancyVelocity * 0.4f);
	BuoyancyVelocity = 0.f;
	if (AController* C = GetController())
	{
		FRotator CR = C->GetControlRotation();
		// Camera levels out at the surface so the dragon is seen launching out of the splash, then eases up (pull-out).
		CR.Pitch = 6.f;
		C->SetControlRotation(CR);
	}
	WaterIgnoreTime = 0.6f;
	PullOutTime = 1.4f;
	UnderwaterAmount = 0.f; // camera arm/socket back to flight framing at once
	CamLagHoldTime = 0.5f; CamLagHoldSpeed = 5.f; CamLagHoldMaxDistance = 2500.f; // camera trails at the surface as the dragon launches
	BurstAmount = 1.f;
	ShakeTime = 0.8f;
	FlapIntensity = 1.9f;
	FlapPhase = HALF_PI;
	WingBeatTimer = 0.5f;
	++WingBeatCount;
	const FVector Dir = FRotator(FlightPitch, FlightYaw, 0.f).Vector();
	ADragonSplash::Spawn(GetWorld(), GetActorLocation(), 1.7f, true, Dir);
	UE_LOG(LogTemp, Display, TEXT("DRAGON_REVIEW burst after %.2fs speed=%.0fkmh"), UnderwaterTime, GetSpeedKmh());
}

bool ADragonFlightPawn::CollectReviewLegs()
{
	ReviewLegs.Reset();
	TArray<TPair<int32, FReviewLeg>> Found;
	for (TActorIterator<AActor> It(GetWorld()); It; ++It)
	{
		int32 Index = INDEX_NONE;
		FReviewLeg Leg;
		for (const FName& TagName : It->Tags)
		{
			FString Key, Value;
			const FString Tag = TagName.ToString();
			if (!Tag.Split(TEXT(":"), &Key, &Value)) { Key = Tag; }
			TArray<FString> Parts;
			Value.ParseIntoArray(Parts, Key == TEXT("Shots") ? TEXT("|") : TEXT(","));
			if (Key == TEXT("ReviewLeg")) { Index = FCString::Atoi(*Value); }
			else if (Key == TEXT("Dur")) { Leg.Duration = FCString::Atof(*Value); }
			else if (Key == TEXT("Pitch")) { Leg.Pitch = FCString::Atof(*Value); }
			else if (Key == TEXT("Speed")) { Leg.SpeedKmh = FCString::Atof(*Value); }
			else if (Key == TEXT("Dive")) { Leg.DiveAt = FCString::Atof(*Value); }
			else if (Key == TEXT("Boost")) { Leg.bBoost = true; }
			else if (Key == TEXT("Name")) { Leg.Name = Value.Replace(TEXT("_"), TEXT(" ")); }
			else if (Key == TEXT("Shots")) { for (const FString& P : Parts) { Leg.Shots.Add(FCString::Atof(*P)); } }
			else if (Key == TEXT("Orbit") && Parts.Num() == 2) { Leg.bOrbit = true; Leg.OrbitYaw = FCString::Atof(*Parts[0]); Leg.OrbitPitch = FCString::Atof(*Parts[1]); }
			else if (Key == TEXT("FollowShip") && Parts.Num() == 3) { Leg.bFollowShip = true; Leg.FollowOffset = FVector(FCString::Atof(*Parts[0]), FCString::Atof(*Parts[1]), FCString::Atof(*Parts[2])); }
			else if (Key == TEXT("AimAt") && Parts.Num() == 3) { Leg.bAimAt = true; Leg.AimAt = FVector(FCString::Atof(*Parts[0]), FCString::Atof(*Parts[1]), FCString::Atof(*Parts[2])); }
		}
		if (Index != INDEX_NONE)
		{
			Leg.Location = It->GetActorLocation();
			Leg.Rotation = It->GetActorRotation();
			Found.Add(TPair<int32, FReviewLeg>(Index, Leg));
		}
	}
	Found.Sort([](const TPair<int32, FReviewLeg>& A, const TPair<int32, FReviewLeg>& B) { return A.Key < B.Key; });
	for (const TPair<int32, FReviewLeg>& P : Found) { ReviewLegs.Add(P.Value); }
	UE_LOG(LogTemp, Display, TEXT("DRAGON_REVIEW legs=%d"), ReviewLegs.Num());
	return ReviewLegs.Num() > 0;
}

void ADragonFlightPawn::StartReviewLeg(int32 Index)
{
	ReviewLeg = Index;
	ReviewLegTime = 0.f;
	ReviewLegShot = 0;
	if (!ReviewLegs.IsValidIndex(Index)) { return; }
	FReviewLeg& L = ReviewLegs[Index];
	if (L.bFollowShip)
	{
		const ALongshipActor* Best = nullptr;
		for (TActorIterator<ALongshipActor> It(GetWorld()); It; ++It)
		{
			if (It->SailSpeed > 1.f && (!Best || FVector::DistSquared(It->GetActorLocation(), L.Location) < FVector::DistSquared(Best->GetActorLocation(), L.Location))) { Best = *It; }
		}
		if (Best)
		{
			const FVector Fwd = FVector(Best->GetActorForwardVector().X, Best->GetActorForwardVector().Y, 0.f).GetSafeNormal();
			const FVector Right(-Fwd.Y, Fwd.X, 0.f);
			L.Location = Best->GetActorLocation() - Fwd * L.FollowOffset.X + Right * L.FollowOffset.Y + FVector(0.f, 0.f, L.FollowOffset.Z);
			L.AimAt = Best->GetActorLocation() + Fwd * 1500.f;
			L.bAimAt = true;
			UE_LOG(LogTemp, Display, TEXT("DRAGON_REVIEW follow ship %s at %s yaw %.0f hidden=%d"), *Best->GetName(), *Best->GetActorLocation().ToString(),
				Best->GetActorRotation().Yaw, Best->IsHidden() ? 1 : 0);
		}
	}
	if (bUnderwater) { bUnderwater = false; bBurstRising = false; }
	if (bDiveHeld) { OnDiveStop(FInputActionValue()); }
	SetActorLocation(L.Location);
	FRotator R = L.Rotation;
	if (L.bAimAt) { R = (L.AimAt - L.Location).Rotation(); }
	FlightYaw = R.Yaw; FlightPitch = FMath::Clamp(FRotator::NormalizeAxis(R.Pitch), -30.f, 30.f);
	Speed = L.SpeedKmh > 0.f ? L.SpeedKmh / 0.036f : CruiseSpeed;
	Bank = 0.f; YawRate = 0.f; VerticalBoost = 0.f; BurstAmount = 0.f; DiveAmount = 0.f; UnderwaterAmount = 0.f; PullOutTime = 0.f;
	Stamina = MaxStamina;
	if (WaterComponent) { Collision->IgnoreComponentWhenMoving(WaterComponent, false); }
	CameraBoom->bDoCollisionTest = true;
	if (AController* C = GetController()) { C->SetControlRotation(FRotator(L.Pitch, FlightYaw, 0.f)); }
	UE_LOG(LogTemp, Display, TEXT("DRAGON_REVIEW leg %d (%s) at %s yaw %.1f"), Index, *L.Name, *L.Location.ToString(), FlightYaw);
}

void ADragonFlightPawn::UpdateLegReview(float Dt)
{
	ReviewTime += Dt;
	AController* C = GetController();
	if (!C) { return; }
	if (ReviewLeg < 0) { StartReviewLeg(0); }
	if (!ReviewLegs.IsValidIndex(ReviewLeg)) { return; }
	const FReviewLeg& L = ReviewLegs[ReviewLeg];
	ReviewLegTime += Dt;

	// Camera: optional fixed orbit around the dragon for beauty shots, otherwise the normal chase camera.
	if (L.bOrbit)
	{
		CameraBoom->SetUsingAbsoluteRotation(true);
		CameraBoom->bUsePawnControlRotation = false;
		CameraBoom->SetWorldRotation(FRotator(L.OrbitPitch, FlightYaw + L.OrbitYaw, 0.f));
	}
	else if (CameraBoom->IsUsingAbsoluteRotation())
	{
		CameraBoom->SetUsingAbsoluteRotation(false);
		CameraBoom->bUsePawnControlRotation = true;
	}
	if (!bDiveHeld && !bUnderwater && PullOutTime <= 0.f)
	{
		float AimYaw = L.Rotation.Yaw;
		if (L.bAimAt) { AimYaw = (L.AimAt - L.Location).Rotation().Yaw; }
		C->SetControlRotation(FRotator(L.Pitch, AimYaw, 0.f));
	}
	if (L.SpeedKmh > 0.f && !bDiveHeld && !bUnderwater && PullOutTime <= 0.f) { Speed = L.SpeedKmh / 0.036f; }
	bBoosting = L.bBoost && !bDiveHeld && !bUnderwater;
	Stamina = MaxStamina;
	if (L.DiveAt >= 0.f && ReviewLegTime >= L.DiveAt && !bDiveHeld && !bUnderwater && ReviewLegTime < L.DiveAt + 0.2f) { OnDiveStart(FInputActionValue()); }
	if (bDiveHeld && bUnderwater) { OnDiveStop(FInputActionValue()); }

	if (ReviewLegShot < L.Shots.Num() && ReviewLegTime >= L.Shots[ReviewLegShot])
	{
		ReviewScreenshot(*FString::Printf(TEXT("%s +%.1fs"), *L.Name, L.Shots[ReviewLegShot]));
		++ReviewLegShot;
	}
	if (ReviewLegTime >= L.Duration)
	{
		if (ReviewLeg + 1 < ReviewLegs.Num()) { StartReviewLeg(ReviewLeg + 1); }
		else if (APlayerController* PC = Cast<APlayerController>(C)) { PC->ConsoleCommand(TEXT("quit")); }
	}
}

void ADragonFlightPawn::UpdateReviewMode(float Dt)
{
	if (ReviewLegs.Num() > 0) { UpdateLegReview(Dt); return; }
	ReviewTime += Dt;
	AController* C = GetController();
	if (!C) { return; }
	const float T = ReviewTime;
	FRotator Aim = C->GetControlRotation();

	// Script: cruise -> beauty orbit shots -> right turn -> boosted dive -> climb with wing beats.
	if (T > 4.f && T < 11.f)
	{
		CameraBoom->SetUsingAbsoluteRotation(true);
		CameraBoom->bUsePawnControlRotation = false; // otherwise the control rotation overrides the orbit
		const float OrbitYaw = T < 7.5f ? 150.f : 95.f;
		CameraBoom->SetWorldRotation(FRotator(T < 7.5f ? -8.f : -22.f, FlightYaw + OrbitYaw, 0.f));
	}
	else if (CameraBoom->IsUsingAbsoluteRotation())
	{
		CameraBoom->SetUsingAbsoluteRotation(false);
		CameraBoom->bUsePawnControlRotation = true;
	}
	if (T > 11.f && T < 17.f) { Aim.Yaw += 28.f * Dt; Aim.Pitch = -6.f; }
	if (T > 17.f && T < 23.f) { bBoosting = true; Aim.Pitch = -32.f; }
	if (T >= 23.f && T < 24.f) { bBoosting = false; }
	if (T > 23.f && T < 30.f) { Aim.Pitch = 22.f; OnWingBeat(FInputActionValue()); }
	// Second act: climb out over the open sea, power-dive into the water, plunge, burst out.
	if (T > 30.f && T < 35.5f) { Aim.Pitch = 30.f; OnWingBeat(FInputActionValue()); }
	C->SetControlRotation(Aim);

	static const float ShotTimes[] = { 3.f, 6.8f, 10.3f, 15.f, 21.5f, 27.f };
	if (ReviewShot < UE_ARRAY_COUNT(ShotTimes) && T >= ShotTimes[ReviewShot])
	{
		ReviewScreenshot(TEXT("timed"));
	}

	switch (ReviewPhase)
	{
	case 0: // waiting to start the dive
		if (T >= 35.5f) { OnDiveStart(FInputActionValue()); ReviewPhase = 1; ReviewEventTime = T; }
		break;
	case 1: // diving: shot once it is tucked and fast, then wait for the plunge
		if (ReviewShot == 6 && ((DiveAmount > 0.9f && GetSpeedKmh() > 560.f) || GetAltitudeMeters() < 90.f)) { ReviewScreenshot(TEXT("power-dive")); }
		if (bUnderwater)
		{
			if (ReviewShot == 6) { ReviewScreenshot(TEXT("power-dive (late)")); }
			OnDiveStop(FInputActionValue());
			ReviewPhase = 2; ReviewEventTime = T;
		}
		break;
	case 2: // underwater
		if (ReviewShot == 7 && T - ReviewEventTime > 0.3f) { ReviewScreenshot(TEXT("entry splash")); }
		if (ReviewShot == 8 && ((T - ReviewEventTime > 0.8f && UnderwaterView > 0.95f) || T - ReviewEventTime > 1.5f)) { ReviewScreenshot(TEXT("underwater")); }
		if (!bUnderwater)
		{
			while (ReviewShot < 9) { ReviewScreenshot(TEXT("underwater (missed)")); }
			ReviewPhase = 3; ReviewEventTime = T;
		}
		break;
	case 3: // burst
		if (ReviewShot == 9 && T - ReviewEventTime > 0.3f) { ReviewScreenshot(TEXT("burst")); }
		if (ReviewShot == 10 && T - ReviewEventTime > 1.1f) { ReviewScreenshot(TEXT("after burst")); }
		if (T - ReviewEventTime > 3.f) { ReviewPhase = 4; }
		break;
	case 4: // village low pass: jump out to sea in front of the start village and fly in low over it
	case 6: // fleet pass: jump behind the rowing fleet and overtake it low along its side
	{
		FVector Target = FVector::ZeroVector, Dir = FVector::ForwardVector, Side = FVector::RightVector;
		float Back = 0.f, Alt = 0.f, Offset = 0.f;
		bool bFound = false;
		if (ReviewPhase == 4)
		{
			// Skerholm is the village right ahead of the start; Innvik (deep in the fjord) catches the evening sun.
			const FName VillageTag = ReviewPass == 0 ? FName(TEXT("Village_Skerholm")) : FName(TEXT("Village_Innvik"));
			for (TActorIterator<AActor> It(GetWorld()); It; ++It)
			{
				if (It->ActorHasTag(VillageTag))
				{
					// Longhouse doors (+Y) face the water: approach from the sea along -right.
					Target = It->GetActorLocation(); Dir = -It->GetActorRightVector(); bFound = true;
					break;
				}
			}
			Back = 30000.f; Alt = 5200.f; Offset = 4500.f; // pass beside the longhouse so the dragon doesn't hide it
		}
		else
		{
			int32 N = 0;
			for (TActorIterator<ALongshipActor> It(GetWorld()); It; ++It)
			{
				if (It->SailSpeed > 1.f) { Target += It->GetActorLocation(); Dir = It->GetActorForwardVector(); ++N; }
			}
			if (N > 0) { Target /= N; bFound = true; }
			Back = 26000.f; Alt = 2600.f; Offset = 6000.f;
		}
		Dir = FVector(Dir.X, Dir.Y, 0.f).GetSafeNormal();
		Side = FVector(-Dir.Y, Dir.X, 0.f);
		if (bFound)
		{
			SetActorLocation(FVector(Target.X, Target.Y, Alt) - Dir * Back + Side * Offset);
			FlightYaw = Dir.Rotation().Yaw;
			FlightPitch = -2.f; Speed = CruiseSpeed; Bank = 0.f; YawRate = 0.f;
			VerticalBoost = 0.f; BurstAmount = 0.f; DiveAmount = 0.f; UnderwaterAmount = 0.f; PullOutTime = 0.f; bDiveHeld = false;
			C->SetControlRotation(FRotator(-6.f, FlightYaw, 0.f));
		}
		UE_LOG(LogTemp, Display, TEXT("DRAGON_REVIEW %s pass found=%d target=%s"), ReviewPhase == 4 ? TEXT("village") : TEXT("fleet"), bFound ? 1 : 0, *Target.ToString());
		++ReviewPhase; ++ReviewPass; ReviewEventTime = T;
		break;
	}
	case 5:
		C->SetControlRotation(FRotator(-5.f, FlightYaw, 0.f));
		// Screenshots grab a later frame, so wait a moment after each shot before teleporting on.
		if (ReviewPass == 1)
		{
			if (ReviewShot == 11 && T - ReviewEventTime > 4.f) { ReviewScreenshot(TEXT("village Skerholm approach")); }
			if (T - ReviewEventTime > 4.5f) { ReviewPhase = 4; }
		}
		else
		{
			if (ReviewShot == 12 && T - ReviewEventTime > 5.f) { ReviewScreenshot(TEXT("village Innvik pass")); }
			if (T - ReviewEventTime > 5.5f) { ReviewPhase = 6; }
		}
		break;
	case 7:
		C->SetControlRotation(FRotator(-0.5f, FlightYaw, 0.f));
		if (ReviewShot == 13 && T - ReviewEventTime > 4.f) { ReviewScreenshot(TEXT("fleet pass")); }
		if (ReviewShot == 14 && T - ReviewEventTime > 6.f) { ReviewScreenshot(TEXT("fleet alongside")); }
		if (T - ReviewEventTime > 6.5f) { ReviewPhase = 8; }
		break;
	default: break;
	}
	if (ReviewPhase >= 8 || T > 110.f)
	{
		if (APlayerController* PC = Cast<APlayerController>(C)) { PC->ConsoleCommand(TEXT("quit")); }
	}
}

void ADragonFlightPawn::ReviewScreenshot(const TCHAR* What)
{
	FScreenshotRequest::RequestScreenshot(FString::Printf(TEXT("DragonReview_%02d"), ReviewShot), true, false);
	UE_LOG(LogTemp, Display, TEXT("DRAGON_REVIEW shot %d (%s) t=%.1f speed=%.0fkmh alt=%.1fm pitch=%.1f bank=%.1f dive=%.2f underwater=%d view=%.2f loc=%s"),
		ReviewShot, What, ReviewTime, GetSpeedKmh(), GetAltitudeMeters(), FlightPitch, Bank, DiveAmount, bUnderwater ? 1 : 0, UnderwaterView,
		*GetActorLocation().ToString());
	++ReviewShot;
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
	DiveAction = MakeAction(TEXT("IA_DragonDive"), EInputActionValueType::Boolean);

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
	C->MapKey(DiveAction, EKeys::LeftControl);
	C->MapKey(DiveAction, EKeys::RightMouseButton);
	C->MapKey(DiveAction, EKeys::Gamepad_LeftTrigger);

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
		EIC->BindAction(DiveAction, ETriggerEvent::Started, this, &ADragonFlightPawn::OnDiveStart);
		EIC->BindAction(DiveAction, ETriggerEvent::Completed, this, &ADragonFlightPawn::OnDiveStop);
	}
}

void ADragonFlightPawn::OnDiveStart(const FInputActionValue&)
{
	bDiveHeld = true;
	PullOutTime = 0.f;
}

void ADragonFlightPawn::OnDiveStop(const FInputActionValue&)
{
	// Only auto pull out of a real dive; a tap at cruise shouldn't yank the nose up.
	if (bDiveHeld && !bUnderwater && DiveAmount > 0.3f) { PullOutTime = PullOutDuration; }
	bDiveHeld = false;
}

void ADragonFlightPawn::OnLook(const FInputActionValue& Value)
{
	const FVector2D V = Value.Get<FVector2D>();
	if (V.SizeSquared() > 0.04f) { LastLookInputTime = GetWorld()->GetTimeSeconds(); }
	AddControllerYawInput(V.X * MouseSensitivity);
	AddControllerPitchInput(-V.Y * MouseSensitivity);
}

void ADragonFlightPawn::OnBank(const FInputActionValue& Value) { BankInput = Value.Get<float>(); }
void ADragonFlightPawn::OnThrottle(const FInputActionValue& Value) { ThrottleInput = Value.Get<float>(); }
void ADragonFlightPawn::OnBoostStart(const FInputActionValue&) { bBoosting = Stamina > 5.f; }
void ADragonFlightPawn::OnBoostStop(const FInputActionValue&) { bBoosting = false; }

void ADragonFlightPawn::OnWingBeat(const FInputActionValue&)
{
	// Under water, Space means "burst for the surface now".
	if (bUnderwater)
	{
		if (UnderwaterTime > 0.2f) { bBurstRising = true; }
		return;
	}
	if (WingBeatTimer > 0.f || Stamina < 3.f) { return; }
	WingBeatTimer = 0.42f;
	++WingBeatCount;
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
	const bool bLookIdle = GetWorld()->GetTimeSeconds() - LastLookInputTime > 0.35f;

	// A/D steer the aim sideways so keyboard-only players can turn without the mouse.
	if (C && !FMath::IsNearlyZero(BankInput))
	{
		FRotator Aim = C->GetControlRotation();
		Aim.Yaw += BankInput * StrafeYawRate * Dt;
		C->SetControlRotation(Aim);
	}

	// Power dive: tuck in, and pull the aim (and so the camera) toward a steep dive unless already steeper.
	const bool bDiving = bDiveHeld && !bUnderwater;
	DiveAmount += ((bDiving ? 1.f : 0.f) - DiveAmount) * ExpAlpha(bDiving ? PowerDiveBlendRate : PowerDiveBlendRate * 0.7f, Dt);
	UnderwaterAmount += ((bUnderwater ? 1.f : 0.f) - UnderwaterAmount) * ExpAlpha(5.f, Dt);
	BurstAmount = FMath::Max(0.f, BurstAmount - Dt / 1.1f);
	PullOutTime = FMath::Max(0.f, PullOutTime - Dt);
	if (C)
	{
		FRotator CR = C->GetControlRotation();
		float P = FRotator::NormalizeAxis(CR.Pitch);
		if (bDiving && P > PowerDivePitch + 12.f)
		{
			// Camera settles a little shallower than the dragon so the dive reads in 3/4 view rather than top-down.
			P += (PowerDivePitch + 12.f - P) * ExpAlpha(3.2f * DiveAmount, Dt);
		}
		else if (PullOutTime > 0.f)
		{
			// Slingshot: after releasing the dive, ease the nose back up while momentum carries us.
			if (!bLookIdle) { PullOutTime = 0.f; }
			else if (P < PullOutPitch) { P += (PullOutPitch - P) * ExpAlpha(2.4f, Dt); }
		}
		else if (bUnderwater && bLookIdle)
		{
			// Let the camera swing round behind/below the dragon as it turns for the surface.
			P += (FMath::Clamp(FlightPitch * 0.5f, -30.f, 25.f) - P) * ExpAlpha(2.5f, Dt);
		}
		CR.Pitch = P;
		C->SetControlRotation(CR);
	}

	FRotator Aim = C ? C->GetControlRotation() : GetActorRotation();
	float AimPitch = FMath::Clamp(FRotator::NormalizeAxis(Aim.Pitch), -80.f, 80.f);
	if (bUnderwater)
	{
		// Buoyancy turns the dragon toward the light; steering still works but loses this tug-of-war over time.
		UnderwaterTime += Dt;
		if (UnderwaterTime >= MaxUnderwaterTime) { bBurstRising = true; }
		const float Rise = bBurstRising ? 1.f : Smooth01(UnderwaterTime / (MaxUnderwaterTime * 0.5f));
		AimPitch = FMath::Lerp(AimPitch, bBurstRising ? 70.f : 55.f, Rise);
	}
	else
	{
		// Dive: nose to PowerDivePitch unless already steeper. Burst: hold a steep climb while the camera settles.
		AimPitch = FMath::Lerp(AimPitch, FMath::Min(AimPitch, PowerDivePitch), DiveAmount);
		if (BurstAmount > 0.f) { AimPitch = FMath::Max(AimPitch, BurstExitPitch * Smooth01(BurstAmount * 1.6f)); }
	}

	// Heading chases the camera aim; heavier when boosting or tucked in a dive.
	float Resp = TurnResponsiveness * (bBoosting ? 0.7f : 1.f) * FMath::Lerp(0.75f, 1.15f, Smooth01((Speed - MinSpeed) / CruiseSpeed));
	Resp *= FMath::Lerp(1.f, PowerDiveSteerScale, DiveAmount);
	if (bUnderwater) { Resp *= bBurstRising ? 2.2f : 1.3f; }
	const float A = ExpAlpha(Resp, Dt);
	const float YawStep = FMath::FindDeltaAngleDegrees(FlightYaw, Aim.Yaw) * A;
	FlightYaw = FRotator::NormalizeAxis(FlightYaw + YawStep);
	FlightPitch += (AimPitch - FlightPitch) * A;
	YawRate = FMath::FInterpTo(YawRate, YawStep / Dt, Dt, 8.f);

	const float TargetBank = FMath::Clamp(YawRate * BankPerYawRate + BankInput * 25.f, -MaxBankAngle, MaxBankAngle);
	Bank = FMath::FInterpTo(Bank, TargetBank, Dt, 4.f);

	// Speed: throttle target + dive/climb energy exchange.
	const float PrevSpeed = Speed;
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
	Recovery *= FMath::Lerp(1.f, PowerDiveDragScale, DiveAmount);

	if (bUnderwater)
	{
		Speed += (UnderwaterSwimSpeed * (bBurstRising ? 1.6f : 1.f) - Speed) * ExpAlpha(UnderwaterDrag, Dt);
	}
	else
	{
		if (Speed < Target || bBoosting) { Speed += (Target - Speed) * Recovery * Dt; }
		else { Speed += (Target - Speed) * Recovery * 0.6f * Dt; } // bleed excess dive speed slowly

		const float PitchSin = FMath::Sin(FMath::DegreesToRadians(FlightPitch));
		const float Gravity = PitchSin > 0.f ? 0.55f : FMath::Lerp(1.f, PowerDiveGravityScale, DiveAmount);
		Speed -= PitchSin * DiveAcceleration * Gravity * Dt;
	}
	// Dive cap while diving; afterwards speed above MaxSpeed is kept (never grows) and bleeds off.
	const float Cap = bDiving ? PowerDiveMaxSpeed : FMath::Max(MaxSpeed, FMath::Min(PrevSpeed, PowerDiveMaxSpeed));
	Speed = FMath::Clamp(Speed, bUnderwater ? 800.f : MinSpeed, Cap);

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
	FVector Velocity = FlightRot.Vector() * Speed + FVector::UpVector * VerticalBoost + Dodge;
	if (bUnderwater)
	{
		BuoyancyVelocity = FMath::Min(BuoyancyVelocity + Buoyancy * Dt, 4200.f);
		if (bBurstRising) { BuoyancyVelocity = FMath::FInterpTo(BuoyancyVelocity, 7000.f, Dt, 5.f); }
		Velocity += FVector::UpVector * BuoyancyVelocity;
	}

	FHitResult Hit;
	AddActorWorldOffset(Velocity * Dt, true, &Hit);
	if (Hit.bBlockingHit)
	{
		const bool bWater = !bUnderwater && IsWaterComponent(Hit.GetComponent());
		const bool bSteepFast = FlightPitch < PlungeMaxPitch && Speed > PlungeMinSpeed;
		if (bWater && (bSteepFast || (bDiving && FlightPitch < -10.f)))
		{
			// Plunge: stop colliding with the sea plane and carry on through it.
			EnterWater(Hit.ImpactPoint);
			AddActorWorldOffset(Velocity * Dt * (1.f - Hit.Time), true);
		}
		else
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
	}

	// Water state transitions by height.
	const float Z = GetActorLocation().Z;
	if (bUnderwater)
	{
		if (Z < -150.f) { bSubmerged = true; }
		if ((bSubmerged && Z > 0.f) || (!bSubmerged && UnderwaterTime > 0.6f)) { ExitWater(); }
	}
	else if (WaterComponent && WaterIgnoreTime > 0.f)
	{
		WaterIgnoreTime -= Dt;
		if (Z < -150.f) { EnterWater(FVector(GetActorLocation().X, GetActorLocation().Y, 0.f)); }
		else if (WaterIgnoreTime <= 0.f)
		{
			if (Z > Collision->GetScaledSphereRadius() + 50.f)
			{
				Collision->IgnoreComponentWhenMoving(WaterComponent, false);
				CameraBoom->bDoCollisionTest = true;
			}
			else { WaterIgnoreTime = 0.05f; } // still overlapping the surface; check again shortly
		}
	}

	SetActorRotation(FRotator(FlightPitch, FlightYaw, Bank + RollOffset));
}

void ADragonFlightPawn::UpdateAnimation(float Dt)
{
	AnimTime += Dt;
	if (bRigged) { return; } // the rigged dragon is animated by UDragonAnimInstance
	const bool bDiving = FlightPitch < -18.f && ThrottleInput <= 0.f && !bBoosting;
	float Rate = 0.85f, Intensity = 0.8f;
	if (ThrottleInput > 0.1f) { Rate = 1.25f; Intensity = 1.0f; }
	if (FlightPitch > 15.f) { Rate = 1.35f; Intensity = 1.1f; }
	if (bBoosting) { Rate = 1.9f; Intensity = 1.15f; }
	if (bDiving) { Intensity = 0.08f; }
	if (WingBeatTimer > 0.f) { Rate = 2.3f; }
	// Tucked dive / underwater: wings stop beating (a slow swim stroke under water).
	Intensity = FMath::Lerp(Intensity, 0.f, DiveAmount);
	if (UnderwaterAmount > 0.01f) { Rate = FMath::Lerp(Rate, 0.7f, UnderwaterAmount); Intensity = FMath::Lerp(Intensity, 0.35f, UnderwaterAmount); }

	FlapIntensity = FMath::FInterpTo(FlapIntensity, Intensity, Dt, WingBeatTimer > 0.f ? 1.0f : 2.5f);
	FlapPhase = FMath::Fmod(FlapPhase + 2.f * PI * Rate * Dt, 2.f * PI);

	const float Flap = FMath::Sin(FlapPhase);
	const float Sweep = FMath::Lerp(0.f, 38.f, Smooth01((Speed - FastSpeed) / (BoostSpeed - FastSpeed)) + (bDiving ? 0.7f : 0.f));
	float ShoulderSweep = FMath::Min(Sweep, 45.f), TipSweep = Sweep * 0.4f;
	float Shoulder = 6.f + Flap * 40.f * FlapIntensity;
	float Wrist = (bDiving ? -10.f : 4.f) + FMath::Sin(FlapPhase - 1.0f) * 30.f * FlapIntensity;

	// Fully tucked pose: arms swept hard back along the body, finger folded back, wings held flat and tight.
	const float Tuck = FMath::Max(DiveAmount, UnderwaterAmount * 0.75f);
	ShoulderSweep = FMath::Lerp(ShoulderSweep, 66.f, Tuck);
	TipSweep = FMath::Lerp(TipSweep, 30.f, Tuck);
	Shoulder = FMath::Lerp(Shoulder, 3.f + Flap * 40.f * FlapIntensity * 0.3f, Tuck);
	Wrist = FMath::Lerp(Wrist, -6.f, Tuck);
	// Burst: wings flung wide and high.
	Shoulder += BurstAmount * 22.f;
	ShoulderSweep *= 1.f - BurstAmount * 0.8f;

	RightWingPivot->SetRelativeRotation(FRotator(0.f, ShoulderSweep, Shoulder));
	LeftWingPivot->SetRelativeRotation(FRotator(0.f, -ShoulderSweep, -Shoulder));
	RightWingTipPivot->SetRelativeRotation(FRotator(0.f, TipSweep, Wrist));
	LeftWingTipPivot->SetRelativeRotation(FRotator(0.f, -TipSweep, -Wrist));

	// Body rises on the downstroke, settles on the upstroke.
	BodyRoot->SetRelativeLocation(FVector(0.f, 0.f, -FMath::Cos(FlapPhase) * 22.f * FlapIntensity));
	BodyRoot->SetRelativeRotation(FRotator(FMath::Cos(FlapPhase) * 2.f * FlapIntensity, 0.f, 0.f));

	// Head looks into turns (stretched forward in a dive); tail counter-swings with a travelling wave, straightens in a dive.
	const float TailCalm = 1.f - 0.75f * DiveAmount;
	NeckPivot->SetRelativeRotation(FRotator(FMath::Sin(AnimTime * 0.9f) * 3.f * TailCalm - FlightPitch * 0.08f - DiveAmount * 12.f,
		FMath::Clamp(YawRate * 0.12f, -18.f, 18.f), 0.f));
	for (int32 i = 0; i < TailSegments.Num(); ++i)
	{
		const float Wave = FMath::Sin(AnimTime * (1.6f + UnderwaterAmount * 2.f) - i * 0.6f);
		const float YawAmt = Wave * (3.f + i * 1.2f) * (TailCalm + UnderwaterAmount * 1.5f) - FMath::Clamp(YawRate * 0.05f, -8.f, 8.f);
		const float PitchAmt = FMath::Sin(AnimTime * 1.1f - i * 0.5f) * 2.5f * TailCalm + FlightPitch * 0.04f * TailCalm;
		TailSegments[i]->SetRelativeRotation(FRotator(PitchAmt, YawAmt, 0.f));
	}
}

void ADragonFlightPawn::UpdateCamera(float Dt)
{
	const float Speed01 = Smooth01((Speed - SlowSpeed) / (BoostSpeed - SlowSpeed));
	const float Over01 = Smooth01((Speed - BoostSpeed) / (PowerDiveMaxSpeed - BoostSpeed)); // beyond boost speed
	const float FOVTarget = FMath::Lerp(BaseFOV, MaxFOV, FMath::Pow(Speed01, 1.3f))
		+ PowerDiveFOVExtra * DiveAmount * (0.35f + 0.65f * Over01) + BurstAmount * 10.f - UnderwaterAmount * 8.f;
	Camera->SetFieldOfView(FMath::FInterpTo(Camera->FieldOfView, FOVTarget, Dt, 2.5f + BurstAmount * 3.f));
	const float ArmTarget = (BaseArmLength + SpeedArmExtra * Speed01)
		* FMath::Lerp(1.f, PowerDiveArmScale, DiveAmount) * FMath::Lerp(1.f, 0.6f, UnderwaterAmount) + BurstAmount * 900.f;
	// Burst: swing the camera back fast so the exit splash and the launching dragon share the frame.
	CameraBoom->TargetArmLength = FMath::FInterpTo(CameraBoom->TargetArmLength, ArmTarget, Dt, 2.f + 6.f * BurstAmount);
	CameraBoom->SocketOffset.Z = FMath::Lerp(560.f, 160.f, UnderwaterAmount);
	const bool bOrbit = CameraBoom->IsUsingAbsoluteRotation(); // review beauty orbit: frame the whole dragon
	if (bOrbit) { CameraBoom->SocketOffset.Z = 0.f; CameraBoom->TargetArmLength = BaseArmLength + 600.f; }
	CamLagHoldTime = FMath::Max(0.f, CamLagHoldTime - Dt);
	CameraBoom->CameraLagSpeed = CamLagHoldTime > 0.f ? CamLagHoldSpeed : 9.f;
	CameraBoom->CameraLagMaxDistance = CamLagHoldTime > 0.f ? CamLagHoldMaxDistance : 900.f;

	ShakeTime = FMath::Max(0.f, ShakeTime - Dt);
	const float Amp = Speed01 * Speed01 * 5.f + ShakeTime * 45.f + DiveAmount * (3.f + 16.f * Over01) + BurstAmount * 10.f;
	const float T = AnimTime;
	Camera->SetRelativeLocation(FVector(0.f, (FMath::Sin(T * 31.f) + 0.5f * FMath::Sin(T * 17.3f)) * Amp, FMath::Cos(T * 27.f) * Amp));
	Camera->SetRelativeRotation(FRotator(bOrbit ? 0.f : -9.f, 0.f, Bank * 0.12f)); // look down onto the dragon's back

	UpdateUnderwaterView(Dt);
}

void ADragonFlightPawn::UpdateUnderwaterView(float Dt)
{
	// Murky blue-green look whenever the camera itself is below the surface.
	const float Target = Camera->GetComponentLocation().Z < -10.f ? 1.f : 0.f;
	UnderwaterView = FMath::FInterpConstantTo(UnderwaterView, Target, Dt, 6.f);
	const float U = UnderwaterView;
	const bool bOn = U > 0.001f;

	FPostProcessSettings& PP = Camera->PostProcessSettings;
	PP.bOverride_SceneColorTint = bOn;
	PP.SceneColorTint = FMath::Lerp(FLinearColor::White, FLinearColor(0.32f, 0.78f, 0.80f), U);
	PP.bOverride_ColorSaturation = bOn;
	PP.ColorSaturation = FVector4(FMath::Lerp(1.f, 0.55f, U), FMath::Lerp(1.f, 0.55f, U), FMath::Lerp(1.f, 0.55f, U), 1.f);
	PP.bOverride_ColorContrast = bOn;
	PP.ColorContrast = FVector4(FMath::Lerp(1.f, 0.8f, U), FMath::Lerp(1.f, 0.8f, U), FMath::Lerp(1.f, 0.8f, U), 1.f);
	PP.bOverride_AutoExposureBias = bOn;
	PP.AutoExposureBias = FMath::Lerp(0.4f, -0.4f, U);
	PP.VignetteIntensity = FMath::Lerp(0.45f, 1.2f, U);
	PP.bOverride_BloomIntensity = bOn;
	PP.BloomIntensity = FMath::Lerp(0.9f, 2.2f, U);
	PP.bOverride_SceneFringeIntensity = bOn;
	PP.SceneFringeIntensity = FMath::Lerp(0.6f, 3.5f, U);
	PP.bOverride_DepthOfFieldFocalDistance = bOn;
	PP.DepthOfFieldFocalDistance = 700.f;
	PP.bOverride_DepthOfFieldFstop = bOn;
	PP.DepthOfFieldFstop = 1.2f;

	// Short visibility: thicken the level's height fog into murky water while the camera is submerged.
	if (!WorldFog) { return; }
	if (bOn && !bFogSaved)
	{
		SavedFogDensity = WorldFog->FogDensity;
		SavedFogFalloff = WorldFog->FogHeightFalloff;
		SavedFogColor = WorldFog->FogInscatteringLuminance;
		SavedFogDirColor = WorldFog->DirectionalInscatteringLuminance;
		SavedFogStart = WorldFog->StartDistance;
		SavedFogMaxOpacity = WorldFog->FogMaxOpacity;
		bSavedVolumetricFog = WorldFog->bEnableVolumetricFog;
		bFogSaved = true;
		WorldFog->SetVolumetricFog(false);
	}
	if (!bFogSaved) { return; }
	if (!bOn)
	{
		WorldFog->SetFogDensity(SavedFogDensity);
		WorldFog->SetFogHeightFalloff(SavedFogFalloff);
		WorldFog->SetFogInscatteringColor(SavedFogColor);
		WorldFog->SetDirectionalInscatteringColor(SavedFogDirColor);
		WorldFog->SetStartDistance(SavedFogStart);
		WorldFog->SetFogMaxOpacity(SavedFogMaxOpacity);
		WorldFog->SetVolumetricFog(bSavedVolumetricFog);
		bFogSaved = false;
		return;
	}
	WorldFog->SetFogDensity(FMath::Lerp(SavedFogDensity, 1.3f, U));
	WorldFog->SetFogHeightFalloff(FMath::Lerp(SavedFogFalloff, 0.001f, U));
	WorldFog->SetFogInscatteringColor(FMath::Lerp(SavedFogColor, FLinearColor(0.02f, 0.09f, 0.1f), U));
	WorldFog->SetDirectionalInscatteringColor(FMath::Lerp(SavedFogDirColor, FLinearColor(0.02f, 0.08f, 0.07f), U));
	WorldFog->SetStartDistance(FMath::Lerp(SavedFogStart, 0.f, U));
	WorldFog->SetFogMaxOpacity(FMath::Lerp(SavedFogMaxOpacity, 1.f, U));
}
