# Dragon Rider

An Unreal Engine 5.8 Viking fantasy action-adventure where dragon flight is the core mechanic. You start as a Viking riding a dragon over a Nordic fjord at golden hour. ("Dragon Rider" is a working title.)

## What's playable now

- **Dragon flight** (C++ `ADragonFlightPawn`): mouse aim with banking turns, dive/climb energy, wing beats, boost with stamina, barrel rolls.
- **Power dive** into the sea: plunge under water, then burst back out.
- **Rigged dragon and Viking rider**, made in Blender, with glide / flap / hover / dive-tuck / wing-beat animation blended by flight state.
- **A 16 km fjord** with three clan villages (Skerholm, Fjordmunn, Innvik) and a longship fleet rowing in from the sea.

**Controls:** mouse steer · W/S faster/slower · A/D bank · Space wing beat (and burst out from under water) · Shift boost · Ctrl or right mouse power dive · Q/E barrel roll. A gamepad is mapped but untested.

## Open and play (Windows)

1. Install Unreal Engine 5.8, Visual Studio 2026 (C++ game workload) and Git LFS.
2. Clone this repository and run `git lfs pull`. The default branch is `claude/dragon-flight`.
3. Open `Game/DragonRider/DragonRider.uproject`. Unreal will offer to build the C++ module; say yes. Select your UE 5.8 install if it asks.
4. The editor opens on `Lvl_Opening`. Press Play.

There are also two scripts:
- `tools/Play-DragonRider.ps1` launches the game in a window without the editor.
- `tools/Review-Opening.ps1` flies a scripted route and saves screenshots to `Game/DragonRider/Saved/Screenshots/`.

A browser version of the flight (three.js, same tuning) is in `web/flight-preview.html`.

## Rebuilding generated content

Generated content is rebuilt by scripts. Run each Unreal step as a commandlet from **PowerShell**:

```
UnrealEditor-Cmd.exe <uproject> -run=pythonscript -script=<script>
```

Git Bash mangles `/Game/...` paths, so don't run these from Git Bash.

1. **Blender** (headless, `blender -b -P <script>`):
   - `tools/blender/gen_fjord_terrain.py`: terrain FBX.
   - `tools/blender/dragon/` (`build_dragon.py`, `build_rider.py`, `export.py`): the dragon and rider.
   - `tools/blender/world/build_props.py`: the Viking prop kit.

   The output goes to `Game/DragonRider/Saved/Generated/`. That folder is not in Git.
2. `tools/import_world_kit.py`: rebuilds `/Game/DragonRider/World/`.
3. `tools/import_dragon.py`: rebuilds `/Game/DragonRider/Characters/`.
4. `tools/build_opening_level.py`: rebuilds `/Game/DragonRider/Opening/` (terrain, sky, water, start point), then runs `tools/place_world.py` to place the villages and fleet.

Each of these scripts deletes and recreates **only its own folder**.

The older Codex builder scripts (`tools/build_flight_*.py`) refuse to overwrite their assets. Leave them alone.

Epic's Third Person template content is not included; see `NOTICES.md`. Project history, decisions and next steps are in `notes/handoff.md`.
