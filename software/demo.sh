#!/usr/bin/env bash
# Pre-flight for the 90-second demo.  Runbook: docs/DEMO_90S.md
# Usage:  ./demo.sh            start backend + agent, then arm
#         ./demo.sh arm        just re-arm an already-running stack (between rehearsals)
set -uo pipefail
cd "$(dirname "$0")"
[ -f ../.env ] && { set -a; . ../.env; set +a; }   # python does NOT read .env on its own
B=${BACKEND_URL:-http://127.0.0.1:8000}
SPEED=${SPEED:-4}
LOGS=${LOGS:-/tmp/wlb}

up () { curl -s -m5 -o /dev/null "$B/api/state"; }

start () {
  mkdir -p "$LOGS"
  if up; then echo "backend already up at $B"; else
    echo "starting backend -> $LOGS/backend.log"
    nohup python3 -m uvicorn backend.app:app --port "${B##*:}" > "$LOGS/backend.log" 2>&1 &
    for _ in $(seq 1 120); do up && break; done
    up || { echo "backend failed to start; see $LOGS/backend.log"; exit 1; }
  fi

  if pgrep -f "tsx src/index.ts" > /dev/null; then echo "agent already running"; else
    echo "starting agent -> $LOGS/agent.log"
    ( cd agent && nohup npx tsx src/index.ts > "$LOGS/agent.log" 2>&1 & )
    for _ in $(seq 1 150); do grep -q "online on" "$LOGS/agent.log" 2>/dev/null && break; done
    grep -q "online on" "$LOGS/agent.log" 2>/dev/null \
      && grep -E "operators:|online on" "$LOGS/agent.log" | tail -2 \
      || { echo "agent failed to start; see $LOGS/agent.log"; exit 1; }
  fi
}

arm () {
  if ! up; then
    echo "backend is not running at $B -- start it with:  ./demo.sh"
    exit 1
  fi
  echo "--- arming ---"
  curl -s -m10 -o /dev/null -X POST "$B/api/speed/$SPEED" && echo "speed        ${SPEED}x"

  local q; q=$(curl -s -m10 "$B/api/approvals")
  if [ "$q" = "[]" ]; then echo "approvals    empty"; else
    echo "approvals    NOT EMPTY -- a rehearsal left a request on the dashboard:"; echo "   $q" | head -c 300; echo
  fi

  curl -s -m30 -o /dev/null -X POST "$B/api/command" -H 'content-type: application/json' \
       -d '{"kind":"run_control","action":"reset"}' && echo "bench        reset"

  curl -s -m10 "$B/api/state" | python3 -c "
import json,sys; d=json.load(sys.stdin)
print('mode        ',d['mode']); print('connected   ',d['mega']['connected'])
print('vessels     ',' '.join(d['vessels']))
assert d['mega']['connected'], 'BENCH NOT CONNECTED'
"
  echo
  echo "dashboard    $B/          (camera: overview)"
  echo "agent line   the Photon project's shared iMessage line (Photon dashboard -> iMessage)"
  echo "operators    ${OPERATOR_PHONES:-(none set - see OPERATOR_PHONES in .env)}"
  echo
  echo "  0:00  i want to run the elephant toothpaste experiment"
  echo "  0:08  operator bench-2026"
  echo "  0:14  ok go ahead          <- clock starts; eruption ~1:18, done ~1:24"
  echo "  0:35  how does it look?"
  echo "  1:25  what did it weigh out?"
  echo
  echo "  short on time: 'run the quick demo: 20 g developer, 5 g yeast, 15 g water, 10 second activation'"
  echo "  something spills: text 'stop'"
}

[ "${1:-start}" = arm ] || start
arm
