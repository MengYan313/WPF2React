# 分层迁移评测

当前评测器实现两类相互独立的验证：组件编译、页面编译、页面调用测试组成的可执行性评测，以及人工截图对驱动的页面视觉评测。评测器只读取迁移结果，不修改或修复目标代码。

本文侧重清单、命令和输出文件的使用方法。指标分类、完整公式、诊断价值、聚合方式和结论边界见 [WPF→React 迁移评价指标规范](evaluation-metrics.md)。

## 1. 指标

### 1.1 组件

`C-CPR = COMPILE_PASSED 组件数 / GT 组件总数`。

组件判别器先定位对应目标实现，TypeScript 编译器再作最终裁决。默认判别器组合页面路径、TS/TSX 文件名、导出符号、MUI 映射、JSX 标签、源名称和文本证据；同一 JSX occurrence 不会重复分配给多个源组件。后续可以实现 `ComponentJudge` 接口接入 LLM 辅助定位，但 LLM 不能代替编译器决定成功。

互斥终态：

- `NOT_FOUND`；
- `AMBIGUOUS`；
- `COMPILE_FAILED`；
- `COMPILE_PASSED`；
- `EVALUATOR_ERROR`。

`C-MR` 合并前两个定位失败状态，`C-CFR` 统计找到但编译失败。存在 `EVALUATOR_ERROR` 时三个组件比例均为 `null`，避免把缺少编译器等评测环境问题误计为迁移失败。

### 1.2 页面

`P-CPR = PAGE_COMPILE_PASSED 页面数 / GT 页面总数`。

互斥终态：`PAGE_MISSING`、`PAGE_AMBIGUOUS`、`PAGE_COMPILE_FAILED`、`PAGE_COMPILE_PASSED`、`EVALUATOR_ERROR`。

### 1.3 页面调用

`PECTPR = TEST_PASSED 调用边数 / GT 调用边总数`。

只有冻结清单中的每条调用边都配置了测试代码，且没有评测器错误时，PECTPR 才产生数值。源页面或目标页面未通过编译时，该边记为 `PAGE_UNAVAILABLE` 并保留在固定分母中。`call_test_coverage` 单独报告已配置测试的 GT 边覆盖率。

## 2. 构建待核验清单

先运行 Parser，再从 `dependency/controls/{page-id}.json` 和 `page_dependency.json` 生成规则抽取初稿：

```bash
.venv/bin/python -m src.parser ExpenseItDemo
.venv/bin/python -m src.migration.evaluation build-manifest ExpenseItDemo \
  --target-root results/ExpenseItDemo \
  --output outputs/ExpenseItDemo/evaluation_manifest.json
```

生成的清单标记为 `metadata.review_status = "unreviewed"`。正式实验前必须独立核验、补充调用测试并冻结；清单、断言和测试代码不能进入迁移方法的 prompt、RAG 或修复上下文。

组件抽取单位是 Parser `controls` 树中的实例，`page_id` 使用带 `.xaml` 后缀的仓库相对 POSIX 路径，`component_id` 使用稳定的 `page_id:node_path`。schema 2.0 会校验所有页面 ID，并要求非空目标提示包含把同一路径 `.xaml` 替换为 `.tsx` 后的精确镜像路径；评测器不再按 basename 回退搜索。标准控件可以定位到页面内联 JSX，自定义或命名组件也可以定位到独立符号；实际编译范围始终是承载该实现的 TS/TSX 文件及其依赖。

## 3. 配置编译器

目标工程具有 `tsconfig.json` 和本地 `node_modules/.bin/tsc` 时，无需在清单中配置命令。评测器会生成临时 `tsconfig.eval.json`，只编译当前入口及其依赖，不会执行 `npm install` 或隐式下载。

也可以在清单中配置不经过 shell 的命令模板：

```json
{
  "compiler": {
    "command": [
      "node_modules/.bin/tsc",
      "--noEmit",
      "--jsx",
      "react-jsx",
      "{entry}"
    ],
    "timeout_seconds": 120
  }
}
```

可用占位符为 `{entry}`、`{target_root}` 和 `{tsconfig}`。命令以参数数组执行，不支持 shell 管道、重定向或命令替换。

## 4. 配置页面调用测试

每条 GT 边指定测试文件，全局命令负责运行该文件：

```json
{
  "call_tester": {
    "command": [
      "node_modules/.bin/vitest",
      "run",
      "{test_file}"
    ],
    "timeout_seconds": 120
  },
  "call_edges": [
    {
      "edge_id": "MainWindow->CreateExpenseReportDialogBox",
      "source_page": "MainWindow",
      "target_page": "CreateExpenseReportDialogBox",
      "call_type": "dialog",
      "test_file": "tests/navigation/main_to_create.test.tsx",
      "test_command": [],
      "metadata": {}
    }
  ]
}
```

调用测试应验证触发入口、目标页面或 Dialog、必要 props/路由参数，以及适用的关闭或返回接口。边级 `test_command` 可以覆盖全局命令。可用占位符为 `{edge_id}`、`{source_page}`、`{target_page}`、`{target_root}` 和 `{test_file}`。

## 5. 运行评测

```bash
.venv/bin/python -m src.migration.evaluation run \
  outputs/ExpenseItDemo/evaluation_manifest.json \
  --method-id MigraUI \
  --run-id seed-1 \
  --workspace-root . \
  --output-dir outputs/evaluation/MigraUI/seed-1
```

输出：

