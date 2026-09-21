#!/usr/bin/env python
"""Run a custom program through BOOM RTL (if a sim exists) or a VCD, then LACPo.

Examples:
  python tools/run_program.py --c programs/load_step.c
  python tools/run_program.py --elf programs/build/load_step.riscv
  python tools/run_program.py --vcd traces/load_step/dump.vcd --name load_step
  python tools/run_program.py --dummy-vcd --name load_step --n-cycles 1024
"""
from __future__ import print_function

import argparse
import os
import subprocess
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from run_lacpo_flow import discover_blocks, predict_blocks, TRACES, VDD_V
from vcd2features import (
    needed_nets,
    raw_net,
    vcd_to_features,
    write_vcd,
)

CLOCK = "TestDriver.testHarness.TestHarness.boom_tile.core.lsu.clock"
WIN_PY37 = os.path.join(ROOT, ".envs", "py37", "python.exe")


def die(msg):
    sys.stderr.write(msg + "\n")
    sys.exit(1)


def wsl_path(win_path):
    p = os.path.abspath(win_path).replace("\\", "/")
    if len(p) >= 2 and p[1] == ":":
        return "/mnt/" + p[0].lower() + p[2:]
    return p


def have_wsl():
    try:
        r = subprocess.call(["wsl", "-d", "Ubuntu", "--", "true"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return r == 0
    except Exception:
        return False


def compile_c(src, out_elf):
    os.makedirs(os.path.dirname(out_elf) or ".", exist_ok=True)
    cc = os.environ.get("RISCV_CC", "riscv64-unknown-elf-gcc")
    cmd = [
        cc, "-O2", "-static", "-mcmodel=medany",
        "-march=rv64imafdc", "-mabi=lp64d",
        src, "-o", out_elf,
    ]
    if have_wsl() and os.name == "nt":
        wsrc = wsl_path(src)
        wout = wsl_path(out_elf)
        wdir = wsl_path(os.path.dirname(out_elf) or ".")
        inner = "mkdir -p %s && %s -O2 -static -mcmodel=medany -march=rv64imafdc -mabi=lp64d %s -o %s" % (
            wdir, cc, wsrc, wout)
        cmd = ["wsl", "-d", "Ubuntu", "--", "bash", "-lc", inner]
    print("compile:", " ".join(cmd) if cmd[0] != "wsl" else inner)
    r = subprocess.call(cmd)
    if r != 0:
        die("RISC-V compile failed. Install riscv64-unknown-elf-gcc in WSL or set RISCV_CC.")
    print("elf", out_elf)
    return out_elf


def run_simulator(elf, vcd_path, max_cycles):
    sim = os.environ.get("BOOM_SIM")
    if not sim:
        return None
    script = os.path.join(ROOT, "sim", "run_boom.sh")
    if have_wsl() and os.name == "nt":
        inner = "export BOOM_SIM=${BOOM_SIM:-%s}; bash %s %s %s %s" % (
            os.environ.get("BOOM_SIM", ""),
            wsl_path(script),
            wsl_path(elf),
            wsl_path(vcd_path),
            str(max_cycles),
        )
        cmd = ["wsl", "-d", "Ubuntu", "--", "bash", "-lc", inner]
    else:
        cmd = ["bash", script, elf, vcd_path, str(max_cycles)]
    print("sim:", inner if cmd[0] == "wsl" else " ".join(cmd))
    r = subprocess.call(cmd)
    if r != 0 or not os.path.isfile(vcd_path):
        return None
    return vcd_path


def dummy_vcd_for_program(name, n_cycles, out_vcd, blocks):
    """Activity-shaped dummy VCD used only until a real BOOM dump exists."""
    import numpy as np
    from run_lacpo_flow import activity_schedule
    feats = []
    for b in blocks:
        feats.extend(b["features"])
    nets = needed_nets(feats)
    act = activity_schedule(n_cycles)
    if "idle" in name:
        act = act * 0.05
    elif "matmul" in name or "burst" in name:
        act = np.clip(act * 1.2, 0, 1)
    elif "branch" in name:
        # sustained mid-high activity (frontend-ish dummy envelope)
        act = np.clip(act * 0.65 + 0.20, 0, 1)
    rng = np.random.RandomState(20260826)
    traces = {CLOCK: [1] * n_cycles}
    for net in nets:
        if net == CLOCK:
            continue
        traces[net] = [
            int(rng.randint(0, 2 ** 31) if rng.rand() < a else 0) for a in act
        ]
    os.makedirs(os.path.dirname(out_vcd) or ".", exist_ok=True)
    write_vcd(out_vcd, CLOCK, traces, period_ns=3)
    print("dummy vcd", out_vcd, "nets", len(traces), "cycles", n_cycles)
    return out_vcd


def main():
    p = argparse.ArgumentParser(description="Custom program -> BOOM activity -> LACPo P(t)/I(t)")
    p.add_argument("--c", dest="c_src", help="RISC-V C source")
    p.add_argument("--elf", help="Already-compiled rv64 ELF / .riscv")
    p.add_argument("--vcd", help="Existing BOOM VCD dump")
    p.add_argument("--dummy-vcd", action="store_true", help="Emit a dummy VCD (pipeline test, not RTL)")
    p.add_argument("--name", default=None)
    p.add_argument("--n-cycles", type=int, default=1024)
    p.add_argument("--max-cycles", type=int, default=100000)
    p.add_argument("--out", default=None)
    p.add_argument("--vdd", type=float, default=VDD_V)
    args = p.parse_args()

    name = args.name
    if not name:
        for cand in (args.c_src, args.elf, args.vcd):
            if cand:
                name = os.path.splitext(os.path.basename(cand))[0]
                break
        if not name:
            name = "program"
    out_dir = args.out or os.path.join(TRACES, name)
    os.makedirs(out_dir, exist_ok=True)

    elf = args.elf
    if args.c_src:
        elf = compile_c(args.c_src, os.path.join(ROOT, "programs", "build", name + ".riscv"))

    vcd = args.vcd
    if elf and not vcd and not args.dummy_vcd:
        vcd = run_simulator(elf, os.path.join(out_dir, "dump.vcd"), args.max_cycles)
        if vcd is None:
            print("No BOOM simulator yet (set BOOM_SIM or build via sim/setup_wsl.sh).")
            print("ELF is ready. Re-run with --vcd once the dump exists, or --dummy-vcd to test the power path.")
            if not args.dummy_vcd:
                return

    blocks = discover_blocks()
    if args.dummy_vcd and not vcd:
        vcd = dummy_vcd_for_program(name, args.n_cycles, os.path.join(out_dir, "dump.dummy.vcd"), blocks)

    if not vcd:
        die("Need --vcd, --dummy-vcd, or a working BOOM_SIM for --c/--elf")

    feats = []
    for b in blocks:
        feats.extend(b["features"])
    print("parsing VCD", vcd)
    features_df, period = vcd_to_features(vcd, feats, CLOCK)
    feat_path = os.path.join(out_dir, name + ".features.csv")
    features_df["Benchmark"] = name
    features_df.to_csv(feat_path, index=False)
    print("features", feat_path, "cycles", len(features_df), "period", period)

    predict_blocks(
        blocks,
        features_df=features_df,
        n_cycles=len(features_df),
        out_dir=out_dir,
        vdd=args.vdd,
        name=name,
    )


if __name__ == "__main__":
    main()
