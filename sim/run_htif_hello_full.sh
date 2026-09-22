#!/usr/bin/env bash
# Full HTIF hello: run until tohost (no cycle cap), keep stdout, dump VCD.
set -euo pipefail
export JAVA_HOME=/mnt/d/cy-deps/jdk
export RISCV=/mnt/d/chipyard/riscv-tools-install
export PATH="/mnt/d/cy-deps/bin:${JAVA_HOME}/bin:${RISCV}/bin:${PATH}"
export LD_LIBRARY_PATH="/mnt/d/cy-deps/lib:${RISCV}/lib"

SIM=/mnt/d/chipyard/sims/verilator/simulator-chipyard-MediumBoomConfig-debug
OUT=/mnt/d/cy-tmp/boom_real
ELF="${OUT}/hello.riscv"
LOG="${OUT}/hello_full.log"
VCD="${OUT}/hello.vcd"
WIN_ELF=/mnt/c/Users/unnat/Documents/DecouplingCap/programs/build/hello.riscv

mkdir -p "${OUT}" /mnt/c/Users/unnat/Documents/DecouplingCap/programs/build
cp -f "${ELF}" "${WIN_ELF}"
cd "${OUT}"
rm -f "${VCD}" dump.vcd

echo "=== full hello: no max-cycles, VCD=${VCD} ==="
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
exit "${STATUS}"
