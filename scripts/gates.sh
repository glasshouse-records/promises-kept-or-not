#!/bin/sh
# The review gates, quietly: one line per gate, detail only on failure.
# Costs no model tokens to run and very few to read. `--full` adds doctor.
cd "$(dirname "$0")/.." || exit 2
fail=0
run() {
  name=$1; shift
  [ -x "$1" ] || { echo "FAIL  $name (missing $1)"; fail=1; return; }
  if out=$("$@" 2>&1); then echo "ok    $name"
  else echo "FAIL  $name"; echo "$out" | tail -30; fail=1; fi
}
run ruff      .venv/bin/ruff check src/ tests/
run semgrep   .venv/bin/semgrep --config .semgrep.yml src/ --error --quiet
run pytest    .venv/bin/pytest -q -x -p no:cacheprovider
run integrity .venv/bin/glasshouse integrity
if [ "$1" = "--full" ]; then
  out=$(.venv/bin/glasshouse doctor 2>&1)
  if ! echo "$out" | grep -qE "\[(ok |ERR|WRN)\]"; then
    echo "FAIL  doctor (no report)"; echo "$out" | tail -15; fail=1
  elif echo "$out" | grep -E "^\s*\[ERR\]"; then fail=1
  else echo "$out" | grep -E "^\s*\[WRN\]"; echo "ok    doctor"; fi
fi
exit $fail
