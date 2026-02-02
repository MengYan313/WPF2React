# WPF2React

一个用于将 WPF (Windows Presentation Foundation) 项目自动转换为 React + TypeScript + Material-UI 项目的智能迁移工具。

## 项目简介

本项目旨在帮助开发者将基于 XAML 和 C# 的 WPF 应用程序自动迁移到基于 React 的现代 Web 应用程序。通过深度解析 WPF 项目结构、依赖关系和代码逻辑，结合大语言模型（LLM）的代码生成能力，实现从 WPF 到 React 的自动化迁移。

### 核心特性

- **智能解析**：深度解析 XAML 和 C# 代码，提取完整的项目结构和依赖关系
- **多 Agent 协作**：基于 Autogen 的多 Agent 系统，分工协作完成复杂迁移任务
- **渐进式迁移**：采用多轮渐进式修改策略，逐步优化迁移结果
- **依赖感知**：自动分析页面、组件、资源和数据依赖，确保迁移顺序正确
- **代码质量保证**：遵循 React 和 TypeScript 最佳实践，生成高质量代码

## 项目结构

```
WPF2React/
├── src/                    # 源代码目录
│   ├── parser/            # 解析器模块（详见下文）
│   ├── migration/         # 迁移模块（详见下文）
│   ├── llm/               # LLM 客户端和配置
│   └── logger.py          # 日志工具
├── repos/                 # WPF 示例项目
│   ├── ExpenseItDemo/     # 费用报销示例
│   ├── DataBindingDemo/   # 数据绑定示例
│   └── ...
├── outputs/               # 解析结果输出目录（git 忽略）
│   └── {project_name}/
│       ├── dependency/    # 依赖分析结果
│       └── migration/      # 迁移中间结果
├── result/                # 最终迁移结果（git 忽略）
│   └── {project_name}/
│       ├── *.tsx          # React 页面组件
│       ├── *.ts           # TypeScript 数据模型
│       └── public/        # 静态资源
├── rag/                   # RAG 知识库
│   └── mui/               # MUI 组件文档和映射
├── tests/                 # 测试模块
├── .gitignore
├── README.md
└── requirements.txt       # Python 依赖
```

## 核心模块

### 1. src/parser - 解析器模块

解析器模块负责深度解析 WPF 项目，提取所有必要的结构信息和依赖关系，为迁移提供数据基础。

#### 1.1 主要功能

**文件解析：**
- **C# 文件解析** (`cs_parser.py`)：使用 tree-sitter 解析 C# 语法树，提取类、方法、属性、字段等结构信息
- **XAML 文件解析** (`xaml_parser.py`)：解析 XAML/XML 文件，提取元素结构、属性、命名空间和源代码

**依赖分析：**
- **C# 文件依赖分析** (`cs_dependency.py`)：分析 C# 文件之间的引用关系，确定迁移顺序
- **页面依赖分析** (`page_dependency.py`)：分析页面之间的导航和引用关系，构建页面依赖图
- **资源依赖分析** (`resource_dependency.py`)：分析静态资源（图片、样式等）的引用关系
- **控件依赖分析** (`control_dependency.py`)：分析 XAML 控件树结构，提取组件层级关系
- **间接资源分析** (`indirect_resource_analysis.py`)：分析数据资源和模板资源的引用关系

#### 1.2 工作流程

解析器模块按以下顺序执行（`src/parser/__main__.py`）：

```
1. 解析 C# 文件
   └─> 输出：outputs/{project}/cs/{file}.cs.json

2. 解析 XAML 文件
   └─> 输出：outputs/{project}/xaml/{file}.xaml.json

3. 分析 C# 文件依赖关系
   └─> 输出：outputs/{project}/dependency/cs_dependency.json
   └─> 包含：迁移顺序、文件依赖图

4. 分析间接资源引用/依赖
   └─> 输出：outputs/{project}/dependency/indirect_resource_dependency.json
   └─> 输出：outputs/{project}/dependency/data_resources.json
   └─> 输出：outputs/{project}/dependency/template_resources.json

5. 分析页面依赖关系
   └─> 输出：outputs/{project}/dependency/page_dependency.json
   └─> 包含：页面依赖图、迁移顺序

6. 分析资源依赖关系
   └─> 输出：outputs/{project}/dependency/resource_dependency.json

7. 分析控件依赖关系
   └─> 输出：outputs/{project}/dependency/control_{page}.json
   └─> 包含：控件树结构、组件层级关系
```

