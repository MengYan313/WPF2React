# WPF2React

WPF2React 是一个将 WPF/XAML 项目迁移为 React + TypeScript + Material UI 的小型实验项目。它先通过静态分析生成控件树和依赖，再由多 Agent 迁移组件与页面。

## 当前流程

| 阶段 | 入口 | 产物 |
| --- | --- | --- |
| WPF 解析 | `python -m src.parser <project>` | `outputs/<project>/` 中的 C#/XAML、控件树和依赖 |
| React 迁移 | `python -m src.migration <project>` | `results/<project>/` 中的 TSX 与静态资源 |
| 只读评价 | `python -m src.migration.evaluation ...` | 编译、组件、页面和视觉指标 |

解析器使用仓库相对路径作为文件和页面 ID。迁移顺序是资源 → C# → 数据 → 页面；页面内部自底向上迁移控件，再组装完整 TSX。标准 WPF 控件使用直接映射，自建控件通过本地 MUI 知识库检索。

项目只支持当前解析和迁移产物，不使用内容哈希、提交哈希或项目版本字段作为流程门禁。

## 环境

```bash
python3.11 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
cp .env.example .env
```

`requirements-local.lock` 仅保留在本机并由 Git 忽略。迁移会向 `.env` 配置的模型端点发送源码上下文，运行前请确认数据披露范围和调用成本。

## 最小示例

将 WPF 项目放入 `repos/<project>/`：

```bash
.venv/bin/python -m src.parser ExpenseItDemo
.venv/bin/python -m src.migration ExpenseItDemo
```

使用当前实验页集：

```bash
.venv/bin/python scripts/build_experiment_page_set.py
.venv/bin/python -m src.migration Prism \
  --output-base-dir outputs/parser-completeness/current \
  --page-set docs/research/experiment-page-set.json
```

在隔离目录批量运行完整 MigraUI 实验：

```bash
.venv/bin/python scripts/run_migration_experiment.py \
  --run-id <run-id> \
  --parser-output-base-dir outputs/parser-completeness/current \
  --project <project>
```

构建并执行评价清单：

```bash
.venv/bin/python -m src.migration.evaluation build-manifest ExpenseItDemo \
  --target-root results/ExpenseItDemo \
  --output outputs/ExpenseItDemo/evaluation_manifest.json

.venv/bin/python -m src.migration.evaluation run \
  outputs/ExpenseItDemo/evaluation_manifest.json \
  --method-id MigraUI --run-id seed-1 \
  --output-dir outputs/evaluation/MigraUI/seed-1
```

迁移器输出源码与静态资源，不生成 `package.json`、TypeScript 配置和应用入口。

## 验证

```bash
.venv/bin/python -m unittest discover -s tests -t . -v
```

更多说明见 [`src/parser/README.md`](src/parser/README.md)、[`src/migration/README.md`](src/migration/README.md)、[`src/migration/evaluation/README.md`](src/migration/evaluation/README.md) 和 [`docs/research/experiment-page-set.md`](docs/research/experiment-page-set.md)。
