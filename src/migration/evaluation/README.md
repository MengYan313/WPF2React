# 迁移评价

本模块根据人工核验清单计算组件、页面、调用边与视觉指标。评价输入和中间证据写入 `outputs/evaluation/`，冻结后的最终汇总写入 `results/`。

## 启动命令

```bash
.venv/bin/python -m src.migration.evaluation build-manifest ExpenseItDemo \
  --target-root results/ExpenseItDemo \
  --output outputs/ExpenseItDemo/evaluation_manifest.json

.venv/bin/python -m src.migration.evaluation run \
  outputs/ExpenseItDemo/evaluation_manifest.json \
  --method-id MigraUI --run-id seed-1 \
  --output-dir outputs/evaluation/MigraUI/seed-1

.venv/bin/python -m src.migration.evaluation visual-run \
  outputs/ExpenseItDemo/evaluation_manifest.json \
  --method-id MigraUI --run-id seed-1 --model-tier low \
  --output-dir outputs/evaluation/MigraUI/seed-1
```

指标定义见[评价指标规范](../../../docs/guides/evaluation-metrics.md)，清单与状态说明见[评价指南](../../../docs/guides/evaluation.md)。
