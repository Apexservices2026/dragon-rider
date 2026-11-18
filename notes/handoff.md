# Dragon Rider — Handoff

## Current state

- GitHub repository: https://github.com/Apexservices2026/dragon-rider
- Repository remains public and unchanged by this work; nothing was pushed.
- Local project: the repository root on the owner's PC (full path kept out of the repo)
- Current branch: `codex/flight-foundation`
- Local commit: `bb1713c Start dragon flight pawn scaffold`
- Unreal Engine 5.8 project: `Game\DragonRider\DragonRider.uproject`, based on the Third Person Blueprint template.
- Opened in Unreal Editor; current level remains the stock Third Person graybox map.
- First project-specific asset: `/Game/DragonRider/BP_DragonFlightPawn`, a Pawn Blueprint with Unreal's Floating Pawn Movement component. Unreal's editor showed it compiled successfully and all changes saved.
- This is a foundation only. It has no dragon model, custom camera, input bindings, working flight controls, mount/dismount, combat, or custom Nordic environment yet.
- Git LFS is installed and tracks the project's 239 `.uasset` / `.umap` files locally. The content totals about 129 MiB; no LFS data has been uploaded.
- Unreal-generated cache/build folders are ignored. Editor-specific `DefaultEditorPerProjectUserSettings.ini` is local only.

## Next steps

1. Add a clear placeholder visual and a camera boom/camera to the flight Pawn.
2. Implement and evaluate the first controllable flight loop: forward acceleration, banking/turning, and vertical climb/dive input.
3. Set up the Pawn's input and a small open test space, then tune speed and camera comfort on the owner's PC.
4. Replace graybox visuals gradually with appropriate dragon and Nordic environment art while keeping visual goals cinematic and realistic.

## Owner and workflow

The owner is new to game development and wants beginner-friendly, one-step-at-a-time guidance. Preserve the cinematic realism and dragon-flight focus. Distinguish work that requires the Windows Unreal desktop from cloud-friendly work. Continue using focused `codex/<task>` branches, commit working steps, and update this handoff. Never push or merge without explicit permission.

## Camera structure update

- Added a SpringArm under DefaultSceneRoot and a Camera attached to the SpringArm in BP_DragonFlightPawn.
- Compiled successfully in Unreal Editor and saved; no gameplay playtest has been performed.
- Camera defaults are still untuned (300 cm boom, 90 degree field of view).
- Owner confirmed that routine implementation choices should follow our recommendations without repeated preference questions. Planned first controls: mouse steering plus keyboard speed and altitude control.
- Next implementation must wire input and movement, add a collision root and placeholder visual, then evaluate in a dedicated flight test map. The game is not yet flyable.

## Latest checkpoint — November 17, 2026 (supersedes current-state text above)

- Active branch: `codex/flight-pass`.
- Added `Lvl_FlightPass`, a six-gate native-pawn graybox course.
- Added `BP_FlightPrototype` (DefaultPawn subclass), `BP_FlightPrototypeMode`, and `Lvl_FlightPrototype`. Original BP_DragonFlightPawn is preserved unchanged.
- Prototype uses native mouse/WASD/Space/Ctrl bindings, spherical collision, and a visible sphere placeholder. Camera: 650 cm boom, +120 cm socket height, 85 degree FOV, positional lag speed 7. Movement: max 2400 cm/s, acceleration 1400, deceleration 950, turning boost 2.
- `tools/build_flight_pass.py` and `tools/build_flight_prototype.py` create the assets and refuse replacement. `tools/verify_flight_prototype.py` checks persisted movement, game mode, map assignment, and camera attachment without saving its inspection world.
- Validation: generation and verification both finished with zero Unreal commandlet errors/warnings. Standalone game rendered the course and third-person sphere camera. Mouse view response observed. Sustained keyboard movement, course completion, collision behavior, camera comfort, and frame-rate performance still require hands-on verification. Do not describe this as complete custom dragon flight.
- `tools/Play-FlightPrototype.ps1` and README provide launch instructions. Engine association GUID is local; another machine may need to select UE 5.8.
- Owner explicitly authorized uploading project checkpoints to the existing GitHub repository and wants ongoing work saved periodically. Repository was empty when checked before this checkpoint. No merge, force push, purchase, or visibility change authorized.
- Owner intends to alternate Codex and Claude. Before edits, fetch/read the latest branch and this handoff; preserve uncommitted work and avoid simultaneous writes to binary assets. Record what was actually tested after every meaningful checkpoint. Both assistants should use focused branches and avoid silently merging others' work.

