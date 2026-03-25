from __future__ import annotations

import unittest

from decision_layer.utils import extract_decision_from_text_or_json


class UtilsTests(unittest.TestCase):
    def test_access_status_true_is_accepted(self) -> None:
        payload = '{"plateNumber":"ABC123","accessStatus":true}'
        self.assertEqual(extract_decision_from_text_or_json(payload), "Accepted")

    def test_completed_false_is_denied(self) -> None:
        payload = '{"id":3,"completed":false}'
        self.assertEqual(extract_decision_from_text_or_json(payload), "Denied")


if __name__ == "__main__":
    unittest.main()

