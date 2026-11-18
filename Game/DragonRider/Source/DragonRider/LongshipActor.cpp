#include "LongshipActor.h"

#include "Components/StaticMeshComponent.h"
#include "Engine/StaticMesh.h"
#include "Engine/World.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "UObject/ConstructorHelpers.h"
#include "EngineUtils.h"
#include "Engine/StaticMeshActor.h"

namespace
{
	constexpr int32 NumWake = 24;
	constexpr float WakeLife = 8.f;
	constexpr float WakeInterval = 0.7f; // one V pair per interval

	// Oar ports from Saved/Generated/World/props_manifest.json (metres, Blender axes: port = +Y).
	// Unreal's FBX import mirrors Y, so port oars sit at -Y here and their blades already point along -Y.
	const float OarX[16] = { -6.613f, -5.731f, -4.848f, -3.966f, -3.084f, -2.203f, -1.321f, -0.44f, 0.44f, 1.321f, 2.203f, 3.084f, 3.966f, 4.848f, 5.731f, 6.613f };
	const float OarY[16] = { 1.718f, 1.947f, 2.133f, 2.28f, 2.39f, 2.468f, 2.514f, 2.534f, 2.534f, 2.514f, 2.468f, 2.39f, 2.28f, 2.133f, 1.947f, 1.718f };
	const float OarZ[16] = { 1.168f, 0.996f, 0.879f, 0.806f, 0.764f, 0.744f, 0.736f, 0.735f, 0.735f, 0.736f, 0.744f, 0.764f, 0.806f, 0.879f, 0.996f, 1.168f };
	const FVector SailPivotCm(65.f, 0.f, 1050.f);

	UStaticMeshComponent* MakePart(AActor* Owner, const FName Name, USceneComponent* Parent)
	{
		UStaticMeshComponent* C = Owner->CreateDefaultSubobject<UStaticMeshComponent>(Name);
		C->SetupAttachment(Parent);
		C->SetCollisionEnabled(ECollisionEnabled::NoCollision);
		C->SetGenerateOverlapEvents(false);
		return C;
	}
}

ALongshipActor::ALongshipActor()
{
	PrimaryActorTick.bCanEverTick = true;
	Root = CreateDefaultSubobject<USceneComponent>(TEXT("Root"));
	SetRootComponent(Root);
	Deck = CreateDefaultSubobject<USceneComponent>(TEXT("Deck"));
	Deck->SetupAttachment(Root);

	static ConstructorHelpers::FObjectFinder<UStaticMesh> HullAF(TEXT("/Game/DragonRider/World/Meshes/SM_Longship_ClanA.SM_Longship_ClanA"));
	static ConstructorHelpers::FObjectFinder<UStaticMesh> HullBF(TEXT("/Game/DragonRider/World/Meshes/SM_Longship_ClanB.SM_Longship_ClanB"));
	static ConstructorHelpers::FObjectFinder<UStaticMesh> SailAF(TEXT("/Game/DragonRider/World/Meshes/SM_LongshipSail_ClanA.SM_LongshipSail_ClanA"));
	static ConstructorHelpers::FObjectFinder<UStaticMesh> SailBF(TEXT("/Game/DragonRider/World/Meshes/SM_LongshipSail_ClanB.SM_LongshipSail_ClanB"));
	static ConstructorHelpers::FObjectFinder<UStaticMesh> OarF(TEXT("/Game/DragonRider/World/Meshes/SM_LongshipOar.SM_LongshipOar"));
	static ConstructorHelpers::FObjectFinder<UStaticMesh> SphereF(TEXT("/Engine/BasicShapes/Sphere.Sphere"));
	static ConstructorHelpers::FObjectFinder<UMaterialInterface> MatF(TEXT("/Engine/BasicShapes/BasicShapeMaterial.BasicShapeMaterial"));
	HullA = HullAF.Object; HullB = HullBF.Object; SailA = SailAF.Object; SailB = SailBF.Object;
	FoamBase = MatF.Object;

	Hull = MakePart(this, TEXT("Hull"), Deck);
	Hull->SetStaticMesh(HullA);
	Sail = MakePart(this, TEXT("Sail"), Deck);
	Sail->SetStaticMesh(SailA);
	Sail->SetRelativeLocation(SailPivotCm);
	Sail->CastShadow = true;

	for (int32 Side = 0; Side < 2; ++Side) // 0 = port (-Y), 1 = starboard (+Y)
	{
		for (int32 i = 0; i < 16; ++i)
		{
			UStaticMeshComponent* Oar = MakePart(this, *FString::Printf(TEXT("Oar_%s_%02d"), Side ? TEXT("Starboard") : TEXT("Port"), i), Deck);
			Oar->SetStaticMesh(OarF.Object);
			Oar->SetRelativeLocation(FVector(OarX[i], Side ? OarY[i] : -OarY[i], OarZ[i]) * 100.f);
			Oars.Add(Oar);
			OarBase.Add(Side ? FQuat(FVector::ZAxisVector, PI) : FQuat::Identity);
			OarSide.Add(Side ? -1.f : 1.f);
		}
	}

	UStaticMesh* SphereMesh = SphereF.Object;
	auto MakeFoam = [this, SphereMesh](const FName Name)
	{
		UStaticMeshComponent* C = MakePart(this, Name, Root);
		C->SetStaticMesh(SphereMesh);
		C->CastShadow = false;
		return C;
	};
	for (int32 i = 0; i < NumWake; ++i)
	{
		UStaticMeshComponent* C = MakeFoam(*FString::Printf(TEXT("Wake%02d"), i));
		C->SetUsingAbsoluteLocation(true);
		C->SetUsingAbsoluteRotation(true);
		C->SetUsingAbsoluteScale(true);
		C->SetVisibility(false);
		WakeParts.Add(C);
	}
	for (int32 s = -1; s <= 1; s += 2)
	{
		UStaticMeshComponent* C = MakeFoam(*FString::Printf(TEXT("BowWave%s"), s < 0 ? TEXT("L") : TEXT("R")));
		C->SetRelativeLocation(FVector(980.f, 130.f * s, 3.f));
		C->SetRelativeRotation(FRotator(0.f, -22.f * s, 0.f));
		BowWave.Add(C);
	}
}