#### 1.3 使用方式

**命令行：**
```bash
python -m src.parser ExpenseItDemo
```

**编程方式：**
```python
from src.parser import analyze_project

results = analyze_project("ExpenseItDemo", output_base_dir="outputs")
```

#### 1.4 输出文件格式

**C# 解析结果** (`{file}.cs.json`)：
```json
{
  "source_file": "path/to/file.cs",
  "file_type": "page",
  "root": {
    "node_type": "class",
    "name": "MainWindow",
    "modifiers": ["public", "partial"],
    "base_types": ["Window"],
    "source_code": "public partial class MainWindow : Window { ... }",
    "children": [
      {
        "node_type": "method",
        "name": "InitializeComponent",
        "return_type": "void",
        "source_code": "..."
      }
    ]
  }
}
```

**XAML 解析结果** (`{file}.xaml.json`)：
```json
{
  "source_file": "path/to/file.xaml",
  "namespaces": {
    "default": "http://schemas.microsoft.com/winfx/2006/xaml/presentation",
    "x": "http://schemas.microsoft.com/winfx/2006/xaml"
  },
  "root": {
    "tag": "Window",
    "full_tag": "{http://...}Window",
    "attributes": { "Title": "MainWindow", "Width": "640" },
    "source_code": "<Window xmlns=\"...\" ...>...</Window>",
    "children": [...]
  }
}
```

**页面依赖关系** (`page_dependency.json`)：
```json
{
  "total_pages": 3,
  "migration_order": ["MainWindow", "CreateExpenseReportDialogBox", "ViewChartWindow"],
  "pages": {
    "MainWindow": {
      "dependencies": [],
      "dependents": ["CreateExpenseReportDialogBox"]
    },
    "CreateExpenseReportDialogBox": {
      "dependencies": ["MainWindow"],
      "dependents": ["ViewChartWindow"]
    }
  }
}
```

---

### 2. src/migration - 迁移模块

迁移模块基于多 Agent 协作架构，使用 Autogen Runtime 管理 Agent 生命周期和消息路由，实现智能化的代码迁移。

#### 2.1 架构设计

**核心组件：**

1. **MigrationOrchestrator** (`migration_orchestrator.py`)：迁移编排器，负责协调整个迁移流程
2. **MigrationTeam** (`migration_team.py`)：迁移团队，管理所有 Agent 的注册和消息路由
3. **BaseMigrationAgent** (`base.py`)：所有 Agent 的基类，提供统一的 LLM 调用接口

**Agent 系统：**

- **MUISelectAgent** (`mui_select_agent.py`)：为 WPF 组件选择最合适的 MUI 组件
- **ComponentMigrateAgent** (`component_migrate_agent.py`)：将单个 WPF 组件迁移为 React 组件
- **PageMigrateAgent** (`page_migrate_agent.py`)：协调整个页面的迁移，管理组件树的递归迁移
- **PageAssemblyAgent** (`page_assembly_agent.py`)：将已迁移的组件整合成完整的 React 页面
- **ResourceMigrateAgent** (`resource_migrate_agent.py`)：迁移静态资源文件（图片、样式等）
- **CsMigrateAgent** (`cs_migrate_agent.py`)：将 C# 类文件迁移为 TypeScript 文件
- **DataMigrateAgent** (`data_migrate_agent.py`)：迁移数据资源（XAML 数据绑定、资源字典等）

#### 2.2 迁移流程

迁移模块按以下顺序执行（`src/migration/__main__.py`）：

