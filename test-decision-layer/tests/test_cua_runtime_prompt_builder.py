from __future__ import annotations

import unittest

from cua_runtime.prompt_builder import build_task_prompt, resolve_connection_details


class RuntimePromptBuilderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.connections = {
            "nomachine": {
                "building_cua_host": {
                    "name": "Building-CUA Host",
                    "ip": "10.0.0.10",
                    "port": 4000,
                    "username": "u",
                    "password": "p",
                }
            }
        }

    def test_build_task_prompt_injects_connection_details_for_ref(self) -> None:
        prompt = build_task_prompt(
            task_text="Connect to the remote host.",
            connections=self.connections,
            connection_ref="building_cua_host",
        )

        self.assertIn("Connection reference: building_cua_host", prompt)
        self.assertIn("Remote connection app: NoMachine", prompt)
        self.assertIn("Connection name: Building-CUA Host", prompt)
        self.assertIn("IP: 10.0.0.10", prompt)
        self.assertIn("Port: 4000", prompt)
        self.assertIn("Username: u", prompt)
        self.assertIn("Password: p", prompt)

    def test_build_task_prompt_without_ref_returns_original_text(self) -> None:
        prompt = build_task_prompt(
            task_text="Connect to the remote host.",
            connections=self.connections,
            connection_ref=None,
        )

        self.assertEqual(prompt, "Connect to the remote host.")

    def test_resolve_connection_details_rejects_unknown_ref(self) -> None:
        with self.assertRaises(KeyError):
            resolve_connection_details(self.connections, "missing_ref")


if __name__ == "__main__":
    unittest.main()
