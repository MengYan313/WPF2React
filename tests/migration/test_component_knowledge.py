"""组件知识库的确定性覆盖和自建控件召回评测。"""

from __future__ import annotations

import asyncio
import os
import unittest
from unittest.mock import patch

from src.parser.wpf_base_controls import WPF_BASE_CONTROLS
from src.migration.mui_select_agent import MUISelectAgent


CUSTOM_RECALL_CASES = (
    ("ProgressRing", "显示异步任务的圆形加载和忙碌状态", "Progress"),
    ("ExtendedTextBox", "输入并编辑单行文本", "TextField"),
    ("NumberBox", "输入具有最小值和最大值的数字", "TextField"),
    ("ToggleSwitch", "立即开启或关闭一项设置", "Switch"),
    ("SliderEx", "在最小值和最大值之间调整音量", "Slider"),
    ("SuperToolTip", "鼠标悬停时展示简短帮助说明", "Tooltip"),
    ("RadioButtons", "从互斥选项中选择一项", "RadioButton"),
    ("PopupEx", "锚定在按钮附近显示临时浮层", "Popover"),
    ("ResultListBox", "纵向展示可选择的搜索结果集合", "List"),
    ("CustomWindowTitleBar", "窗口顶部标题、图标和操作区", "AppBar"),
    ("NavigationView", "应用侧栏和页面导航菜单", "Drawer"),
    ("MultiSelectDataGrid", "按行列显示并多选结构化数据", "Table"),
)

SEMANTIC_HOLDOUT_CASES = (
    ("BusySpinner", "任务执行期间显示旋转的加载和等待状态", "Progress"),
    ("SecretEntry", "让用户输入隐藏字符的密码字段", "TextField"),
    ("SoundLevelControl", "在最小值到最大值之间连续调节音量", "Slider"),
    ("InlineHelpBubble", "鼠标悬停或键盘聚焦时显示简短帮助说明", "Tooltip"),
    ("SearchSuggestInput", "输入查询文字并显示可过滤的候选建议", "Autocomplete"),
    ("SideNavigationPane", "从页面左侧展开应用导航菜单", "Drawer"),
    ("RowColumnReport", "按表头、行和列显示结构化明细数据", "Table"),
    ("TemporaryAnchorPanel", "依附触发按钮附近显示临时浮层", "Popover"),
)


class ComponentKnowledgeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        with patch.dict(
            os.environ,
            {
                "OPENAI_API_KEY": "offline-placeholder",
                "OPENAI_BASE_URL": "http://127.0.0.1:1/v1",
            },
        ):
            cls.agent = MUISelectAgent(use_semantic_similarity=False)

    @classmethod
    def tearDownClass(cls) -> None:
        asyncio.run(cls.agent.close_llm())

    def test_all_standard_controls_have_deterministic_mapping(self) -> None:
        missing = sorted(set(WPF_BASE_CONTROLS) - set(self.agent.wpf_to_mui_mapping))
        self.assertEqual(missing, [])

    def test_excluded_entries_are_not_retrievable(self) -> None:
        self.assertNotIn("NumberField", self.agent.mui_components_index)
        self.assertNotIn("Masonry", self.agent.mui_components_index)

    def test_unknown_generic_control_does_not_fall_back_to_box(self) -> None:
        candidates = self.agent.retrieve_candidates(
            "完全未知的专有视觉对象", "CustomControl", k=3
        )
        self.assertLess(candidates[0][2], self.agent.minimum_confidence)

    def _assert_recall_quality(self, cases: tuple[tuple[str, str, str], ...]) -> None:
        reciprocal_ranks = []
        hits = 0
        for tag, description, expected in cases:
            names = [
                name
                for name, _, _ in self.agent.retrieve_candidates(
                    description, tag, k=3
                )
            ]
            if expected in names:
                hits += 1
                reciprocal_ranks.append(1 / (names.index(expected) + 1))
            else:
                reciprocal_ranks.append(0)

        recall_at_3 = hits / len(cases)
        mean_reciprocal_rank = sum(reciprocal_ranks) / len(cases)
        self.assertEqual(recall_at_3, 1.0)
        self.assertGreaterEqual(mean_reciprocal_rank, 0.8)

    def test_registered_custom_control_top3_recall_and_mrr(self) -> None:
        self._assert_recall_quality(CUSTOM_RECALL_CASES)

    def test_unregistered_name_semantic_holdout_recall_and_mrr(self) -> None:
        self._assert_recall_quality(SEMANTIC_HOLDOUT_CASES)


if __name__ == "__main__":
    unittest.main()
