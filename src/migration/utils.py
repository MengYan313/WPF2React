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
import logging

logger = logging.getLogger(__name__)


def extract_tag_content(response: str, tag_name: str, default: str = "", logger_instance: logging.Logger = None) -> str:
    """
    从 LLM 响应中提取指定标记的内容
    
    统一标记解析流程：
    1. 首先判断标记是否存在
    2. 若不存在，直接 warning 并返回默认值（或原始响应）
    3. 若存在，进行标记解析，直接得到标记内的代码
    4. 解析成功后不要验证，直接返回提取的内容
    
    Args:
        response: LLM 响应文本
        tag_name: 标记名称（例如 "TypeScript Code", "Component Name", "Description"）
        default: 如果标记不存在时返回的默认值。如果为空字符串，则返回原始响应
        logger_instance: 日志记录器实例。如果为 None，使用模块级别的 logger
    
    Returns:
        提取的标记内容（已去除标记），如果标记不存在则返回 default 或原始响应
    """
    if logger_instance is None:
        logger_instance = logger
    
    cleaned_response = response.strip()
    
    # 首先判断标记是否存在（支持多种格式）
    # 检查 [TagName] 和 [/TagName] 或 [Tag Name] 和 [/Tag Name]
    tag_patterns = [
        f"[{tag_name}",  # [TypeScript Code
        f"[/{tag_name}",  # [/TypeScript Code
        f"[{tag_name.replace(' ', '')}",  # [TypeScriptCode
        f"[/{tag_name.replace(' ', '')}",  # [/TypeScriptCode
    ]
    
    has_marker = any(pattern in cleaned_response for pattern in tag_patterns)
    
    if not has_marker:
        # 若不存在，直接 warning 并返回默认值或原始响应
        if default:
            logger_instance.warning(f"无法从 LLM 响应中提取 [{tag_name}] 标记，使用默认值。完整响应:\n{response[:30]}")
            return default
        else:
            logger_instance.warning(f"无法从 LLM 响应中提取 [{tag_name}] 标记，返回原始响应。完整响应:\n{response[:30]}")
            return cleaned_response
    else:
        # 若存在，进行标记解析，直接得到标记内的代码
        # 支持多种标记格式：
        # 1. [Tag Name] ... [/Tag Name] (带空格)
        # 2. [TagName] ... [/TagName] (无空格)
        # 3. [Tag Name] ... [/Tag Name] (标准格式)
        patterns = [
            rf'\[{re.escape(tag_name)}.*?\]\s*\n?(.*?)\n?\[/{re.escape(tag_name)}.*?\]',  # 标准格式，支持属性
            rf'\[{re.escape(tag_name)}\]\s*\n?(.*?)\n?\[/{re.escape(tag_name)}\]',  # 简化格式
            rf'\[{re.escape(tag_name.replace(" ", ""))}\]\s*\n?(.*?)\n?\[/{re.escape(tag_name.replace(" ", ""))}\]',  # 无空格格式
        ]
        
        for pattern in patterns:
            match = re.search(pattern, cleaned_response, re.DOTALL | re.IGNORECASE)
            if match:
                return match.group(1).strip()
        
        # 如果正则没匹配到，尝试更通用的提取（移除标记）
        # 这种情况可能是标记格式不标准，尝试直接移除标记
        if f"[{tag_name}" in cleaned_response or f"[/{tag_name}" in cleaned_response:
            # 移除开头的标记
            cleaned_response = re.sub(
                rf'^\s*\[{re.escape(tag_name)}.*?\]\s*\n?', 
                '', 
                cleaned_response, 
                flags=re.IGNORECASE | re.MULTILINE
            )
            # 移除结尾的标记
            cleaned_response = re.sub(
                rf'\n?\s*\[/{re.escape(tag_name)}.*?\]\s*$', 
                '', 
                cleaned_response, 
                flags=re.IGNORECASE | re.MULTILINE
            )
            cleaned_response = cleaned_response.strip()
        
        # 解析成功后不要验证，直接返回提取的代码
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

