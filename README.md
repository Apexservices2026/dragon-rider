# Dragon Rider

Unreal Engine 5.8 Viking fantasy action-adventure, with dragon flight as the core mechanic. Target: realistic cinematic Nordic landscapes and exciting, responsive flight.

## Current prototype

A six-gate flight course with a native DefaultPawn-derived flying sphere, tuned acceleration/braking, and a third-person spring-arm camera. This is a graybox movement foundation, not finished dragon gameplay. No dragon art, wing animation, mount/dismount, combat, banking, or missions yet.

## Open and play (Windows)

1. Clone this repository with Git LFS installed, checkout `codex/shared-prototype`, and run `git lfs pull`.
2. Open `Game/DragonRider/DragonRider.uproject` with Unreal Engine 5.8. The saved engine association is machine-specific; select your installed 5.8 version if prompted.
3. In Content > DragonRider, open `Lvl_FlightPrototype`, then press Play and click the viewport.
4. Mouse steers; W/S forward/back, A/D strafe, Space/E rise, Ctrl/Q descend. Release movement keys to brake. Escape ends editor Play mode. Close the window to end a standalone run.

On the original development PC, `tools/Play-FlightPrototype.ps1` launches the standalone test using the installed UE 5.8 path. This is an editor-based prototype, not a packaged executable.

## Continue development

Read `AGENTS.md` and `notes/handoff.md` first. They describe verified progress, limitations, and next steps for Codex and Claude. The editable Unreal assets are stored with Git LFS; source scripts are in `tools`. Do not rerun builder scripts against existing assets: they intentionally refuse to replace them.

Target PC: Ryzen 5 7600X, Radeon RX 7700 XT 12 GB, 16 GB RAM. Rendering, input playtests, and Unreal asset edits require the Windows Unreal desktop; cloud work can review scripts and documentation.
