#!/usr/bin/env python3
"""One 16:9 slide: which BOOM microarch signals warn before I(t)."""
import os

import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, Rectangle

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
OUT = os.path.join(ROOT, "traces", "slides")

NAVY = "#1B365D"
TEAL = "#1A7A6D"
RED = "#A93226"
GRAY = "#5D6D7E"
INK = "#1C2833"
LINE = "#D5D8DC"
PALE_TEAL = "#E8F6F3"
PALE_RED = "#FDEDEC"
PALE = "#F4F6F7"


def main():
    os.makedirs(OUT, exist_ok=True)
    plt.rcParams.update({
        "font.size": 12,
        "figure.facecolor": "white",
        "savefig.facecolor": "white",
        "savefig.dpi": 300,
    })

    fig = plt.figure(figsize=(13.333, 7.5))

    fig.text(0.06, 0.93, "Early microarch signals vs same-cycle power nets",
             fontsize=22, fontweight="semibold", color=NAVY, va="center")
    fig.text(0.06, 0.875,
             "Tokens need ~30 clocks of warning.  LACPo nets estimate I(t) now.",
             fontsize=13, color=GRAY, va="center")

    # Pipeline
    ax = fig.add_axes([0.06, 0.68, 0.88, 0.14])
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 10)
    ax.axis("off")

    stages = ["Fetch", "Decode", "Rename", "Dispatch", "Issue", "Reg-read", "EX / LSU / RF"]
    w, gap, h, y = 12.2, 1.6, 4.2, 4.2
    xs = []
    for i, name in enumerate(stages):
        x = 1.5 + i * (w + gap)
        xs.append(x)
        late = i >= 4
        ax.add_patch(Rectangle(
            (x, y), w, h,
            facecolor=PALE_RED if late else PALE_TEAL,
            edgecolor=RED if late else TEAL,
            lw=1.2,
        ))
        ax.text(x + w / 2, y + h / 2, name, ha="center", va="center",
                fontsize=12, color=RED if late else TEAL, fontweight="semibold")
        if i < len(stages) - 1:
            ax.annotate(
                "", xy=(x + w + gap - 0.15, y + h / 2),
                xytext=(x + w + 0.15, y + h / 2),
                arrowprops=dict(arrowstyle="->", color=GRAY, lw=1.2),
            )

    ax.add_patch(Rectangle((xs[0], 0.7), xs[3] + w - xs[0], 2.4,
                           facecolor=PALE_TEAL, edgecolor=TEAL, lw=1.0))
    ax.text((xs[0] + xs[3] + w) / 2, 1.9, "tokens   ~8 to 30+ clk   (~90 ns)",
            ha="center", va="center", fontsize=11, color=TEAL, fontweight="semibold")

    ax.add_patch(Rectangle((xs[4], 0.7), xs[6] + w - xs[4], 2.4,
                           facecolor=PALE_RED, edgecolor=RED, lw=1.0))
    ax.text((xs[4] + xs[6] + w) / 2, 1.9, "too late   0 to 2 clk",
            ha="center", va="center", fontsize=11, color=RED, fontweight="semibold")

    # Two columns
    def panel(left, title, color, fill, lines):
        a = fig.add_axes([left, 0.16, 0.42, 0.46])
        a.set_xlim(0, 1)
        a.set_ylim(0, 1)
        a.axis("off")
        a.add_patch(FancyBboxPatch(
            (0.02, 0.02), 0.96, 0.96,
            boxstyle="round,pad=0.01,rounding_size=0.015",
            facecolor=fill, edgecolor=color, lw=1.3, transform=a.transAxes,
        ))
        a.text(0.07, 0.90, title, fontsize=15, fontweight="semibold",
               color=color, va="center")
        y = 0.74
        for head, sub in lines:
            a.text(0.07, y, head, fontsize=13, fontweight="semibold",
                   color=INK, va="center")
            a.text(0.07, y - 0.07, sub, fontsize=11, color=GRAY, va="center")
            y -= 0.16

    panel(0.06, "Early enough  —  use as tokens", TEAL, PALE_TEAL, [
        ("Stall falling  /  I-cache miss  /  fetch resume", "20–40+ clk   stall-then-burst"),
        ("D-cache miss  /  MSHR allocate", "10–40+ clk   wakeup after fill"),
        ("Fetch + decode opcode  (int / mem / FP)", "8–15 clk   which units will fire"),
        ("ROB empty → full, dispatch valids", "10–20 clk   OoO issue ramp"),
    ])
    panel(0.52, "Too late  —  LACPo only", RED, PALE_RED, [
        ("ALU / FPU operand Hamming", "same cycle as execute current"),
        ("Integer / FP register-file access", "same cycle as RF current"),
        ("LSU memreq / exe_resp", "same cycle as memory current"),
        ("Issue fire, commit, writeback", "0–2 clk   cannot arm a dump"),
    ])

    fig.text(0.06, 0.09,
             "30 clk × 3 ns  ≈  90 ns to pre-enable the dump.   "
             "Pipeline depth alone is only 8–15 clk; the extra lead is stall, miss, and ROB fill.",
             fontsize=12.5, color=NAVY, va="center")
    fig.text(0.06, 0.04,
             "Medium BOOM  ·  schematic pipeline/event latency, not a measured VCD study",
             fontsize=10, color=GRAY, va="center")

    png = os.path.join(OUT, "09_leadtime_signals.png")
    svg = os.path.join(OUT, "09_leadtime_signals.svg")
    fig.savefig(png, bbox_inches=None, pad_inches=0)
    fig.savefig(svg, bbox_inches=None, pad_inches=0)
    plt.close(fig)
    print("wrote", png)


if __name__ == "__main__":
    main()
