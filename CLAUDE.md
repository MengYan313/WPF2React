# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

WPF2React converts WPF (XAML + C#) projects into React + TypeScript + Material-UI projects. It is a two-stage pipeline: a deterministic **parser** that extracts structure/dependencies, followed by an LLM-driven **multi-agent migration** built on `autogen-core`.

## Commands

For this macOS checkout, use the project-local venv documented in `AGENTS.md` and `docs/LOCAL_DEVELOPMENT_BASELINE.md`. The old Linux conda path `/home/wenxinyao/anaconda3/envs/autogen` is historical and does not exist on this machine.

```bash
# Setup
/opt/homebrew/bin/python3.11 -m venv .venv
.venv/bin/python -m pip install -r requirements-local.lock

# Stage 1 — parse a WPF project from repos/ into outputs/{project}/
.venv/bin/python -m src.parser ExpenseItDemo

# Stage 2 — migrate (requires stage 1 output to exist); writes to results/{project}/
.venv/bin/python -m src.migration ExpenseItDemo
nohup .venv/bin/python -m src.migration ExpenseItDemo &   # long runs (see nohup.out)

# Run the migrated React app
cd results/ExpenseItDemo && npm install && npm start
```

Domain integration tests are standalone async scripts, not a pytest suite (`pytest` lines in requirements.txt are commented out). Shared infrastructure has an offline `unittest`:

```bash
.venv/bin/python -m unittest tests.common.test_shared_infrastructure -v
.venv/bin/python -m tests.parser.test_parser_pipeline            # offline parser smoke test
.venv/bin/python -m tests.llm.test_model_config                  # offline model-tier config test
.venv/bin/python -m tests.llm.test_connectivity                  # one low-tier LLM call
.venv/bin/python -m tests.migration.test_component_smoke         # one component-generation call
.venv/bin/python -m tests.migration.test_mui_select_smoke        # synthetic custom-control selection
.venv/bin/python -m tests.migration.test_cs_smoke                # synthetic C# migration + analysis
.venv/bin/python -m tests.migration.test_data_smoke              # one synthetic data migration call
.venv/bin/python -m tests.migration.test_page_assembly_smoke     # four synthetic assembly calls
.venv/bin/python -m tests.migration.test_page_pipeline_smoke     # one-control synthetic page pipeline
.venv/bin/python -m tests.migration.test_single_page_migration   # migrate one page (ExpenseItDemo/ViewChartWindow)
.venv/bin/python -m tests.migration.test_agents
.venv/bin/python -m tests.migration.test_cs_migration
.venv/bin/python -m tests.migration.test_data_migration
.venv/bin/python -m tests.llm.test_examples
```

Test modules mirror the five source packages under `tests/{agents,common,llm,migration,parser}/`; keep `tests/` itself free of duplicate compatibility runners.
The single-page test also validates the final TSX and must exit nonzero when the LLM pipeline finishes but generated code is statically invalid.

## Environment

`.env` at repo root, loaded via `python-dotenv`:
- `OPENAI_API_KEY` (required)
- `OPENAI_BASE_URL` (required for the configured OpenAI-compatible relay)
- `OPENAI_MODEL_LOW=gpt-5.6-luna`
- `OPENAI_MODEL_MEDIUM=gpt-5.6-terra`
- `OPENAI_MODEL_HIGH=gpt-5.6-sol`

Current code intentionally routes every generative Agent through `OPENAI_MODEL_LOW`; medium and high are configured but unused. The MUI embedding model is separate from these LLM tiers.

## Architecture

**Stage 1 — parser** (`src/parser/`, entry `__main__.py:analyze_project`). Runs analyzers in a fixed order; later steps consume earlier outputs. tree-sitter parses C#; lxml (fallback: ElementTree) parses XAML. All results land in `outputs/{project}/` — especially `outputs/{project}/dependency/`, which the migration stage reads. The key per-page artifact is `control_{page}.json` (control tree + `root_info.template` / `root_info.data`); `page_dependency.json` defines `migration_order`.

**Stage 2 — migration** (`src/migration/`). `MigrationOrchestrator` drives the overall sequence: resources → C# files → data resources → pages (in dependency order). `MigrationTeam` registers agents on an autogen-core runtime; agents communicate by passing pydantic messages (`messages.py`), not direct calls. Per-page flow: `PageMigrateAgent` walks the control tree bottom-up, asking `MUISelectAgent` then `ComponentMigrateAgent` per node, then hands the collected results to `PageAssemblyAgent`.

**`PageAssemblyAgent` 7-round progressive assembly** (the most actively iterated code — see git log "W2MR" commits): initial assembly → resource fixup → template integration → data integration → layout fixup → sub-page integration → code cleanup. Rounds 2–4 are conditionally skipped when the relevant resource/template/data dependency is absent. If a round's LLM response fails to parse, it falls back to the previous round's output rather than aborting.

### Critical conventions (don't regress these)

- **JSON Schema, not marker tags.** All structured migration calls use provider-native JSON mode and an explicit schema. Business prompts and explanatory fields use Chinese; code, necessary technical terms, and JSON field names may remain English. `src/llm/json_output.py` strictly parses the complete response, validates the schema, and uses the same model for at most one repair attempt. Do not reintroduce marker extraction or Markdown/substring guessing.
- **No `<Grid>`.** Grid support was deliberately removed (commits c11374f / 8b68871). Generated layouts must use `<Box>` and `<Stack>`.
- **Page component patterns.** `MainWindow` takes no props and imports state from `./data`; Dialog/Modal components take `{ open, onClose }` and wrap content in MUI `<Dialog>`. Generated code must not import nonexistent files — implement inline instead of leaving dangling imports.
- **Pinned target versions** baked into prompts: React 18.2.0, MUI 5.18.0, Emotion 11.11.x, TypeScript 5.9.3.

### Per-agent model selection

All generative migration agents currently use `LLMConfig.json_mode_config()`, resolving `OPENAI_MODEL_LOW` (`gpt-5.6-luna`) with `temperature=0` and JSON mode. Keep tier lookup centralized in `src/llm/config.py` and the AutoGen model metadata shim in `src/llm/client.py`; do not hard-code models at individual call sites. Resource migration uses no LLM.

### Shared helpers introduced by the refactor (prefer these)

- **`src/parser/io_utils.py`** — `read_json(path)` / `write_json(path, data, *, indent=2)`. All parser JSON I/O goes through these (byte-identical to the old scattered `json.dump(..., ensure_ascii=False, indent=2)`). Don't re-introduce ad-hoc `open()+json` in the parser.
- **`PageAssemblyAgent._run_assembly_round(label, temp_tsx_path, page_name, round_coro)`** — the rounds-2–7 "call → empty-response fallback to previous temp → save → log" boilerplate. Round 1 stays a special inline seed (no previous temp to fall back to). Add new rounds via this helper; keep the exact label/log strings.
- **`src/llm/json_output.py`** — strict full-response JSON parsing, lightweight schema validation, and one bounded same-model repair shared with CodeIdiomMine.
- **`LLMConfig.json_mode_config()`** / `LLMConfig.model_for_tier(tier)` / `LLMConfig._first_env(*names)` — low-tier JSON config + model/API env lookup.
- Parser output is now **deterministic**: `cs_dependency.json`'s `defined_types` is `sorted()` (was `list(set(...))`, order varied per Python process). Keep set-derived serialized lists sorted.

## Repo layout

`repos/` local input WPF projects (git-ignored and untracked) · `outputs/` parser results + migration intermediates (git-ignored) · `results/` final React output (git-ignored) · `rags/mui/` MUI component docs/mappings used by `MUISelectAgent` · `tests/{agents,common,llm,migration,parser}/` mirrors `src/` · `scripts/` contains maintenance checks · `logs/` & `nohup.out` are run logs. Shared infrastructure rules are in `docs/guides/shared-development-conventions.md`.

## Git

Work on `master`, push to `origin master`. Commit messages follow the existing Chinese convention `W2MR <version>: <描述>` (see `git log`); `docs/GIT_WORKFLOW.md` documents the team's flow.
