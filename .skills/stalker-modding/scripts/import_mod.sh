#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if command -v python3 >/dev/null 2>&1; then
  exec python3 "$script_dir/import_mod.py" "$@"
fi
if command -v python >/dev/null 2>&1; then
  exec python "$script_dir/import_mod.py" "$@"
fi
"$script_dir/bootstrap_env.sh" ensure python
if command -v python3 >/dev/null 2>&1; then
  exec python3 "$script_dir/import_mod.py" "$@"
fi
if command -v python >/dev/null 2>&1; then
  exec python "$script_dir/import_mod.py" "$@"
fi
echo "Python was not found after bootstrap attempt." >&2
exit 1
