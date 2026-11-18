# Fly the scripted review route in the opening level, save screenshots, and quit (~80 s).
# Shots 00-05: cruise, orbit, turn, boosted dive, climb. 06-10: power dive, entry splash, underwater, burst, after burst. 11-14: village low pass, fleet pass.
# Screenshots land in Game/DragonRider/Saved/Screenshots/Windows*/DragonReview_XX.png
$ErrorActionPreference = 'Stop'
$editor = 'C:\Program Files\Epic Games\UE_5.8\Engine\Binaries\Win64\UnrealEditor.exe'
$project = (Resolve-Path (Join-Path $PSScriptRoot '..\Game\DragonRider\DragonRider.uproject')).Path
$shots = Join-Path (Split-Path $project) 'Saved\Screenshots'
Get-ChildItem $shots -Recurse -Filter 'DragonReview_*.png' -ErrorAction SilentlyContinue | Remove-Item
$p = Start-Process $editor -ArgumentList "`"$project`" /Game/DragonRider/Opening/Lvl_Opening -game -windowed -ResX=1600 -ResY=900 -NoSplash -DragonShots -log=DragonReview.log" -PassThru
if (-not $p.WaitForExit(240000)) { $p.Kill(); throw 'Review run timed out' }
Get-ChildItem $shots -Recurse -Filter 'DragonReview_*.png' | Select-Object -ExpandProperty FullName
Select-String -Path (Join-Path (Split-Path $project) 'Saved\Logs\DragonReview.log') -Pattern 'DRAGON_REVIEW' | ForEach-Object { $_.Line -replace '^.*DRAGON_REVIEW', 'DRAGON_REVIEW' }
