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
4. The editor opens on `Lvl_Archipelago` and you press Play. That level is only there after you build it (see below). On a fresh clone, open `Lvl_Opening` instead.

**The archipelago level is not in Git** (its terrain files are about 200 MB and would use up the free Git LFS storage). After a fresh clone, build it once in this order (about 15 minutes; see "Rebuilding generated content" below):
   1. Step 0: `gen_archipelago.py`. It needs the DEM tiles.
   2. `python -I tools/terrain/pick_landmark_sites.py`.
   3. Step 5: `build_archipelago.py`.
   4. `place_landmarks.py`.

   The landmark meshes are already in Git, so you can skip `import_landmarks.py`.

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

0. **Archipelago terrain** (system Python with numpy; `tifffile` and `imagecodecs` for the real elevation data. All three are BSD-3 licensed and only used by these local tools):
   `python -I tools/terrain/gen_archipelago.py` (about 7 minutes). It writes heightmaps and `archipelago.json` to `Game/DragonRider/Saved/Generated/Archipelago/`.
   - The main island uses the Copernicus GLO-30 DEM tiles `Copernicus_DSM_COG_10_N61_00_E006_00_DEM.tif` and `..._N61_00_E007_00_DEM.tif`. They are not in Git. Download them from the Copernicus Data Space Ecosystem (dataspace.copernicus.eu, collection COP-DEM GLO-30) or its public COG mirror, accept the COP-DEM GLO-30 licence, and put them in `Saved/Generated/DEM/`. Credit is in `NOTICES.md`. The script reads them from there (`--dem <tif> ...` for other tiles, `--no-dem` for a procedural placeholder). The crop is set by `DEM_CENTRE` / `DEM_SIZE_M` in the script.
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
   - Optional, before importing: `tools/halve_landmark_textures.py` (run with Blender's bundled Python) writes 1024 px copies of the 2048 px rune-normal, rune-roughness and shingle maps, to keep Git LFS lean.
   - `tools/import_landmarks.py` imports them into `/Game/DragonRider/World/Landmarks`. It needs the Blender output; skip it if the committed meshes are fine.
   - `python -I tools/terrain/pick_landmark_sites.py` picks the sites and writes `Saved/Generated/Archipelago/landmarks.json`.
   - `tools/place_landmarks.py` places them in `Lvl_Archipelago`. It only adds and removes its own actors; it never rebuilds the landscapes. Step 5 recreates the level, so run `pick_landmark_sites.py` before step 5 (the forest village uses its sites) and `place_landmarks.py` again after every step-5 rebuild.

Each of these scripts deletes and recreates **only its own folder**.

The older Codex builder scripts (`tools/build_flight_*.py`) refuse to overwrite their assets. Leave them alone.

Epic's Third Person template content is not included; see `NOTICES.md`. Project history, decisions and next steps are in `notes/handoff.md`.

### Asset hygiene and fixes that run in place

- All three importers end by running `tools/scrub_import_paths.py`. Unreal's PNG importer stores the absolute source path, which includes your Windows user name, inside every texture asset; the scrub replaces it with a project-relative path. Run it on its own to clean assets that are already imported.
- Collision rules for the kit and landmark meshes are in `tools/collision_rules.py`. Run it on its own to reapply them without reimporting.
- `tools/tune_archipelago_material.py` applies landscape-material tweaks to an existing `Lvl_Archipelago` without rebuilding it.
