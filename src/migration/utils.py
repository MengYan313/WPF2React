"""
标记提取工具函数

统一处理所有 LLM 响应的标记提取逻辑。

统一流程：
1. 首先判断标记是否存在
2. 若不存在，直接 warning 并返回所有内容（或默认值）
3. 若存在，进行标记解析，直接得到标记内的代码
4. 解析成功后不要验证，直接使用提取的内容
"""

import re
import json
import logging
from typing import List, Optional
from pathlib import Path

logger = logging.getLogger(__name__)


def extract_tag_content(response: str, tag_name: str, default: str = "", logger_instance: logging.Logger = None) -> str:
    """
    从 LLM 响应中提取指定标记的内容
    
    使用标准标记格式：[Tag Name] ... [/Tag Name]
    
    Args:
        response: LLM 响应文本
        tag_name: 标记名称（例如 "TypeScript Code", "Component Name", "Description"）
        default: 如果标记不存在或解析失败时返回的默认值。如果为空字符串，则返回原始响应
        logger_instance: 日志记录器实例。如果为 None，使用模块级别的 logger
    
    Returns:
        提取的标记内容（已去除标记），如果标记不存在或解析失败则返回 default 或原始响应
    """
    if logger_instance is None:
        logger_instance = logger
    
    cleaned_response = response.strip()
    
    # 使用标准标记格式进行解析：[Tag Name] ... [/Tag Name]
    pattern = rf'\[{re.escape(tag_name)}\]\s*\n?(.*?)\n?\[/{re.escape(tag_name)}\]'
    match = re.search(pattern, cleaned_response, re.DOTALL | re.IGNORECASE)
    
    if match:
        return match.group(1).strip()
    
    # 解析失败，根据 default 记录错误并返回默认值或原始响应
    if default:
        logger_instance.warning(f"无法从 LLM 响应中提取 [{tag_name}] 标记，使用默认值。完整响应:\n{response[:300]}")
        return default
    else:
        logger_instance.warning(f"无法从 LLM 响应中提取 [{tag_name}] 标记，返回原始响应。完整响应:\n{response[:300]}")
        return cleaned_response


def extract_tag_content_lines(response: str, tag_name: str, default: list = None, logger_instance: logging.Logger = None) -> list:
    """
    从 LLM 响应中提取指定标记的内容，并按行分割返回列表
    
    用于提取需要按行处理的标记内容，如 [Selected Components] 或 [Imports]
    
    Args:
        response: LLM 响应文本
        tag_name: 标记名称
        default: 如果标记不存在时返回的默认值列表
        logger_instance: 日志记录器实例
    
    Returns:
        提取的内容按行分割后的列表，过滤空行
    """
    if default is None:
        default = []
    
    content = extract_tag_content(response, tag_name, "", logger_instance)
    
    if not content:
        return default
    
    # 按行分割，过滤空行和空白
    lines = [line.strip() for line in content.split('\n') if line.strip()]
    return lines if lines else default


def inject_imports(code: str, imports: List[str]) -> str:
    """
    将自动生成的 import 语句注入到代码中
    
    Args:
        code: TypeScript 代码
        imports: 要注入的 import 语句列表
        
    Returns:
        注入 import 后的代码
    """
    if not imports:
        return code
    
    lines = code.split('\n')
    
    # 查找第一个 import 语句的位置
    first_import_idx = -1
    for i, line in enumerate(lines):
        if line.strip().startswith('import '):
            first_import_idx = i
            break
    
    # 查找最后一个 import 语句的位置
    last_import_idx = first_import_idx
    if first_import_idx >= 0:
        for i in range(first_import_idx + 1, len(lines)):
            if lines[i].strip().startswith('import '):
                last_import_idx = i
            elif lines[i].strip() and not lines[i].strip().startswith('//'):
                # 遇到非空非注释行，停止
                break
    
    # 检查哪些 import 已经存在
    existing_imports = set()
    for line in lines:
        if line.strip().startswith('import '):
            existing_imports.add(line.strip())
    
    # 过滤掉已存在的 import
    new_imports = []
    for imp in imports:
        if imp.strip() not in existing_imports:
            new_imports.append(imp.strip())
    
    if not new_imports:
        return code
    
    # 在最后一个 import 之后插入新的 import
    if first_import_idx >= 0:
        # 在最后一个 import 后插入
        insert_idx = last_import_idx + 1
        # 如果下一个非空行不是 import，添加空行
        if insert_idx < len(lines) and lines[insert_idx].strip() and not lines[insert_idx].strip().startswith('import '):
            lines.insert(insert_idx, '')
            insert_idx += 1
        lines.insert(insert_idx, '\n'.join(new_imports))
    else:
        # 没有 import，在文件开头插入
        if lines and lines[0].strip():
            lines.insert(0, '\n'.join(new_imports))
            lines.insert(len(new_imports), '')
        else:
            lines.insert(0, '\n'.join(new_imports))
    
    return '\n'.join(lines)


