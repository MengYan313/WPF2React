# 仓库架构

WPF2React 将本地 WPF 源码转换为 React、TypeScript 与静态资源。本文只描述实现职责和稳定合同；启动命令集中在根目录及各功能模块的 `README.md`。

## 目录职责

| 路径 | 职责 |
| --- | --- |
| `repos/` | 本地源码输入；项目平级存放且不纳入版本控制 |
| `src/parser/` | 确定性解析、源码身份和依赖图构建 |
| `src/migration/` | Agent 编排、MUI 选择、代码与资源迁移 |
| `src/common/` | 日志、进度显示和源码身份等横切能力 |
| `src/llm/` | 模型配置、客户端和结构化输出合同 |
| `src/agents/` | 两项目统一的 Agent 基类与注册入口 |
| `rags/` | 第三方检索语料，不是项目设计文档 |
| `outputs/` | 可由输入与配置重新生成的中间产物 |
| `results/` | 最终迁移代码与冻结评价结果 |
| `logs/` | 每次命令追加写入的运行日志 |
| `docs/` | 设计、测试、评估和研究说明 |

## 数据流

```text
repos/<project>/
  -> outputs/<project>/{cs,xaml}/
  -> outputs/<project>/dependency/
  -> outputs/<project>/migration/
  -> results/<project>/{*.tsx,*.ts,public/}
  -> outputs/evaluation/<method>/<run>/
  -> results/<frozen-evaluation>/
```

Parser 是迁移的唯一结构化输入来源。它先为仓库相对 POSIX 路径生成稳定 `source_id`，再保存 C# AST、XAML 语义节点和依赖侧车。后续阶段发现旧 schema、越界路径或缺失身份字段时必须失败并提示重新解析，不能把 basename 当成稳定身份。

控件依赖产物的 `controls/control_count` 继续只包含基础控件，用于保持冻结评测分母；`migration_controls/migration_control_count` 额外保留可视自建控件，供页面迁移使用。资源对象、行为、转换器、命令和 ViewModel 等非可视节点仍只进入完整节点清单。

## Parser 七阶段

Parser 依次执行：C# 解析、XAML/csproj 解析、C# 依赖、间接资源、页面依赖、资源依赖和控件依赖。前两阶段失败会中止，因为后续输入不完整；后续分析失败会保留已生成证据，并在命令退出码和汇总中明确标记。

所有 Parser 文件、依赖图和审计报告都属于中间产物，写入 `outputs/`。解析过程不执行输入仓库的构建脚本、安装命令或二进制。

## 迁移四阶段

迁移器依次处理资源、C#、数据和页面。前三个项目级阶段准备共享上下文；页面阶段按依赖图的 `migration_order` 顺序执行。每页结果独立记录成功、失败、依赖和输出路径，单页失败不会抹掉其他页面的结果。

迁移生成的 React/TypeScript 与静态资源属于最终产物，写入 `results/<project>/`。用于调试、恢复、评价或记录模型调用的可再生成数据仍写入 `outputs/`。当前实现不生成完整 React 工程骨架，因此不能把缺失的 `package.json`、Vite 或 TypeScript 配置误报为迁移器已完成的能力。

组件选择分为两条路径：标准控件读取确定性 WPF→MUI 配方；自建控件根据标签、属性、语义引用和用途说明执行名称/别名、BM25 与本地向量融合检索。结构化目录固定目标前端版本和允许 import，低置信结果显式标记为未解析，不回退为通用 `Box`。详细合同见[组件知识库设计](component-knowledge-base.md)。

## 日志与进度

关键解析和迁移阶段在交互式控制台展示进度条。业务事件、失败原因和产物路径通过 `src.common.logging.get_logger()` 追加写入 `logs/<run-name>.log`；进度条本身不作为可复现实验证据。日志不得包含密钥、完整端点或未获授权的私有源码。

## LLM 与 Agent 边界

`src/llm/` 只提供模型与结构化输出基础设施。迁移提示词、消息类型、MUI 检索和回退策略属于 `src/migration/`。Agent 使用 `SingleThreadedAgentRuntime`、强类型消息和显式启动/关闭生命周期；默认生成式调用只使用低档模型，切换档位必须由调用方显式指定。

共享基础设施要求见[两项目共享开发约定](shared-development-conventions.md)，指标和 baseline 分别见[评价指标规范](evaluation-metrics.md)与[baseline 规范](baselines.md)。
