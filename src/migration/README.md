# 迁移模块

本模块消费 `outputs/<project>/` 的解析与依赖产物，按“资源 → C# → 数据 → 页面”顺序编排 Agent，最终把 React/TypeScript 文件写入 `results/<project>/`。MUI 检索语料仅作为生成上下文，不改变 Parser 的中间合同。

## 启动命令

```bash
.venv/bin/python -m src.migration ExpenseItDemo
```

运行前必须先完成 Parser，并配置 `.env`。迁移会把源码上下文发送到模型端点，应事先确认成本与披露范围。

架构和数据流见[仓库架构](../../docs/guides/repository-architecture.md)。Baseline 与评价分别见 [baselines/README.md](baselines/README.md) 和 [evaluation/README.md](evaluation/README.md)。
