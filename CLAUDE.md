# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

WPF2React converts WPF (XAML + C#) projects into React + TypeScript + Material-UI projects. It is a two-stage pipeline: a deterministic **parser** that extracts structure/dependencies, followed by an LLM-driven **multi-agent migration** built on `autogen-core`.

## Commands

```bash
# Setup
pip install -r requirements.txt          # Python 3.8+

# Stage 1 — parse a WPF project from repos/ into outputs/{project}/
python -m src.parser ExpenseItDemo

# Stage 2 — migrate (requires stage 1 output to exist); writes to result/{project}/
python -m src.migration ExpenseItDemo
nohup python -m src.migration ExpenseItDemo &   # long runs (see nohup.out)

# Run the migrated React app
cd result/ExpenseItDemo && npm install && npm start
```

Tests are standalone async scripts, not a pytest suite (`pytest` lines in requirements.txt are commented out). Run an individual one from the repo root:

```bash
python -m tests.test_single_page_migration   # migrate one page (ExpenseItDemo/ViewChartWindow)
python -m tests.test_agents
python -m tests.test_cs_migration
python -m tests.test_data_migration
python -m tests.test_llm_examples
```

## Environment

`.env` at repo root, loaded via `python-dotenv`:
- `OPENAI_API_KEY` (required)
- `OPENAI_BASE_URL` (optional; the project routes OpenAI-compatible models — `gpt-4o`, `gpt-4o-mini`, `gpt-5` — through this endpoint)

## Architecture

**Stage 1 — parser** (`src/parser/`, entry `__main__.py:analyze_project`). Runs analyzers in a fixed order; later steps consume earlier outputs. tree-sitter parses C#; lxml (fallback: ElementTree) parses XAML. All results land in `outputs/{project}/` — especially `outputs/{project}/dependency/`, which the migration stage reads. The key per-page artifact is `control_{page}.json` (control tree + `root_info.template` / `root_info.data`); `page_dependency.json` defines `migration_order`.

**Stage 2 — migration** (`src/migration/`). `MigrationOrchestrator` drives the overall sequence: resources → C# files → data resources → pages (in dependency order). `MigrationTeam` registers agents on an autogen-core runtime; agents communicate by passing pydantic messages (`messages.py`), not direct calls. Per-page flow: `PageMigrateAgent` walks the control tree bottom-up, asking `MUISelectAgent` then `ComponentMigrateAgent` per node, then hands the collected results to `PageAssemblyAgent`.

**`PageAssemblyAgent` 7-round progressive assembly** (the most actively iterated code — see git log "W2MR" commits): initial assembly → resource fixup → template integration → data integration → layout fixup → sub-page integration → code cleanup. Rounds 2–4 are conditionally skipped when the relevant resource/template/data dependency is absent. If a round's LLM response fails to parse, it falls back to the previous round's output rather than aborting.

### Critical conventions (don't regress these)

- **Marker format, not JSON.** Despite some prose in README/prompts mentioning "JSON mode", all migration agents run with `json_mode=False` and exchange content via marker tags `[Tag Name] ... [/Tag Name]`. Parsing lives in `src/migration/utils.py` (`extract_tag_content` / `extract_tag_content_lines`, regex `\[Tag\]...\[/Tag\]`). Keep prompt output and parser in sync when editing either. **Footgun (documented in the docstring, behavior intentionally unchanged):** with the default `default=""`, a missing tag makes `extract_tag_content` return the *entire raw response*; callers guard with `if result == response.strip(): return ""`. Don't "fix" this contract without auditing every call site.
- **No `<Grid>`.** Grid support was deliberately removed (commits c11374f / 8b68871). Generated layouts must use `<Box>` and `<Stack>`.
- **Page component patterns.** `MainWindow` takes no props and imports state from `./data`; Dialog/Modal components take `{ open, onClose }` and wrap content in MUI `<Dialog>`. Generated code must not import nonexistent files — implement inline instead of leaving dangling imports.
- **Pinned target versions** baked into prompts: React 18.2.0, MUI 5.18.0, Emotion 11.11.x, TypeScript 5.9.3.

### Per-agent model selection

Models are assigned per agent in `src/migration/__main__.py:migrate_project` (currently `gpt-4o` for page/data/assembly agents, `gpt-4o-mini` for mui-select/component/cs, no LLM for resource migration), all `temperature=0`. Change models there, not in `LLMConfig` defaults (`src/llm/config.py`). Configs are built via `LLMConfig.marker_mode(model)` — the project-wide factory encoding the `temperature=0` + marker-format convention; pass a different model string, don't hand-roll `LLMConfig(...)`.

### Shared helpers introduced by the refactor (prefer these)

- **`src/parser/io_utils.py`** — `read_json(path)` / `write_json(path, data, *, indent=2)`. All parser JSON I/O goes through these (byte-identical to the old scattered `json.dump(..., ensure_ascii=False, indent=2)`). Don't re-introduce ad-hoc `open()+json` in the parser.
- **`PageAssemblyAgent._run_assembly_round(label, temp_tsx_path, page_name, round_coro)`** — the rounds-2–7 "call → empty-response fallback to previous temp → save → log" boilerplate. Round 1 stays a special inline seed (no previous temp to fall back to). Add new rounds via this helper; keep the exact label/log strings.
- **`LLMConfig.marker_mode(model)`** / `LLMConfig._first_env(*names)` — config factory + env-var lookup.
- Parser output is now **deterministic**: `cs_dependency.json`'s `defined_types` is `sorted()` (was `list(set(...))`, order varied per Python process). Keep set-derived serialized lists sorted.

## Repo layout

`repos/` input WPF projects · `outputs/` parser results + migration intermediates (git-ignored) · `result/` final React output (git-ignored) · `rag/mui/` MUI component docs/mappings used by `MUISelectAgent` · `logs/` & `nohup.out` run logs.

## Git

Work on `master`, push to `origin master`. Commit messages follow the existing Chinese convention `W2MR <version>: <描述>` (see `git log`); `GIT_WORKFLOW.md` documents the team's flow.