### Next development tasks

1. Verify sustained flight input and course traversal in Unreal; fix any input or camera issues first.
2. Improve course readability and presentation with gate labels, directional cues, and a coherent test environment; capture actual screenshots.
3. Add a suitable dragon visual and animation through an explicitly selected asset workflow; do not purchase or import unlicensed art.
4. Develop bespoke dragon momentum, bank/roll, takeoff/landing and mount/dismount. Native free-flight strafing is only the present baseline.
5. Keep graphics ambition, but do not claim the current graybox is cinematic or production-ready.

### Public sharing checkpoint

- Public development branch is `codex/shared-prototype`. The older `codex/flight-pass` branch remains local for historical reference.
- Public history begins with a clean snapshot because the original Unreal template config included an autogenerated Android file-server token. Removed the token and disabled the unused Android file server for this Windows prototype. Do not push the older local branches or merge their history into the public branch.
- This preserves previous local commits while excluding that configuration value from public Git history.

### Course presentation checkpoint — November 18, 2026

- Core prototype checkpoint `20a08c6` was successfully pushed to `origin/codex/shared-prototype`; all 243 LFS objects uploaded and remote commit matched local.
- Continued after that save: added `tools/build_flight_trial.py`, `Lvl_FlightTrial`, and three materials (TrialAmber, TrialFrost, TrialSlate). Builder completed with zero commandlet errors/warnings. This separate map adds gate numbers, amber gates, blue route markers, a title, controls, and an end-of-course sign; it retains the same flying sphere and camera.
- Presentation map has NOT been visually verified. Offscreen screenshot launch was interrupted, then aborted. No exported screenshots were produced. Existing earlier game-window captures showed the graybox prototype only.
- Next: open Lvl_FlightTrial in Windows Unreal, check text orientation/legibility and materials, test sustained WASD/altitude input and course collision, then capture two real screenshots. Keep Lvl_FlightPrototype as the verified-render baseline until the trial passes review.
- No gate scoring, timer, victory logic, dragon model, wing animation, mount/dismount, or combat has been implemented. This remains a free-flight prototype rather than a finished game.

## Claude checkpoint — November 18, 2026 (supersedes the "current state" sections above)

Owner moved development from Codex to Claude, working locally on the Windows PC. Owner decisions: free assets first (no purchases), cinematic-arcade flight feel, C++ for flight code, game opens with a Viking riding a dragon.

- Branch: `claude/dragon-flight` (from `codex/shared-prototype`). Nothing pushed yet.
- The project is now **C++ + Blueprint**: module `Game/DragonRider/Source/DragonRider` (builds with VS 2026 / UE 5.8; `Build.bat DragonRiderEditor Win64 Development -Project=...`).
  - `ADragonFlightPawn`: custom arcade flight. Mouse aims, dragon chases the aim and banks into turns; dives convert altitude to speed, climbs bleed it; W/S throttle, A/D bank-turn, Space wing beat (lift + speed), Shift boost (stamina), Q/E barrel roll. Sweep collision skims/deflects off terrain and water. Camera: lagged spring arm, speed-based FOV/arm length, shake, motion blur. All tuning values are `EditAnywhere`. Gamepad mapped too (untested).
  - Placeholder dragon built from engine primitives with procedural wing beats (shoulder + wrist), glide pose in dives, travelling-wave tail, head looking into turns. Rider = UE mannequin (standing idle) — placeholder until a Viking model.
  - `ADragonRiderGameMode` / `ADragonHUD`: title card, speed/altitude, stamina bar, control hints.
  - `-DragonShots` command-line flag: scripted review flight that saves 6 screenshots and quits (`tools/Review-Opening.ps1`).
- Opening level `/Game/DragonRider/Opening/Lvl_Opening` (now the default game + editor map):
  - Terrain from Blender: `tools/blender/gen_fjord_terrain.py` (headless, ~6 s) → 16×16 km fjord, 2M tris → `Saved/Generated/SM_FjordTerrain.fbx` (not in Git; regenerate).
  - `tools/build_opening_level.py` rebuilds everything under `/Game/DragonRider/Opening` (it deletes and recreates only that folder): imports terrain (Nanite OFF — with Nanite on, only the 27k-tri fallback rendered), procedural height/slope terrain material (rock/moss/snow/wet shore + streak noise — FBX vertex colours did not survive import), water, golden-hour sun, sky atmosphere, volumetric clouds, height fog, post-process grade, player start over the sea facing the fjord mouth.
