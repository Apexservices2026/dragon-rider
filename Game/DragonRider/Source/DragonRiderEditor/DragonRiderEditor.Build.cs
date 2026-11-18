using UnrealBuildTool;

// Editor-only helpers for the content build scripts (tools/*.py). Not part of the game.
public class DragonRiderEditor : ModuleRules
{
	public DragonRiderEditor(ReadOnlyTargetRules Target) : base(Target)
	{
		PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;
		PublicDependencyModuleNames.AddRange(new string[] { "Core", "CoreUObject", "Engine" });
		PrivateDependencyModuleNames.AddRange(new string[] { "UnrealEd", "Landscape", "RenderCore" });
	}
}