```
第一步：迁移资源文件
  └─> ResourceMigrateAgent
  └─> 输出：result/{project}/public/{resource}

第二步：迁移 C# 文件
  └─> CsMigrateAgent（批量迁移）
  └─> 输出：result/{project}/{file}.ts

第三步：迁移数据资源
  └─> DataMigrateAgent
  └─> 输出：result/{project}/data.ts
  └─> 输出：outputs/{project}/migration/data_descriptions.json

第四步：迁移页面（按依赖顺序）
  └─> 对每个页面：
      1. PageMigrateAgent 协调迁移
         ├─> 递归遍历控件树（从叶子节点向上）
         ├─> 对每个组件：
         │    ├─> MUISelectAgent 选择 MUI 组件
         │    └─> ComponentMigrateAgent 迁移组件
         └─> 收集所有组件迁移结果
      2. PageAssemblyAgent 整合页面
         ├─> 第一轮：初始组装
         ├─> 第二轮：资源修复（如有资源文件）
         ├─> 第三轮：模板整合（如有模板依赖）
         ├─> 第四轮：数据整合（如有数据依赖）
         ├─> 第五轮：布局优化
         ├─> 第六轮：子页面集成
         └─> 第七轮：代码规范
      3. 输出完整页面代码
  └─> 输出：result/{project}/{page}.tsx
```

#### 2.3 Agent 详细说明

##### MUISelectAgent

**职责：** 为 WPF 组件选择最合适的 MUI 组件（1-3 个候选）

**输入：**
- WPF 组件源代码
- MUI 组件文档（从 RAG 知识库加载）

**输出：**
- 选中的 MUI 组件列表（JSON 格式）
- 每个组件的使用说明和示例

**特点：**
- 使用 JSON 模式确保结构化输出
- 考虑视觉外观、交互模式、功能需求
- 兼容 MUI v5.18.0 API

##### ComponentMigrateAgent

**职责：** 将单个 WPF 组件迁移为 React 组件

**输入：**
- WPF 组件源代码
- 选中的 MUI 组件信息
- 依赖代码（父组件、子组件已迁移的代码）
- MUI 组件使用示例

**输出：**
- 迁移后的 React 组件代码（TypeScript）
- 组件导入语句
- 迁移说明

**特点：**
- 使用 JSON 模式确保结构化输出
- 支持递归迁移（子组件先迁移）
- 保留组件逻辑和交互行为

##### PageMigrateAgent

**职责：** 协调整个页面的迁移过程

**工作流程：**
1. 加载 `control_{page}.json` 文件（控件依赖分析结果）
2. 递归遍历控件树，从叶子节点开始向上迁移
3. 对每个组件：
   - 发送 `MUISelectionRequest` 给 MUISelectAgent
   - 接收 `MUISelectionResponse`
   - 发送 `ComponentMigrationRequest` 给 ComponentMigrateAgent
   - 接收 `ComponentMigrationResponse`
4. 收集所有组件迁移结果
5. 发送 `PageAssemblyRequest` 给 PageAssemblyAgent
6. 接收 `PageAssemblyResponse`（完整页面代码）

**特点：**
- 使用消息传递与其他 Agent 通信（Autogen 最佳实践）
- 管理迁移结果缓存，避免重复迁移
- 支持依赖注入（子组件迁移结果传递给父组件）

##### PageAssemblyAgent

**职责：** 将已迁移的根组件整合成完整的 React 页面

**多轮渐进式修改策略：**

1. **第一轮：初始组装**
   - 修正函数签名格式
   - 添加必要的 React 导入
   - 组装组件结构
   - 根据依赖信息判断页面类型（MainWindow vs Dialog/Modal）

2. **第二轮：资源修复**（可选，仅在存在资源文件时执行）
   - 修复资源引用路径
   - 确保资源引用正确

3. **第三轮：模板整合**（可选，仅在存在模板依赖时执行）
   - 集成模板依赖（从 `control_{page}.json` 的 `root_info.template` 读取）
   - 应用模板样式和结构
   - 忽略无效或不可迁移的模板部分

4. **第四轮：数据整合**（可选，仅在存在数据依赖时执行）
   - 集成数据依赖（从 `control_{page}.json` 的 `root_info.data` 读取）
   - 添加数据导入和绑定
   - 严格遵循数据命名规范（camelCase 常量/属性，PascalCase 接口）

