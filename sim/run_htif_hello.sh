#!/usr/bin/env bash
# Build libgloss-htif, link hello with tohost, run MediumBoom (no pk).
set -euo pipefail
export JAVA_HOME=/mnt/d/cy-deps/jdk
export RISCV=/mnt/d/chipyard/riscv-tools-install
export PATH="/mnt/d/cy-deps/bin:${JAVA_HOME}/bin:${RISCV}/bin:${PATH}"
export LD_LIBRARY_PATH="/mnt/d/cy-deps/lib:${RISCV}/lib"
export CC="${RISCV}/bin/riscv64-unknown-elf-gcc"
export AR="${RISCV}/bin/riscv64-unknown-elf-ar"
export SIZE="${RISCV}/bin/riscv64-unknown-elf-size"

NM="${RISCV}/bin/riscv64-unknown-elf-nm"
SIM=/mnt/d/chipyard/sims/verilator/simulator-chipyard-MediumBoomConfig-debug
LIBSRC=/mnt/d/chipyard/toolchains/libgloss
LIBBLD=/mnt/d/cy-tmp/libgloss-build
UTIL="${LIBSRC}/util"
SRC=/mnt/c/Users/unnat/Documents/DecouplingCap/programs/hello.c
OUT=/mnt/d/cy-tmp/boom_real
ELF="${OUT}/hello.riscv"
LOG="${OUT}/hello_htif.log"

mkdir -p "${OUT}" "${LIBBLD}"

echo "=== build libgloss-htif ==="
if [[ ! -f "${LIBBLD}/libgloss_htif.a" ]]; then
  cd "${LIBBLD}"
  if [[ ! -f Makefile ]]; then
    "${LIBSRC}/configure" \
      --prefix="${RISCV}/riscv64-unknown-elf" \
      --host=riscv64-unknown-elf \
      --disable-multilib
  fi
  make -j2
else
  echo "already have ${LIBBLD}/libgloss_htif.a"
fi
ls -lh "${LIBBLD}/libgloss_htif.a"

echo "=== compile hello (htif_nano, tohost, no pk) ==="
cp -f "${UTIL}/htif.ld" "${LIBBLD}/htif.ld"
cp -f "${UTIL}/htif_nano.specs" "${LIBBLD}/htif_nano.specs"
cd "${OUT}"
"${CC}" -std=gnu99 -O2 -fno-common -fno-builtin-printf -Wall \
  -specs="${LIBBLD}/htif_nano.specs" -B"${LIBBLD}" -L"${LIBBLD}" \
  -static -mcmodel=medany -march=rv64imafdc -mabi=lp64d \
  "${SRC}" -o "${ELF}"
ls -lh "${ELF}"
echo "=== tohost symbols ==="
"${NM}" "${ELF}" | grep -E "tohost|fromhost"

echo "=== sim max-cycles=200000 (no +verbose) ==="
echo "start $(date -Is)"
set +e
"${SIM}" +permissive +max-cycles=200000 +permissive-off "${ELF}" > "${LOG}" 2>&1
STATUS=$?
set -e
echo "end $(date -Is) sim_exit=${STATUS}"
echo "----- log -----"
cat "${LOG}"
echo "----- end -----"
ls -lh "${LOG}"
exit "${STATUS}"
