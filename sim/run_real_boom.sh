#!/usr/bin/env bash
# Rebuild load_step and run MediumBoom (real RTL, no VCD).
set -euo pipefail
export JAVA_HOME=/mnt/d/cy-deps/jdk
export RISCV=/mnt/d/chipyard/riscv-tools-install
export PATH="/mnt/d/cy-deps/bin:${JAVA_HOME}/bin:${RISCV}/bin:${PATH}"
export LD_LIBRARY_PATH="/mnt/d/cy-deps/lib:${RISCV}/lib"

SIM=/mnt/d/chipyard/sims/verilator/simulator-chipyard-MediumBoomConfig-debug
PK="${RISCV}/riscv64-unknown-elf/bin/pk"
SRC=/mnt/c/Users/unnat/Documents/DecouplingCap/programs/load_step.c
OUT=/mnt/d/cy-tmp/boom_real
ELF="${OUT}/load_step.riscv"
WIN_ELF=/mnt/c/Users/unnat/Documents/DecouplingCap/programs/build/load_step.riscv
CC="${RISCV}/bin/riscv64-unknown-elf-gcc"
NM="${RISCV}/bin/riscv64-unknown-elf-nm"

mkdir -p "${OUT}" /mnt/c/Users/unnat/Documents/DecouplingCap/programs/build
cd "${OUT}"

echo "=== compile ==="
"${CC}" -O2 -static -mcmodel=medany -march=rv64imafdc -mabi=lp64d \
  "${SRC}" -o "${ELF}"
cp -f "${ELF}" "${WIN_ELF}"
ls -lh "${ELF}"
echo "=== tohost? ==="
"${NM}" "${ELF}" | grep -E "tohost|fromhost" || echo "NO tohost in ELF (will use pk)"
ls -lh "${PK}" "${SIM}"

echo "=== smoke 20k cycles with pk ==="
echo "start $(date -Is)"
set +e
"${SIM}" \
  +permissive +max-cycles=20000 +permissive-off \
  "${PK}" "${ELF}" > smoke20k.log 2>&1
SMOKE=$?
set -e
echo "end $(date -Is) smoke_exit=${SMOKE}"
tail -40 smoke20k.log
wc -c smoke20k.log
