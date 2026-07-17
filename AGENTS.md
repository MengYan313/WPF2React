# AGENTS.md

## Cross-project unified development contract

This repository and its sibling repository remain independent, but reusable infrastructure must follow the same contract. Before changing logging, LLM wrappers, AutoGen setup, directory roles, or test organization, read `docs/guides/shared-development-conventions.md` and update both repositories' shared files together.

Mandatory conventions:

- Use `repos/` for local source-repository inputs, `outputs/` for reproducible intermediates, `results/` for final artifacts, `logs/` for run logs, `tests/` for tests, and `docs/` for versioned documentation. Keep `repos/` ignored and untracked; do not add a duplicate `inputs/` alias.
- New logging imports use `from src.common.logging import get_logger`. One command writes all module logs to append-only `logs/<run-name>.log`; `src.logger` is compatibility-only.
- LLM code imports shared APIs from `src.llm`. Root `.env` loading, model tiers, GPT-5.6 metadata, client creation, JSON mode, schema validation, one-shot JSON repair, and client closure stay centralized there. Low tier is the only implicit default.
- Business prompts and explanatory fields use Chinese; retain English only for code, model/API names, necessary technical terms, and JSON field names. Structured calls build stable system prompts with `build_json_system_prompt(...)`, use native JSON mode plus explicit JSON Schema, and never use `[JSON]` or domain marker wrappers.
- AutoGen code uses `SingleThreadedAgentRuntime`, strong messages, `BaseRoutedAgent`, `register_agent(...)`, `default_agent_id(...)`, and a `start -> try/finally -> stop` lifecycle. Agents communicate through routed messages.
- Keep offline tests deterministic and free of downloads or paid calls. Real LLM tests require an explicit model, bounded call count, cost/privacy review, and separate smoke outputs.
- Run `.venv/bin/python scripts/check_shared_infrastructure.py --other ../<sibling>` after changing a shared file. The two projects may keep different verified Python minor versions and different domain packages.

This file provides guidance to Codex (Codex.ai/code) when working with code in this repository.

## What this is

