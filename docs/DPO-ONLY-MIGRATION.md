# DPO-only Oh Story implementation notes (feature/dpo-only-story)

## Approved architecture
Codex prepares setup/analyze/world/volume/DPO outlines. User switches to `claudeqwen` in the same book root; `/story-long-write 写第N章` spawns `narrative-writer` inheriting local Qwen 27B DPO LoRA. Default one generation per full chapter. No generic prose fallback. No original 9-field outline.

## Implemented in branch
- `references/dpo-outline-contract.md` and `workflow-outline.md`: single inline DPO chapter outline protocol
- `scripts/check-outline-contract.js`: DPO-only structural checker (prior checker's `--supply` still needs migration)
- `scripts/build_dpo_prompt.py`: model-card-shaped prompt JSON generator; existing `build_writer_prompt.py` delegates to it
- `references/workflow-chapter.md`, `workflow-daily.md`, `workflow-revision.md`, `agent-calls.md`, `dpo-writer.md`: DPO-only chapter SOP
- `story-setup/references/templates/agents/narrative-writer.md`: `model: inherit`
- `scripts/build_architect_brief.py` includes DPO outline contract; DPO-only CI smoke tests
- Original story tracking format and scripts retained; `字数目标` and `字数口径` preserved in DPO chapter control for compatibility

## NOT YET COMPLETE — must be addressed before production
1. Audit & update old 9-field outline requirements across related Skills, agents, hooks, validation scripts and tests. `check-outline-contract.js --supply` deliberately returns unsupported until proper unit supply validator exists.
2. Prompt compiler is currently **a scaffold**: it refuses missing `追踪/上下文.md` and records that controller review is required, but does not yet deterministically merge previous chapter tail, current volume unit, character/realm files and tracking deltas. These must be compiled and verified before quality claims.
3. `model: inherit` routing to claudeqwen local LoRA, child-agent tool calls and ability to write full 2500-char text require actual user's Windows environment; cannot be simulated remotely.
4. The original `story-setup` installation, old templates in other hosts and all 13 Skills need complete regression and DPO contract migration. Cross-platform CI may fail until all old assumptions are updated.
5. Existing book project with old outline must be backed up and migrated, not silently treated as DPO-ready. A controlled migration converter remains to be built.
6. Original storyctl/wordcount/tracking commit need integration run with the new outline: single-chapter + 3 serial chapters, restart and revision.

## Safety
Do not merge this draft PR until those checks pass. `main` unchanged.

## 2026-10-14 additional implementation and verification
- Added `migrate_legacy_outline.py`: preview by default, `--write` backs up source to `.before-dpo.bak` and refuses to overwrite an existing backup; unmapped details marked for author review. Migration smoke test is green.
- `build_dpo_prompt.py` now enforces seven tracking sections, reads prior chapter tail (for chapter 2+), returns context/constraints as controller-only metadata, and composes model-card four-section writer user text. This is **not** automatic semantic consistency verification.
- Updated DPO reference-gate and outline structural tests to match the approved replacement format, instead of falsely testing the removed nine-field contract.
- Synced OpenCode narrative writer agent and corrected metadata/static references; DPO-only smoke and OpenCode synchronization have passed in GitHub Actions.
- Still blocked from claiming end-to-end completeness: original cross-platform/release workflows have failures from remaining legacy assumptions; other Skills, agents, hooks, and chapter transaction integration need audit; local `claudeqwen`/LoRA inheritance can only be verified on user's Windows environment.
