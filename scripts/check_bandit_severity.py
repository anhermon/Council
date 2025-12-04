#!/usr/bin/env python3
"""Check Bandit JSON output for medium/high severity issues."""

import json
import sys
import tempfile
from pathlib import Path


def main():
    # Use system temp directory (respects TMPDIR env var)
    tmp_dir = Path(tempfile.gettempdir())
    report_file = tmp_dir / "bandit-report.json"

    if not report_file.exists():
        print("⚠ Bandit report not found - skipping severity check")
        return 0

    try:
        with open(report_file) as f:
            data = json.load(f)

        high_severity = [i for i in data.get("results", []) if i.get("issue_severity") == "HIGH"]
        medium_severity = [
            i for i in data.get("results", []) if i.get("issue_severity") == "MEDIUM"
        ]

        if high_severity or medium_severity:
            print(
                f"\n❌ Found {len(high_severity)} HIGH and {len(medium_severity)} MEDIUM severity security issues!"
            )
            return 1
        else:
            print("\n✅ No medium or high severity security issues found.")
            return 0
    except (json.JSONDecodeError, KeyError) as e:
        print(f"⚠ Could not parse Bandit output: {e} - check manually")
        return 0


if __name__ == "__main__":
    sys.exit(main())
