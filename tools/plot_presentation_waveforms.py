#!/usr/bin/env python3
"""Render drop-in PPT waveforms from LACPo composed_P_t.csv traces.

Uses system Python + matplotlib (does not load sklearn pickles).
"""
from __future__ import print_function

import csv
import os
import sys

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import FancyBboxPatch

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
TRACES = os.path.join(ROOT, "traces")
SLIDES = os.path.join(TRACES, "slides")

FOOTER_VCD = (
    "LACPo pretrained BOOM DTs  ·  dummy VCD → Hamming/history features → 20-block DTs  ·  "
    "I = P / 1.1 V  ·  Tclk = 3 ns  ·  not gate-level RTL / CoreMark"
)
FOOTER_SYN = (
    "LACPo pretrained BOOM DTs  ·  synthetic activity (no VCD) → 20-block DTs  ·  "
    "I = P / 1.1 V  ·  Tclk = 3 ns  ·  not gate-level RTL / CoreMark"
)

NAVY = "#1B365D"
RED = "#C0392B"
TEAL = "#1A7A6D"
ORANGE = "#D35400"
GOLD = "#B7950B"
GRAY = "#5D6D7E"
LIGHT = "#D6EAF8"
BG = "#FFFFFF"


def load_composed(path):
    with open(path, "r", newline="") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        raise SystemExit("empty " + path)
    cols = list(rows[0].keys())
    cycle = np.array([int(r["Cycle"]) for r in rows])
    t_ns = np.array([float(r["time_ns"]) for r in rows])
    p_mw = np.array([float(r["P_mW"]) for r in rows])
    i_a = np.array([float(r["I_A"]) for r in rows])
    act = np.array([float(r["activity"]) for r in rows]) if "activity" in cols else None
    skip = {"Cycle", "time_ns", "activity", "P_mW", "I_A"}
    blocks = {}
    for c in cols:
        if c in skip:
            continue
        try:
            blocks[c] = np.array([float(r[c]) for r in rows])
        except ValueError:
            pass
    return {"cycle": cycle, "t_ns": t_ns, "P_mW": p_mw, "I_A": i_a, "activity": act, "blocks": blocks}


def style():
    plt.rcParams.update({
        "figure.facecolor": BG,
        "axes.facecolor": BG,
        "savefig.facecolor": BG,
        "axes.edgecolor": "#2C3E50",
        "axes.labelcolor": "#1C2833",
        "xtick.color": "#1C2833",
        "ytick.color": "#1C2833",
        "text.color": "#1C2833",
        "font.size": 13,
        "axes.titlesize": 16,
        "axes.labelsize": 13,
        "legend.fontsize": 11,
        "axes.grid": True,
        "grid.color": "#D5D8DC",
        "grid.linewidth": 0.6,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "figure.dpi": 120,
        "savefig.dpi": 300,
        "savefig.bbox": "tight",
        "savefig.pad_inches": 0.18,
    })


def footer(fig, text):
    fig.text(0.01, 0.01, text, fontsize=7.5, color="#7F8C8D", ha="left", va="bottom")


def save(fig, name):
    os.makedirs(SLIDES, exist_ok=True)
    png = os.path.join(SLIDES, name + ".png")
    svg = os.path.join(SLIDES, name + ".svg")
    fig.savefig(png)
    fig.savefig(svg)
    plt.close(fig)
    print("wrote", png)
    return png


def fig16x9():
    return plt.subplots(figsize=(13.333, 7.5))


def plot_current(d, title, footer_text, out):
    fig, ax = fig16x9()
    t_us = d["t_ns"] * 1e-3
    ax.plot(t_us, d["I_A"] * 1e3, color=NAVY, lw=1.8, solid_capstyle="round")
    ax.fill_between(t_us, d["I_A"] * 1e3, color=LIGHT, alpha=0.85)
    ax.set_xlabel("Time (µs)")
    ax.set_ylabel("Load current I(t)  (mA)")
    ax.set_title(title, pad=12, fontweight="semibold")
    i_mA = d["I_A"] * 1e3
    ax.axhline(np.mean(i_mA), color=RED, ls="--", lw=1.1, label="mean  %.0f mA" % np.mean(i_mA))
    ax.axhline(np.max(i_mA), color=ORANGE, ls=":", lw=1.1, label="peak  %.0f mA" % np.max(i_mA))
    ax.legend(loc="upper right", frameon=True, fancybox=False, edgecolor="#BDC3C7")
    ax.set_xlim(t_us[0], t_us[-1])
    ax.set_ylim(0, np.max(i_mA) * 1.18)
    footer(fig, footer_text)
    return save(fig, out)


