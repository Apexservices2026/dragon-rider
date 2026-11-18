#pragma once

#include "CoreMinimal.h"
#include "GameFramework/GameModeBase.h"
#include "GameFramework/HUD.h"
#include "DragonRiderGameMode.generated.h"

UCLASS()
class DRAGONRIDER_API ADragonRiderGameMode : public AGameModeBase
{
	GENERATED_BODY()
public:
	ADragonRiderGameMode();
};

/** Minimal flight HUD: title card on start, speed/altitude readout, stamina bar, control hints. */
UCLASS()
class DRAGONRIDER_API ADragonHUD : public AHUD
{
	GENERATED_BODY()
public:
	virtual void DrawHUD() override;
	virtual void BeginPlay() override;
private:
	float StartTime = 0.f;
};
