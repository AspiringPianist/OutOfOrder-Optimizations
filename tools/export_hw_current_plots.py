#!/usr/bin/env python3
"""Export hardware-current CSVs and PNGs. No UI."""
from __future__ import print_function

import csv
import os
import shutil
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

VDD = 1.1
GROUPS = ["frontend", "int_ex", "glue", "fp", "mem", "rename_rob", "decode"]
GROUP_LABEL = {
    "frontend": "frontend (I$/BTB/BPD)",
    "int_ex": "INT EX (IQ/ALU/RF)",
    "glue": "tile glue",
    "fp": "FP pipe",
    "mem": "MEM (IQ/LSU)",
    "rename_rob": "rename/ROB",
    "decode": "decode",
}
# LACPo block stem -> short label (matches decompose_hw_current.BLOCK_MAP)
BLOCK_LABEL = {
    "frontend__fetch_controller_1": "I$/FTQ/fetch",
    "frontend__bpdpipeline__btb_handpicked_signals_1": "BTB",
    "frontend__bpdpipeline__bpd__counter_table_1": "gshare/BPD",
    "core__decode_units_0_1": "decode0",
    "core__decode_units_1_1": "decode1",
    "core__rename_stage__freelist_history_1_1": "int freelist",
    "core__rename_stage___maptable_history_1_1": "int maptable",
    "core__fp_rename_stage__freelist_1": "fp freelist",
    "core__fp_rename_stage__maptable_1": "fp maptable",
    "core__rob_handpicked_signals_1": "ROB",
    "core__int_issue_unit_handpicked_signals_3_1": "INT IQ",
    "core__ALUExeUnit_handpicked_signals_1": "INT0 ALU/JMP/MUL",
    "core__csr_exe_unit_1": "INT1 ALU/CSR/DIV",
    "core__csr_1": "CSR file",
    "core__iregfile_1": "int RF",
    "core__iregister_read_handpicked_signals_1": "int RF read",
    "core__mem_issue_unit_1": "MEM IQ",
    "core__lsu_1": "AGU/LDQ/STQ/D$",
    "core__fp_pipeline_handpicked_signals_2_1": "FP IQ/FPU/FMA/FDiv",
    "core_glue_1": "tile glue",
}


def read_summary(path):
    rows = []
    with open(path, "r") as f:
        for r in csv.DictReader(f):
            rows.append(r)
    return rows


def read_I(path):
    t, tile = [], []
    g = {k: [] for k in GROUPS}
    blocks = {k: [] for k in BLOCK_LABEL}
    with open(path, "r") as f:
        rd = csv.DictReader(f)
        for r in rd:
            t.append(float(r["time_ns"]) * 1e-3)
            tile.append(float(r["I_tile_mA"]))
            for k in GROUPS:
                g[k].append(float(r["I_%s_mA" % k]))
            for k in BLOCK_LABEL:
                col = "I_%s_mA" % k
                if col in r:
                    blocks[k].append(float(r[col]))
    return (
        np.array(t),
        np.array(tile),
        {k: np.array(v) for k, v in g.items()},
        {k: np.array(v) for k, v in blocks.items() if v},
    )


def style():
    plt.rcParams.update({
        "font.size": 10,
        "axes.grid": True,
        "grid.alpha": 0.3,
        "figure.facecolor": "white",
        "axes.facecolor": "white",
        "savefig.bbox": "tight",
        "savefig.dpi": 140,
    })


def save(fig, *paths):
    for p in paths:
        os.makedirs(os.path.dirname(p) or ".", exist_ok=True)
        fig.savefig(p)
        print("wrote", p)
    plt.close(fig)


def slug(s):
    out = []
    for ch in s:
        if ch.isalnum():
            out.append(ch)
        elif out and out[-1] != "_":
            out.append("_")
    return "".join(out).strip("_")


def plot_one(t, y, ylabel, title, paths, color="black"):
    fig, ax = plt.subplots(figsize=(10, 3.2))
    ax.plot(t, y, color=color, lw=0.7)
    ax.set_xlabel("time (us)")
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    save(fig, *paths)


def plot_grid(t, series, titles, paths, title, nrows, ncols, figsize):
    fig, axes = plt.subplots(nrows, ncols, figsize=figsize, sharex=True)
    axes = np.asarray(axes).ravel()
    n = len(series)
    for i, (y, lab) in enumerate(zip(series, titles)):
        axes[i].plot(t, y, color="black", lw=0.55)
        axes[i].set_title(lab, fontsize=9)
        axes[i].set_ylabel("I (mA)", fontsize=8)
        axes[i].tick_params(labelsize=8)
    for j in range(n, len(axes)):
        axes[j].set_visible(False)
    for ax in axes[max(0, n - ncols):n]:
        ax.set_xlabel("time (us)")
    fig.suptitle(title, y=1.01)
    fig.tight_layout()
    save(fig, *paths)


