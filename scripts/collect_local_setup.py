#!/usr/bin/env python3
"""Generate a local environment report for Milestone 2 training readiness.

Usage:
  python scripts/collect_local_setup.py
  python scripts/collect_local_setup.py --output docs/artifacts/milestone2-local-setup.md
"""

from __future__ import annotations

import argparse
import json
import platform
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


@dataclass
class ToolStatus:
    name: str
    available: bool
    version: str
    path: str


def run_command(cmd: list[str]) -> tuple[bool, str]:
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    except Exception as exc:  # pragma: no cover - defensive
        return False, f"error: {exc}"

    output = (proc.stdout or proc.stderr).strip()
    if proc.returncode != 0:
        return False, output or f"non-zero exit code: {proc.returncode}"
    return True, output


def detect_tool(name: str, version_cmd: list[str]) -> ToolStatus:
    path = shutil.which(name)
    if not path:
        return ToolStatus(name=name, available=False, version="not found", path="-")

    ok, output = run_command(version_cmd)
    first_line = output.splitlines()[0] if output else "unknown"
    version = first_line if ok else f"unable to detect ({first_line})"
    return ToolStatus(name=name, available=True, version=version, path=path)


def get_python_packages(packages: Iterable[str]) -> dict[str, str]:
    results: dict[str, str] = {}
    for pkg in packages:
        code = (
            "import importlib.metadata as m; "
            f"print(m.version('{pkg}'))"
        )
        ok, output = run_command([sys.executable, "-c", code])
        results[pkg] = output if ok else "not installed"
    return results


def gather_report() -> dict:
    tool_checks = [
        ("python", [sys.executable, "--version"]),
        ("pip", [sys.executable, "-m", "pip", "--version"]),
        ("git", ["git", "--version"]),
        ("node", ["node", "--version"]),
        ("npm", ["npm", "--version"]),
        ("pnpm", ["pnpm", "--version"]),
        ("docker", ["docker", "--version"]),
    ]

    tools = [detect_tool(name, cmd) for name, cmd in tool_checks]
    python_packages = get_python_packages(["tensorflow", "tflite-runtime", "numpy", "pandas", "scikit-learn"])

    return {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "system": {
            "platform": platform.platform(),
            "python_executable": sys.executable,
            "python_version": platform.python_version(),
        },
        "tools": [tool.__dict__ for tool in tools],
        "python_packages": python_packages,
    }


def render_markdown(report: dict) -> str:
    tools = report["tools"]
    pkg = report["python_packages"]

    lines = [
        "# Milestone 2 Local Setup Report",
        "",
        f"Generated (UTC): `{report['generated_at_utc']}`",
        "",
        "## System",
        f"- Platform: `{report['system']['platform']}`",
        f"- Python executable: `{report['system']['python_executable']}`",
        f"- Python version: `{report['system']['python_version']}`",
        "",
        "## Tooling status",
        "| Tool | Available | Version | Path |",
        "|---|---|---|---|",
    ]

    for tool in tools:
        lines.append(
            f"| {tool['name']} | {'yes' if tool['available'] else 'no'} | "
            f"`{tool['version']}` | `{tool['path']}` |"
        )

    lines.extend(
        [
            "",
            "## Python package status",
            "| Package | Version |",
            "|---|---|",
        ]
    )

    for name, version in pkg.items():
        lines.append(f"| {name} | `{version}` |")

    missing_tools = [t["name"] for t in tools if not t["available"]]
    missing_pkgs = [name for name, version in pkg.items() if version == "not installed"]

    lines.extend(
        [
            "",
            "## Milestone 2 readiness summary",
            f"- Missing tools: `{', '.join(missing_tools) if missing_tools else 'none'}`",
            f"- Missing Python packages: `{', '.join(missing_pkgs) if missing_pkgs else 'none'}`",
            "",
            "## Raw JSON",
            "```json",
            json.dumps(report, indent=2),
            "```",
            "",
            "## What to upload",
            "Commit this file to the repo at `docs/artifacts/milestone2-local-setup.md` and share it with the team.",
        ]
    )

    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        default="docs/artifacts/milestone2-local-setup.md",
        help="Where to write the Markdown report.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = gather_report()
    text = render_markdown(report)

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(text, encoding="utf-8")

    print(f"Wrote Milestone 2 setup report to: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