WPF2React converts WPF (XAML + C#) projects into React + TypeScript + Material-UI projects. It is a two-stage pipeline: a deterministic **parser** that extracts structure/dependencies, followed by an LLM-driven **multi-agent migration** built on `autogen-core`.

## Commands

### This macOS checkout

The Linux conda path `/home/wenxinyao/anaconda3/envs/autogen` is historical and does not exist on this machine. For `/Users/sophon/Codex/WPF2React`, always use the project-local venv:

- Python executable: `/Users/sophon/Codex/WPF2React/.venv/bin/python`
- Installed base interpreter: Homebrew `python@3.11` at `/opt/homebrew/bin/python3.11` (Python 3.11.12, arm64)
- Activate with `source .venv/bin/activate`, or prefer explicit `.venv/bin/python` commands.
- Never install project packages into `/usr/bin/python3`, the Command Line Tools Python, or a global Homebrew site-packages directory.
- Recreate the verified macOS arm64 environment with `python3.11 -m venv .venv` and `.venv/bin/python -m pip install -r requirements-local.lock`.

The source and current dependency metadata require Python 3.10 or newer. Python 3.11 is the verified baseline; see `docs/LOCAL_DEVELOPMENT_BASELINE.md`.

```bash
# Setup for this checkout
/opt/homebrew/bin/python3.11 -m venv .venv
.venv/bin/python -m pip install -r requirements-local.lock

# Stage 1 — parse a WPF project from repos/ into outputs/{project}/
.venv/bin/python -m src.parser ExpenseItDemo

# Stage 2 — migrate (requires stage 1 output to exist); writes to results/{project}/
.venv/bin/python -m src.migration ExpenseItDemo
nohup .venv/bin/python -m src.migration ExpenseItDemo &   # long runs (see nohup.out)

# After supplying a real React package/TypeScript entry scaffold
cd results/ExpenseItDemo && npm install && npm start
```

Domain integration tests are standalone async scripts, not a pytest suite (`pytest` lines in requirements.txt are commented out). Shared infrastructure has an offline `unittest`. Run from the repo root:

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

Keep test modules under the package matching `src/`: `tests/agents/`, `tests/common/`, `tests/parser/`, `tests/migration/`, and `tests/llm/`. Do not add duplicate compatibility runners directly under `tests/`.
`tests.migration.test_single_page_migration` must validate the final `results/{project}/{page}.tsx`, not merely the intermediate migration JSON; generated-code errors must make the script exit nonzero.

## Environment

`.env` at repo root, loaded via `python-dotenv`:
- `OPENAI_API_KEY` (required)
- `OPENAI_BASE_URL` (required for the configured OpenAI-compatible relay)
- `OPENAI_MODEL_LOW=gpt-5.6-luna`
- `OPENAI_MODEL_MEDIUM=gpt-5.6-terra`
- `OPENAI_MODEL_HIGH=gpt-5.6-sol`

The current runtime intentionally uses only `OPENAI_MODEL_LOW` through `LLMConfig.json_mode_config()`. Medium and high are reserved for later explicit routing decisions. `text-embedding-3-small` in `MUISelectAgent` is an embedding model, not a generative LLM tier.

Never print, log, commit, or copy secret values or enterprise source/data outside the approved environment. Only report whether a variable exists. `.env` files and generated outputs are ignored. The verified Node environment is Node 23.11.0 + npm 11.6.2; do not install generated-project packages until a real `package.json` exists. The semantic MUI selector also needs the `all-MiniLM-L6-v2` model on first use; its cache was absent at baseline time.

## Architecture

**Stage 1 — parser** (`src/parser/`, entry `__main__.py:analyze_project`). Runs analyzers in a fixed order; later steps consume earlier outputs. tree-sitter parses C#; lxml (fallback: ElementTree) parses XAML. All results land in `outputs/{project}/` — especially `outputs/{project}/dependency/`, which the migration stage reads. The key per-page artifact is `control_{page}.json` (control tree + `root_info.template` / `root_info.data`); `page_dependency.json` defines `migration_order`.

**Stage 2 — migration** (`src/migration/`). `MigrationOrchestrator` drives the overall sequence: resources → C# files → data resources → pages (in dependency order). `MigrationTeam` registers agents on an autogen-core runtime; agents communicate by passing pydantic messages (`messages.py`), not direct calls. Per-page flow: `PageMigrateAgent` walks the control tree bottom-up, asking `MUISelectAgent` then `ComponentMigrateAgent` per node, then hands the collected results to `PageAssemblyAgent`.

**`PageAssemblyAgent` 7-round progressive assembly** (the most actively iterated code — see git log "W2MR" commits): initial assembly → resource fixup → template integration → data integration → layout fixup → sub-page integration → code cleanup. Rounds 2–4 are conditionally skipped when the relevant resource/template/data dependency is absent. If a round's LLM response fails to parse, it falls back to the previous round's output rather than aborting.

### Critical conventions (don't regress these)

- **JSON Schema, not marker tags.** All structured migration responses use provider-native JSON mode. Business prompts are Chinese and each call supplies an explicit schema. `src/llm/json_output.py` strictly parses the complete response, validates the required schema subset, and uses the same model for at most one repair attempt. Do not reintroduce marker extraction, Markdown JSON guessing, or silent raw-response fallbacks.
- **No `<Grid>`.** Grid support was deliberately removed (commits c11374f / 8b68871). Generated layouts must use `<Box>` and `<Stack>`.
- **Page component patterns.** `MainWindow` takes no props and imports state from `./data`; Dialog/Modal components take `{ open, onClose }` and wrap content in MUI `<Dialog>`. Generated code must not import nonexistent files — implement inline instead of leaving dangling imports.
- **Pinned target versions** baked into prompts: React 18.2.0, MUI 5.18.0, Emotion 11.11.x, TypeScript 5.9.3.

### Per-agent model selection

All generative migration agents currently use the low tier resolved from `OPENAI_MODEL_LOW` (`gpt-5.6-luna`), with `temperature=0` and JSON mode. Central model-tier defaults and environment lookup live in `src/llm/config.py`; use `LLMConfig.json_mode_config()` instead of hard-coding model strings at call sites. AutoGen 0.7.5 requires explicit model metadata for the new 5.6 names; `src/llm/client.py` supplies it centrally. Resource migration uses no LLM.

### Shared helpers introduced by the refactor (prefer these)

- **`src/common/logging.py`** — one console/file logging contract; new code imports `get_logger` here, while `src/logger.py` remains a compatibility shim.
- **`src/agents/base.py`** — `BaseRoutedAgent`, `register_agent`, and `default_agent_id`; all migration Agents inherit it through `BaseMigrationAgent`, and `MigrationTeam` registers factories through the helper.
- **`src/parser/io_utils.py`** — `read_json(path)` / `write_json(path, data, *, indent=2)`. All parser JSON I/O goes through these (byte-identical to the old scattered `json.dump(..., ensure_ascii=False, indent=2)`). Don't re-introduce ad-hoc `open()+json` in the parser.
- **`PageAssemblyAgent._run_assembly_round(label, temp_tsx_path, page_name, round_coro)`** — the rounds-2–7 "call → empty-response fallback to previous temp → save → log" boilerplate. Round 1 stays a special inline seed (no previous temp to fall back to). Add new rounds via this helper; keep the exact label/log strings.
- **`LLMConfig.json_mode_config()`** / `LLMConfig.model_for_tier(tier)` / `LLMConfig._first_env(*names)` — low-tier JSON config + model/API env lookup.
- Parser output is now **deterministic**: `cs_dependency.json`'s `defined_types` is `sorted()` (was `list(set(...))`, order varied per Python process). Keep set-derived serialized lists sorted.

## Repo layout

`repos/` local input WPF projects (git-ignored and untracked) · `outputs/` parser results + migration intermediates (git-ignored) · `results/` final React output (git-ignored) · `rags/mui/` MUI component docs/mappings used by `MUISelectAgent` · `tests/{agents,common,llm,migration,parser}/` mirrors the five `src/` packages · `scripts/` holds maintenance checks · `logs/` & `nohup.out` hold run logs.

## Local baseline and research scope

Read these before changing architecture or experimental behavior:

- `docs/guides/shared-development-conventions.md`
- `CLAUDE.md`, `README.md`, `docs/DEPENDENCIES.md`, `docs/GIT_WORKFLOW.md`
- `docs/02_前端UI迁移研究稿.md`
- `docs/03_面向代码可复用性增强的融合研究方案.md`
- `docs/LOCAL_DEVELOPMENT_BASELINE.md`

The two research documents describe future dissertation methods and experiments. They are context, not a current implementation specification. Do not replace the existing two-stage parser/migration flow, agent count, retrieval path, seven assembly rounds, or pinned React/MUI versions merely to match those drafts. The C++ reuse project and this UI repository remain separate unless the user explicitly requests otherwise.

Verified parser baseline at commit `54e23ffd5c58`: all four local input projects parse successfully and all 86 generated JSON files validate. On 2026-07-17 the configured relay passed luna connectivity plus synthetic component, MUI selection, C#, data, four-round assembly, and one-control page-pipeline smokes. The user explicitly confirmed this repository is open source and approved real-source relay tests: real `LineItem`, all three ExpenseItDemo data resources, and `ViewChartWindow` (9/9 controls, six assembly rounds) passed. The page finalizer now preserves function-local names, enforces the exact root/dialog props contract, retains required data imports, validates object-vs-array access, and performs at most one bounded repair before failing closed. Do not generalize this approval to private or enterprise code. Treat `docs/LOCAL_DEVELOPMENT_BASELINE.md` as the detailed source of truth.

## Git

Work on `master`, push to `origin master`. Commit messages follow the existing Chinese convention `W2MR <version>: <描述>` (see `git log`); `docs/GIT_WORKFLOW.md` documents the team's flow.
