from __future__ import annotations

import unittest
from pathlib import Path

from decision_layer.config_loader import load_config
from decision_layer.prompt_parser import parse_prompt


class PromptParserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.config = load_config(
            Path(__file__).resolve().parents[1] / "config" / "buildings.sample.json"
        )

    def test_extracts_driver_prompt_fields(self) -> None:
        prompt = (
            "Hey, I'm Travis from Building-A. I lost my ticket. "
            "My Licence plate number is BYU0293. Can you patch me through"
        )
        parsed = parse_prompt(prompt, self.config.alias_lookup)

        self.assertEqual(parsed.requester_name, "Travis")
        self.assertEqual(parsed.building_id, "Building-A")
        self.assertEqual(parsed.license_plate, "BYU0293")

    def test_handles_missing_plate(self) -> None:
        prompt = "Hi, I am Alex from Building-A and lost my ticket."
        parsed = parse_prompt(prompt, self.config.alias_lookup)
        self.assertEqual(parsed.building_id, "Building-A")
        self.assertIsNone(parsed.license_plate)


if __name__ == "__main__":
    unittest.main()
