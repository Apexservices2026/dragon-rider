# Dragon Rider

An Unreal Engine 5.8 Viking fantasy action-adventure where dragon flight is the core mechanic. You start as a Viking riding a dragon over a Nordic fjord at golden hour. ("Dragon Rider" is a working title.)

## What's playable now

- **Dragon flight** (C++ `ADragonFlightPawn`): mouse aim with banking turns, dive/climb energy, wing beats, boost with stamina, barrel rolls.
- **Power dive** into the sea: plunge under water, then burst back out.
- **Rigged dragon and Viking rider**, made in Blender, with glide / flap / hover / dive-tuck / wing-beat animation blended by flight state.
- **An archipelago** (`Lvl_Archipelago`, the default map): a main fjord island built from real elevation data (Fjærlandsfjorden, Norway), plus three eroded islands a minute's flight apart: the forest isle (sea cliff, waterfall gorge), the glacier isle (jagged peaks, ice fields, fjords) and the ember isle (volcano with a lava-lit caldera, the dragon's lair). Villages on the main and forest islands, and longships rowing between the islands.
- The older **16 km fjord** map (`Lvl_Opening`) is kept as it was.

**Controls:** mouse steer · W/S faster/slower · A/D bank · Space wing beat (and burst out from under water) · Shift boost · Ctrl or right mouse power dive · Q/E barrel roll. A gamepad is mapped but untested.

## Open and play (Windows)

1. Install Unreal Engine 5.8, Visual Studio 2026 (C++ game workload) and Git LFS.
2. Clone this repository and run `git lfs pull`. The default branch is `claude/dragon-flight`.
3. Open `Game/DragonRider/DragonRider.uproject`. Unreal will offer to build the C++ module; say yes. Select your UE 5.8 install if it asks.
4. The editor opens on `Lvl_Archipelago`. Press Play.

**The archipelago level is not in Git** (its terrain files are about 200 MB and would use up the free Git LFS storage). After a fresh clone, build it once with steps 0 and 5 under "Rebuilding generated content" below (about 15 minutes, needs the DEM tiles). Until then, play `Lvl_Opening`.

There are also two scripts:
- `tools/Play-DragonRider.ps1` launches the game in a window without the editor.
- `tools/Review-Archipelago.ps1` flies a scripted route across the archipelago and saves screenshots to `Game/DragonRider/Saved/Screenshots/`. `tools/Review-Opening.ps1` does the same for the old fjord map.

A browser version of the flight (three.js, same tuning) is in `web/flight-preview.html`.

## Rebuilding generated content

Generated content is rebuilt by scripts. Run each Unreal step as a commandlet from **PowerShell**:

```
UnrealEditor-Cmd.exe <uproject> -run=pythonscript -script=<script>
```

Git Bash mangles `/Game/...` paths, so don't run these from Git Bash.

0. **Archipelago terrain** (system Python with numpy; `tifffile` for the real elevation data):
   `python -I tools/terrain/gen_archipelago.py` (about 7 minutes). It writes heightmaps and `archipelago.json` to `Game/DragonRider/Saved/Generated/Archipelago/`.
   - The main island uses the Copernicus GLO-30 DEM tiles in `Saved/Generated/DEM/` (`--dem <tif> ...` for other tiles, `--no-dem` for a procedural placeholder). The crop is set by `DEM_CENTRE` / `DEM_SIZE_M` in the script.
   - `--quick` makes a fast preview; `--only forest,ember` rebuilds some islands and keeps the rest.
1. **Blender** (headless, `blender -b -P <script>`):
   - `tools/blender/gen_fjord_terrain.py`: terrain FBX.
   - `tools/blender/dragon/` (`build_dragon.py`, `build_rider.py`, `export.py`): the dragon and rider.
   - `tools/blender/world/build_props.py`: the Viking prop kit.

   The output goes to `Game/DragonRider/Saved/Generated/`. That folder is not in Git.
2. `tools/import_world_kit.py`: rebuilds `/Game/DragonRider/World/`.
3. `tools/import_dragon.py`: rebuilds `/Game/DragonRider/Characters/`.
4. `tools/build_opening_level.py`: rebuilds `/Game/DragonRider/Opening/` (terrain, sky, water, start point), then runs `tools/place_world.py` to place the villages and fleet.
5. `tools/build_archipelago.py`: rebuilds `/Game/DragonRider/Archipelago/` (World Partition level, one Landscape per island, auto landscape material, sky, sea, start point, review route), then runs `tools/place_archipelago.py` (villages, fleet). It needs the C++ editor module `DragonRiderEditor` built (it creates the landscapes), and the commandlet must be run with `-AllowCommandletRendering` (the landscape heights are merged on the GPU).
6. Island landmarks (Vertex's kit from `tools/blender/world/build_landmarks.py`):
   - `tools/import_landmarks.py` imports them into `/Game/DragonRider/World/Landmarks`.
   - `python -I tools/terrain/pick_landmark_sites.py` picks the sites and writes `Saved/Generated/Archipelago/landmarks.json`.
   - `tools/place_landmarks.py` places them in `Lvl_Archipelago`. It only adds and removes its own actors; it never rebuilds the landscapes.

Each of these scripts deletes and recreates **only its own folder**.

The older Codex builder scripts (`tools/build_flight_*.py`) refuse to overwrite their assets. Leave them alone.

Epic's Third Person template content is not included; see `NOTICES.md`. Project history, decisions and next steps are in `notes/handoff.md`.
