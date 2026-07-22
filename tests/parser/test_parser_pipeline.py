"""Parser 流水线冒烟测试，不调用 LLM 或外部 API。"""

import sys
import tempfile
from pathlib import Path

from src.parser import analyze_project


EXPECTED_STEPS = {
    "cs_parser",
    "xaml_parser",
    "cs_dependency",
    "indirect_resource_dependency",
    "page_dependency",
    "resource_dependency",
    "control_dependency",
}


def main() -> bool:
    """解析最小示例并检查关键步骤与产物。"""
    with tempfile.TemporaryDirectory(prefix="wpf2react-parser-") as temp_dir:
        results = analyze_project("ExpenseItDemo", output_base_dir=temp_dir)
        steps = results.get("steps", {})

        missing_steps = EXPECTED_STEPS.difference(steps)
        failed_steps = [
            name for name, result in steps.items()
            if not result.get("success", False)
        ]

        dependency_dir = Path(temp_dir) / "ExpenseItDemo" / "dependency"
        required_artifacts = {
            "cs_dependency.json",
            "page_dependency.json",
            "resource_dependency.json",
            "data_resources.json",
            "template_resources.json",
        }
        missing_artifacts = [
            name for name in sorted(required_artifacts)
            if not (dependency_dir / name).is_file()
        ]
        control_artifacts = list((dependency_dir / "controls").rglob("*.xaml.json"))

        if missing_steps or failed_steps or missing_artifacts or not control_artifacts:
            print(f"缺少步骤: {sorted(missing_steps)}")
            print(f"失败步骤: {failed_steps}")
            print(f"缺少产物: {missing_artifacts}")
            print(f"控件产物数量: {len(control_artifacts)}")
            return False

        print(
            "解析冒烟测试通过: "
            f"{len(steps)} 个步骤，{len(control_artifacts)} 个控件依赖产物"
        )
        return True


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
