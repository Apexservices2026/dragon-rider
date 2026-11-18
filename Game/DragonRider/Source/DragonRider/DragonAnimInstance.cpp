#include "DragonAnimInstance.h"

#include "DragonFlightPawn.h"
#include "Animation/AnimSequence.h"
#include "Animation/AnimationPoseData.h"
#include "AnimationRuntime.h"
#include "BonePose.h"

namespace
{
	float ExpA(float Rate, float Dt) { return 1.f - FMath::Exp(-Rate * Dt); }
	float Wrap(float T, const UAnimSequence* S) { const float L = S ? S->GetPlayLength() : 1.f; return L > 0.f ? FMath::Fmod(T, L) : 0.f; }
}

void UDragonAnimInstance::NativeInitializeAnimation()
{
	Super::NativeInitializeAnimation();
	Weights[(int32)EDragonPose::Glide] = 1.f;
}

void UDragonAnimInstance::NativeUpdateAnimation(float DeltaSeconds)
{
	Super::NativeUpdateAnimation(DeltaSeconds);
	const ADragonFlightPawn* P = Cast<ADragonFlightPawn>(TryGetPawnOwner());
	const float Dt = FMath::Min(DeltaSeconds, 0.1f);
	if (!P) { return; }

	// Effort -> flapping: throttle, boost, climbing and wing beats all push toward Flap (and a faster flap rate).
	const float Pitch = P->GetFlightPitch();
	float Effort = FMath::Max(P->GetThrottle(), 0.f) * 0.8f + (P->IsBoosting() ? 1.f : 0.f)
		+ FMath::SmoothStep(4.f, 22.f, Pitch) * 0.9f + (P->IsWingBeating() ? 0.6f : 0.f);
	Effort = FMath::Clamp(Effort, 0.f, 1.f);
	const float Speed = P->GetSpeedKmh();
	FlapW += (Effort - FlapW) * ExpA(3.f, Dt);
	HoverW += ((P->IsUnderwater() ? 0.f : 1.f - FMath::SmoothStep(62.f, 92.f, Speed)) - HoverW) * ExpA(2.5f, Dt);
	DiveW = FMath::Max(P->GetDiveAmount(), P->GetUnderwaterAmount() * 0.9f); // already smoothed by the pawn

	// WingBeatStrong: restart the one-shot on every new beat / burst, short fade in and out.
	if (P->GetWingBeatCount() != LastBeatCount) { LastBeatCount = P->GetWingBeatCount(); BeatTime = 0.f; }
	BeatTime += Dt;
	const float BeatLen = WingBeatSeq ? WingBeatSeq->GetPlayLength() : 1.33f;
	const float BeatTarget = BeatTime < BeatLen ? FMath::Min(1.f, BeatTime / 0.08f) * FMath::Clamp((BeatLen - BeatTime) / 0.3f, 0.f, 1.f) : 0.f;
	BeatW = BeatTarget * (1.f - DiveW);

	float W[(int32)EDragonPose::Count];
	W[(int32)EDragonPose::Glide] = 1.f - FlapW;
	W[(int32)EDragonPose::Flap] = FlapW;
	W[(int32)EDragonPose::Hover] = 0.f;
	for (float& X : W) { X *= 1.f - HoverW; }
	W[(int32)EDragonPose::Hover] = HoverW;
	for (float& X : W) { X *= 1.f - DiveW; }
	W[(int32)EDragonPose::DiveTuck] = DiveW;
	for (float& X : W) { X *= 1.f - BeatW; }
	W[(int32)EDragonPose::WingBeat] = BeatW;
	FMemory::Memcpy(Weights, W, sizeof(W));

	Times[(int32)EDragonPose::Glide] = Wrap(Times[(int32)EDragonPose::Glide] + Dt, GlideSeq);
	Times[(int32)EDragonPose::Flap] = Wrap(Times[(int32)EDragonPose::Flap] + Dt * FMath::Lerp(0.75f, 1.45f, Effort), FlapSeq);
	Times[(int32)EDragonPose::DiveTuck] = Wrap(Times[(int32)EDragonPose::DiveTuck] + Dt, DiveSeq);
	Times[(int32)EDragonPose::Hover] = Wrap(Times[(int32)EDragonPose::Hover] + Dt, HoverSeq);
	Times[(int32)EDragonPose::WingBeat] = FMath::Min(BeatTime, BeatLen);

	// Head looks into turns and along the flight path; stretched forward in a dive.
	const FRotator Target(FMath::Clamp(-Pitch * 0.08f - DiveW * 10.f, -14.f, 10.f), FMath::Clamp(P->GetYawRate() * 0.12f, -18.f, 18.f), 0.f);
	NeckOffset = FMath::RInterpTo(NeckOffset, Target, Dt, 4.f);
}

