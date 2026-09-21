#!/usr/bin/env bash
# Bring up a matching Chipyard/BOOM Verilator sim in WSL.
# LACPo models were trained on example.TestHarness.MediumBoomConfig (chipyard 1.3.0).
# WSL often cannot reach GitHub; clone/submodules must use Windows Git onto D:\chipyard.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CHIPYARD="${CHIPYARD:-/mnt/d/chipyard}"
PREFIX="${PREFIX:-/mnt/d/cy-deps}"

echo "CHIPYARD=$CHIPYARD PREFIX=$PREFIX"
if [[ ! -d "$CHIPYARD/generators/boom" ]]; then
  echo "Clone Chipyard 1.3.0 to D:\\chipyard with Windows Git first (WSL git to GitHub is blocked)."
  exit 1
fi

bash "$ROOT/scripts/chipyard-build-deps.sh"
bash "$ROOT/scripts/chipyard-build-toolchain.sh"
# shellcheck disable=SC1091
source "$CHIPYARD/env.sh"

mkdir -p "$CHIPYARD/sims/verilator"
cd "$CHIPYARD/sims/verilator"
make CONFIG=MediumBoomConfig debug -j2

echo "Simulator: $CHIPYARD/sims/verilator/simulator-example-MediumBoomConfig-debug"
echo "export BOOM_SIM=$CHIPYARD/sims/verilator/simulator-example-MediumBoomConfig-debug"
