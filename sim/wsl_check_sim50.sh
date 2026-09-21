#!/usr/bin/env bash
set -euo pipefail
export RISCV=/mnt/d/chipyard/riscv-tools-install
export LD_LIBRARY_PATH="/mnt/d/cy-deps/lib:${RISCV}/lib"
SIM=/mnt/d/chipyard/sims/verilator/simulator-chipyard-MediumBoomConfig-debug
ELF=/mnt/c/Users/unnat/Documents/DecouplingCap/programs/build/load_step.riscv
OUT=/mnt/d/cy-tmp/wsl_check
mkdir -p "$OUT"
cd "$OUT"
echo "start $(date -Is)"
set +e
timeout 180s "$SIM" +permissive +max-cycles=50 +permissive-off "$ELF" >sim_50.log 2>&1
echo "sim50_exit=$?"
set -e
echo "end $(date -Is)"
tail -25 sim_50.log
ls -lh
echo "=== vcd 50 cycles ==="
set +e
timeout 180s "$SIM" +permissive +max-cycles=50 +vcdfile="$OUT/dump.vcd" -v "$OUT/dump.vcd" +permissive-off "$ELF" >sim_vcd50.log 2>&1
echo "vcd_exit=$?"
set -e
ls -lh dump.vcd "$OUT/dump.vcd" 2>/dev/null || echo "NO vcd"
tail -15 sim_vcd50.log