- `evaluation_report.json`：完整逐项结果和指标汇总；
- `evaluation_records.jsonl`：按组件、页面和调用边保存的逐项证据。

三条实验 baseline 已包含固定目标骨架，可以把 `target_root` 直接指向 `results/baselines/<method>/<run>/<project>`；完整示例见 [UI 迁移 Baseline 运行规范](baselines.md)。各方法仍必须使用同一份已核验并冻结的 manifest，不能为某个方法单独改变分母。

命令、退出码、耗时及截断后的 stdout/stderr 会写入证据；源码正文不会进入评测日志。

## 6. 页面视觉评测

视觉评测使用人工提供的同一页面、同一状态截图：图像 1 固定为原 WPF 页面，图像 2 固定为迁移后 React 页面。将截图对加入冻结清单的 `visual_pairs`：

```json
{
  "visual_pairs": [
    {
      "pair_id": "MainWindow-default",
      "page_id": "MainWindow.xaml",
      "source_image": "screenshots/wpf/MainWindow-default.png",
      "target_image": "screenshots/react/MainWindow-default.png",
      "state_id": "default",
      "state_description": "应用启动后的主窗口，尚未选择报销单",
      "comparison_notes": "两张截图使用相同测试数据",
      "metadata": {}
    }
  ]
}
```

图片相对路径以 `--workspace-root` 为基准。每个截图对调用一次当前档位的多模态模型；响应严格按 JSON Schema 解析，失败时最多使用同一模型修复一次。运行命令：

```bash
.venv/bin/python -m src.migration.evaluation visual-run \
  outputs/ExpenseItDemo/evaluation_manifest.json \
  --method-id MigraUI \
  --run-id seed-1 \
  --model-tier low \
  --workspace-root . \
  --output-dir outputs/evaluation/MigraUI/seed-1
```

`low` 默认解析为项目当前配置的 GPT-5.6-Luna。视觉调用会把两张截图发送到 `.env` 配置的 OpenAI 兼容端点；只有已获准发送的截图才能加入清单。官方模型支持图像输入不等于任意中转服务一定正确转发图像，正式实验前应使用非敏感截图做一次端到端冒烟测试。

### 6.1 分项指标

每项使用 0～100 分，并要求模型输出理由和可见证据：

- `component_fidelity`：可见组件的类型、数量、层级、状态和显隐关系；
- `layout_fidelity`：相对位置、尺寸、对齐、间距、分组和视觉层次；
- `style_fidelity`：颜色、字体、边框、圆角、阴影、图标和视觉密度；
- `content_fidelity`：可见文本、数值、标签、图标语义和数据状态；
- `aesthetic_quality`：迁移后页面自身的清晰度、一致性、层次感和视觉完成度。

程序按固定公式计算忠实度，而不是让模型再给一个不可追溯的总分：

`overall_fidelity = 0.35 × component + 0.30 × layout + 0.20 × style + 0.15 × content`。

`aesthetic_quality` 不进入总忠实度。一个页面可以比原页面更现代、更美观，但这不代表迁移更忠实；论文中应将“忠实度”和“目标页面视觉质量”作为两组结果分别报告。

### 6.2 可比较性与聚合

模型先输出 `comparison_valid`。任一图片不可读、主要区域缺失、页面或状态明显不一致时，五项分数必须为 `null`，该截图对状态为 `INVALID_COMPARISON`，不进入均值。`visual_pair_coverage = EVALUATED 截图对数 / GT 截图对总数`，用于揭示因截图质量或状态不一致造成的样本损失；模型或评测环境故障另记为 `EVALUATOR_ERROR`。

多个页面或状态按有效截图对做宏平均。为避免页面状态数量不一致导致权重偏斜，正式论文实验还应同时报告“先按页面平均、再按项目平均”的结果；当前 JSONL 保留逐截图对结果，可在统计脚本中完成该层聚合。

输出：

- `visual_evaluation_report.json`：完整结果、固定权重和宏平均；
- `visual_evaluation_records.jsonl`：每行一个截图对，包含图片 SHA-256、分项证据、问题严重度与建议。

### 6.3 截图采集约束

同一截图对应尽量固定窗口或 viewport 尺寸、缩放比例、主题、字体、语言、数据、滚动位置、弹窗状态和时间相关内容。截图尺寸不同时，模型按相对几何关系评估，不直接比较像素坐标。每个关键状态应拥有独立 `pair_id`，不要把一个页面的多个状态拼成一张长图。

LLM 视觉评分具有主观性。正式实验宜随机抽取一部分样本由至少两名人工评审独立打分，报告人与人、人与模型的一致性，并冻结模型名、提示词版本和截图清单。当前实现记录 `model`、`prompt_version` 和图片哈希以支持复现。

## 7. 当前边界

- C-CPR 和 P-CPR 只衡量编译层级，不代表完整视觉、行为或语义等价；
- 多个内联组件可能共享同一个页面编译结果，这是当前编译层级定义的一部分；
- 默认判别器是可复现的确定性基线，复杂重命名或跨文件重组可以通过实现新的 `ComponentJudge` 增强；
- 原 `python -m src.migration` 入口仍不生成 React 工程骨架；三条 baseline 入口已生成固定骨架，但仍需在对应目标目录安装锁定依赖后才能执行真实编译指标；
- 截图评测只能衡量可见的静态状态，不能证明交互正确、可访问、响应及时或真实用户满意；这些仍需页面调用测试、浏览器交互测试或用户研究验证。
