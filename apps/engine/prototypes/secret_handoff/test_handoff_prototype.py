#!/usr/bin/env python3
"""Tests for minimal secret handoff prototype."""

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from handoff_prototype import run_handoff


class SecretHandoffPrototypeTests(unittest.TestCase):
    def test_successful_handoff(self) -> None:
        result = run_handoff(simulate_mismatch=False)
        self.assertTrue(result.success)
        self.assertIn("succeeded", result.reason)

    def test_nonce_mismatch_rejected_before_handoff(self) -> None:
        result = run_handoff(simulate_mismatch=True)
        self.assertFalse(result.success)
        self.assertIn("nonce mismatch", result.reason)


if __name__ == "__main__":
    unittest.main()
