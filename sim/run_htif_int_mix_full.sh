#!/usr/bin/env bash
# Full HTIF int_mix: run until tohost, dump VCD (do not git the VCD).
set -euo pipefail
export JAVA_HOME=/mnt/d/cy-deps/jdk
export RISCV=/mnt/d/chipyard/riscv-tools-install
export PATH="/mnt/d/cy-deps/bin:${JAVA_HOME}/bin:${RISCV}/bin:${PATH}"
export LD_LIBRARY_PATH="/mnt/d/cy-deps/lib:${RISCV}/lib"

SIM=/mnt/d/chipyard/sims/verilator/simulator-chipyard-MediumBoomConfig-debug
OUT=/mnt/d/cy-tmp/boom_real
ELF="${OUT}/int_mix.riscv"
LOG="${OUT}/int_mix_full.log"
VCD="${OUT}/int_mix.vcd"
WIN_LOG=/mnt/c/Users/unnat/Documents/DecouplingCap/results/int_mix/sim_full.log

mkdir -p "${OUT}" /mnt/c/Users/unnat/Documents/DecouplingCap/results/int_mix
cd "${OUT}"
rm -f "${VCD}" dump.vcd

echo "=== full int_mix: no max-cycles, VCD=${VCD} ==="
ls -lh "${ELF}" "${SIM}"
echo "start $(date -Is)"
set +e
"${SIM}" \
  +permissive \
  +vcdfile="${VCD}" \
  -v "${VCD}" \
  +permissive-off \
  "${ELF}" > "${LOG}" 2>&1
STATUS=$?
set -e
echo "end $(date -Is) sim_exit=${STATUS}"
echo "----- log -----"
cat "${LOG}"
echo "----- end -----"
ls -lh "${LOG}" "${VCD}" dump.vcd 2>/dev/null || true
cp -f "${LOG}" "${WIN_LOG}"
exit "${STATUS}"
