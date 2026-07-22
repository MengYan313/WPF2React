"""迁移结果的确定性 TypeScript/TSX 工具。"""

import re
import json
import logging
from typing import List, Optional
from pathlib import Path

logger = logging.getLogger(__name__)


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
    if logger_instance is None:
        logger_instance = logger

    lines = code.split('\n')

    # 先识别顶层函数/组件声明。旧实现会扫描任意缩进层级的 ``const``，
    # 因而把函数组件内部的第一个局部变量误当成组件并重命名。
    expected_declared = any(
        re.match(
            rf'^(?:export\s+default\s+|export\s+)?function\s+{re.escape(expected_name)}\s*\(',
            line,
        )
        or re.match(
            rf'^(?:export\s+)?const\s+{re.escape(expected_name)}\s*(?::|=)',
            line,
        )
        for line in lines
    )

    if not expected_declared:
        declaration_patterns = (
            re.compile(r'^(?:export\s+default\s+|export\s+)?function\s+(\w+)\s*\('),
            re.compile(r'^(?:export\s+)?const\s+(\w+)\s*(?::\s*(?:React\.)?(?:FC|FunctionComponent)\b|=)'),
        )
        for index, line in enumerate(lines):
            match = next((pattern.match(line) for pattern in declaration_patterns if pattern.match(line)), None)
            if match is None:
                continue
            old_name = match.group(1)
            lines[index] = (
                line[:match.start(1)] + expected_name + line[match.end(1):]
            )
            logger_instance.debug(f"修正组件名: {old_name} -> {expected_name}")
            break

    export_pattern = re.compile(r'export\s+default\s+\w+(\s*;)?')
    export_found = False
    for index, line in enumerate(lines):
        if export_pattern.search(line):
            lines[index] = export_pattern.sub(
                f'export default {expected_name};', line
            )
            export_found = True
            logger_instance.debug(f"修正导出名: -> {expected_name}")

    if not export_found:
        lines.append(f'export default {expected_name};')
        logger_instance.debug(f"添加导出语句: export default {expected_name};")

    return '\n'.join(lines)


def validate_generated_tsx(
    page_name: str,
    code: str,
    *,
    expected_props: Optional[List[str]] = None,
    required_data_identifiers: Optional[List[str]] = None,
    object_data_identifiers: Optional[List[str]] = None,
) -> List[str]:
    """对最终 TSX 做确定性的低成本静态检查。"""
    errors: List[str] = []

    if not code.strip():
        return ["最终 TSX 代码为空"]
    if re.search(r"<Grid(?:\s|>)", code):
        errors.append("最终 TSX 使用了禁止的 MUI <Grid> 组件")
    if re.search(rf"\b(?:const|let|var)\s+{re.escape(page_name)}\b", code):
        errors.append(f"组件内部声明了与页面同名的变量: {page_name}")
    if not re.search(
        rf"\b(?:export\s+default\s+|export\s+)?function\s+{re.escape(page_name)}\s*\(|"
        rf"\b(?:export\s+)?const\s+{re.escape(page_name)}\s*(?::|=)",
        code,
    ):
        errors.append(f"最终 TSX 未声明页面组件: {page_name}")
    if not re.search(rf"\bexport\s+default\s+{re.escape(page_name)}\s*;?", code):
        errors.append(f"最终 TSX 缺少正确的默认导出: {page_name}")

    if expected_props is not None:
        function_match = re.search(
            rf"\bexport\s+function\s+{re.escape(page_name)}\s*\((.*?)\)\s*\{{",
            code,
            flags=re.DOTALL,
        )
        if function_match:
            parameters = function_match.group(1).strip()
            if not expected_props and parameters:
                errors.append(f"根页面 {page_name} 不应接收 props")
            elif expected_props:
                destructured = re.match(
                    rf"\s*\{{(.*?)\}}\s*:\s*{re.escape(page_name)}Props\s*$",
                    parameters,
                    flags=re.DOTALL,
                )
                actual_props = set()
                if destructured:
                    actual_props = {
                        item.split(":", 1)[0].split("=", 1)[0].strip()
                        for item in destructured.group(1).split(",")
                        if item.strip() and not item.strip().startswith("...")
                    }
                if actual_props != set(expected_props):
                    errors.append(
                        f"子页面 {page_name} props 必须且只能是: "
                        + ", ".join(expected_props)
                    )

                interface_match = re.search(
                    rf"\binterface\s+{re.escape(page_name)}Props\s*\{{(.*?)\}}",
                    code,
                    flags=re.DOTALL,
                )
                interface_props = set()
                if interface_match:
                    interface_props = set(
                        re.findall(
                            r"^\s*([A-Za-z_$][\w$]*)\??\s*:",
                            interface_match.group(1),
                            flags=re.MULTILINE,
                        )
                    )
                if interface_props != set(expected_props):
                    errors.append(
                        f"{page_name}Props 字段必须且只能是: "
                        + ", ".join(expected_props)
                    )

    for identifier in required_data_identifiers or []:
        import_found = any(
            re.search(rf"\b{re.escape(identifier)}\b", names)
            for names in re.findall(
                r"\bimport\s*\{([^}]*)\}\s*from\s*['\"][^'\"]+['\"]",
                code,
                flags=re.DOTALL,
            )
        )
        if not import_found:
            errors.append(f"最终 TSX 缺少数据导入: {identifier}")
        elif len(re.findall(rf"\b{re.escape(identifier)}\b", code)) < 2:
            errors.append(f"最终 TSX 导入但未使用数据: {identifier}")

    for identifier in object_data_identifiers or []:
        if re.search(
            rf"\b{re.escape(identifier)}\s*\.\s*(?:map|reduce|filter|forEach)\s*\(",
            code,
        ):
            errors.append(
                f"对象型数据 {identifier} 不能直接调用数组方法，必须访问其数组属性"
            )

    if re.search(r"\bexpenses(?:\.|\[)", code):
        expenses_declared = any(
            re.search(pattern, code, flags=re.DOTALL)
            for pattern in (
                r"\b(?:const|let|var)\s+expenses\b",
                r"\bimport\s+\{[^}]*\bexpenses\b[^}]*\}",
                r"function\s+\w+\s*\([^)]*\bexpenses\b[^)]*\)",
            )
        )
        if not expenses_declared:
            errors.append("最终 TSX 引用了未声明的 expenses")

    return errors


def get_available_resources(resources_dir) -> List[str]:
    """
    获取可用的资源文件列表
    
    Args:
        resources_dir: 资源文件目录路径（Path 对象或字符串）
        
    Returns:
        资源文件名列表（不包括路径）
    """
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
    result_dir = Path(result_dir)
    if not result_dir.exists():
        return []
    
    files = []
    for file_path in result_dir.rglob("*"):
        if file_path.is_file() and file_path.suffix in ['.ts', '.tsx']:
            # 排除临时文件
            if not file_path.name.endswith('_temp.tsx'):
                files.append(file_path.relative_to(result_dir).as_posix())
    
    return sorted(files)


def save_tsx_file(temp_path, code: str, page_name: str, logger_instance: logging.Logger = None) -> None:
    """
    保存临时 TSX 文件并确保导出名称正确
    
    Args:
        temp_path: 临时文件路径（Path 对象或字符串）
        code: 已从 JSON 字段中取得的纯净 TypeScript 代码
        page_name: 页面名称
        logger_instance: 日志记录器实例。如果为 None，使用模块级别的 logger
    """
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
