#!/usr/bin/env python3
"""Remove unused arguments from test functions based on ruff ARG002 errors."""

import json
import re
import subprocess
import sys
from pathlib import Path

# Get ruff output in JSON format
result = subprocess.run(
    ["uv", "run", "ruff", "check", "tests/", "--select", "ARG002", "--output-format=json"],
    capture_output=True,
    text=True,
)

if result.returncode != 0 and not result.stdout:
    print("No ruff output or error occurred")
    sys.exit(1)

try:
    data = json.loads(result.stdout)
except json.JSONDecodeError:
    print("Failed to parse ruff JSON output")
    sys.exit(1)

files_to_fix = {}

for item in data:
    file_path = item["filename"]
    line_num = item["location"]["row"]
    message = item["message"]

    # Extract argument name from message
    arg_match = re.search(r"`([^`]+)`", message)
    if arg_match:
        arg_name = arg_match.group(1)
        if file_path not in files_to_fix:
            files_to_fix[file_path] = []
        files_to_fix[file_path].append((line_num, arg_name))

# Fix files
total_fixed = 0
for file_path, fixes in files_to_fix.items():
    path = Path(file_path)
    if not path.exists():
        continue

    content = path.read_text()
    lines = content.split("\n")

    # Process fixes in reverse order to maintain line numbers
    fixes.sort(reverse=True)

    for line_num, arg_name in fixes:
        idx = line_num - 1
        if idx < len(lines):
            line = lines[idx]
            original = line

            # Remove argument with proper comma handling
            # Pattern: def test(self, arg1, unused_arg, arg2):
            # Remove: , unused_arg
            line = re.sub(rf",\s*{re.escape(arg_name)}(?=\s*,|\s*\)|$)", "", line)
            # Pattern: def test(self, unused_arg, arg2):
            # Remove: unused_arg,
            if line == original:
                line = re.sub(rf"{re.escape(arg_name)}\s*,\s*", "", line)
            # Pattern: def test(self, unused_arg):
            # Remove: , unused_arg
            if line == original:
                line = re.sub(rf",\s*{re.escape(arg_name)}\s*\)", ")", line)

            if line != original:
                lines[idx] = line
                total_fixed += 1

    path.write_text("\n".join(lines))
    print(f"Fixed {len(fixes)} issues in {file_path}")

print(f"\nTotal issues fixed: {total_fixed} in {len(files_to_fix)} files")
