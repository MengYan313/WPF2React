# AGENTS.md

## 跨项目统一开发契约

本仓库与同级仓库保持相互独立，但可复用基础设施必须遵循同一套契约。修改日志、LLM 封装、AutoGen 配置、提示词、目录职责或测试组织方式前，先阅读 `docs/guides/shared-development-conventions.md`；提示词工作还应阅读 `docs/guides/prompt-engineering-guide.md`。共享文件必须在两个仓库中同步更新。

强制约定：

- 项目自有文档统一使用中文，包括 `README.md`、`AGENTS.md` 和 `docs/**/*.md` 的标题、正文、表格说明与图注；仅代码、命令、路径、模型/API 名称、标准缩写、公式、JSON 字段和必要引文保留英文。第三方论文与 `rags/` 等原始检索语料保持来源语言，不得伪装成项目自有中文文档。开发文档统一放在 `docs/guides/`，研究材料统一放在 `docs/research/`；除约定入口文件和带编号的研究稿外，Markdown 文件名使用小写 kebab-case。评估指标、baseline 复现和本地基线分别固定命名为 `evaluation-metrics.md`、`baselines.md` 和 `local-baseline.md`。
- 使用 `repos/` 存放本地源码仓库输入，`outputs/` 存放可复现的中间产物，`results/` 存放最终产物，`logs/` 存放运行日志，`tests/` 存放测试，`docs/` 存放纳入版本控制的文档。`repos/` 必须保持忽略且不受 Git 跟踪；不要增加重复的 `inputs/` 别名。
- 新日志代码统一使用 `from src.common.logging import get_logger`。同一命令的所有模块日志均以追加方式写入 `logs/<run-name>.log`；`src.logger` 仅用于兼容旧代码。
- LLM 代码统一从 `src.llm` 导入共享 API。根目录 `.env` 加载、模型档位、GPT-5.6 元数据、客户端创建、JSON 模式、Schema 校验、单次 JSON 修复及客户端关闭逻辑都必须集中在该包中。只有低档模型可以作为隐式默认值。
- 业务提示词和解释性字段使用中文；仅代码、模型/API 名称、必要技术术语及 JSON 字段名保留英文。结构化调用使用 `build_json_system_prompt(...)` 构建稳定的系统提示词，启用原生 JSON 模式并提供明确的 JSON Schema；不得使用 `[JSON]` 或领域标记包装响应。
- AutoGen 代码统一使用 `SingleThreadedAgentRuntime`、强类型消息、`BaseRoutedAgent`、`register_agent(...)`、`default_agent_id(...)`，并遵循 `start -> try/finally -> stop` 生命周期。Agent 之间通过路由消息通信。
- 离线测试必须可确定复现，且不得触发下载或付费调用。真实 LLM 测试必须明确模型、限制调用次数、审查成本与隐私，并将冒烟测试产物单独存放。
- 修改共享文件后，运行 `.venv/bin/python scripts/check_shared_infrastructure.py --other ../<sibling>`。两个项目可以保留各自已验证的 Python 次版本和领域依赖。

## 提示词开发规范

- 日常新增、修改、重写或评审 LLM 提示词时，先阅读本地 `docs/guides/prompt-engineering-guide.md`，无需每次访问官网。
- 目标模型/API 变化、用户要求最新实践、出现无法解释的持续回归或准备冻结正式实验配置时，使用 `$openai-docs` skill 刷新本地指南，并同步两个仓库。
- 官方指南是模型能力与 API 行为的最终来源；本地指南负责保存已经采用的稳定实践。两者都必须服从项目实际配置、领域契约和用户明确要求，不得假设项目必须使用 GPT-5.6。
- 需要刷新但 `$openai-docs` 不可用时，应明确说明，并基于本地指南继续处理。

本文件用于指导 Codex 在本仓库中处理代码。

## 项目简介

WPF2React 将 WPF（XAML + C#）项目转换为 React + TypeScript + Material-UI 项目。项目采用两阶段流水线：先由确定性**解析器**提取结构和依赖，再由基于 `autogen-core` 构建、由 LLM 驱动的**多 Agent 迁移系统**完成转换。

## 命令

### 当前 macOS 工作区

Linux conda 路径 `/home/wenxinyao/anaconda3/envs/autogen` 仅为历史记录，本机不存在该路径。在 `/Users/sophon/Codex/WPF2React` 中始终使用项目本地虚拟环境：