- Verified (by automated review run, screenshots inspected): level loads, dragon spawns and flies, banking turn, boosted dive reaches ~418 km/h, wing-beat climb recovers, terrain/water/sky render correctly. NOT verified: hands-on mouse/keyboard feel, gamepad, frame rate, collision feel when hitting cliffs.
- Codex's earlier maps (Lvl_FlightPrototype/Pass/Trial) and builder scripts are untouched.

### Next steps
1. Owner playtest of flight feel → tune values.
2. Real dragon + Viking rider art (free Fab assets, or a Blender-built dragon), seated riding pose.
3. Terrain detail: free Megascans rock/snow textures, more resolution near the fjord, Viking settlement + longships as the first landmark.
4. Opening cinematic (camera fly-in), music/wind audio, wing/whoosh sounds.

## Claude checkpoint 2 — November 18, 2026 (supersedes everything above)

Claude is now in charge of the project. ChatGPT/Codex may occasionally help with visuals. Default branch on GitHub: `claude/dragon-flight` (pushed; owner authorised pushes to this branch). The work is organised Atlas-style with specialists: Forge (code), Vertex (Blender), Sentinel (licences), Scout (QA).

**Built and verified by review runs and screenshots:**
- Flight: power dive (Ctrl/RMB/LT, up to about 800 km/h, slingshot pull-out) and the water plunge (murky underwater camera, 2.5 s breath, Space bursts out). The splash is made from engine shapes (`ADragonSplash`).
- Rigged dragon (65 bones, about 136k tris) and Viking rider (about 65k tris), procedural from `tools/blender/dragon/`. Animations: Flap, Glide, DiveTuck (bat fold), WingBeatStrong, Hover, RiderIdle. In Unreal: `tools/import_dragon.py` plus the `UDragonAnimInstance` blends. The rider attaches to the `Saddle` bone, with the Blender rest roll undone in code.
- Viking world kit (`tools/blender/world/`): longships in two clans, longhouse, huts, pier, palisade, watchtower and banners. `tools/import_world_kit.py` imports it, `tools/place_world.py` places three villages (Skerholm, Fjordmunn, Innvik) using the terrain vertex grid, because line traces return nothing in commandlets. `ALongshipActor` is a 6-ship fleet that rows, bobs, billows and loops back to sea.
- Start point: derived from the real terrain (the mesh is mirrored relative to the old `centre()` formula). It faces up the fjord mouth.
- Browser preview (`web/flight-preview.html`, an artifact): same physics and the real model via `DragonRider.gltf.json`. The artifact host doesn't serve .glb, so it is converted with `tools/web/glb_to_gltf_json.py`.

**Rebuild order:** Blender scripts, then `import_world_kit.py`, then `import_dragon.py`, then `build_opening_level.py` (which runs `place_world.py`). Details are in README.

