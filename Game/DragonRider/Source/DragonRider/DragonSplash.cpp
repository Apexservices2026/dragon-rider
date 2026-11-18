#include "DragonSplash.h"

#include "Components/StaticMeshComponent.h"
#include "Engine/StaticMesh.h"
#include "Engine/World.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "UObject/ConstructorHelpers.h"

namespace
{
	constexpr int32 NumCrown = 30;
	constexpr int32 NumSpray = 44;
	constexpr int32 NumRing = 26;
	constexpr int32 NumColumn = 3;
	constexpr float SplashGravity = 1650.f;

	float Smooth01S(float X) { X = FMath::Clamp(X, 0.f, 1.f); return X * X * (3.f - 2.f * X); }
}

ADragonSplash::ADragonSplash()
{
	PrimaryActorTick.bCanEverTick = true;
	SetRootComponent(CreateDefaultSubobject<USceneComponent>(TEXT("Root")));

	static ConstructorHelpers::FObjectFinder<UStaticMesh> SphereF(TEXT("/Engine/BasicShapes/Sphere.Sphere"));
	static ConstructorHelpers::FObjectFinder<UMaterialInterface> MatF(TEXT("/Engine/BasicShapes/BasicShapeMaterial.BasicShapeMaterial"));
	BaseMaterial = MatF.Object;

	UStaticMesh* SphereMesh = SphereF.Object;
	auto Make = [this, SphereMesh](const FString& Name)
	{
		UStaticMeshComponent* C = CreateDefaultSubobject<UStaticMeshComponent>(*Name);
		C->SetupAttachment(GetRootComponent());
		C->SetStaticMesh(SphereMesh);
		C->SetCollisionEnabled(ECollisionEnabled::NoCollision);
		C->SetGenerateOverlapEvents(false);
		C->CastShadow = false;
		C->SetUsingAbsoluteLocation(false);
		C->SetVisibility(false);
		return C;
	};
	for (int32 i = 0; i < NumCrown + NumSpray; ++i) { DropParts.Add(Make(FString::Printf(TEXT("Drop%d"), i))); }
	for (int32 i = 0; i < NumRing; ++i) { RingParts.Add(Make(FString::Printf(TEXT("Ring%d"), i))); }
	for (int32 i = 0; i < NumColumn; ++i) { ColumnParts.Add(Make(FString::Printf(TEXT("Column%d"), i))); }
	FoamDisk = Make(TEXT("Foam"));
}

ADragonSplash* ADragonSplash::Spawn(UWorld* World, const FVector& Location, float InStrength, bool bExit, const FVector& Travel)
{
	if (!World) { return nullptr; }
	FActorSpawnParameters P;
	P.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
	ADragonSplash* S = World->SpawnActor<ADragonSplash>(ADragonSplash::StaticClass(), FVector(Location.X, Location.Y, 0.f), FRotator::ZeroRotator, P);
	if (S) { S->Init(InStrength, bExit, Travel); }
	return S;
}

void ADragonSplash::Init(float InStrength, bool bExit, const FVector& Travel)
{
	Strength = FMath::Clamp(InStrength, 0.4f, 1.8f);
	bIsExit = bExit;
	Life = 1.5f + 0.25f * Strength;
	RingRadiusMax = 900.f + 650.f * Strength;

	if (BaseMaterial)
	{
		UMaterialInstanceDynamic* Foam = UMaterialInstanceDynamic::Create(BaseMaterial, this);
		Foam->SetVectorParameterValue(TEXT("Color"), FLinearColor(0.86f, 0.93f, 0.96f));
		UMaterialInstanceDynamic* Spray = UMaterialInstanceDynamic::Create(BaseMaterial, this);
		Spray->SetVectorParameterValue(TEXT("Color"), FLinearColor(0.95f, 0.98f, 1.0f));
		UMaterialInstanceDynamic* Green = UMaterialInstanceDynamic::Create(BaseMaterial, this);
		Green->SetVectorParameterValue(TEXT("Color"), FLinearColor(0.55f, 0.75f, 0.74f));
		for (int32 i = 0; i < DropParts.Num(); ++i) { DropParts[i]->SetMaterial(0, i < NumCrown ? Foam : Spray); }
		for (UStaticMeshComponent* C : RingParts) { C->SetMaterial(0, Foam); }
		for (int32 i = 0; i < ColumnParts.Num(); ++i) { ColumnParts[i]->SetMaterial(0, i == 0 ? Green : Foam); }
		FoamDisk->SetMaterial(0, Foam);
	}

	const FVector Flat = FVector(Travel.X, Travel.Y, 0.f).GetSafeNormal();
	const float S = Strength;
	Drops.SetNum(DropParts.Num());
	for (int32 i = 0; i < Drops.Num(); ++i)
	{
		FDrop& D = Drops[i];
		const bool bCrown = i < NumCrown;
		const float Ang = (bCrown ? (2.f * PI * i / NumCrown) : FMath::FRandRange(0.f, 2.f * PI)) + FMath::FRandRange(-0.15f, 0.15f);
		const FVector Out(FMath::Cos(Ang), FMath::Sin(Ang), 0.f);
		float H, V;
		if (bCrown)
		{
			H = bExit ? FMath::FRandRange(250.f, 650.f) : FMath::FRandRange(650.f, 1150.f);
			V = bExit ? FMath::FRandRange(1900.f, 2800.f) : FMath::FRandRange(1100.f, 1750.f);
			D.Size = FMath::FRandRange(0.5f, 0.95f);
		}
		else
		{
			H = FMath::FRandRange(900.f, 1900.f);
			V = FMath::FRandRange(700.f, 1700.f) * (bExit ? 1.4f : 1.f);
			D.Size = FMath::FRandRange(0.18f, 0.36f);
		}
		D.Pos = Out * (bCrown ? 220.f : 120.f) * S;
		D.Vel = (Out * H + Flat * 500.f) * FMath::Sqrt(S) + FVector(0.f, 0.f, V * FMath::Sqrt(S));
		D.Delay = bCrown ? FMath::FRandRange(0.f, 0.06f) : FMath::FRandRange(0.f, 0.12f);
		D.Size *= FMath::Sqrt(S);
	}
	FoamDisk->SetVisibility(true);
	for (UStaticMeshComponent* C : RingParts) { C->SetVisibility(true); }
	for (UStaticMeshComponent* C : ColumnParts) { C->SetVisibility(true); }
	Tick(0.f);
}