- Python 可执行文件：`/Users/sophon/Codex/WPF2React/.venv/bin/python`。
- 已安装的基础解释器：Homebrew `python@3.11`，路径为 `/opt/homebrew/bin/python3.11`（Python 3.11.12，arm64）。
- 使用 `source .venv/bin/activate` 激活环境，或优先显式调用 `.venv/bin/python`。
- 不得向 `/usr/bin/python3`、Command Line Tools Python 或全局 Homebrew site-packages 目录安装项目依赖。
- 使用 `python3.11 -m venv .venv` 创建已验证的 macOS arm64 环境，并执行 `.venv/bin/python -m pip install -r requirements-local.lock` 安装依赖。

源码和当前依赖元数据要求 Python 3.10 或更高版本。Python 3.11 是已验证基线；详见 `docs/guides/local-baseline.md`。

```bash
# 配置当前工作区
/opt/homebrew/bin/python3.11 -m venv .venv
.venv/bin/python -m pip install -r requirements-local.lock
```

解析、迁移、baseline 与评价的启动命令只维护在根 `README.md`、`repos/README.md` 及对应 `src/*/README.md`；详细设计文档和本文件只引用这些入口。

领域集成测试是独立的异步脚本，不是 pytest 测试套件（`requirements.txt` 中的 pytest 条目已被注释）。共享基础设施提供离线 `unittest`。从仓库根目录运行：

```bash
.venv/bin/python -m unittest tests.common.test_shared_infrastructure -v
.venv/bin/python -m tests.parser.test_parser_pipeline            # 离线解析器冒烟测试
.venv/bin/python -m unittest tests.parser.test_dataset_parser_regressions -v  # 数据集发现的通用解析回归
.venv/bin/python -m tests.llm.test_model_config                  # 离线模型档位配置测试
.venv/bin/python -m tests.llm.test_connectivity                  # 一次低档 LLM 调用
.venv/bin/python -m tests.migration.test_component_smoke         # 一次组件生成调用
.venv/bin/python -m tests.migration.test_mui_select_smoke        # 合成自定义控件选择
.venv/bin/python -m tests.migration.test_cs_smoke                # 合成 C# 迁移与分析
.venv/bin/python -m tests.migration.test_data_smoke              # 一次合成数据迁移调用
.venv/bin/python -m tests.migration.test_page_assembly_smoke     # 四次合成组装调用
.venv/bin/python -m tests.migration.test_page_pipeline_smoke     # 单控件合成页面流水线
.venv/bin/python -m tests.migration.test_single_page_migration   # 迁移一个页面（ExpenseItDemo/ViewChartWindow）
.venv/bin/python -m unittest tests.migration.test_evaluation -v  # 组件/页面/调用三层离线评测
.venv/bin/python -m unittest tests.migration.test_visual_evaluation -v  # 截图对视觉评测（Fake LLM）
.venv/bin/python -m tests.migration.test_agents
.venv/bin/python -m tests.migration.test_cs_migration
.venv/bin/python -m tests.migration.test_data_migration
.venv/bin/python -m tests.llm.test_examples
```

测试模块应放在与 `src/` 中源码包对应的目录下：`tests/agents/`、`tests/common/`、`tests/parser/`、`tests/migration/` 和 `tests/llm/`。不得在 `tests/` 根目录增加重复的兼容运行脚本。
`tests.migration.test_single_page_migration` 必须验证最终按页面 ID 镜像生成的 `results/{project}/{relative-page}.tsx`，而不能只验证迁移中间 JSON；生成代码存在错误时，脚本必须以非零状态退出。

## 环境配置

根目录 `.env` 通过 `python-dotenv` 加载：

- `OPENAI_API_KEY`（必需）。
- `OPENAI_BASE_URL`（当前配置的 OpenAI 兼容中转服务必需）。
- `OPENAI_MODEL_LOW=gpt-5.6-luna`。
- `OPENAI_MODEL_MEDIUM=gpt-5.6-terra`。
- `OPENAI_MODEL_HIGH=gpt-5.6-sol`。

当前运行时有意只通过 `LLMConfig.json_mode_config()` 使用 `OPENAI_MODEL_LOW`。中档和高档模型保留给后续明确的路由决策。`MUISelectAgent` 中的 `text-embedding-3-small` 是嵌入模型，不属于生成式 LLM 档位。

不得打印、记录、提交密钥值，也不得将企业源码或数据复制到未经批准的环境。只能报告环境变量是否存在。`.env` 文件和生成产物均已被忽略。已验证的 Node 环境为 Node 23.11.0 + npm 11.6.2；在真实 `package.json` 存在前，不得安装生成项目的依赖。语义 MUI 选择器首次使用时还需要 `all-MiniLM-L6-v2` 模型；建立基线时该模型尚未缓存。

