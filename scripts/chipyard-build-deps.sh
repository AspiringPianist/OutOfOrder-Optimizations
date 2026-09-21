#!/usr/bin/env bash
set -euo pipefail
export PREFIX=/mnt/d/cy-deps
export SRC=/mnt/d/cy-src
export BUILD="${HOME}/cy-build"
export PATH="${PREFIX}/bin:${PREFIX}/cmake/bin:${PREFIX}/jdk/bin:${PATH}"
export LD_LIBRARY_PATH="${PREFIX}/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
export LIBRARY_PATH="${PREFIX}/lib${LIBRARY_PATH:+:$LIBRARY_PATH}"
export CPATH="${PREFIX}/include${CPATH:+:$CPATH}"
export PKG_CONFIG_PATH="${PREFIX}/lib/pkgconfig${PKG_CONFIG_PATH:+:$PKG_CONFIG_PATH}"
export JAVA_HOME="${PREFIX}/jdk"
export MAKEFLAGS="${MAKEFLAGS:--j2}"
mkdir -p "${PREFIX}" "${BUILD}" "${PREFIX}/bin"

echo "=== disk ==="
df -h / /mnt/d | cat

if [ ! -x "${PREFIX}/jdk/bin/java" ]; then
  echo "=== JDK ==="
  mkdir -p "${PREFIX}/jdk"
  tar -xzf /mnt/d/OpenJDK11U-jdk_x64_linux_hotspot_11.0.28_6.tar.gz -C "${PREFIX}/jdk" --strip-components=1
fi
java -version

if [ ! -x "${PREFIX}/cmake/bin/cmake" ]; then
  echo "=== CMake ==="
  mkdir -p "${PREFIX}/cmake"
  tar -xzf "${SRC}/cmake-3.28.6-linux-x86_64.tar.gz" -C "${PREFIX}/cmake" --strip-components=1
fi
cmake --version | head -1

if [ ! -x "${PREFIX}/bin/autoconf" ]; then
  echo "=== autoconf ==="
  rm -rf "${BUILD}/autoconf"
  mkdir -p "${BUILD}/autoconf"
  tar -xf "${SRC}/autoconf-2.71.tar.gz" -C "${BUILD}/autoconf" --strip-components=1
  ( cd "${BUILD}/autoconf" && ./configure --prefix="${PREFIX}" && make && make install )
fi
autoconf --version | head -1

if [ ! -x "${PREFIX}/bin/automake" ]; then
  echo "=== automake ==="
  rm -rf "${BUILD}/automake"
  mkdir -p "${BUILD}/automake"
  tar -xf "${SRC}/automake-1.16.5.tar.gz" -C "${BUILD}/automake" --strip-components=1
  ( cd "${BUILD}/automake" && ./configure --prefix="${PREFIX}" && make && make install )
fi

if [ ! -x "${PREFIX}/bin/libtool" ]; then
  echo "=== libtool ==="
  rm -rf "${BUILD}/libtool"
  mkdir -p "${BUILD}/libtool"
  tar -xf "${SRC}/libtool-2.4.7.tar.gz" -C "${BUILD}/libtool" --strip-components=1
  ( cd "${BUILD}/libtool" && ./configure --prefix="${PREFIX}" && make && make install )
fi

if [ ! -f "${PREFIX}/lib/libgmp.a" ] && [ ! -f "${PREFIX}/lib/libgmp.so" ]; then
  echo "=== gmp ==="
  rm -rf "${BUILD}/gmp"
  mkdir -p "${BUILD}/gmp"
  tar -xf "${SRC}/gmp-6.3.0.tar.xz" -C "${BUILD}/gmp" --strip-components=1
  ( cd "${BUILD}/gmp" && ./configure --prefix="${PREFIX}" --enable-cxx && make && make install )
fi

if [ ! -f "${PREFIX}/lib/libmpfr.a" ] && [ ! -f "${PREFIX}/lib/libmpfr.so" ]; then
  echo "=== mpfr ==="
  rm -rf "${BUILD}/mpfr"
  mkdir -p "${BUILD}/mpfr"
  tar -xf "${SRC}/mpfr-4.2.1.tar.xz" -C "${BUILD}/mpfr" --strip-components=1
  ( cd "${BUILD}/mpfr" && ./configure --prefix="${PREFIX}" --with-gmp="${PREFIX}" && make && make install )
fi

if [ ! -f "${PREFIX}/lib/libmpc.a" ] && [ ! -f "${PREFIX}/lib/libmpc.so" ]; then
  echo "=== mpc ==="
  rm -rf "${BUILD}/mpc"
  mkdir -p "${BUILD}/mpc"
  tar -xf "${SRC}/mpc-1.3.1.tar.gz" -C "${BUILD}/mpc" --strip-components=1
  ( cd "${BUILD}/mpc" && ./configure --prefix="${PREFIX}" --with-gmp="${PREFIX}" --with-mpfr="${PREFIX}" && make && make install )
fi

if [ ! -x "${PREFIX}/bin/makeinfo" ]; then
  echo "=== texinfo ==="
  rm -rf "${BUILD}/texinfo"
  mkdir -p "${BUILD}/texinfo"
  tar -xf "${SRC}/texinfo-7.1.tar.xz" -C "${BUILD}/texinfo" --strip-components=1
  ( cd "${BUILD}/texinfo" && ./configure --prefix="${PREFIX}" && make && make install )
fi

if [ ! -x "${PREFIX}/bin/help2man" ]; then
  echo "=== help2man ==="
  rm -rf "${BUILD}/help2man"
  mkdir -p "${BUILD}/help2man"
  tar -xf "${SRC}/help2man-1.49.3.tar.xz" -C "${BUILD}/help2man" --strip-components=1
  ( cd "${BUILD}/help2man" && ./configure --prefix="${PREFIX}" && make && make install ) || echo "help2man failed (optional)"
fi

if [ ! -x "${PREFIX}/bin/verilator" ]; then
  echo "=== verilator 4.034 ==="
  rm -rf "${BUILD}/verilator"
  mkdir -p "${BUILD}/verilator"
  tar -xzf /mnt/d/verilator-4.034.tar.gz -C "${BUILD}/verilator" --strip-components=1
  (
    cd "${BUILD}/verilator"
    # Bison 3.7+ includes the generated header instead of pasting it.
    python3 - <<'PY'
from pathlib import Path
p = Path("src/verilog.y")
t = p.read_text()
needle = "class AstSenTree;\n%}\n"
insert = needle + "\nBISONPRE_VERSION(3.7,%define api.header.include {\"V3ParseBison.h\"})\n"
if "api.header.include" not in t:
    if needle not in t:
        raise SystemExit("verilog.y patch point not found")
    p.write_text(t.replace(needle, insert, 1))
    print("patched src/verilog.y for bison 3.7+")
else:
    print("verilog.y already patched")
PY
    autoconf
    ./configure --prefix="${PREFIX}"
    make
    make install
  )
fi
verilator --version || true

echo "DEPS_DONE"
java -version
autoconf --version | head -1
verilator --version