void ALongshipActor::OnConstruction(const FTransform& Transform)
{
	Super::OnConstruction(Transform);
	ApplyClan();
	UpdateOars(0.f);
}

void ALongshipActor::ApplyClan()
{
	Hull->SetStaticMesh(bClanB && HullB ? HullB : HullA);
	Sail->SetStaticMesh(bClanB && SailB ? SailB : SailA);
	const bool bMoving = SailSpeed > 1.f;
	for (UStaticMeshComponent* C : BowWave) { C->SetVisibility(bMoving && bWake); }
}

void ALongshipActor::BeginPlay()
{
	Super::BeginPlay();
	StartLocation = GetActorLocation();
	ApplyClan();
	UE_LOG(LogTemp, Verbose, TEXT("LONGSHIP %s clanB=%d hull=%s sail=%s speed=%.0f"), *GetName(), bClanB ? 1 : 0,
		*GetNameSafe(Hull->GetStaticMesh()), *GetNameSafe(Sail->GetStaticMesh()), SailSpeed);
	Phase = FMath::FRandRange(0.f, 2.f * PI);
	Wake.SetNum(NumWake);
	if (FoamBase)
	{
		UMaterialInstanceDynamic* Foam = UMaterialInstanceDynamic::Create(FoamBase, this);
		Foam->SetVectorParameterValue(TEXT("Color"), FLinearColor(0.3f, 0.36f, 0.38f)); // lit by a low sun, white reads as glowing; keep it grey-green
		for (UStaticMeshComponent* C : WakeParts) { C->SetMaterial(0, Foam); }
		for (UStaticMeshComponent* C : BowWave) { C->SetMaterial(0, Foam); }
	}
	// Find the sea plane so the land check ignores it (same rule as the dragon: huge BasicShapes Plane at Z=0).
	for (TActorIterator<AStaticMeshActor> It(GetWorld()); It; ++It)
	{
		UStaticMeshComponent* SM = It->GetStaticMeshComponent();
		if (SM && SM->GetStaticMesh() && SM->GetStaticMesh()->GetName() == TEXT("Plane") && FMath::Abs(It->GetActorLocation().Z) < 50.f)
		{
			WaterComponent = SM;
			break;
		}
	}
}

bool ALongshipActor::LandAhead() const
{
	const FVector Ahead = GetActorLocation() + GetActorForwardVector() * LandCheckAhead;
	FCollisionQueryParams Params(SCENE_QUERY_STAT(LongshipLand), true, this);
	if (WaterComponent) { Params.AddIgnoredComponent(WaterComponent.Get()); }
	FHitResult Hit;
	const bool bHit = GetWorld()->LineTraceSingleByChannel(Hit, Ahead + FVector(0, 0, 50000.f), Ahead - FVector(0, 0, 3000.f), ECC_Visibility, Params);
	return bHit && Hit.ImpactPoint.Z > -900.f; // shallower than 9 m: we're about to run aground
}

