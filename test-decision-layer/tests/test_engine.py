from __future__ import annotations

import unittest
from pathlib import Path

from decision_layer.config_loader import load_config
from decision_layer.engine import DecisionEngine


class EngineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        config = load_config(
            Path(__file__).resolve().parents[1] / "config" / "buildings.sample.json"
        )
        cls.engine = DecisionEngine(config)

    def test_api_route_accepts_known_plate(self) -> None:
        prompt = (
            "Hey, I'm Travis from Building-A. I lost my ticket. "
            "My Licence plate number is BYU0293."
        )
        result = self.engine.process_prompt(prompt)
        self.assertEqual(result.route, "api")
        self.assertEqual(result.decision, "Accepted")

    def test_cua_route_denies_unknown_plate(self) -> None:
        prompt = "Hi, I'm Sam from Building-B, plate number is ZZZ000."
        result = self.engine.process_prompt(prompt)
        self.assertEqual(result.route, "cua")
        self.assertEqual(result.decision, "Denied")
        self.assertIn("handoff", result.details)

    def test_openclaw_route_delegates(self) -> None:
        prompt = "Hello, I'm Morgan from Building-C. Licence plate is CAA123."
        result = self.engine.process_prompt(prompt)
        self.assertEqual(result.route, "openclaw")
        self.assertEqual(result.decision, "Delegating to openclaw")

    def test_unknown_building_denies(self) -> None:
        prompt = "Hi, I'm Lee from Building-Z. Plate number is A1B2C3."
        result = self.engine.process_prompt(prompt)
        self.assertEqual(result.decision, "Denied")
        self.assertEqual(result.route, "unrouted")


if __name__ == "__main__":
    unittest.main()