5. **第五轮：布局优化**
   - 比较原始 WPF 页面代码与当前 React 代码的布局差异
   - 修复组件迁移时可能遗漏的全局页面布局问题
   - 使用 MUI 布局组件（优先使用 `<Box>` 和 `<Stack>`，不使用 `<Grid>`）
   - **关键要求**：不能导入不存在的文件，删除不存在的 import 语句并在代码中直接实现相应组件

6. **第六轮：子页面集成**
   - 集成子页面组件（Dialog、Modal 等）
   - 添加页面间交互逻辑（`open`/`onClose` props）
   - 确保所有直接依赖的子页面都包含在代码中

7. **第七轮：代码规范**
   - 统一代码风格和结构
   - 优化导入语句顺序
   - **错误检查与修复**：
     - 检查并删除未使用的 Props 接口（MainWindow 不应有 Props）
     - 检查并修复命名冲突（不能定义与组件同名的变量/函数）
     - 删除未使用的接口、类型、变量或导入

**特点：**
- 使用非 JSON 模式（返回纯代码）
- 严格的导入限制（只允许官方 React/MUI 组件、子页面、数据资源）
- 遵循页面组件模式（MainWindow 无 props，Dialog 使用 `{ open, onClose }`）
- 错误处理机制：如果某轮 LLM 响应解析失败返回空字符串，自动使用上一轮的结果继续执行
- 条件跳过机制：根据是否存在相关资源/数据/模板，智能跳过不必要的组装轮次

##### CsMigrateAgent

**职责：** 将 C# 类文件迁移为 TypeScript 文件

**迁移规则：**
- 优先使用 `public` 而非 `private`（便于 React 组件访问）
- 简化 getter/setter（无逻辑的属性转为简单属性）
- MainWindow 类不接收 props，使用 `useState` 和 `data.ts` 导入
- 使用接口 + 工厂函数模式（而非类）用于纯数据结构
- 移除观察者模式（由 React 状态管理替代）

**输出：**
- TypeScript 类/接口定义
- 工厂函数（如适用）

##### DataMigrateAgent

**职责：** 迁移数据资源（XAML 数据绑定、资源字典等）

**处理内容：**
- `XmlDataProvider` → TypeScript 接口和数组
- 数据绑定表达式 → TypeScript 对象
- 资源字典 → TypeScript 常量

**输出：**
- `data.ts` 文件（包含所有数据资源）
- `data_descriptions.json`（数据资源描述，供页面集成使用）

##### ResourceMigrateAgent

**职责：** 迁移静态资源文件

**处理内容：**
- 图片文件（`.png`, `.jpg`, `.ico` 等）
- 样式文件（`.css`）
- 其他静态资源

**输出：**
- `result/{project}/public/{resource}`

#### 2.4 使用方式

**命令行：**
```bash
# 设置环境变量（OPENAI_API_KEY）
export OPENAI_API_KEY=your_api_key

# 运行迁移
python -m src.migration ExpenseItDemo
```

**编程方式：**
```python
import asyncio
from src.migration import migrate_project

async def main():
    results = await migrate_project("ExpenseItDemo", output_base_dir="outputs")
    print(f"成功迁移 {results['successful_pages']} 个页面")

asyncio.run(main())
```

#### 2.5 版本要求

迁移模块生成的代码遵循以下版本要求：

- **React**: 18.2.0
- **Material-UI (MUI)**: 5.18.0
- **Emotion**: 11.11.x
- **TypeScript**: 5.9.3

所有 Agent 的 prompt 都明确指定这些版本，确保生成的代码兼容。

#### 2.6 页面组件模式

迁移模块遵循以下页面组件模式：

**MainWindow 模式：**
- 无 props：`export function MainWindow() { ... }`
- 数据导入：`import { expenseData, employees, costCenters } from './data'`
- 状态管理：使用 `useState` 管理 UI 状态（对话框开关等）
- 数据更新：直接修改全局数据对象（`expenseData.alias = value`）

**Dialog/Modal 模式：**
- Props 接口：`{ open: boolean; onClose: () => void }`
- 函数签名：`export function DialogName({ open, onClose }: DialogNameProps)`
- MUI Dialog：使用 `<Dialog open={open} onClose={onClose}>` 包裹内容

