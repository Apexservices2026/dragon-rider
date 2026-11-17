# Dragon Rider — Handoff

## Current state

- GitHub repository: https://github.com/Apexservices2026/dragon-rider
- Repository remains public and unchanged by this work; nothing was pushed.
- Local project: `C:\Users\smart\Documents\Codex\DragonRider`
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
