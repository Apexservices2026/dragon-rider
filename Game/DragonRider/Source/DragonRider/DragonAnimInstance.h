#pragma once

#include "CoreMinimal.h"
#include "Animation/AnimInstance.h"
#include "Animation/AnimInstanceProxy.h"
#include "DragonAnimInstance.generated.h"

class UAnimSequence;
class ADragonFlightPawn;

/** The poses the dragon blends between (one per FBX take from tools/blender/dragon). */
enum class EDragonPose : uint8 { Glide, Flap, DiveTuck, WingBeat, Hover, Count };

/** Worker-thread side: samples each weighted sequence and blends them, then turns the neck into turns. */
struct FDragonAnimProxy : public FAnimInstanceProxy
{
	FDragonAnimProxy() = default;
	explicit FDragonAnimProxy(UAnimInstance* Instance) : FAnimInstanceProxy(Instance) {}

	virtual void PreUpdate(UAnimInstance* InAnimInstance, float DeltaSeconds) override;
	virtual bool Evaluate(FPoseContext& Output) override;

	const UAnimSequence* Seq[(int32)EDragonPose::Count] = {};
	float Time[(int32)EDragonPose::Count] = {};
	float Weight[(int32)EDragonPose::Count] = {};
	TArray<FName> NeckBones;
	FRotator NeckOffset = FRotator::ZeroRotator; // spread across NeckBones
};

/**
 * Native anim instance for the rigged dragon: no Anim Blueprint needed.
 * Reads the pawn's state values each frame (speed, dive, underwater, burst, throttle, climb, boost, wing beats)
 * and turns them into smoothed blend weights: Glide when cruising, Flap with effort (rate scales with effort),
 * DiveTuck by dive/underwater amount, WingBeatStrong one-shot on each wing beat and water burst, Hover when slow.
 */
UCLASS(Transient)
class DRAGONRIDER_API UDragonAnimInstance : public UAnimInstance
{
	GENERATED_BODY()

public:
	UPROPERTY(Transient) TObjectPtr<UAnimSequence> GlideSeq;
	UPROPERTY(Transient) TObjectPtr<UAnimSequence> FlapSeq;
	UPROPERTY(Transient) TObjectPtr<UAnimSequence> DiveSeq;
	UPROPERTY(Transient) TObjectPtr<UAnimSequence> WingBeatSeq;
	UPROPERTY(Transient) TObjectPtr<UAnimSequence> HoverSeq;

	/** Current blend weights (0..1), for debugging / HUD. */
	float Weights[(int32)EDragonPose::Count] = {};
	float Times[(int32)EDragonPose::Count] = {};
	FRotator NeckOffset = FRotator::ZeroRotator;
	TArray<FName> NeckBones;

protected:
	virtual void NativeInitializeAnimation() override;
	virtual void NativeUpdateAnimation(float DeltaSeconds) override;
	virtual FAnimInstanceProxy* CreateAnimInstanceProxy() override { return new FDragonAnimProxy(this); }
	virtual void DestroyAnimInstanceProxy(FAnimInstanceProxy* InProxy) override { delete InProxy; }

private:
	float FlapW = 0.f, HoverW = 0.f, DiveW = 0.f, BeatW = 0.f;
	float BeatTime = 10.f;
	int32 LastBeatCount = 0;
};
