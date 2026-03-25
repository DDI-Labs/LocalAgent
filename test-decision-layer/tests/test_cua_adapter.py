from __future__ import annotations

import unittest

from decision_layer.adapters.cua_adapter import CuaAdapter


class CuaAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.adapter = CuaAdapter()

    def test_extracts_final_decision_marker(self) -> None:
        text = "Checked record.\nFINAL_DECISION: Accepted"
        self.assertEqual(self.adapter._extract_agent_decision(text), "Accepted")

    def test_extracts_completed_false_fallback(self) -> None:
        text = "The page shows completed: false"
        self.assertEqual(self.adapter._extract_agent_decision(text), "Denied")

    def test_build_task_prompt_includes_url_and_rule(self) -> None:
        handoff = {
            "building_id": "Building-CUA",
            "remote_connection_app": "NoMachine",
            "remote_host": "10.0.0.10",
            "credentials": {"username": "u", "password": "p"},
            "remote_verification_app": "Google Chrome",
            "verification_steps": ["Open Chrome"],
            "claimant": {"name": "Pat", "license_plate": "3"},
        }
        cua_cfg = {
            "decision_field": "completed",
            "verification_url_template": "https://jsonplaceholder.typicode.com/todos/{license_plate}",
        }

        prompt = self.adapter._build_cua_task_prompt(handoff, cua_cfg)
        self.assertIn("https://jsonplaceholder.typicode.com/todos/3", prompt)
        self.assertIn("FINAL_DECISION: Accepted", prompt)
        self.assertIn("'completed' is true", prompt)


if __name__ == "__main__":
    unittest.main()

