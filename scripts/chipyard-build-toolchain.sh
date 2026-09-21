#!/usr/bin/env bash
# Slim RISC-V toolchain: newlib elf-gcc + Spike fesvr + pk + libgloss.
# Skips linux-gnu gcc, qemu, and dromajo (not needed for BOOM Verilator + LACPo).
set -euo pipefail
PREFIX="${PREFIX:-/mnt/d/cy-deps}"
CHIPYARD="${CHIPYARD:-/mnt/d/chipyard}"
RISCV="${RISCV:-${CHIPYARD}/riscv-tools-install}"
export PATH="${PREFIX}/bin:${PREFIX}/cmake/bin:${PREFIX}/jdk/bin:${PATH}"
export LD_LIBRARY_PATH="${PREFIX}/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
export LIBRARY_PATH="${PREFIX}/lib${LIBRARY_PATH:+:$LIBRARY_PATH}"
export CPATH="${PREFIX}/include${CPATH:+:$CPATH}"
export PKG_CONFIG_PATH="${PREFIX}/lib/pkgconfig${PKG_CONFIG_PATH:+:$PKG_CONFIG_PATH}"
export JAVA_HOME="${PREFIX}/jdk"
export RISCV
export MAKEFLAGS="${MAKEFLAGS:--j2}"
NPROC="${NPROC:-2}"

if [ ! -x "${PREFIX}/bin/autoconf" ] || [ ! -x "${PREFIX}/jdk/bin/java" ]; then
  echo "Run scripts/chipyard-build-deps.sh first (autoconf + JDK missing)."
  exit 1
fi

mkdir -p "${RISCV}"
GNU="${CHIPYARD}/toolchains/riscv-tools/riscv-gnu-toolchain"
BUILD="${HOME}/cy-build/gnu-toolchain"

if [ ! -x "${RISCV}/bin/riscv64-unknown-elf-gcc" ]; then
  echo "=== riscv64-unknown-elf-gcc (newlib, no linux) ==="
  rm -rf "${BUILD}"
  mkdir -p "${BUILD}"
  (
    cd "${BUILD}"
  "${GNU}/configure" --prefix="${RISCV}" --with-cmodel=medany --disable-gdb \
    --with-gmp="${PREFIX}" --with-mpfr="${PREFIX}" --with-mpc="${PREFIX}"
    make -j"${NPROC}"
  )
else
  echo "=== skip elf-gcc (already installed) ==="
fi

ISA="${CHIPYARD}/toolchains/riscv-tools/riscv-isa-sim"
if [ ! -x "${RISCV}/bin/spike" ]; then
  echo "=== spike / libfesvr ==="
  rm -rf "${HOME}/cy-build/isa-sim"
  mkdir -p "${HOME}/cy-build/isa-sim"
  (
    cd "${HOME}/cy-build/isa-sim"
    "${ISA}/configure" --prefix="${RISCV}"
    make -j"${NPROC}"
    make install
    # static fesvr for TestHarness
    make libfesvr.a || true
    if [ -f libfesvr.a ]; then
      cp -p libfesvr.a "${RISCV}/lib/"
    elif [ -f "${ISA}/build/libfesvr.a" ]; then
      cp -p "${ISA}/build/libfesvr.a" "${RISCV}/lib/"
    fi
  )
else
  echo "=== skip spike (already installed) ==="
  if [ ! -f "${RISCV}/lib/libfesvr.a" ]; then
    echo "=== libfesvr.a ==="
    mkdir -p "${HOME}/cy-build/isa-sim"
    (
      cd "${HOME}/cy-build/isa-sim"
      if [ ! -f Makefile ]; then
        "${ISA}/configure" --prefix="${RISCV}"
      fi
      make libfesvr.a
      mkdir -p "${RISCV}/lib"
      cp -p libfesvr.a "${RISCV}/lib/"
    )
  fi
fi

PK="${CHIPYARD}/toolchains/riscv-tools/riscv-pk"
if [ ! -x "${RISCV}/riscv64-unknown-elf/bin/pk" ] && [ ! -x "${RISCV}/bin/pk" ]; then
  echo "=== proxy kernel ==="
  rm -rf "${HOME}/cy-build/pk"
  mkdir -p "${HOME}/cy-build/pk"
  (
    cd "${HOME}/cy-build/pk"
    CC= CXX= "${PK}/configure" --prefix="${RISCV}" --host=riscv64-unknown-elf
    make -j"${NPROC}"
    make install
  )
fi

GLOSS="${CHIPYARD}/toolchains/libgloss"
if [ ! -f "${RISCV}/riscv64-unknown-elf/lib/libgloss_htif.a" ] && [ ! -f "${RISCV}/riscv64-unknown-elf/lib/libgloss.a" ]; then
  echo "=== libgloss-htif ==="
  rm -rf "${HOME}/cy-build/libgloss"
  mkdir -p "${HOME}/cy-build/libgloss"
  (
    cd "${HOME}/cy-build/libgloss"
    "${GLOSS}/configure" --prefix="${RISCV}/riscv64-unknown-elf" --host=riscv64-unknown-elf
    make -j"${NPROC}"
    make install
  )
fi

ENV_FILE="${CHIPYARD}/env.sh"
{
  echo "# auto-generated slim toolchain (elf only, no qemu/linux)"
  echo "export CHIPYARD_TOOLCHAIN_SOURCED=1"
  echo "export JAVA_HOME=${PREFIX}/jdk"
  echo "export RISCV=${RISCV}"
  echo "export PATH=${PREFIX}/bin:${PREFIX}/cmake/bin:\${JAVA_HOME}/bin:\${RISCV}/bin:\${PATH}"
  echo "export LD_LIBRARY_PATH=${PREFIX}/lib:\${RISCV}/lib\${LD_LIBRARY_PATH:+:\${LD_LIBRARY_PATH}}"
  echo "export LIBRARY_PATH=${PREFIX}/lib\${LIBRARY_PATH:+:\${LIBRARY_PATH}}"
  echo "export CPATH=${PREFIX}/include\${CPATH:+:\${CPATH}}"
  echo "export PKG_CONFIG_PATH=${PREFIX}/lib/pkgconfig\${PKG_CONFIG_PATH:+:\${PKG_CONFIG_PATH}}"
} > "${ENV_FILE}"

echo "TOOLCHAIN_DONE"
riscv64-unknown-elf-gcc --version | head -1
ls -l "${RISCV}/lib/libfesvr.a"
