# 项目依赖说明

本文档详细说明 WPF2React 项目的所有 Python 依赖及其用途。

## Python 版本要求

- **Python 3.8+** （推荐 3.8-3.11）

## 依赖分类

### 1. 核心依赖（必需）

这些包是项目运行所必需的，必须安装。

| 包名 | 版本 | 用途 | 代码位置 |
|------|------|------|----------|
| `autogen-core` | 0.7.5 | Autogen Runtime 核心，用于 Agent 系统、消息路由和生命周期管理 | `src/migration/base.py`, `src/migration/migration_team.py` |
| `autogen-ext` | 0.7.5 | Autogen 扩展，提供 OpenAI 模型客户端 | `src/llm/client.py` |
| `pydantic` | 2.12.2 | 数据验证和消息模型定义（Autogen 要求使用 Pydantic BaseModel） | `src/migration/messages.py` |
| `python-dotenv` | 1.1.1 | 环境变量管理，用于加载 `.env` 文件中的 `OPENAI_API_KEY` | `src/migration/__main__.py`, `src/migration/migration_orchestrator.py` |
| `tree-sitter` | 0.25.2 | 语法树解析库，用于 C# 代码解析 | `src/parser/cs_parser.py` |
| `tree-sitter-c-sharp` | 0.23.1 | C# 语言的 tree-sitter 语法定义 | `src/parser/cs_parser.py` |

### 2. 推荐依赖（有回退机制）

这些包推荐安装，但代码提供了回退机制，不安装也能运行。

| 包名 | 版本 | 用途 | 回退机制 | 代码位置 |
|------|------|------|----------|----------|
| `lxml` | >=6.0.0 | XAML/XML 解析，提供更好的命名空间处理 | 回退到标准库 `xml.etree.ElementTree` | `src/parser/xaml_parser.py` |

**说明**：
- 如果安装了 `lxml`，XAML 解析会保留原始的命名空间前缀（xmlns, x:, local: 等）
- 如果未安装，会使用标准库 `ElementTree`，命名空间前缀可能会被简化为 `ns0`, `ns1` 等

### 3. 可选依赖（功能增强）

这些包用于特定功能，不安装也能运行，但相关功能会被禁用。

| 包名 | 版本 | 用途 | 影响 | 代码位置 |
|------|------|------|------|----------|
| `sentence-transformers` | >=5.0.0 | 语义相似度计算（本地模型），用于 MUI 组件选择 | 如果不安装，MUI 组件选择将仅使用直接映射，不使用语义相似度 | `src/migration/mui_select_agent.py` |
| `openai` | >=2.0.0 | OpenAI API 客户端，可用于语义相似度计算 | 如果不安装，无法使用 OpenAI 模式的语义相似度 | `src/migration/mui_select_agent.py` |

**说明**：
- `sentence-transformers` 和 `openai` 二选一安装即可，或都不安装
- 如果都不安装，`MUISelectAgent` 将仅使用直接映射（`wpf_to_mui_mapping.json`）来选择 MUI 组件
- 如果安装了 `sentence-transformers`，默认使用本地模型进行语义相似度计算
- 如果安装了 `openai`，可以通过配置使用 OpenAI API 进行语义相似度计算

## 安装方式

### 方式 1: 安装所有依赖（推荐）

```bash
pip install -r requirements.txt
```

这将安装：
- 所有核心依赖
- 推荐依赖（lxml）
- 可选依赖（sentence-transformers 和 openai）

### 方式 2: 仅安装最小依赖

```bash
pip install -r requirements-minimal.txt
```

这将仅安装核心依赖，不包含：
- lxml（会使用标准库回退）
- sentence-transformers（MUI 组件选择仅使用直接映射）
- openai（无法使用 OpenAI 模式的语义相似度）

### 方式 3: 使用 Conda 环境（推荐）

```bash
# 创建 conda 环境
conda create -n wpf2react python=3.10
conda activate wpf2react

# 安装依赖
pip install -r requirements.txt
```

## 环境变量配置

项目需要配置以下环境变量：

```bash
# .env 文件
OPENAI_API_KEY=your_api_key_here
```

`python-dotenv` 会自动加载 `.env` 文件中的环境变量。

## 依赖使用情况

### 按模块分类

#### 解析器模块 (`src/parser/`)
- `tree-sitter`, `tree-sitter-c-sharp`: C# 代码解析
- `lxml` (推荐): XAML/XML 解析

#### 迁移模块 (`src/migration/`)
- `autogen-core`, `autogen-ext`: Agent 系统核心
- `pydantic`: 消息模型定义
- `python-dotenv`: 环境变量加载
- `sentence-transformers` (可选): 语义相似度
- `openai` (可选): OpenAI API 客户端

#### LLM 模块 (`src/llm/`)
- `autogen-ext`: OpenAI 模型客户端

## 版本兼容性

### Autogen 版本

项目使用 Autogen Runtime (autogen-core 0.7.5)，这是 Autogen 的新架构：
- 不再使用 `autogen` 包（旧版本）
- 使用 `autogen-core` 和 `autogen-ext` 包
- 消息传递基于 `MessageContext` 和 `message_handler` 装饰器

### Pydantic 版本

项目使用 Pydantic v2 (2.12.2)，注意：
- 与 Pydantic v1 不兼容
- 所有消息模型必须继承自 `pydantic.BaseModel`

## 故障排除

### 问题 1: tree-sitter 安装失败

如果 `tree-sitter-c-sharp` 安装失败，可能需要编译工具：
```bash
# Ubuntu/Debian
sudo apt-get install build-essential

# macOS
xcode-select --install
```

### 问题 2: lxml 安装失败

如果 `lxml` 安装失败，可能需要系统库：
```bash
# Ubuntu/Debian
sudo apt-get install libxml2-dev libxslt1-dev

# macOS
brew install libxml2 libxslt
```

### 问题 3: sentence-transformers 安装很慢

`sentence-transformers` 会下载模型文件，首次使用时会自动下载。如果网络较慢，可以：
- 使用国内镜像源
- 手动下载模型文件

## 更新依赖

定期更新依赖以获得安全补丁和新功能：

```bash
pip install --upgrade -r requirements.txt
```

注意：更新后请测试项目功能，确保兼容性。