**Compliance (Sentinel):**
- Epic template content was removed from the repo (it's ignored, local copies are kept). Old history still contains it.
- `NOTICES.md` lists the third-party code and fonts.
- Commits use the GitHub noreply email.
- The local Codex branches holding the old Android token were deleted.
- "Dragon Rider" is the title of a Cornelia Funke novel and has a game trademark filing. Clear the name before any commercial release.

**Open, weakest first:**
- Owner feedback: it looks too "claymation and boxy". The owner wants the look of a high-end open-world reference video: photoreal cliffs, forests, waterfalls, clouds below the dragon, a brighter dragon and a jacked Viking.
- Plan:
  - Megascans (free on Fab again as of Nov 2026) plus Landscape and PCG foliage for the environment.
  - MetaHuman for the rider.
  - A higher-quality dragon. The free options are weak; whether to buy a paid one on Fab is the owner's decision.
- Downloading from Fab needs the owner's Epic login.
- Known issues:
  - A white band at the horizon from altitude (the sea plane's edge).
  - The splash and wakes look like primitives.
  - Ships have no collision.
  - The first village is hard to see from the start.
- Not tested: hands-on feel, gamepad, frame rate.

## Forge checkpoint: archipelago — November 18, 2026

The default map is now `/Game/DragonRider/Archipelago/Lvl_Archipelago` (World Partition). `Lvl_Opening` and its scripts are unchanged. The archipelago level itself (`Content/DragonRider/Archipelago/` and its `__ExternalActors__` / `__ExternalObjects__` folders, about 211 MB) is git-ignored by the owner's choice (2026-11-18) to save Git LFS storage; rebuild it locally with `gen_archipelago.py` + `build_archipelago.py`. Only scripts and code go to GitHub.

- **Terrain generator** `tools/terrain/` (system Python + numpy, no scipy): `gen_archipelago.py` (recipes, layout), `terrain_lib.py` (noise, stream-power hydraulic erosion with uplift + hillslope diffusion on a stochastic D8 network, thermal talus, chamfer distance fields), `dem_import.py` (GeoTIFF -> metre grid -> sea shelf -> drowned-edge island), `png16.py`. Output: `Saved/Generated/Archipelago/*.r16|png` + `archipelago.json` (placement, landscape scale, POIs, start, fleet routes).
- **Main island**: Copernicus GLO-30, Fjærlandsfjorden. Crop centre 6.73 E 61.39 N, 14.1 km square (6.598–6.862 E, 61.327–61.453 N; only the E006 tile is used), heights x1.1, 3.5 m/px. The window edges are drowned along the real valleys (ria coast).
- **Landscapes**: one per island + three 1 km skerry tiles, created by the editor-only C++ module `DragonRiderEditor` (`UDragonLandscapeLibrary::ImportHeightmapLandscape`, wraps `ALandscape::Import` + `ChangeGridSize`). Streaming proxies are always loaded for now (no HLODs yet).
- **Material** `M_ArchipelagoLand` + `MI_Land_*`: auto height/slope/noise layers, texture parameters ready for Megascans (`UseTextures`, `T_<Layer>_Albedo/Normal`, `<Layer>TileCm`).
- **Sea**: 60 km plane + 400 km far-ocean skirt (no collision) to fix the white horizon band.
- **Build**: `build_archipelago.py` must run with `-AllowCommandletRendering` (landscape heights are a GPU merge of the edit layer). It then checks 300 random points per landscape against its heightmap and logs `verify <island>`.
- **Review**: `tools/Review-Archipelago.ps1`; the route is the `ReviewLeg:<n>` markers placed by `build_archipelago.py` and `place_archipelago.py` (the pawn reads them in `-DragonShots` mode). Legs teleport without a sweep, so a leg placed inside a mountain flies through it unseen; keep leg points over the sea or well above the ground.
- **Weak / next**: no foliage or Megascans yet (flat colour, visible noise pattern up close); glacier isle valleys are comb-like; forest cliffs are rounded; the waterfall gorge was empty here (now filled, see the landmarks checkpoint); no HLODs (all landscape proxies always loaded); Nanite landscape off; frame rate not measured.

## Landmarks checkpoint — November 18, 2026 (commit cf3e12f)

- Vertex's landmark kit (`tools/blender/world/build_landmarks.py`, all procedural, own scripts) is imported by `tools/import_landmarks.py` into `/Game/DragonRider/World/Landmarks` (about 53 MB, tracked in LFS). `tools/place_landmarks.py` places it into `Lvl_Archipelago`, with sites chosen by `tools/terrain/pick_landmark_sites.py` and `tools/archipelago_heights.py`. The placement only adds and removes its own actors and never rebuilds the landscapes.
- What's placed:
  - Forest isle: a ring-fort with gatehouse and mead hall on a hilltop, and a waterfall in the gorge.
  - Glacier isle: a rune circle and an ice shrine.
  - Ember caldera: the dragon lair. The lava lake now has a soft crust edge.
  - All coasts: wrecks, beacons and driftwood.
- Fleet fix: the ships' shore check now ignores the sea planes; it had been hitting the far-ocean skirt. Each ship returns to the start of its route.
- Forest village moved to flatter ground; the worst burial is now 0.86 m.
- The archipelago level is git-ignored (owner's choice, to save LFS storage). Rebuild it after a clone with README steps 0, 5 and 6. GitHub LFS use is about 775 MB of a 1 GB free quota, so check before large uploads.
- Weak / next:
  - Fort walls and the gatehouse sink up to 4.5 m.
  - The lair reads small from the air and the skull reads pale.
  - The ice shrine sits on a summit.
  - Stair-stepped beaches on the main island.
  - The waterfall is one flat sheet.
  - Landmark textures are 2048 px (halving them saves about 25 MB).
  - Frame rate not measured.
- Compliance (Sentinel): the DEM credit now uses the licence's exact Art. 6(b) text plus the liability and non-endorsement lines. Imported textures embed the local import path; the fix is pending.
