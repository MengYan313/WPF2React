# Parser 模块

本模块把 `repos/<project>/` 中的 C#、XAML 和项目文件转换为可追溯 JSON，并依次构建 C#、页面、资源、控件和间接资源依赖。所有产物是可再生成的中间数据，统一写入 `outputs/<project>/`。

## 启动命令

```bash
.venv/bin/python -m src.parser ExpenseItDemo
```

数据集单项目解析及摘要：

```bash
.venv/bin/python scripts/run_dataset_parse.py ExpenseItDemo \
  --output-base-dir outputs/dataset-analysis/smoke
```

阶段顺序、身份合同和失败边界见[仓库架构](../../docs/guides/repository-architecture.md)，完整性审计见[Parser 完整性研究记录](../../docs/research/parser-completeness-audit.md)。
