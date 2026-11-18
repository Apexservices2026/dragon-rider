# Fly the scripted archipelago review (Lvl_Archipelago), save screenshots, and quit (~2.5 min).
# The route is data-driven: tools/build_archipelago.py places "ReviewLeg:<n>" markers in the level (start, fjord, a
# crossing from the main island to the forest isle, two-islands views, each new island up close, horizon at
# altitude, a water plunge, the fleet). Each leg's name is in the log line for its shots.
# Screenshots land in Game/DragonRider/Saved/Screenshots/Windows*/DragonReview_XX.png
$ErrorActionPreference = 'Stop'
$editor = 'C:\Program Files\Epic Games\UE_5.8\Engine\Binaries\Win64\UnrealEditor.exe'
$project = (Resolve-Path (Join-Path $PSScriptRoot '..\Game\DragonRider\DragonRider.uproject')).Path
$shots = Join-Path (Split-Path $project) 'Saved\Screenshots'
Get-ChildItem $shots -Recurse -Filter 'DragonReview_*.png' -ErrorAction SilentlyContinue | Remove-Item
$p = Start-Process $editor -ArgumentList "`"$project`" /Game/DragonRider/Archipelago/Lvl_Archipelago -game -windowed -ResX=1600 -ResY=900 -NoSplash -DragonShots -log=DragonReviewArchipelago.log" -PassThru
if (-not $p.WaitForExit(480000)) { $p.Kill(); throw 'Review run timed out' }
Get-ChildItem $shots -Recurse -Filter 'DragonReview_*.png' | Select-Object -ExpandProperty FullName
Select-String -Path (Join-Path (Split-Path $project) 'Saved\Logs\DragonReviewArchipelago.log') -Pattern 'DRAGON_REVIEW' | ForEach-Object { $_.Line -replace '^.*DRAGON_REVIEW', 'DRAGON_REVIEW' }
