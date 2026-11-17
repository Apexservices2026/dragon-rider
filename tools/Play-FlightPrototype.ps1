$ErrorActionPreference = 'Stop'
$project = Join-Path $PSScriptRoot '../Game/DragonRider/DragonRider.uproject'
$editor = 'C:/Program Files/Epic Games/UE_5.8/Engine/Binaries/Win64/UnrealEditor.exe'
if (-not (Test-Path -LiteralPath $editor)) { throw 'Unreal Engine 5.8 was not found at the expected location.' }
& $editor $project /Game/DragonRider/Lvl_FlightPrototype -game -windowed -ResX=1280 -ResY=720 -NoSplash