void ADragonSplash::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);
	Age += DeltaSeconds;
	const float T = Age / Life;
	if (T >= 1.f) { Destroy(); return; }
	const float S = Strength;
	const float Fade = 1.f - Smooth01S((T - 0.45f) / 0.55f);

	// Droplets: ballistic, stretched along their velocity, shrink as they fall back.
	for (int32 i = 0; i < Drops.Num(); ++i)
	{
		FDrop& D = Drops[i];
		UStaticMeshComponent* C = DropParts[i];
		if (Age < D.Delay) { C->SetVisibility(false); continue; }
		D.Vel.Z -= SplashGravity * DeltaSeconds;
		D.Vel *= FMath::Exp(-0.35f * DeltaSeconds); // air drag
		D.Pos += D.Vel * DeltaSeconds;
		const bool bAlive = D.Pos.Z > -40.f || D.Vel.Z > 0.f;
		C->SetVisibility(bAlive);
		if (!bAlive) { continue; }
		const float Sz = D.Size * FMath::Max(0.15f, Fade);
		const float Stretch = 1.f + FMath::Min(D.Vel.Size() / 1000.f, 1.6f);
		C->SetRelativeLocation(D.Pos);
		C->SetRelativeRotation(D.Vel.Rotation());
		C->SetRelativeScale3D(FVector(Sz * Stretch, Sz, Sz));
	}

	// Central column: shoots up then collapses back into the sea.
	const float ColT = FMath::Clamp(Age / (bIsExit ? 1.1f : 0.95f), 0.f, 1.f);
	const float Height = (bIsExit ? 2300.f : 1000.f) * S * FMath::Sin(PI * ColT) * (1.f - 0.25f * ColT);
	for (int32 i = 0; i < ColumnParts.Num(); ++i)
	{
		const float Frac = 1.f - 0.27f * i;
		const float W = (bIsExit ? 1.5f : 1.8f) * (1.f - 0.25f * i) * S * (0.6f + 0.4f * (1.f - ColT));
		const float Hh = FMath::Max(Height * Frac, 1.f);
		// Exit: no solid column (it would hide the dragon); the near-vertical crown reads as water streaming off it.
		ColumnParts[i]->SetVisibility(!bIsExit && Hh > 30.f);
		ColumnParts[i]->SetRelativeLocation(FVector(0.f, 0.f, Hh * 0.45f));
		ColumnParts[i]->SetRelativeScale3D(FVector(W, W, Hh / 100.f));
	}

	// Foam ring spreading across the surface, plus a churned foam disk in the middle.
	const float R = RingRadiusMax * (1.f - FMath::Exp(-2.6f * Age)) + 200.f * S;
	const float RingFade = 1.f - Smooth01S((T - 0.35f) / 0.65f);
	for (int32 i = 0; i < RingParts.Num(); ++i)
	{
		const float Ang = 2.f * PI * i / RingParts.Num();
		const float Wobble = 1.f + 0.06f * FMath::Sin(i * 2.7f + Age * 3.f);
		UStaticMeshComponent* C = RingParts[i];
		C->SetRelativeLocation(FVector(FMath::Cos(Ang) * R * Wobble, FMath::Sin(Ang) * R * Wobble, 8.f));
		C->SetRelativeRotation(FRotator(0.f, FMath::RadiansToDegrees(Ang) + 90.f, 0.f));
		const float L = (2.f * PI * R / RingParts.Num()) / 100.f * 1.25f;
		C->SetRelativeScale3D(FVector(L, 1.1f * S, 0.35f * S) * FMath::Max(RingFade, 0.05f));
	}
	const float Disk = (220.f + 420.f * Smooth01S(T * 2.f)) * S / 50.f;
	FoamDisk->SetRelativeLocation(FVector(0.f, 0.f, 5.f));
	FoamDisk->SetRelativeScale3D(FVector(Disk, Disk, 0.08f * S) * FMath::Max(RingFade, 0.05f));
}
