#!/usr/bin/env bash
# Check whether we can produce cycle-level I[n] from WSL.
set -euo pipefail
export JAVA_HOME=/mnt/d/cy-deps/jdk
export RISCV=/mnt/d/chipyard/riscv-tools-install
export PATH="/mnt/d/cy-deps/bin:/mnt/d/cy-deps/cmake/bin:${JAVA_HOME}/bin:${RISCV}/bin:${PATH}"
export LD_LIBRARY_PATH="/mnt/d/cy-deps/lib:${RISCV}/lib${LD_LIBRARY_PATH:+:${LD_LIBRARY_PATH}}"

SIM=/mnt/d/chipyard/sims/verilator/simulator-chipyard-MediumBoomConfig-debug
ELF=/mnt/c/Users/unnat/Documents/DecouplingCap/programs/build/load_step.riscv
OUT=/mnt/c/Users/unnat/Documents/DecouplingCap/traces/wsl_check
mkdir -p "$OUT"

echo "=== toolchain ==="
echo "RISCV=$RISCV"
ls -lh "$RISCV/bin/riscv64-unknown-elf-gcc" "$SIM" "$ELF"
ls "$RISCV/bin" | head
echo "pk candidates:"
ls "$RISCV/riscv64-unknown-elf/bin/pk" 2>/dev/null || true
ls "$RISCV/bin/pk" 2>/dev/null || true

echo "=== short RTL sim (no VCD, 200 cycles) ==="
set +e
"$SIM" \
  +permissive \
  +max-cycles=200 \
  +verbose \
  +permissive-off \
  "$ELF" \
  >"$OUT/sim_200.log" 2>&1
SIM_STATUS=$?
set -e
echo "sim_exit=$SIM_STATUS"
tail -30 "$OUT/sim_200.log"

echo "=== try VCD dump 200 cycles ==="
set +e
"$SIM" \
  +permissive \
  +max-cycles=200 \
  +vcdfile="$OUT/dump.vcd" \
  -v "$OUT/dump.vcd" \
  +permissive-off \
  "$ELF" \
  >"$OUT/sim_vcd_200.log" 2>&1
VCD_STATUS=$?
set -e
echo "vcd_sim_exit=$VCD_STATUS"
ls -lh "$OUT"/dump.vcd 2>/dev/null || echo "NO dump.vcd"
# verilator debug often writes dump.vcd in cwd
ls -lh dump.vcd ./dump.vcd /mnt/d/chipyard/sims/verilator/dump.vcd 2>/dev/null || true
tail -20 "$OUT/sim_vcd_200.log"
echo "=== done ==="