def main():
    src = sys.argv[1] if len(sys.argv) > 1 else r"D:\cy-tmp\boom_real\lacpo_hello"
    dests = sys.argv[2:] or [
        src,
        r"C:\Users\unnat\Documents\DecouplingCap\traces\hello_vcd",
    ]
    style()
    t, tile, g, blocks = read_I(os.path.join(src, "hw_I_t.csv"))
    summary = read_summary(os.path.join(src, "hw_current_summary.csv"))
    ts_dirs = [os.path.join(d, "timeseries") for d in dests]
    mask = t >= 30.0

    fig, ax = plt.subplots(figsize=(10, 3.6))
    ax.plot(t, tile, color="black", lw=0.8)
    ax.set_xlabel("time (us)")
    ax.set_ylabel("I (mA)")
    ax.set_title("BoomTile composed current  ·  hello.vcd  ·  I = P/1.1 V")
    save(fig, *[os.path.join(d, "01_tile_I.png") for d in dests])

    fig, ax = plt.subplots(figsize=(10, 4.2))
    stack = [g[k] for k in GROUPS]
    ax.stackplot(t, *stack, labels=[GROUP_LABEL[k] for k in GROUPS])
    ax.plot(t, tile, color="black", lw=0.7, label="tile sum")
    ax.set_xlabel("time (us)")
    ax.set_ylabel("I (mA)")
    ax.set_title("Hardware-group current (stacked)  ·  hello.vcd")
    ax.legend(loc="upper left", ncol=2, fontsize=8)
    save(fig, *[os.path.join(d, "02_groups_stacked.png") for d in dests])

    fig, ax = plt.subplots(figsize=(10, 4.2))
    for k in GROUPS:
        ax.plot(t, g[k], lw=0.9, label=GROUP_LABEL[k])
    ax.set_xlabel("time (us)")
    ax.set_ylabel("I (mA)")
    ax.set_title("Hardware-group current (overlaid)  ·  hello.vcd")
    ax.legend(loc="upper left", ncol=2, fontsize=8)
    save(fig, *[os.path.join(d, "03_groups_lines.png") for d in dests])

    fig, ax = plt.subplots(figsize=(10, 4.2))
    stack = [g[k][mask] for k in GROUPS]
    ax.stackplot(t[mask], *stack, labels=[GROUP_LABEL[k] for k in GROUPS])
    ax.plot(t[mask], tile[mask], color="black", lw=0.7, label="tile sum")
    ax.set_xlabel("time (us)")
    ax.set_ylabel("I (mA)")
    ax.set_title("Hardware-group current  ·  hello active window (t ≥ 30 us)")
    ax.legend(loc="upper left", ncol=2, fontsize=8)
    save(fig, *[os.path.join(d, "04_groups_stacked_active.png") for d in dests])

    means = [float(r["mean_mA"]) for r in summary]
    peaks = [float(r["max_mA"]) for r in summary]
    labels = [r["units"] for r in summary]
    y = np.arange(len(labels))
    fig, ax = plt.subplots(figsize=(9, 6.5))
    ax.barh(y - 0.18, means, 0.36, color="0.35", label="mean")
    ax.barh(y + 0.18, peaks, 0.36, color="0.7", label="peak")
    ax.set_yticks(y)
    ax.set_yticklabels(labels)
    ax.invert_yaxis()
    ax.set_xlabel("I (mA)")
    ax.set_title("Per-block current  ·  20 LACPo trees  ·  hello.vcd")
    ax.legend()
    save(fig, *[os.path.join(d, "05_blocks_mean_peak.png") for d in dests])

    g_mean = {k: float(g[k].mean()) for k in GROUPS}
    g_peak = {k: float(g[k].max()) for k in GROUPS}
    fig, ax = plt.subplots(figsize=(8, 3.8))
    x = np.arange(len(GROUPS))
    ax.bar(x - 0.18, [g_mean[k] for k in GROUPS], 0.36, color="0.35", label="mean")
    ax.bar(x + 0.18, [g_peak[k] for k in GROUPS], 0.36, color="0.7", label="peak")
    ax.set_xticks(x)
    ax.set_xticklabels([GROUP_LABEL[k] for k in GROUPS], rotation=25, ha="right")
    ax.set_ylabel("I (mA)")
    ax.set_title("Group mean vs peak current  ·  hello.vcd")
    ax.legend()
    save(fig, *[os.path.join(d, "06_groups_mean_peak.png") for d in dests])

    # --- time series: tile + groups + every LACPo block ---
    plot_one(
        t[mask], tile[mask], "I (mA)",
        "BoomTile I(t)  ·  hello active window (t ≥ 30 us)",
        [os.path.join(d, "07_tile_I_active.png") for d in dests],
    )
    plot_one(
        t, tile * VDD, "P (mW)",
        "BoomTile composed P(t)  ·  hello.vcd  ·  P = I × 1.1 V",
        [os.path.join(d, "08_tile_P.png") for d in dests],
    )

    fig, ax = plt.subplots(figsize=(10, 4.2))
    for k in GROUPS:
        ax.plot(t[mask], g[k][mask], lw=0.9, label=GROUP_LABEL[k])
    ax.set_xlabel("time (us)")
    ax.set_ylabel("I (mA)")
    ax.set_title("Hardware-group I(t)  ·  hello active window (t ≥ 30 us)")
    ax.legend(loc="upper left", ncol=2, fontsize=8)
    save(fig, *[os.path.join(d, "09_groups_lines_active.png") for d in dests])

    plot_grid(
        t, [g[k] for k in GROUPS], [GROUP_LABEL[k] for k in GROUPS],
        [os.path.join(d, "10_groups_I_t.png") for d in dests],
        "Hardware-group I(t)  ·  hello.vcd",
        4, 2, (12, 10),
    )
    plot_grid(
        t[mask], [g[k][mask] for k in GROUPS], [GROUP_LABEL[k] for k in GROUPS],
        [os.path.join(d, "11_groups_I_t_active.png") for d in dests],
        "Hardware-group I(t)  ·  hello active window (t ≥ 30 us)",
        4, 2, (12, 10),
    )

    bkeys = [k for k in BLOCK_LABEL if k in blocks]
    plot_grid(
        t, [blocks[k] for k in bkeys], [BLOCK_LABEL[k] for k in bkeys],
        [os.path.join(d, "12_blocks_I_t.png") for d in dests],
        "Per-block I(t)  ·  20 LACPo trees  ·  hello.vcd",
        5, 4, (14, 12),
    )
    plot_grid(
        t[mask], [blocks[k][mask] for k in bkeys], [BLOCK_LABEL[k] for k in bkeys],
        [os.path.join(d, "13_blocks_I_t_active.png") for d in dests],
        "Per-block I(t)  ·  hello active window (t ≥ 30 us)",
        5, 4, (14, 12),
    )

    # one PNG per series so they can drop a single unit into a slide
    plot_one(
        t, tile, "I (mA)",
        "BoomTile composed I(t)",
        [os.path.join(d, "I_tile.png") for d in ts_dirs],
    )
    plot_one(
        t[mask], tile[mask], "I (mA)",
        "BoomTile composed I(t)  ·  t ≥ 30 us",
        [os.path.join(d, "I_tile_active.png") for d in ts_dirs],
    )
    for k in GROUPS:
        plot_one(
            t, g[k], "I (mA)",
            "%s  I(t)" % GROUP_LABEL[k],
            [os.path.join(d, "group_%s.png" % k) for d in ts_dirs],
        )
        plot_one(
            t[mask], g[k][mask], "I (mA)",
            "%s  I(t)  ·  t ≥ 30 us" % GROUP_LABEL[k],
            [os.path.join(d, "group_%s_active.png" % k) for d in ts_dirs],
        )
    for k in bkeys:
        name = slug(BLOCK_LABEL[k])
        plot_one(
            t, blocks[k], "I (mA)",
            "%s  I(t)" % BLOCK_LABEL[k],
            [os.path.join(d, "block_%s.png" % name) for d in ts_dirs],
        )
        plot_one(
            t[mask], blocks[k][mask], "I (mA)",
            "%s  I(t)  ·  t ≥ 30 us" % BLOCK_LABEL[k],
            [os.path.join(d, "block_%s_active.png" % name) for d in ts_dirs],
        )

    copies = [
        "hw_I_t.csv",
        "hw_current_summary.csv",
        "composed_P_t.csv",
        "load_current.pwl",
    ]
    for dest in dests:
        if os.path.abspath(dest) == os.path.abspath(src):
            continue
        for name in copies:
            shutil.copy2(os.path.join(src, name), os.path.join(dest, name))
            print("copied", name, "->", dest)


if __name__ == "__main__":
    main()