void FDragonAnimProxy::PreUpdate(UAnimInstance* InAnimInstance, float DeltaSeconds)
{
	FAnimInstanceProxy::PreUpdate(InAnimInstance, DeltaSeconds);
	const UDragonAnimInstance* I = CastChecked<UDragonAnimInstance>(InAnimInstance);
	Seq[(int32)EDragonPose::Glide] = I->GlideSeq;
	Seq[(int32)EDragonPose::Flap] = I->FlapSeq;
	Seq[(int32)EDragonPose::DiveTuck] = I->DiveSeq;
	Seq[(int32)EDragonPose::WingBeat] = I->WingBeatSeq;
	Seq[(int32)EDragonPose::Hover] = I->HoverSeq;
	FMemory::Memcpy(Time, I->Times, sizeof(Time));
	FMemory::Memcpy(Weight, I->Weights, sizeof(Weight));
	NeckOffset = I->NeckOffset;
	NeckBones = I->NeckBones;
}

bool FDragonAnimProxy::Evaluate(FPoseContext& Output)
{
	float Total = 0.f;
	for (int32 i = 0; i < (int32)EDragonPose::Count; ++i) { if (Seq[i] && Weight[i] > 0.002f) { Total += Weight[i]; } }
	if (Total <= 0.f) { Output.ResetToRefPose(); return true; }

	TArray<FCompactPose, TInlineAllocator<5>> Poses;
	TArray<FBlendedCurve, TInlineAllocator<5>> Curves;
	TArray<UE::Anim::FStackAttributeContainer, TInlineAllocator<5>> Attrs;
	TArray<float, TInlineAllocator<5>> W;
	for (int32 i = 0; i < (int32)EDragonPose::Count; ++i)
	{
		if (!Seq[i] || Weight[i] <= 0.002f) { continue; }
		FCompactPose& Pose = Poses.AddDefaulted_GetRef();
		Pose.SetBoneContainer(&Output.Pose.GetBoneContainer());
		FBlendedCurve& Curve = Curves.AddDefaulted_GetRef();
		Curve.InitFrom(Output.Curve);
		UE::Anim::FStackAttributeContainer& Attr = Attrs.AddDefaulted_GetRef();
		FAnimationPoseData PoseData(Pose, Curve, Attr);
		Seq[i]->GetAnimationPose(PoseData, FAnimExtractContext(double(Time[i]), false));
		W.Add(Weight[i] / Total);
	}
	FAnimationPoseData OutData(Output);
	FAnimationRuntime::BlendPosesTogether(Poses, Curves, Attrs, W, OutData);

	// Neck/head turn: the same component-space delta on each neck bone, applied cumulatively down the chain.
	if (NeckBones.Num() > 0 && !NeckOffset.IsNearlyZero(0.05f))
	{
		const FBoneContainer& Bones = Output.Pose.GetBoneContainer();
		FCSPose<FCompactPose> CS;
		CS.InitPose(Output.Pose);
		const FRotator Per = NeckOffset * (1.f / NeckBones.Num());
		const FQuat Delta = Per.Quaternion();
		TArray<TPair<FCompactPoseBoneIndex, FQuat>, TInlineAllocator<8>> Edits;
		for (const FName& Name : NeckBones)
		{
			const int32 MeshIdx = Bones.GetPoseBoneIndexForBoneName(Name);
			if (MeshIdx == INDEX_NONE) { continue; }
			const FCompactPoseBoneIndex Idx = Bones.MakeCompactPoseIndex(FMeshPoseBoneIndex(MeshIdx));
			if (Idx == INDEX_NONE) { continue; }
			const FCompactPoseBoneIndex Parent = Bones.GetParentBoneIndex(Idx);
			const FQuat ParentRot = Parent != INDEX_NONE ? CS.GetComponentSpaceTransform(Parent).GetRotation() : FQuat::Identity;
			Edits.Emplace(Idx, ParentRot.Inverse() * Delta * ParentRot);
		}
		for (const TPair<FCompactPoseBoneIndex, FQuat>& E : Edits)
		{
			FTransform& T = Output.Pose[E.Key];
			T.SetRotation((E.Value * T.GetRotation()).GetNormalized());
		}
	}
	return true;
}