## 架构

**阶段 1——解析器**（`src/parser/`，入口为 `__main__.py:analyze_project`）。分析器按固定顺序运行，后续步骤消费前序输出。tree-sitter 解析 C#；lxml 解析 XAML，并以 ElementTree 作为后备。源码文件唯一 ID 是带扩展名的仓库相对 POSIX 路径，页面 ID 是对应 XAML 的仓库相对路径；解析 JSON、控件树和后续迁移产物都镜像该目录结构。所有结果均写入 `outputs/{project}/`，尤其是迁移阶段读取的 `outputs/{project}/dependency/`。页面级核心产物是 `dependency/controls/{page-id}.json`（控件树及 `root_info.template`/`root_info.data`）；`page_dependency.json` 的键和 `migration_order` 均使用页面 ID。

**阶段 2——迁移**（`src/migration/`）。`MigrationOrchestrator` 驱动整体顺序：资源 → C# 文件 → 数据资源 → 页面（按依赖顺序）。`MigrationTeam` 在 autogen-core runtime 中注册 Agent；Agent 通过传递 Pydantic 消息（`messages.py`）通信，而不是直接相互调用。单页流程为：`PageMigrateAgent` 自底向上遍历控件树，对每个节点依次调用 `MUISelectAgent` 和 `ComponentMigrateAgent`，随后将收集的结果交给 `PageAssemblyAgent`。

仓库相对路径 ID 与 TypeScript 组件符号必须分离：前者负责唯一标识、调度、落盘和评测，后者由页面路径确定性派生，仅用于生成代码。不得从 basename/stem 重新构造文件或页面 ID，也不得恢复扁平输出。阶段 1 后续步骤、迁移和 schema 2.0 评测会拒绝缺少 `repository-relative-posix-v1` 的旧产物；升级后应先归档旧扁平输出再重跑解析器。

**只读评测**（`src/migration/evaluation/`）。工程可用性评测按冻结 GT 清单计算组件 C-CPR/C-MR/C-CFR、页面 P-CPR 和调用 PECTPR/覆盖率；视觉评测读取人工登记的 WPF/React 同状态截图对，使用多模态 LLM 输出分项 JSON，再由程序按固定权重计算 Overall Fidelity，美观度独立报告。详细定义见 `docs/guides/evaluation-metrics.md`，运行方式见 `docs/guides/evaluation.md`。

**`PageAssemblyAgent` 的七轮渐进组装**（当前迭代最频繁的代码，参见 Git 日志中的“W2MR”提交）：初始组装 → 资源修正 → 模板集成 → 数据集成 → 布局修正 → 子页面集成 → 代码清理。当缺少相应资源、模板或数据依赖时，第 2～4 轮会按条件跳过。如果某轮 LLM 响应解析失败，则回退到上一轮输出，而不是中止流程。

### 不得破坏的关键约定

- **使用 JSON Schema，不使用标记标签。** 所有结构化迁移响应均使用提供方原生 JSON 模式。业务提示词使用中文，每次调用都提供明确的 Schema。`src/llm/json_output.py` 严格解析完整响应、校验必需的 Schema 子集，并最多使用同一模型修复一次。不得重新引入标记提取、Markdown JSON 猜测或静默回退到原始响应。
- **禁止 `<Grid>`。** Grid 支持已被有意移除（提交 c11374f/8b68871）。生成布局必须使用 `<Box>` 和 `<Stack>`。
- **页面组件模式。** `MainWindow` 不接收 props，并从 `./data` 导入状态；Dialog/Modal 组件接收 `{ open, onClose }`，并使用 MUI `<Dialog>` 包裹内容。生成代码不得导入不存在的文件；应改为内联实现，不得遗留无效导入。
- **提示词中固定的目标版本：** React 18.2.0、MUI 5.18.0、Emotion 11.11.x、TypeScript 5.9.3。

### 各 Agent 的模型选择

当前所有生成式迁移 Agent 都使用由 `OPENAI_MODEL_LOW` 解析得到的低档模型（`gpt-5.6-luna`），并设置 `temperature=0` 和 JSON 模式。集中式模型档位默认值和环境变量查找位于 `src/llm/config.py`；调用位置应使用 `LLMConfig.json_mode_config()`，不得硬编码模型字符串。AutoGen 0.7.5 要求为新的 5.6 模型名称提供明确元数据；`src/llm/client.py` 统一负责该逻辑。资源迁移不使用 LLM。

### 重构后新增的共享辅助模块（应优先使用）

