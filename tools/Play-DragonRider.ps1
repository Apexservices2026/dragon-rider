# Launch the Dragon Rider opening flight in a window (no editor). Close the window or press Alt+F4 to quit.
$editor = 'C:\Program Files\Epic Games\UE_5.8\Engine\Binaries\Win64\UnrealEditor.exe'
$project = (Resolve-Path (Join-Path $PSScriptRoot '..\Game\DragonRider\DragonRider.uproject')).Path
Start-Process $editor -ArgumentList "`"$project`" /Game/DragonRider/Opening/Lvl_Opening -game -windowed -ResX=1920 -ResY=1080 -NoSplash"