def plot_power(d, title, footer_text, out):
    fig, ax = fig16x9()
    t_us = d["t_ns"] * 1e-3
    ax.plot(t_us, d["P_mW"], color=RED, lw=1.8)
    ax.fill_between(t_us, d["P_mW"], color="#FADBD8", alpha=0.9)
    ax.set_xlabel("Time (µs)")
    ax.set_ylabel("Composed power P(t)  (mW)")
    ax.set_title(title, pad=12, fontweight="semibold")
    ax.axhline(np.mean(d["P_mW"]), color=NAVY, ls="--", lw=1.1, label="mean  %.0f mW" % np.mean(d["P_mW"]))
    ax.axhline(np.max(d["P_mW"]), color=ORANGE, ls=":", lw=1.1, label="peak  %.0f mW" % np.max(d["P_mW"]))
    ax.legend(loc="upper right", frameon=True, fancybox=False, edgecolor="#BDC3C7")
    ax.set_xlim(t_us[0], t_us[-1])
    ax.set_ylim(0, np.max(d["P_mW"]) * 1.18)
    footer(fig, footer_text)
    return save(fig, out)


def plot_pi_twin(d, title, footer_text, out):
    fig, ax = fig16x9()
    t_us = d["t_ns"] * 1e-3
    ax.plot(t_us, d["P_mW"], color=RED, lw=1.7, label="P(t)")
    ax.set_xlabel("Time (µs)")
    ax.set_ylabel("Power (mW)", color=RED)
    ax.tick_params(axis="y", colors=RED)
    ax2 = ax.twinx()
    ax2.spines["right"].set_visible(True)
    ax2.plot(t_us, d["I_A"] * 1e3, color=NAVY, lw=1.4, alpha=0.9, label="I(t)")
    ax2.set_ylabel("Current (mA)", color=NAVY)
    ax2.tick_params(axis="y", colors=NAVY)
    ax.set_title(title, pad=12, fontweight="semibold")
    h1, l1 = ax.get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    ax.legend(h1 + h2, l1 + l2, loc="upper right", frameon=True, fancybox=False, edgecolor="#BDC3C7")
    ax.set_xlim(t_us[0], t_us[-1])
    footer(fig, footer_text)
    return save(fig, out)


def plot_didt_zoom(d, title, footer_text, out):
    i_mA = d["I_A"] * 1e3
    di = np.diff(i_mA)
    k = int(np.argmax(np.abs(di)))
    t_us = d["t_ns"] * 1e-3
    lo = max(0, k - 40)
    hi = min(len(t_us) - 1, k + 80)
    fig, ax = fig16x9()
    ax.plot(t_us[lo:hi], i_mA[lo:hi], color=NAVY, lw=2.2, marker="o", ms=3.2, markevery=2)
    ax.axvline(t_us[k + 1], color=ORANGE, ls="--", lw=1.2, label="max |ΔI|  %.0f mA / cycle" % di[k])
    ax.set_xlabel("Time (µs)")
    ax.set_ylabel("I(t)  (mA)")
    ax.set_title(title, pad=12, fontweight="semibold")
    ax.legend(loc="best", frameon=True, fancybox=False, edgecolor="#BDC3C7")
    footer(fig, footer_text)
    return save(fig, out)


