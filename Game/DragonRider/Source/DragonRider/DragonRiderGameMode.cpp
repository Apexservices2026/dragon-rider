#include "DragonRiderGameMode.h"

#include "DragonFlightPawn.h"
#include "Engine/Canvas.h"
#include "Engine/Engine.h"
#include "Engine/Font.h"
#include "GameFramework/PlayerController.h"

ADragonRiderGameMode::ADragonRiderGameMode()
{
	DefaultPawnClass = ADragonFlightPawn::StaticClass();
	HUDClass = ADragonHUD::StaticClass();
}

void ADragonHUD::BeginPlay()
{
	Super::BeginPlay();
	StartTime = GetWorld()->GetTimeSeconds();
}

void ADragonHUD::DrawHUD()
{
	Super::DrawHUD();
	if (!Canvas) { return; }
	const float W = Canvas->ClipX, H = Canvas->ClipY;
	const float Scale = H / 1080.f;
	const float T = GetWorld()->GetTimeSeconds() - StartTime;
	UFont* Big = GEngine->GetLargeFont();
	UFont* Small = GEngine->GetMediumFont();

	// Title card: fade in 0.5-2s, hold, fade out by 7s.
	const float TitleAlpha = FMath::Clamp((T - 0.5f) / 1.5f, 0.f, 1.f) * FMath::Clamp((7.f - T) / 1.5f, 0.f, 1.f);
	if (TitleAlpha > 0.f)
	{
		FCanvasTextItem Title(FVector2D(W * 0.5f, H * 0.3f), FText::FromString(TEXT("D R A G O N   R I D E R")), Big,
			FLinearColor(1.f, 0.93f, 0.82f, TitleAlpha));
		Title.Scale = FVector2D(3.2f * Scale);
		Title.bCentreX = true;
		Title.EnableShadow(FLinearColor(0, 0, 0, TitleAlpha * 0.7f));
		Canvas->DrawItem(Title);
		FCanvasTextItem Sub(FVector2D(W * 0.5f, H * 0.3f + 80.f * Scale), FText::FromString(TEXT("The fjords of the North await")), Small,
			FLinearColor(0.85f, 0.88f, 0.92f, TitleAlpha * 0.9f));
		Sub.Scale = FVector2D(1.6f * Scale);
		Sub.bCentreX = true;
		Sub.EnableShadow(FLinearColor(0, 0, 0, TitleAlpha * 0.6f));
		Canvas->DrawItem(Sub);
	}

	const APlayerController* PC = GetOwningPlayerController();
	const ADragonFlightPawn* Dragon = PC ? Cast<ADragonFlightPawn>(PC->GetPawn()) : nullptr;
	if (!Dragon) { return; }

	const FLinearColor Ink(0.92f, 0.94f, 0.96f, 0.85f);
	const float X = 48.f * Scale, Y = H - 150.f * Scale;
	FCanvasTextItem SpeedText(FVector2D(X, Y), FText::FromString(FString::Printf(TEXT("%3.0f km/h"), Dragon->GetSpeedKmh())), Big, Ink);
	SpeedText.Scale = FVector2D(1.6f * Scale);
	SpeedText.EnableShadow(FLinearColor(0, 0, 0, 0.6f));
	Canvas->DrawItem(SpeedText);
	FCanvasTextItem AltText(FVector2D(X, Y + 46.f * Scale), FText::FromString(FString::Printf(TEXT("ALT  %4.0f m"), Dragon->GetAltitudeMeters())), Small, Ink);
	AltText.Scale = FVector2D(1.2f * Scale);
	AltText.EnableShadow(FLinearColor(0, 0, 0, 0.6f));
	Canvas->DrawItem(AltText);

	// Stamina bar
	const float BarW = 260.f * Scale, BarH = 8.f * Scale, BarY = Y + 84.f * Scale;
	FCanvasTileItem Back(FVector2D(X, BarY), FVector2D(BarW, BarH), FLinearColor(0, 0, 0, 0.45f));
	Back.BlendMode = SE_BLEND_Translucent;
	Canvas->DrawItem(Back);
	const FLinearColor Fill = Dragon->IsBoosting() ? FLinearColor(1.f, 0.55f, 0.1f, 0.95f) : FLinearColor(0.85f, 0.32f, 0.08f, 0.85f);
	FCanvasTileItem Bar(FVector2D(X, BarY), FVector2D(BarW * Dragon->GetStamina01(), BarH), Fill);
	Bar.BlendMode = SE_BLEND_Translucent;
	Canvas->DrawItem(Bar);

	// Control hints for the first 25 seconds
	const float HintAlpha = FMath::Clamp((25.f - T) / 3.f, 0.f, 1.f) * FMath::Clamp((T - 6.f) / 1.f, 0.f, 1.f);
	if (HintAlpha > 0.f)
	{
		const TCHAR* Lines[] = {
			TEXT("MOUSE  steer"), TEXT("W / S  faster / slower"), TEXT("A / D  bank turn"),
			TEXT("SPACE  wing beat (climb)"), TEXT("SHIFT  boost"), TEXT("Q / E  barrel roll") };
		for (int32 i = 0; i < UE_ARRAY_COUNT(Lines); ++i)
		{
			FCanvasTextItem L(FVector2D(W - 360.f * Scale, H - (230.f - i * 32.f) * Scale), FText::FromString(Lines[i]), Small,
				FLinearColor(0.92f, 0.94f, 0.96f, 0.8f * HintAlpha));
			L.Scale = FVector2D(1.1f * Scale);
			L.EnableShadow(FLinearColor(0, 0, 0, 0.6f * HintAlpha));
			Canvas->DrawItem(L);
		}
	}
}
