## HANDOFF — 2026-05-04

### Session Summary
Fixed WASD/camera input (Enhanced Input class silently broke legacy BindAxis), tuned succubus skeletal mesh Z offset from -40 (sinking) through -20 (floating) to -35 (current best), and fixed material TextureSample pin name from "RGB" to "" (empty string = default output) in material_assign.py. Texture visibility is unconfirmed — user has not yet tested after the pin name fix.

### Completed This Session
- Restored WASD + Space + camera controls by reverting DefaultInput.ini to legacy input classes
- Replaced Q/R camera rotation with Left/Right arrow keys (Q/R consumed by DebugManager in PIE)
- Fixed material_assign.py: added _ensure_skeletal_mesh_usage(), _create_direct_material(), reparent_mi_to param
- Created M_SK_Succubus_Direct (plain UMaterial with TextureSample nodes, bUsedWithSkeletalMesh=True)
- Re-parented MI_SK_Succubus to M_SK_Succubus_Direct
- Changed TextureSample Albedo pin from "RGB" to "" (empty string) for connect_material_property
- Wiki pages updated (character.md, ue5-project.md, log.md, conventions.md)

### In Progress
- Z offset: at -35 in CylinderCharacter.cpp, needs Live Coding (Ctrl+Alt+F11) to take effect, then user validation
- Texture visibility: pin name fix applied to material_assign.py but user hasn't confirmed textures appear in-game
- Level is transient (/Temp/Untitled_1) — needs Ctrl+S in editor to save

### Wiki Pages Updated
- llm-wiki/character.md: Z offset updated from -20 to -35, added tuning history
- llm-wiki/ue5-project.md: added CylinderGameMode to source files, added Enhanced Input and Q/R gotchas
- llm-wiki/log.md: session wrap entry added

### README Changes
NONE — changes are game-project-specific, not plugin-facing.

### Design-Doc Deviations
NONE

### Next Session — Do This First
Stop PIE, trigger Live Coding (Ctrl+Alt+F11) for Z=-35, restart PIE, and check: (1) is the character at ground level? (2) do textures appear on the succubus mesh? If textures still missing, create a constant-color test material to isolate whether the issue is material application vs texture UV mismatch.

### Warnings
- material_assign.py _create_direct_material() accumulates TextureSample nodes on each call (cannot call delete_all_material_expressions — crashes with IsRooted assert). connect_material_property replaces the connection on each property pin, so last-added node wins, but stale nodes remain in the graph.
- FObjectFinder is static — caches result at CDO construction. If the material asset doesn't exist at editor startup, it caches nullptr permanently for that process.
- Level is unsaved transient map. If editor crashes before Ctrl+S, all placed actors are lost.

### Commit Message
[game] Fix input, tune Z offset, fix material pin name

- Revert DefaultInput.ini to legacy input classes (Enhanced Input broke WASD)
- Replace Q/R Turn bindings with Left/Right arrow keys (DebugManager conflict)
- CylinderCharacter Z offset: -40 → -35 (tuning between sinking and floating)
- material_assign.py: Albedo pin "RGB" → "" (empty string = default output)
- Add _ensure_skeletal_mesh_usage, _create_direct_material, reparent_mi_to
- Wiki: character.md, ue5-project.md, log.md updated