def plot_stack(d, title, footer_text, out, n_top=8):
    means = {k: float(np.mean(v)) for k, v in d["blocks"].items()}
    top = sorted(means, key=means.get, reverse=True)[:n_top]
    rest = [k for k in d["blocks"] if k not in top]
    t_us = d["t_ns"] * 1e-3
    series = [d["blocks"][k] for k in top]
    labels = [short_block(k) for k in top]
    if rest:
        other = np.zeros_like(series[0])
        for k in rest:
            other = other + d["blocks"][k]
        series.append(other)
        labels.append("other blocks")
    colors = [NAVY, RED, TEAL, ORANGE, GOLD, "#5B2C6F", "#1F618D", "#117A65", GRAY]
    fig, ax = fig16x9()
    ax.stackplot(t_us, *series, labels=labels, colors=colors[: len(series)], alpha=0.92, lw=0)
    ax.set_xlabel("Time (µs)")
    ax.set_ylabel("Block power (mW)")
    ax.set_title(title, pad=12, fontweight="semibold")
    ax.legend(loc="upper right", ncol=2, frameon=True, fancybox=False, edgecolor="#BDC3C7", fontsize=9)
    ax.set_xlim(t_us[0], t_us[-1])
    ax.set_ylim(0, None)
    footer(fig, footer_text)
    return save(fig, out)


def short_block(name):
    n = name.replace("core__", "").replace("frontend__", "").replace("_handpicked_signals", "")
    n = n.replace("_1", "").replace("bpdpipeline__", "")
    return n[:28]


def plot_overlay(named, title, footer_text, out):
    colors = {
        "idle": GRAY,
        "load_step": NAVY,
        "matmul": ORANGE,
        "branch_storm": TEAL,
    }
    fig, ax = fig16x9()
    for name, d in named:
        t_us = d["t_ns"] * 1e-3
        ax.plot(t_us, d["I_A"] * 1e3, lw=1.8, color=colors.get(name, NAVY), label=name.replace("_", " "))
    ax.set_xlabel("Time (µs)")
    ax.set_ylabel("I(t)  (mA)")
    ax.set_title(title, pad=12, fontweight="semibold")
    ax.legend(loc="upper right", frameon=True, fancybox=False, edgecolor="#BDC3C7")
    footer(fig, footer_text)
    return save(fig, out)


def plot_pipeline(d, vcd_path, feat_path, title, out):
    vcd_lines = []
    if vcd_path and os.path.isfile(vcd_path):
        with open(vcd_path, "r") as f:
            for i, line in enumerate(f):
                if i >= 18:
                    break
                vcd_lines.append(line.rstrip("\n")[:72].replace("$", ""))
    feat_preview = ""
    if feat_path and os.path.isfile(feat_path):
        with open(feat_path, "r") as f:
            hdr = f.readline().strip().split(",")
            row = f.readline().strip().split(",")
        keep = [c for c in hdr if c.startswith("d_") or c.startswith("v1_") or "[" in c][:6]
        if not keep:
            keep = hdr[1:7]
        idxs = [hdr.index(c) for c in keep if c in hdr]
        feat_preview = "  ".join("%s=%s" % (keep[j][-18:], row[idxs[j]] if idxs[j] < len(row) else "?") for j in range(len(idxs)))

    fig = plt.figure(figsize=(13.333, 7.5))
    gs = fig.add_gridspec(2, 2, height_ratios=[1.05, 1.2], hspace=0.38, wspace=0.28, left=0.07, right=0.98, top=0.88, bottom=0.10)

    ax0 = fig.add_subplot(gs[0, 0])
    ax0.set_xlim(0, 1)
    ax0.set_ylim(0, 1)
    ax0.axis("off")
    ax0.set_title("1. Dummy VCD (activity dump)", loc="left", fontsize=13, fontweight="semibold")
    box = FancyBboxPatch((0.02, 0.02), 0.96, 0.96, boxstyle="round,pad=0.02,rounding_size=0.04",
                         facecolor="#F4F6F7", edgecolor="#85929E", lw=1.0, transform=ax0.transAxes)
    ax0.add_patch(box)
    text = "\n".join(vcd_lines) if vcd_lines else "(no VCD)"
    ax0.text(
        0.05, 0.93, text, va="top", ha="left", family="monospace", fontsize=7.4,
        color="#1C2833", transform=ax0.transAxes, parse_math=False,
    )

    ax1 = fig.add_subplot(gs[0, 1])
    ax1.set_xlim(0, 1)
    ax1.set_ylim(0, 1)
    ax1.axis("off")
    ax1.set_title("2. Engineered features  →  3. I = P / VDD", loc="left", fontsize=13, fontweight="semibold")
    steps = [
        "Hamming distance  d_, d1_, d2_",
        "Value history     v1_, v2_",
        "20 pretrained DTs (sklearn 0.20)",
        "Compose P(t)  then  I(t) = P / 1.1 V",
    ]
    y = 0.82
    for s in steps:
        ax1.text(0.06, y, "▸  " + s, fontsize=12, va="center", transform=ax1.transAxes)
        y -= 0.18
    ax1.text(0.06, 0.10, feat_preview[:110], fontsize=7.5, color="#7F8C8D", family="monospace", transform=ax1.transAxes)

    ax2 = fig.add_subplot(gs[1, :])
    t_us = d["t_ns"] * 1e-3
    ax2.plot(t_us, d["I_A"] * 1e3, color=NAVY, lw=1.9)
    ax2.fill_between(t_us, d["I_A"] * 1e3, color=LIGHT, alpha=0.85)
    ax2.set_xlabel("Time (µs)")
    ax2.set_ylabel("I(t)  (mA)")
    ax2.set_xlim(t_us[0], t_us[-1])
    ax2.set_ylim(0, np.max(d["I_A"] * 1e3) * 1.15)

    fig.suptitle(title, fontsize=16, fontweight="semibold", y=0.97)
    footer(fig, FOOTER_VCD)
    return save(fig, out)


