# WPF2React

一个用于将 WPF (Windows Presentation Foundation) 项目转换为 React 项目的工具。

## 项目简介

本项目旨在帮助开发者将基于 XAML 的 WPF 应用程序迁移到基于 React 的 Web 应用程序。通过解析 XAML 文件和 C# 代码，提取结构信息和依赖关系，为后续的转换工作提供数据支持。

## 主要功能

- **XAML 解析器**: 解析 WPF 项目中的 XAML 文件，提取元素结构、属性和命名空间信息
- **CSPROJ 解析**: 解析项目配置文件，识别资源依赖关系
- **源代码提取**: 提取每个 XAML 元素的源代码，格式化后便于 LLM 处理
- **命名空间优化**: 智能处理 XML 命名空间声明，避免子元素重复声明

## 项目结构

```
WPF2React/
├── src/                    # 源代码目录
│   └── parser/            # 解析器模块
│       ├── __init__.py
│       └── xaml_parser.py # XAML/XML 文件解析器
├── repos/                 # WPF 示例项目
│   ├── ExpenseItDemo/     # 费用报销示例
│   ├── DataBindingDemo/   # 数据绑定示例
│   ├── EditingExaminerDemo/  # 编辑检查示例
│   └── CustomComboBox/    # 自定义组合框示例
├── outputs/               # 解析结果输出目录（git 忽略）
├── .gitignore
├── README.md
└── requirements.txt       # Python 依赖
```

## 安装与使用

### 环境要求

- Python 3.6+
- lxml (推荐) 或 xml.etree.ElementTree (内置)

### 安装依赖

```bash
pip install -r requirements.txt
```

### 使用示例

#### 1. 解析单个 XAML 文件

```python
from src.parser.xaml_parser import XamlParser

parser = XamlParser()
root = parser.parse_file("repos/ExpenseItDemo/MainWindow.xaml")
parser.save_to_json("output/MainWindow.xaml.json")
```

#### 2. 批量解析整个项目

```python
from src.parser.xaml_parser import XamlParser

# 解析项目中所有 XAML 和 CSPROJ 文件
results = XamlParser.parse_project("repos/ExpenseItDemo", include_csproj=True)
```

#### 3. 直接运行解析器

```bash
cd /path/to/WPF2React
python3 -m src.parser.xaml_parser
```

## 解析结果格式

解析后的 JSON 文件包含以下信息：

```json
{
  "source_file": "路径/文件名.xaml",
  "namespaces": {
    "default": "http://schemas.microsoft.com/winfx/2006/xaml/presentation",
    "x": "http://schemas.microsoft.com/winfx/2006/xaml"
  },
  "root": {
    "tag": "Window",
    "full_tag": "{http://...}Window",
    "attributes": { "Title": "MainWindow", "Width": "640" },
    "text": null,
    "namespace": "http://schemas.microsoft.com/winfx/2006/xaml/presentation",
    "source_code": "<Window xmlns=\"...\" ...>...</Window>",
    "children": [...]
  }
}
```

## 技术特点

- **双解析器支持**: 优先使用 lxml（更好的命名空间处理），回退到标准库 ElementTree
- **智能命名空间处理**: 根元素保留完整命名空间声明，子元素自动移除冗余声明
- **源代码格式化**: 提取的源代码经过格式化，统一缩进，适合 LLM 输入
- **递归结构解析**: 完整保留 XAML 的树形结构关系

## 示例项目说明

- **ExpenseItDemo**: WPF 费用报销应用示例
- **DataBindingDemo**: WPF 数据绑定机制示例
- **EditingExaminerDemo**: 编辑检查器示例
- **CustomComboBox**: 自定义组合框控件示例

## 开发进度

- [x] XAML 文件解析
- [x] CSPROJ 文件解析
- [x] 命名空间优化
- [x] 源代码提取
- [ ] 页面依赖分析
- [ ] 资源依赖分析
- [ ] 控件依赖分析
- [ ] React 组件生成

## 贡献

欢迎提交 Issue 和 Pull Request！

## 许可证

MIT License

