import tempfile
import unittest
from pathlib import Path

from src.migration.utils import ensure_correct_export_name, validate_generated_tsx


class PageValidationTests(unittest.TestCase):
    def test_export_cleanup_preserves_function_local_variables(self):
        source = """export function ViewChartWindow() {
  const expenses: Expense[] = [];
  return <Box>{expenses.length}</Box>;
}
"""
        cleaned = ensure_correct_export_name(source, "ViewChartWindow")

        self.assertIn("const expenses: Expense[] = [];", cleaned)
        self.assertNotIn("const ViewChartWindow: Expense[]", cleaned)
        self.assertIn("export default ViewChartWindow;", cleaned)
        self.assertEqual(validate_generated_tsx("ViewChartWindow", cleaned), [])

    def test_validator_enforces_page_contract_and_data_usage(self):
        invalid = """interface ViewChartWindowProps {
  open: boolean;
  expenses: Expense[];
  onClose: () => void;
}
export function ViewChartWindow({ open, expenses, onClose }: ViewChartWindowProps) {
  return <Box>{expenses.length}</Box>;
}
export default ViewChartWindow;
"""
        errors = validate_generated_tsx(
            "ViewChartWindow",
            invalid,
            expected_props=["open", "onClose"],
            required_data_identifiers=["expenseData"],
            object_data_identifiers=["expenseData"],
        )

        self.assertTrue(any("props 必须且只能是" in error for error in errors))
        self.assertIn("最终 TSX 缺少数据导入: expenseData", errors)

        wrong_shape = """import { expenseData } from './data';
export function ViewChartWindow({ open, onClose }: ViewChartWindowProps) {
  return <Box>{expenseData.map((item) => item.cost)}</Box>;
}
export default ViewChartWindow;
"""
        shape_errors = validate_generated_tsx(
            "ViewChartWindow",
            wrong_shape,
            object_data_identifiers=["expenseData"],
        )
        self.assertTrue(any("不能直接调用数组方法" in error for error in shape_errors))

    def test_validator_reports_known_invalid_page_patterns(self):
        source = """export function ViewChartWindow() {
  const ViewChartWindow: Expense[] = [];
  return <Grid>{expenses.map((expense) => expense.cost)}</Grid>;
}
export default ViewChartWindow;
"""
        errors = validate_generated_tsx("ViewChartWindow", source)

        self.assertIn(
            "组件内部声明了与页面同名的变量: ViewChartWindow", errors
        )
        self.assertIn("最终 TSX 引用了未声明的 expenses", errors)
        self.assertIn("最终 TSX 使用了禁止的 MUI <Grid> 组件", errors)

    def test_validator_rejects_missing_local_imports(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            source_file = Path(temp_dir) / "Views" / "LoginView.tsx"
            source_file.parent.mkdir()
            code = """import LoginShell from './LoginShell';
export function LoginView() { return <LoginShell />; }
export default LoginView;
"""

            errors = validate_generated_tsx(
                "LoginView",
                code,
                source_file=source_file,
            )

            self.assertIn(
                "最终 TSX 引用了不存在的本地模块: ./LoginShell",
                errors,
            )


if __name__ == "__main__":
    unittest.main()