def read_file_content(file_path) -> str:
    """
    读取文件内容
    
    Args:
        file_path: 文件路径（Path 对象或字符串）
        
    Returns:
        文件内容
    """
    from pathlib import Path
    
    file_path = Path(file_path)
    if not file_path.exists():
        raise FileNotFoundError(f"文件不存在: {file_path}")
    
    with open(file_path, 'r', encoding='utf-8') as f:
        return f.read()


def log_code_output(round_name: str, page_name: str, code: str, logger_instance: logging.Logger = None) -> None:
    """
    将代码输出写入日志
    
    Args:
        round_name: 轮次名称（例如 "第一轮：初始组装"）
        page_name: 页面名称
        code: 生成的代码
        logger_instance: 日志记录器实例。如果为 None，使用模块级别的 logger
    """
    if logger_instance is None:
        logger_instance = logger
    
    if not code or not code.strip():
        logger_instance.warning(f"  {round_name} - 输出代码为空")
        return
    
    # 计算代码行数
    lines = code.split('\n')
    line_count = len(lines)
    
    # 记录代码摘要和完整代码
    logger_instance.info(f"  {round_name} - 输出代码 ({line_count} 行):")
    logger_instance.debug(f"  {'='*80}")
    logger_instance.debug(f"  {round_name} - 完整代码输出:")
    logger_instance.debug(f"  {'='*80}")
    # 逐行记录代码，添加行号
    for i, line in enumerate(lines, 1):
        logger_instance.debug(f"  {i:4d} | {line}")
    logger_instance.debug(f"  {'='*80}")


def ensure_correct_export_name(code: str, expected_name: str, logger_instance: logging.Logger = None) -> str:
    """
    确保代码中的组件名和导出名与期望名称一致
    
    Args:
        code: TypeScript 代码
        expected_name: 期望的组件名
        logger_instance: 日志记录器实例。如果为 None，使用模块级别的 logger
        
    Returns:
        修正后的代码
    """
    import re
    
    if logger_instance is None:
        logger_instance = logger
    
    lines = code.split('\n')
    modified_lines = []
    component_declared = False
    component_name_found = None
    
    for line in lines:
        # 查找组件声明：const ComponentName: React.FC 或 const ComponentName = ...
        if not component_declared:
            # 匹配 const ComponentName: React.FC 或 const ComponentName = ...
            match = re.match(r'^(\s*)const\s+(\w+)\s*[:=]', line)
            if match:
                indent = match.group(1)
                old_name = match.group(2)
                component_name_found = old_name
                if old_name != expected_name:
                    # 替换组件名
                    line = re.sub(
                        r'^(\s*)const\s+\w+\s*',
                        f'{indent}const {expected_name} ',
                        line
                    )
                    component_declared = True
                    logger_instance.debug(f"修正组件名: {old_name} -> {expected_name}")
                else:
                    component_declared = True
        
        # 查找并修正 export default 语句
        if re.search(r'export\s+default\s+', line):
            # 替换为正确的导出名（处理 export default ComponentName; 或 export default ComponentName）
            line = re.sub(
                r'export\s+default\s+\w+(\s*;)?',
                f'export default {expected_name};',
                line
            )
            logger_instance.debug(f"修正导出名: -> {expected_name}")
        
        # 如果组件名已找到，替换代码中对组件名的引用（仅在 export default 之后）
        if component_name_found and component_name_found != expected_name:
            # 在 export default 之后，替换组件名引用
            if re.search(r'export\s+default\s+', line):
                line = line.replace(component_name_found, expected_name)
        
        modified_lines.append(line)
    
    # 如果代码中没有找到 export default，添加它
    code_str = '\n'.join(modified_lines)
    if not re.search(r'export\s+default\s+', code_str):
        modified_lines.append(f'export default {expected_name};')
        logger_instance.debug(f"添加导出语句: export default {expected_name};")
    
    return '\n'.join(modified_lines)


