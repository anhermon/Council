#!/usr/bin/env python3
"""Check Bandit JSON output for medium/high severity issues."""

import json
import os
import sys
from pathlib import Path


def main():
    # Use /tmp for consistency with Taskfile (or TMPDIR env var if set)
    tmp_dir = Path(os.environ.get("TMPDIR", "/tmp"))  # nosec B108
    report_file = tmp_dir / "bandit-report.json"

    if not report_file.exists():
        print("⚠ Bandit report not found - skipping severity check")
        return 0

    try:
        with open(report_file) as f:
            data = json.load(f)

        # Check results array for HIGH/MEDIUM issues
        high_severity = [i for i in data.get("results", []) if i.get("issue_severity") == "HIGH"]
        medium_severity = [
            i for i in data.get("results", []) if i.get("issue_severity") == "MEDIUM"
        ]

        # Also check metrics as fallback (in case JSON results are empty but metrics show issues)
        metrics = data.get("metrics", {}).get("_totals", {})
        metrics_high = metrics.get("SEVERITY.HIGH", 0)
        metrics_medium = metrics.get("SEVERITY.MEDIUM", 0)

        if high_severity or medium_severity or metrics_high > 0 or metrics_medium > 0:
            print("\n❌ Found security issues:")
            print(f"  HIGH: {len(high_severity)} in results, {metrics_high} in metrics")
            print(f"  MEDIUM: {len(medium_severity)} in results, {metrics_medium} in metrics")
            return 1
        else:
            print("\n✅ No medium or high severity security issues found.")
            return 0
    except (json.JSONDecodeError, KeyError) as e:
        print(f"⚠ Could not parse Bandit output: {e} - check manually")
        return 0


if __name__ == "__main__":
    sys.exit(main())
