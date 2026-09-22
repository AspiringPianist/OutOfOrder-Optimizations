#!/usr/bin/env python3
"""Split LACPo composed P(t) into hardware-unit currents I_u = P_u / VDD."""
from __future__ import print_function

import csv
import json
import os
import sys

VDD = 1.1
TCLK_NS = 3.0

# LACPo block column -> (group, token_hint, units)
BLOCK_MAP = {
    "frontend__fetch_controller_1": ("frontend", "LOW", "I$, FTQ, fetch"),
    "frontend__bpdpipeline__btb_handpicked_signals_1": ("frontend", "LOW", "BTB"),
    "frontend__bpdpipeline__bpd__counter_table_1": ("frontend", "LOW", "gshare/BPD"),
    "core__decode_units_0_1": ("decode", "LOW", "decode0"),
    "core__decode_units_1_1": ("decode", "LOW", "decode1"),
    "core__rename_stage__freelist_history_1_1": ("rename_rob", "LOW", "int freelist"),
    "core__rename_stage___maptable_history_1_1": ("rename_rob", "LOW", "int maptable"),
    "core__fp_rename_stage__freelist_1": ("rename_rob", "MID", "fp freelist"),
    "core__fp_rename_stage__maptable_1": ("rename_rob", "MID", "fp maptable"),
    "core__rob_handpicked_signals_1": ("rename_rob", "LOW", "ROB"),
    "core__int_issue_unit_handpicked_signals_3_1": ("int_ex", "LOW", "INT IQ"),
    "core__ALUExeUnit_handpicked_signals_1": ("int_ex", "LOW", "INT0 ALU/JMP/MUL"),
    "core__csr_exe_unit_1": ("int_ex", "MID", "INT1 ALU/CSR/DIV"),
    "core__csr_1": ("int_ex", "MID", "CSR file"),
    "core__iregfile_1": ("int_ex", "LOW", "int RF"),
    "core__iregister_read_handpicked_signals_1": ("int_ex", "LOW", "int RF read"),
    "core__mem_issue_unit_1": ("mem", "MID", "MEM IQ"),
    "core__lsu_1": ("mem", "MID", "AGU, LDQ, STQ, D$"),
    "core__fp_pipeline_handpicked_signals_2_1": ("fp", "HIGH", "FP IQ, FPU, FMA, FDiv"),
    "core_glue_1": ("glue", "LOW", "tile glue"),
}

GROUPS = ["frontend", "decode", "rename_rob", "int_ex", "mem", "fp", "glue"]


def main():
    src = sys.argv[1] if len(sys.argv) > 1 else r"D:\cy-tmp\boom_real\lacpo_hello\composed_P_t.csv"
    out_dir = sys.argv[2] if len(sys.argv) > 2 else os.path.dirname(src)
    rows = []
    with open(src, "r") as f:
        for r in csv.DictReader(f):
            rows.append(r)
    n = len(rows)
    blocks = [c for c in BLOCK_MAP if c in rows[0]]
    # per-cycle group P_mW
    gP = {g: [0.0] * n for g in GROUPS}
    bP = {b: [] for b in blocks}
    for i, r in enumerate(rows):
        for b in blocks:
            p = float(r[b])
            bP[b].append(p)
            gP[BLOCK_MAP[b][0]][i] += p

    def stats(ps):
        s = sum(ps)
        mean = s / n
        mx = max(ps)
        mn = min(ps)
        e_nj = mean * n * TCLK_NS * 1e-3  # mW * ns * 1e-3 = nJ?  P_mW*1e-3 W * t_ns*1e-9 s * 1e9 nJ = P_mW * t_ns * 1e-3
        e_nj = sum(ps) * TCLK_NS * 1e-3
        i_mean = (mean * 1e-3) / VDD
        i_max = (mx * 1e-3) / VDD
        return dict(mean_mW=mean, max_mW=mx, min_mW=mn, energy_nJ=e_nj,
                    mean_mA=i_mean * 1e3, max_mA=i_max * 1e3)

    totP = [sum(gP[g][i] for g in GROUPS) for i in range(n)]
    tot = stats(totP)

    summary = []
    for b in blocks:
        g, tok, units = BLOCK_MAP[b]
        st = stats(bP[b])
        st.update(block=b, group=g, token=tok, units=units,
                  share_mean=st["mean_mW"] / tot["mean_mW"])
        summary.append(st)
    summary.sort(key=lambda x: -x["mean_mW"])

    gsum = []
    for g in GROUPS:
        st = stats(gP[g])
        st.update(group=g, share_mean=st["mean_mW"] / tot["mean_mW"])
        gsum.append(st)

    hw_path = os.path.join(out_dir, "hw_I_t.csv")
    with open(hw_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Cycle", "time_ns", "I_tile_mA"] + ["I_%s_mA" % g for g in GROUPS] +
                   ["I_%s_mA" % b for b in blocks])
        for i, r in enumerate(rows):
            t = float(r["time_ns"])
            row = [i, t, totP[i] * 1e-3 / VDD * 1e3]
            row += [gP[g][i] * 1e-3 / VDD * 1e3 for g in GROUPS]
            row += [bP[b][i] * 1e-3 / VDD * 1e3 for b in blocks]
            w.writerow(["%.0f" % row[0], "%.1f" % row[1]] + ["%.6f" % x for x in row[2:]])

    sum_path = os.path.join(out_dir, "hw_current_summary.csv")
    with open(sum_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=[
            "block", "group", "token", "units", "mean_mA", "max_mA",
            "mean_mW", "max_mW", "energy_nJ", "share_mean"])
        w.writeheader()
        for st in summary:
            w.writerow({k: st[k] for k in w.fieldnames})

    # downsample groups for canvas (~400 pts)
    step = max(1, n // 400)
    wave = []
    for i in range(0, n, step):
        pt = {"t_us": float(rows[i]["time_ns"]) * 1e-3}
        for g in GROUPS:
            pt[g] = gP[g][i] * 1e-3 / VDD * 1e3
        pt["tile"] = totP[i] * 1e-3 / VDD * 1e3
        wave.append(pt)

    meta = {
        "n_cycles": n, "vdd": VDD, "tclk_ns": TCLK_NS,
        "step": step, "n_wave": len(wave),
        "tile": tot, "groups": gsum, "blocks": summary, "wave": wave,
    }
    js = os.path.join(out_dir, "hw_current_decomp.json")
    with open(js, "w") as f:
        json.dump(meta, f)
    print("cycles", n)
    print("tile mean %.2f mA  max %.2f mA  E %.2f nJ" % (
        tot["mean_mA"], tot["max_mA"], tot["energy_nJ"]))
    print("%-12s %8s %8s %7s" % ("group", "mean_mA", "max_mA", "share"))
    for st in gsum:
        print("%-12s %8.2f %8.2f %6.1f%%" % (
            st["group"], st["mean_mA"], st["max_mA"], 100 * st["share_mean"]))
    print("wrote", hw_path)
    print("wrote", sum_path)
    print("wrote", js)


if __name__ == "__main__":
    main()
