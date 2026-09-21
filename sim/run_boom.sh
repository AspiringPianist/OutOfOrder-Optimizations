#!/usr/bin/env bash
# Run a RISC-V ELF on Medium BOOM and dump a VCD.
# Usage: run_boom.sh <elf> <out.vcd> [max_cycles]
set -euo pipefail
ELF="${1:?elf}"
VCD="${2:?vcd}"
MAX="${3:-100000}"
SIM="${BOOM_SIM:?set BOOM_SIM to the Chipyard Verilator/VCS simulator binary}"

mkdir -p "$(dirname "$VCD")"
# Chipyard 1.x TestDriver plusargs. Prefer a dump limited to boom_tile.
set +e
"$SIM" \
  +permissive \
  +max-cycles="$MAX" \
  +verbose \
  +vcdplusfile="$VCD" \
  +vcdfile="$VCD" \
  -v "$VCD" \
  +permissive-off \
  "$ELF"
STATUS=$?
set -e
if [[ ! -f "$VCD" ]]; then
  echo "Simulator exited $STATUS and did not write $VCD" >&2
  echo "Rebuild with tracing enabled, e.g. make CONFIG=MediumBoomConfig debug" >&2
  exit 1
fi
exit "$STATUS"
