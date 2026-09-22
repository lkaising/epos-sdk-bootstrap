#!/usr/bin/env bash
# shellcheck shell=bash
set -Eeuo pipefail
PROJECT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)
cd -- "$PROJECT_DIR"
export PYTHONDONTWRITEBYTECODE=1 LC_ALL=C
/usr/bin/python3 -B -m unittest discover -s tests -p 'test_*.py' -v
mapfile -t shell_files < <(find . -type f \( -name '*.sh' -o -name 'bootstrap-epos-sdk' \) -not -path './.git/*' -print | sort)
for file in "${shell_files[@]}"; do
    bash -n "$file"
done
if command -v shellcheck >/dev/null 2>&1; then
    shellcheck -x "${shell_files[@]}"
else
    printf '[ERROR] shellcheck unavailable; static checks incomplete\n' >&2
    exit 1
fi
/usr/bin/python3 -B - <<'PY'
import ast
from pathlib import Path
paths = sorted(path for path in Path('.').rglob('*.py') if '.git' not in path.parts)
for path in paths:
    ast.parse(path.read_text(encoding='utf-8'), filename=str(path))
print(f'[ OK ] Python syntax: {len(paths)} files parsed without bytecode')
PY
printf '[ OK ] isolated tests, bash -n, and shellcheck -x passed\n'