def main():
    style()
    written = []
    load_dir = os.path.join(TRACES, "load_step")
    load_csv = os.path.join(load_dir, "composed_P_t.csv")
    if os.path.isfile(load_csv):
        d = load_composed(load_csv)
        written.append(plot_current(
            d,
            "VCD → LACPo  ·  load current I(t)   [load_step dummy dump]",
            FOOTER_VCD,
            "01_I_t_from_vcd",
        ))
        written.append(plot_power(
            d,
            "VCD → LACPo  ·  composed power P(t)   [load_step dummy dump]",
            FOOTER_VCD,
            "02_P_t_from_vcd",
        ))
        written.append(plot_pi_twin(
            d,
            "Same trace: P(t) and I(t) = P / 1.1 V",
            FOOTER_VCD,
            "03_P_and_I_twin",
        ))
        written.append(plot_didt_zoom(
            d,
            "di/dt edge (largest cycle-to-cycle ΔI on this dummy VCD)",
            FOOTER_VCD,
            "04_didt_zoom",
        ))
        if d["blocks"]:
            written.append(plot_stack(
                d,
                "Per-block DT predictions (naive sum of 20 LACPo trees)",
                FOOTER_VCD,
                "05_block_stack",
            ))
        written.append(plot_pipeline(
            d,
            os.path.join(load_dir, "dump.dummy.vcd"),
            os.path.join(load_dir, "load_step.features.csv"),
            "Working path: dummy VCD  →  features  →  LACPo current",
            "00_pipeline_vcd_to_current",
        ))

    overlay = []
    for name in ("idle", "load_step", "matmul", "branch_storm"):
        p = os.path.join(TRACES, name, "composed_P_t.csv")
        if os.path.isfile(p):
            overlay.append((name, load_composed(p)))
    if len(overlay) >= 2:
        written.append(plot_overlay(
            overlay,
            "Dummy-VCD programs through the same LACPo models",
            FOOTER_VCD,
            "06_programs_overlay",
        ))

    syn = os.path.join(TRACES, "composed_P_t.csv")
    if not os.path.isfile(syn):
        syn = os.path.join(TRACES, "synthetic", "composed_P_t.csv")
    if os.path.isfile(syn):
        d = load_composed(syn)
        written.append(plot_current(
            d,
            "LACPo I(t) on synthetic activity  (no VCD — longer horizon)",
            FOOTER_SYN,
            "07_I_t_synthetic",
        ))
        written.append(plot_power(
            d,
            "LACPo P(t) on synthetic activity  (no VCD — longer horizon)",
            FOOTER_SYN,
            "08_P_t_synthetic",
        ))

    if not written:
        print("No composed_P_t.csv traces found under", TRACES)
        sys.exit(1)
    print("slides dir", SLIDES)


if __name__ == "__main__":
    main()
