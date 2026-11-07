---
name: shader-cache-cleaner
description: >-
  Scan GPU shader caches (NVIDIA DXCache/GLCache, Windows D3DSCache, per-game
  Unreal-Engine PSO/shader folders) and attribute each cache to its game by
  cross-referencing cache-file timestamps with launcher play-time records, then
  produce a keep/delete cleanup report and optionally delete stale caches. Use
  when the user asks to clean shader caches, free GPU/driver cache disk space,
  or identify which games own a shader cache.
---

# Shader Cache Cleaner

## When to use
The user wants to clean shader caches, free disk space held by GPU/driver
caches, or find which games a shader cache belongs to.

## Run the scanner (read-only)
```bash
python scripts/scan_shader_cache.py
```
Pass `--json` for machine-readable output, or `--roots <dir> [<dir> ...]` to add
game-install roots to the per-game PSO search (e.g. `E:\Program Files` for
non-Steam games). The script NEVER deletes anything; it only measures,
attributes, and reports.

## Shader caches live in MULTIPLE places
Do not assume there is one folder. The full map:

| Location | Content | Identifiable? |
|---|---|---|
| `%LOCALAPPDATA%\NVIDIA\DXCache` | driver-level compiled shaders (`.nvph`) | No — hash-named |
| `%LOCALAPPDATA%\NVIDIA\GLCache` | OpenGL/Vulkan driver cache | No — hash-named |
| `%LOCALAPPDATA%\D3DSCache` | Windows DirectX cache | No — hash-named |
| `<game>\...\Saved\PSO` (Unreal) | per-game pipeline-state cache | Yes — game's own folder |
| `<game>\...\Saved\ShaderCache` | per-game shader cache | Yes |
| `%LOCALAPPDATA%\<GameName>\...` | per-game local data | Yes |

## Attribution method (timestamp correlation)
`.nvph`/D3DSCache filenames are content hashes — the game name is NOT readable
from the filename or the bytes (the files are binary-compressed). Attribute by
cross-referencing TIMESTAMPS instead:

1. Read each launcher's play-time records (Steam `userdata/*/config/localconfig.vdf`
   → `LastPlayed` per appid; other launchers if present).
2. Group cache files by last-write date and by filename prefix (the first 4 hex
   chars of `.nvph` = driver/cache "generation").
3. A date cluster with large volume maps to a game whose `LastPlayed` falls on
   the same day (±1 day).
4. A prefix whose files all share one old date = a stale driver generation —
   safe to delete regardless of game.

## Key gotchas
- **Safe to delete everything**: shader caches regenerate automatically; the
  only cost is brief recompilation/stutter on the next launch of that game.
- **Old caches auto-evict**: a game not played for months usually has NO cache
  left — "keep its cache" is a no-op.
- **Unreal "Saved" is not all cache**: `Saved\PSO` is cache, but sibling folders
  like `Saved\Resources\Video\uhd\Paks` hold game content (HD cutscenes). Never
  delete those — only the `PSO` / `ShaderCache` subfolder.
- **Unity games** (folders containing `*_Data`) keep little per-game cache; their
  shader cache is mostly inside the shared DXCache/D3DSCache.
- **Windows PowerShell 5.1 reads UTF-8 files as GBK** — if scripting in
  PowerShell, use ASCII-only scripts or set
  `[Console]::OutputEncoding=[Text.Encoding]::UTF8` first.

## Cleanup workflow
1. Run the scanner; read the report.
2. Present a keep/delete table to the user:
   - KEEP: caches for games played recently (recompile would cause stutter).
   - DELETE: stale driver generations + games not played recently.
3. Get explicit confirmation before deleting. For NVIDIA DXCache, a clean
   timestamp cutoff (delete files last written before the most recent keep-game's
   play date) separates "current" from "stale" without guessing.
4. Delete, then re-run the scanner to confirm freed space.

## Utility script
`scripts/scan_shader_cache.py` — the scanner/attributor. Execute it; do not
rewrite it from memory.
