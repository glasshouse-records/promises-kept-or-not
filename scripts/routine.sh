#!/bin/sh
# The standing chores, with no model in the loop: capture every tracked policy
# page (the one artefact that cannot be back-filled once a page changes),
# refresh the enforcement sources that have a working endpoint, then ask the
# doctor what is wrong. Prints only what needs attention. Exit 0 = nothing to
# do; exit 1 = a human or the source-medic agent should look at the output.
cd "$(dirname "$0")/.." || exit 2
log=data/routine/$(date +%F).log
mkdir -p data/routine
: >"$log.errors"
step() { echo "== $*" >>"$log"; "$@" >>"$log" 2>&1 || echo "step failed: $*" >>"$log.errors"; }
step .venv/bin/glasshouse ingest commitments
step .venv/bin/glasshouse ingest enforcement --source fed
step .venv/bin/glasshouse ingest enforcement --source doj_fcpa
step .venv/bin/glasshouse integrity
# The doctor exits non-zero when it finds errors, so its exit code cannot tell
# "found problems" from "crashed". A run that printed no verdict line crashed.
doc=$(.venv/bin/glasshouse doctor 2>&1)
echo "$doc" | grep -qE "\[(ok |ERR|WRN)\]" || echo "doctor produced no report (crashed?): $(echo "$doc" | tail -1)" >>"$log.errors"
echo "$doc" | grep -E "\[ERR\]" | grep -v "queue:" >>"$log.errors"
# A changed policy is news; a capture that failed today is a hole in the one
# record that cannot be back-filled. Both are surfaced, each once.
grep -E "^  .*NEW VERSION" "$log" | sort -u
grep -E "WARNING glasshouse.ingest.commitments" "$log" | sed 's/^WARNING glasshouse.ingest.commitments: /capture problem: /' | cut -c1-200 | sort -u >>"$log.errors"
if [ -s "$log.errors" ]; then cat "$log.errors"; echo "log: $log"; exit 1; fi
echo "routine ok ($(date +%F)); log: $log"
