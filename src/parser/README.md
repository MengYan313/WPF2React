# Parser 模块

本模块把 `repos/<project>/` 中的 C#、XAML 和项目文件转换为可追溯 JSON，并依次构建 C#、页面、资源、控件和间接资源依赖。所有产物是可再生成的中间数据，统一写入 `outputs/<project>/`。

控件依赖产物同时保存两棵树：`controls/control_count` 只含基础控件并保持冻结评测兼容，`migration_controls/migration_control_count` 额外包含可视自建控件。行为、转换器、命令、ViewModel、Trigger、Transition 等非可视对象仍只进入节点清单，不参与逐控件迁移。

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
