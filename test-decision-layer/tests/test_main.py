from __future__ import annotations

import unittest

import main
from decision_layer.models import DecisionResult


class MainAlertTests(unittest.TestCase):
    def test_websocket_cua_completion_builds_normal_alert(self) -> None:
        result = DecisionResult(
            route="cua",
            decision="Accepted",
            reason="CUA websocket task completed",
            parsed_prompt={},
            details={"mode": "websocket"},
        )

        self.assertEqual(
            main._build_cua_alert(result),
            (
                "CUA task completed",
                "Decision: Accepted. Check the terminal for details.",
                "normal",
            ),
        )

    def test_websocket_cua_failure_builds_critical_alert(self) -> None:
        result = DecisionResult(
            route="cua",
            decision="Denied",
            reason="CUA websocket task timed out.",
            parsed_prompt={},
            details={"mode": "websocket"},
        )

        self.assertEqual(
            main._build_cua_alert(result),
            (
                "CUA needs attention",
                "CUA websocket task timed out. Check the terminal for details.",
                "critical",
            ),
        )

    def test_non_websocket_cua_does_not_alert(self) -> None:
        result = DecisionResult(
            route="cua",
            decision="Denied",
            reason="CUA simulation",
            parsed_prompt={},
            details={"mode": "simulate"},
        )

        self.assertIsNone(main._build_cua_alert(result))


if __name__ == "__main__":
    unittest.main()