def get_available_resources(resources_dir) -> List[str]:
    """
    获取可用的资源文件列表
    
    Args:
        resources_dir: 资源文件目录路径（Path 对象或字符串）
        
    Returns:
        资源文件名列表（不包括路径）
    """
    from pathlib import Path
    
    resources_dir = Path(resources_dir)
    if not resources_dir.exists():
        return []
    
    resources = []
    for file_path in resources_dir.iterdir():
        if file_path.is_file():
            resources.append(file_path.name)
    
    return sorted(resources)


def get_available_migrated_files(result_dir) -> List[str]:
    """
    获取已迁移的文件列表（.ts 和 .tsx 文件）
    
    Args:
        result_dir: 结果目录路径（Path 对象或字符串）
        
    Returns:
        文件名列表（不包括扩展名）
    """
    from pathlib import Path
    
    result_dir = Path(result_dir)
    if not result_dir.exists():
        return []
    
    files = []
    for file_path in result_dir.iterdir():
        if file_path.is_file() and file_path.suffix in ['.ts', '.tsx']:
            # 排除临时文件
            if not file_path.name.endswith('_temp.tsx'):
                files.append(file_path.stem)
    
    return sorted(files)


def save_tsx_file(temp_path, code: str, page_name: str, logger_instance: logging.Logger = None) -> None:
    """
    保存临时 TSX 文件并确保导出名称正确
    
    Args:
        temp_path: 临时文件路径（Path 对象或字符串）
        code: TypeScript 代码（已经是纯净的代码，不包含标记）
        page_name: 页面名称
        logger_instance: 日志记录器实例。如果为 None，使用模块级别的 logger
    """
    from pathlib import Path
    
    if logger_instance is None:
        logger_instance = logger
    
    temp_path = Path(temp_path)
    
    # 检查代码是否为空
    if not code or code.strip() == "":
        error_msg = f"代码为空，无法保存 - 页面: {page_name}"
        logger_instance.error(error_msg)
        raise ValueError(error_msg)
    
    # 确保导出名称正确
    cleaned_code = ensure_correct_export_name(code, page_name, logger_instance)
    
    # 保存文件
    temp_path.parent.mkdir(parents=True, exist_ok=True)
    with open(temp_path, 'w', encoding='utf-8') as f:
        f.write(cleaned_code)


def get_page_depended_by_count(
    dependency_file: Path,
    page_name: str,
    logger_instance: logging.Logger = None
) -> Optional[int]:
    """
    从 page_dependency.json 文件中获取指定页面的 depended_by_count 值
    
    Args:
        dependency_file: page_dependency.json 文件路径
        page_name: 页面名称
        logger_instance: 日志记录器实例。如果为 None，使用模块级别的 logger
    
    Returns:
        页面的 depended_by_count 值，如果文件不存在或页面不存在则返回 None
    """
    if logger_instance is None:
        logger_instance = logger
    
    dependency_path = Path(dependency_file)
    
    # 检查文件是否存在
    if not dependency_path.exists():
        logger_instance.debug(f"依赖文件不存在: {dependency_path}")
        return None
    
    try:
        # 读取 JSON 文件
        with open(dependency_path, 'r', encoding='utf-8') as f:
            dependency_data = json.load(f)
        
        # 获取页面信息
        pages = dependency_data.get('pages', {})
        page_info = pages.get(page_name)
        
        if page_info is None:
            logger_instance.debug(f"页面 '{page_name}' 在依赖文件中不存在")
            return None
        
        # 获取 depended_by_count
        depended_by_count = page_info.get('depended_by_count')
        
        if depended_by_count is None:
            logger_instance.warning(f"页面 '{page_name}' 的 depended_by_count 字段不存在")
            return None
        
        return depended_by_count
        
    except json.JSONDecodeError as e:
        logger_instance.error(f"解析依赖文件失败: {dependency_path}, 错误: {e}")
        return None
    except Exception as e:
        logger_instance.error(f"读取依赖文件失败: {dependency_path}, 错误: {e}")
        return None

