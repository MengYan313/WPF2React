"""WPF 迁移提示词与 JSON 输出协议的离线契约测试。"""

import unittest
from pathlib import Path

from src.migration.component_migrate_agent import ComponentMigrateAgent
from src.migration.cs_migrate_agent import CsMigrateAgent
from src.migration.json_schemas import (
    DESCRIPTION_SCHEMA,
    PAGE_ANALYSIS_SCHEMA,
    TYPESCRIPT_ANALYSIS_SCHEMA,
    TYPESCRIPT_CODE_SCHEMA,
)


class PromptContractTests(unittest.TestCase):
    SOURCE_DIR = Path(__file__).resolve().parents[2] / "src" / "migration"

    def test_llm_agent_sources_do_not_reintroduce_marker_protocol(self):
        forbidden = (
            "[JSON]",
            "[/JSON]",
            "[TypeScript Code]",
            "[/TypeScript Code]",
            "extract_tag_content",
            "marker_mode",
            "You are ",
            "Migrate the following",
            "Analyze the following",
        )
        for path in sorted(self.SOURCE_DIR.glob("*_agent.py")):
            source = path.read_text(encoding="utf-8")
            for token in forbidden:
                self.assertNotIn(token, source, f"{path.name} 含旧协议: {token}")

    def test_domain_schemas_require_all_declared_fields(self):
        for schema in (
            DESCRIPTION_SCHEMA,
            PAGE_ANALYSIS_SCHEMA,
            TYPESCRIPT_ANALYSIS_SCHEMA,
            TYPESCRIPT_CODE_SCHEMA,
        ):
            self.assertEqual(schema["type"], "object")
            self.assertFalse(schema["additionalProperties"])
            self.assertEqual(
                set(schema["required"]),
                set(schema["properties"]),
            )

    def test_primary_system_prompts_use_shared_structure(self):
        prompts = (
            ComponentMigrateAgent._build_system_prompt(None),
            CsMigrateAgent._build_cs_migration_system_prompt(None),
        )
        for prompt in prompts:
            for section in ("# 角色", "# 目标", "# 成功标准", "# 约束", "# 输出"):
                self.assertIn(section, prompt)

    def test_cs_dynamic_context_stays_in_user_prompt(self):
        system_prompt = CsMigrateAgent._build_cs_migration_system_prompt(None)
        user_prompt = CsMigrateAgent._build_cs_migration_user_prompt(
            None,
            cs_source_code="public class Order {}",
            file_name="Models/Order.cs",
            dependencies=["Models/Customer.cs"],
            defined_types=["Order"],
            migrated_file_names={"Models/Customer.cs": "Models/Customer.ts"},
            files_info={"Models/Customer.cs": {"defined_types": ["Customer"]}},
            dependency_contents={"Models/Customer.cs": "export class Customer {}"},
        )
        self.assertNotIn("public class Order", system_prompt)
        self.assertNotIn("export class Customer", system_prompt)
        self.assertIn("public class Order", user_prompt)
        self.assertIn("export class Customer", user_prompt)
        self.assertIn("源码 ID：Models/Order.cs", user_prompt)
        self.assertIn("目标相对路径：Models/Order.ts", user_prompt)
        self.assertIn(
            "Models/Customer.cs -> Models/Customer.ts",
            user_prompt,
        )
        self.assertNotIn(".cs.cs", user_prompt)

        with self.assertRaisesRegex(ValueError, "必须以 .cs 结尾"):
            CsMigrateAgent._build_cs_migration_user_prompt(
                None,
                cs_source_code="public class Legacy {}",
                file_name="Legacy",
                dependencies=[],
                defined_types=["Legacy"],
                migrated_file_names={},
                files_info={},
            )


if __name__ == "__main__":
    unittest.main()
