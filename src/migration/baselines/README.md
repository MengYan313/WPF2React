# 迁移 Baseline

本模块隔离运行 `RuleTrans-MUI`、`LLM-Direct-Budget` 和 `MigraUI-NoRAG`。各方法共享输入范围与目标工程约束，但不共享会泄漏主方法能力的中间表示或检索结果。

## 启动命令

```bash
.venv/bin/python -m src.migration.baselines --help
.venv/bin/python -m src.migration.baselines RuleTrans-MUI ExpenseItDemo \
  --run-id ruletrans
.venv/bin/python -m src.migration.baselines LLM-Direct-Budget ExpenseItDemo \
  --run-id direct-seed-1
.venv/bin/python -m src.migration.baselines MigraUI-NoRAG ExpenseItDemo \
  --run-id no-rag-seed-1

# 正式数据集的三种方法均传入同一冻结页面集合
.venv/bin/python -m src.migration.baselines RuleTrans-MUI Prism \
  --run-id ruletrans-pages \
  --page-set docs/research/experiment-page-set.json
```

方法边界、预算和产物合同见[baseline 规范](../../../docs/guides/baselines.md)。
