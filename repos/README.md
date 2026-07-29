# 数据集仓库

`repos/` 只保存本地 WPF 源码输入。每个项目必须直接位于本目录，禁止按候选来源、筛选状态或用途再建立中间分组目录。仓库源码由 Git 忽略；只有本说明进入版本控制。

正式实验项目以本地 `results/dataset/dataset-manifest.json` 中状态为“保留”或“条件保留”的 20 项为准。`SimpleTrader`、`worlds-simplest-csharp-wpf-mvvm-example`、`MVVM`、`Page-Navigation-using-MVVM`、`Record-Book-App-WPF-MVVM`、`ai-dev-gallery` 与补充候选 `NeeView` 已排除，不应保留本地副本。`CustomComboBox`、`DataBindingDemo`、`EditingExaminerDemo` 和 `ExpenseItDemo` 是本地冒烟样例，不计入正式数据集。

正式 20 项是用于阶段一完整性分析和后续分层迁移实验的广义语料库，不应直接混算一个扁平的迁移主指标。项目按领域、项目形态、页面规模、迁移挑战和建议实验角色分类为主业务集、压力集、框架导航专项、组件映射专项、平台专项和低复杂度 sanity；分类口径、逐项目标签与抽样原则见[数据集现状统计](../docs/research/wpf-experiment-dataset-status.md#5-数据集多轴分类)，可重建的机器可读分类位于 `results/dataset/dataset-statistics.json` 的 `taxonomy.projects`。

## 快速使用

```bash
.venv/bin/python -m src.parser ExpenseItDemo
.venv/bin/python scripts/run_dataset_parse.py ExpenseItDemo \
  --output-base-dir outputs/dataset-analysis/smoke
```

重建数据集清单和统计：

```bash
.venv/bin/python scripts/build_dataset_manifest.py
.venv/bin/python scripts/analyze_dataset_stats.py
```

筛选证据见[数据集现状统计](../docs/research/wpf-experiment-dataset-status.md)和[逐项排查记录](../docs/research/wpf-experiment-dataset-audit.md)。
