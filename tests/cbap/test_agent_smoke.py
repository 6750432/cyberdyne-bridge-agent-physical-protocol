#!/usr/bin/env python3
"""Run each active agent subrepo's independent smoke test."""

from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SMOKES = [
    ROOT / "agents/cyberdyne/smoke.py",
    ROOT / "agents/mcp-mineflayer/smoke.py",
    ROOT / "agents/mindcraft/smoke.py",
    ROOT / "agents/voyager/smoke.py",
]


class AgentSmokeTest(unittest.TestCase):
    def test_active_agent_smokes(self):
        for smoke in SMOKES:
            result = subprocess.run(
                [sys.executable, str(smoke)],
                cwd=ROOT,
                capture_output=True,
                text=True,
                timeout=30,
            )
            self.assertEqual(
                result.returncode, 0,
                f"{smoke.name} failed:\nstdout={result.stdout}\nstderr={result.stderr}",
            )


if __name__ == "__main__":
    unittest.main()
