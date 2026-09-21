#!/usr/bin/env bash
# Full MediumBoom load_step via pk. No VCD (too large). Log on D:.
set -euo pipefail
export JAVA_HOME=/mnt/d/cy-deps/jdk
export RISCV=/mnt/d/chipyard/riscv-tools-install
export PATH="/mnt/d/cy-deps/bin:${JAVA_HOME}/bin:${RISCV}/bin:${PATH}"
export LD_LIBRARY_PATH="/mnt/d/cy-deps/lib:${RISCV}/lib"

SIM=/mnt/d/chipyard/sims/verilator/simulator-chipyard-MediumBoomConfig-debug
PK="${RISCV}/riscv64-unknown-elf/bin/pk"
ELF=/mnt/d/cy-tmp/boom_real/load_step.riscv
OUT=/mnt/d/cy-tmp/boom_real
LOG="${OUT}/load_step_full.log"
MAX=4000000

cd "${OUT}"
echo "=== full sim max-cycles=${MAX} ==="
echo "start $(date -Is)"
set +e
"${SIM}" \
  +permissive +max-cycles="${MAX}" +permissive-off \
  "${PK}" "${ELF}" > "${LOG}" 2>&1
STATUS=$?
set -e
echo "end $(date -Is) sim_exit=${STATUS}"
tail -50 "${LOG}"
ls -lh "${LOG}"