- **`src/common/logging.py`**——统一的控制台与文件日志契约；新代码从这里导入 `get_logger`，`src/logger.py` 仅保留为兼容层。
- **`src/agents/base.py`**——提供 `BaseRoutedAgent`、`register_agent` 和 `default_agent_id`；所有迁移 Agent 通过 `BaseMigrationAgent` 继承该基类，`MigrationTeam` 通过辅助函数注册工厂。
- **`src/parser/io_utils.py`**——提供 `read_json(path)` 和 `write_json(path, data, *, indent=2)`。所有解析器 JSON I/O 都必须通过这些函数完成，其字节输出与原先分散的 `json.dump(..., ensure_ascii=False, indent=2)` 一致。不得在解析器中重新引入临时的 `open()+json` 写法。
- **`src/parser/path_utils.py`**——提供确定性项目文件发现，统一排除 `bin/`、`obj/`、`Generated Files/`、IDE 目录、`node_modules/` 和越界符号链接。C#、XAML 解析器及数据集输入清点必须共用该逻辑。
- **`CsDependencyAnalyzer.generate_migration_order()`**——使用强连通分量压缩真实循环依赖，组内和组间顺序都必须确定，并在 `cycle_groups` 中显式保留限制。不得恢复为遇循环即终止整个项目。
- **`PageAssemblyAgent._run_assembly_round(label, temp_tsx_path, page_name, round_coro)`**——封装第 2～7 轮“调用 → 空响应时回退到上一临时结果 → 保存 → 记录日志”的样板逻辑。第 1 轮是特殊的内联初始种子，没有可回退的上一临时结果。新增轮次时必须使用该辅助函数，并保留准确的标签和日志字符串。
- **`LLMConfig.json_mode_config()`、`LLMConfig.model_for_tier(tier)`、`LLMConfig._first_env(*names)`**——分别负责低档 JSON 配置以及模型/API 环境变量查找。
- 解析器输出现在具有**确定性**：`cs_dependency.json` 的 `defined_types` 使用 `sorted()`，而不是会随 Python 进程改变顺序的 `list(set(...))`。由 set 派生并序列化的列表必须保持排序。

## 仓库布局

`repos/`：本地输入 WPF 项目，已被 Git 忽略且不受跟踪；`outputs/`：解析结果和迁移中间产物，已忽略；`results/`：最终 React 输出，已忽略；`rags/mui/`：供 `MUISelectAgent` 使用的 MUI 组件文档和映射；`tests/{agents,common,llm,migration,parser}/`：与五个 `src` 包对应；`scripts/`：维护检查脚本；`logs/` 和 `nohup.out`：运行日志。

## 本地基线与研究范围

修改架构或实验行为前，应阅读：

- `docs/guides/shared-development-conventions.md`。
- `docs/guides/prompt-engineering-guide.md`。
- `README.md`、`docs/guides/dependencies.md`、`docs/guides/git-workflow.md`。
- `docs/research/02_前端UI迁移研究稿.md`。
- `docs/research/03_面向代码可复用性增强的融合研究方案.md`。
- `docs/research/wpf-experiment-dataset-status.md`。
- `docs/research/wpf-experiment-dataset-audit.md`。
- `docs/guides/local-baseline.md`。

两份研究文档描述未来的论文方法和实验，是背景资料而不是当前实现规范。不得仅为匹配草案而替换现有两阶段解析/迁移流程、Agent 数量、检索路径、七轮组装或固定的 React/MUI 版本。除非用户明确要求，否则 C++ 复用项目和本 UI 仓库保持独立。

提交 `54e23ffd5c58` 的已验证解析器基线显示：四个本地输入项目均解析成功，全部 86 个生成 JSON 均通过校验。2026-07-17，当前配置的中转服务已通过 Luna 连通性测试，以及合成组件、MUI 选择、C#、数据、四轮组装和单控件页面流水线冒烟测试。用户已明确确认本仓库为开源项目，并批准使用真实源码进行中转服务测试：真实 `LineItem`、ExpenseItDemo 的全部三个数据资源及 `ViewChartWindow`（9/9 个控件、六轮组装）均已通过。页面最终处理器现会保留函数局部名称、强制精确的根页面/Dialog props 契约、保留必要的数据导入、验证对象与数组的访问方式，并在失败关闭前最多执行一次有界修复。不得将该批准扩展到私有或企业代码。详细事实来源以 `docs/guides/local-baseline.md` 为准。

## Git 约定

在 `master` 分支工作，并推送到 `origin master`。提交消息沿用现有中文格式 `W2MR <version>: <描述>`（参见 `git log`）；团队流程记录在 `docs/guides/git-workflow.md`。
