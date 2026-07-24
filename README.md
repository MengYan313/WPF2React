# WPF2React

当前版本：**W2MR 4.6**。

WPF2React 将 WPF 项目的 XAML、C#、资源和依赖关系解析为结构化中间数据，再通过 AutoGen Agent 生成 React、TypeScript 与静态资源。

## 目录

```text
WPF2React/
├── src/       # parser、migration 与共享基础设施
├── tests/     # 与 src 功能包对应的测试
├── repos/     # 本地 WPF 输入，所有项目平级存放
├── outputs/   # 解析、迁移上下文和评价中间产物
├── results/   # 最终迁移代码与冻结结果
├── logs/      # 每次命令的追加日志
├── docs/      # 设计、评估与研究说明
├── rags/      # 第三方 MUI 检索语料
└── scripts/   # 数据集与完整性审计工具
```

`repos/`、`outputs/`、`results/` 和 `logs/` 默认不纳入版本控制。正式数据集和本地样例边界见 [repos/README.md](repos/README.md)。

## 安装与配置

已验证环境为 Python 3.11：

```bash
/opt/homebrew/bin/python3.11 -m venv .venv
.venv/bin/python -m pip install -r requirements-local.lock
.venv/bin/python -m pip check
```

从 `.env.example` 创建根目录 `.env` 并填入模型端点、密钥和低档模型。迁移会把源码上下文发送到该端点，运行前应确认成本与数据披露范围。

## 最小流水线

```bash
.venv/bin/python -m src.parser ExpenseItDemo
.venv/bin/python -m src.migration ExpenseItDemo
```

Parser 的七阶段中间数据写入 `outputs/ExpenseItDemo/`；迁移后的最终代码写入 `results/ExpenseItDemo/`。当前迁移器不生成完整 React 工程骨架，运行生成代码前需要自行接入含 `package.json`、TypeScript 配置和应用入口的工程。

关键阶段会在交互式控制台显示进度条，并把事件和错误追加到 `logs/<run-name>.log`。

## 模块入口

- [Parser](src/parser/README.md)
- [迁移编排](src/migration/README.md)
- [迁移 baseline](src/migration/baselines/README.md)
- [迁移评价](src/migration/evaluation/README.md)
- [Agent 基础设施](src/agents/README.md)
- [LLM 基础设施](src/llm/README.md)
- [公共基础设施](src/common/README.md)

详细设计从[文档索引](docs/README.md)进入；模块职责和产物边界见[仓库架构](docs/guides/repository-architecture.md)，验证顺序见[本地基线](docs/guides/local-baseline.md)。