void ALongshipActor::UpdateOars(float T)
{
	const bool bMoving = SailSpeed > 1.f;
	const float P = 2.f * PI * T / FMath::Max(StrokePeriod, 0.5f) + Phase;
	// Power stroke (blade deep, bow -> stern) for the first half of the cycle, raised recovery for the second.
	const float Sweep = bMoving ? 25.f * FMath::Cos(P) : 0.f;
	const float Dip = bMoving ? FMath::Lerp(2.f, 12.f, FMath::SmoothStep(-0.25f, 0.25f, FMath::Sin(P))) : -8.f; // moored: oars shipped up
	for (int32 i = 0; i < Oars.Num(); ++i)
	{
		const FQuat Sw(FVector::ZAxisVector, FMath::DegreesToRadians(Sweep * OarSide[i]));
		const FQuat Lift(FVector::XAxisVector, FMath::DegreesToRadians(Dip));
		Oars[i]->SetRelativeRotation(OarBase[i] * Lift * Sw);
	}
}

void ALongshipActor::UpdateWake(float Dt)
{
	if (!bWake || SailSpeed <= 1.f) { return; }
	WakeTimer -= Dt;
	if (WakeTimer <= 0.f)
	{
		WakeTimer = WakeInterval;
		// Kelvin-style V: a pair of foam streaks off the stern quarters that drift apart as they age.
		for (int32 S = -1; S <= 1; S += 2)
		{
			FWakeBlob& B = Wake[NextWake];
			B.Pos = GetActorTransform().TransformPosition(FVector(-950.f, 140.f * S, 0.f));
			B.Pos.Z = 3.f;
			B.Yaw = GetActorRotation().Yaw;
			B.Side = static_cast<float>(S);
			B.Age = 0.f;
			NextWake = (NextWake + 1) % Wake.Num();
		}
	}
	for (int32 i = 0; i < Wake.Num(); ++i)
	{
		FWakeBlob& B = Wake[i];
		B.Age += Dt;
		UStaticMeshComponent* C = WakeParts[i];
		const float A = B.Age / WakeLife;
		if (A >= 1.f) { C->SetVisibility(false); continue; }
		C->SetVisibility(true);
		const float Grow = 1.f - FMath::Exp(-2.f * A * WakeLife / 3.f);
		const float Fade = 1.f - FMath::SmoothStep(0.4f, 1.f, A);
		const FRotator R(0.f, B.Yaw, 0.f);
		const FVector Out = R.RotateVector(FVector(0.f, B.Side, 0.f));
		C->SetWorldLocation(B.Pos + Out * (90.f * B.Age));
		C->SetWorldRotation(FRotator(0.f, B.Yaw - 18.f * B.Side, 0.f));
		// Sphere is 1 m across: a thin streak that lengthens, widens a little and thins out.
		C->SetWorldScale3D(FVector((4.f + 5.f * Grow) * FMath::Max(Fade, 0.2f), (0.9f + 1.6f * Grow) * Fade + 0.05f, 0.02f));
	}
	const float Pulse = 1.f + 0.12f * FMath::Sin(Time * 2.3f);
	for (UStaticMeshComponent* C : BowWave) { C->SetRelativeScale3D(FVector(3.6f * Pulse, 0.8f, 0.03f)); }
}

void ALongshipActor::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);
	const float Dt = FMath::Min(DeltaSeconds, 0.1f);
	Time += Dt;

	if (SailSpeed > 1.f)
	{
		AddActorWorldOffset(GetActorForwardVector() * SailSpeed * Dt);
		LandCheckTimer -= Dt;
		if (LandCheckTimer <= 0.f)
		{
			LandCheckTimer = 1.f;
			if (LandAhead())
			{
				// Loop back far out along the track; hide the old wake so it doesn't streak across the sea.
				SetActorLocation(bReturnToStart ? StartLocation : GetActorLocation() - GetActorForwardVector() * LoopDistance);
				for (FWakeBlob& B : Wake) { B.Age = WakeLife; }
			}
		}
	}

	// Swell: bob, roll and pitch on slow incommensurate sines; ships out of phase with each other.
	const float T = Time + Phase * 3.f;
	Deck->SetRelativeLocation(FVector(0.f, 0.f, BobHeight * FMath::Sin(T * 0.9f) + BobHeight * 0.4f * FMath::Sin(T * 2.1f)));
	Deck->SetRelativeRotation(FRotator(PitchDegrees * FMath::Sin(T * 0.7f + 1.f), 0.f, RollDegrees * FMath::Sin(T * 0.55f)));

	// Sail billows: the belly (+X) breathes, the cloth stretches slightly across.
	const float Billow = SailSpeed > 1.f ? 1.f : 0.5f;
	Sail->SetRelativeScale3D(FVector(1.f + Billow * (0.14f * FMath::Sin(T * 1.3f) + 0.06f * FMath::Sin(T * 3.1f)), 1.f + 0.015f * FMath::Sin(T * 1.3f), 1.f));

	UpdateOars(Time);
	UpdateWake(Dt);
}