**数据交互模式：**
- 读取数据：从 `data.ts` 导入并直接读取
- 更新数据：直接修改全局数据对象
- 本地状态：仅用于 UI 状态（对话框开关、表单选择等）

## 安装与使用

### 环境要求

- Python 3.8+
- Node.js 18+（用于运行迁移后的 React 项目）
- OpenAI API Key（用于 LLM 调用）

### 安装依赖

```bash
pip install -r requirements.txt
```

**主要依赖：**
- `autogen-core`: Autogen Runtime（Agent 管理）
- `tree-sitter` + `tree-sitter-c-sharp`: C# 代码解析
- `lxml`: XML/XAML 解析（推荐）
- `openai`: OpenAI API 客户端
- `python-dotenv`: 环境变量管理

### 配置环境变量

创建 `.env` 文件：

```bash
OPENAI_API_KEY=your_api_key_here
```

### 完整使用流程

#### 步骤 1：解析 WPF 项目

```bash
python -m src.parser ExpenseItDemo
```

这将生成所有必要的依赖分析文件到 `outputs/ExpenseItDemo/` 目录。

#### 步骤 2：迁移项目

```bash
python -m src.migration ExpenseItDemo
```

这将执行完整的迁移流程，生成 React 项目到 `result/ExpenseItDemo/` 目录。

#### 步骤 3：运行迁移后的项目

```bash
cd result/ExpenseItDemo
npm install
npm start
```

## 输出结果

### 解析结果（outputs/）

```
outputs/{project}/
├── cs/                    # C# 文件解析结果
│   └── {file}.cs.json
├── xaml/                  # XAML 文件解析结果
│   └── {file}.xaml.json
└── dependency/            # 依赖分析结果
    ├── cs_dependency.json
    ├── page_dependency.json
    ├── resource_dependency.json
    ├── control_{page}.json
    ├── data_resources.json
    └── template_resources.json
```

### 迁移结果（result/）

```
result/{project}/
├── {page}.tsx             # React 页面组件
├── {class}.ts             # TypeScript 数据模型
├── data.ts                # 数据资源
└── public/                # 静态资源
    └── {resource}
```

## 技术特点

### 解析器模块

- **双解析器支持**：优先使用 lxml（更好的命名空间处理），回退到标准库 ElementTree
- **语法树解析**：使用 tree-sitter 进行 C# 代码的精确解析
- **智能命名空间处理**：根元素保留完整命名空间声明，子元素自动移除冗余声明
- **源代码格式化**：提取的源代码经过格式化，统一缩进，适合 LLM 输入
- **递归结构解析**：完整保留 XAML 和 C# 的树形结构关系

### 迁移模块

- **多 Agent 协作**：基于 Autogen Runtime 的消息传递架构
- **渐进式优化**：多轮渐进式修改策略，逐步优化迁移结果
- **依赖感知**：自动分析并遵循依赖关系，确保迁移顺序正确
- **代码质量保证**：严格的 prompt 工程，确保生成的代码符合最佳实践
- **版本兼容性**：明确指定 React、MUI、TypeScript 版本，确保兼容性

## 示例项目

- **ExpenseItDemo**: WPF 费用报销应用示例（完整迁移示例）
- **DataBindingDemo**: WPF 数据绑定机制示例
- **EditingExaminerDemo**: 编辑检查器示例

## 开发进度

### 已完成

- [x] XAML 文件解析
- [x] C# 文件解析
- [x] 页面依赖分析
- [x] 资源依赖分析
- [x] 控件依赖分析
- [x] C# 文件依赖分析
- [x] 多 Agent 迁移系统
- [x] 组件级迁移
- [x] 页面整合
- [x] 资源迁移
- [x] C# 文件迁移
- [x] 数据资源迁移
- [x] 模板和数据依赖集成

### 进行中

- [ ] 迁移结果质量评估和优化
- [ ] 更多 WPF 控件支持
- [ ] 迁移结果自动化测试

### 计划中

- [ ] 迁移结果自动修复
- [ ] 迁移进度可视化
- [ ] 迁移结果对比工具

## 贡献

欢迎提交 Issue 和 Pull Request！

## 许可证

MIT License
