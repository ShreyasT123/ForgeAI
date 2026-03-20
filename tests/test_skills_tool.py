import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from helius_agent.tools.skills import load_skill, register_skill, list_skills  # noqa: E402


class TestSkillsTool(unittest.TestCase):
    def test_load_skill_success(self):
        register_skill.invoke({
            "name": "example", 
            "description": "Example skill", 
            "content": "Do X then Y"
        })
        result = load_skill.invoke({"skill_name": "example"})
        self.assertIn("example", result)
        self.assertIn("Do X then Y", result)

    def test_load_skill_missing(self):
        result = load_skill.invoke({"skill_name": "missing"})
        self.assertIn("not found", result)

    def test_load_react_best_practices_skill(self):
        # This skill should be auto-loaded because it's in agent-skills/skills/
        # Check if it's available (might be under vercel-react-best-practices or react-best-practices)
        available = list_skills.invoke({})
        self.assertIn("react-best-practices", available.lower())
        
        # Try loading it
        result = load_skill.invoke({"skill_name": "vercel-react-best-practices"})
        if "not found" in result:
             result = load_skill.invoke({"skill_name": "react-best-practices"})
             
        self.assertNotIn("not found", result)
        self.assertIn("React Best Practices", result)


if __name__ == "__main__":
    unittest.main(verbosity=2)
