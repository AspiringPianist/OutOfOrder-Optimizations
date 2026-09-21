#!/usr/bin/env python3
"""Map RISC-V/BOOM uops to hardware units and composable energy/power tokens.

Concurrent issue is the model, not a bug:

    I[n] ~= I0 + sum_c w_c * N_c[n]

N_c[n] = how many class-c uops are in issue/EX this cycle.
w_c is instruction-level intent. The token the scheduler spends is the SUM.

Default BOOM grant (IssueUnitCollapsing, age-ordered): oldest ready slot
whose (fu_code & fu_types(port)) is nonzero takes the first free port.
No current budget today.

Packing (Powering Superscalar Processors): cluster HIGH with HIGH, then
LOW with LOW, so the PDN sees plateaus instead of many di/dt edges.

ICPP08 (Fu et al.) is the IQ-select cousin (ACE-bit tags + dispatch cap)
on an 8-wide Alpha SMT -- not BOOM parameters. The posted 4-wide figure
matches MegaBoom, not MediumBoom. LACPo pickles and the built sim are
MediumBoomConfig; do not retarget Chisel to Mega without retraining.
"""
from __future__ import print_function

import csv
import os

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
CSV_PATH = os.path.join(ROOT, "sim", "isa_hw_categories.csv")

# Chipyard 1.3 WithMediumBooms vs the diagram vs WithMegaBooms.
# Diagram ~ Mega (4-wide decode, 32 IQ*, 128 ROB/RF, 2 AGU, 512KB L2).
BOOM_PARAMS = {
    "medium_chipyard13": {
        "fetch": 4, "decode": 2,
        "iq": {"MEM": (1, 12), "INT": (2, 20), "FP": (1, 16)},  # (issueWidth, entries)
        "rob": 64, "ireg": 80, "freg": 64, "ldq": 16, "stq": 16,
        "i": "16KB 4-way", "d": "16KB 4-way 2 MSHR",
        "eus": "2 int issue + 1 mem + 1 fp",
    },
    "figure_mega_like": {
        "fetch": 8, "decode": 4, "ftq": 32, "fb": 32,
        "iq": {"MEM": (2, 32), "INT": (4, 32), "FP": (1, 32)},
        "rob": 128, "ireg": 128, "freg": 128, "ldq": 32, "stq": 32,
        "i": "32KB 8-way", "d": "32KB 8-way 8 MSHR",
        "eus": "4 ALU + IMul + 2 FPU + 2 AGU",
        "l2": "512KB 8-way",
    },
    "mega_chipyard13": {
        "fetch": 8, "decode": 4,
        "iq": {"MEM": (2, 24), "INT": (4, 40), "FP": (2, 32)},
        "rob": 128, "ireg": 128, "freg": 128, "ldq": 32, "stq": 32,
    },
}

# Relative mA priors per issued uop of that class. Replace by OLS on
# LACPo I[n] vs occupancy once a real VCD name-map exists.
DEFAULT_W = {
    "INT_ALU": 8.0, "INT_BR": 10.0, "INT_MUL": 28.0, "INT_DIV": 35.0,
    "INT_CSR": 12.0, "MEM_LD": 22.0, "MEM_ST": 18.0, "MEM_AMO": 30.0,
    "FP_ALU": 32.0, "FP_FMA": 40.0, "FP_DIV": 45.0, "FP_MOV": 16.0, "SYS": 6.0,
}
I0_MA = 64.0  # idle composed tile from dummy LACPo (~0.064 A)
HIGH_BUDGET_MA = 80.0  # max extra HIGH current granted in one cycle (Medium: 1-2 HIGH)

TOKEN_MA = {"LOW": 8.0, "MID": 20.0, "HIGH": 36.0}


def load_categories(path=CSV_PATH):
    rows = []
    with open(path, "r") as f:
        for r in csv.DictReader(f):
            rows.append(r)
    return rows


def uopc_to_category(uopc_name):
    """Map a BOOM uopc string (e.g. uopMUL) to a category row."""
    u = uopc_name.upper().replace("UOP", "")
    if u in ("NOP", "MOV"):
        return "INT_ALU"
    if u in ("LD",):
        return "MEM_LD"
    if u in ("STA", "STD"):
        return "MEM_ST"
    if u in ("AMO_AG",):
        return "MEM_AMO"
    if u.startswith("MUL"):
        return "INT_MUL"
    if u.startswith(("DIV", "REM")):
        return "INT_DIV"
    if u.startswith("CSR") or u in ("WFI", "ERET"):
        return "INT_CSR"
    if u in ("BEQ", "BNE", "BGE", "BGEU", "BLT", "BLTU", "J", "JAL", "JALR"):
        return "INT_BR"
    if u.startswith("F") and ("DIV" in u or "SQRT" in u):
        return "FP_DIV"
    if "MADD" in u or "MSUB" in u:
        return "FP_FMA"
    if u.startswith("FMV") or u.startswith("FCVT") or u.startswith("FCLASS"):
        return "FP_MOV"
    if u.startswith("F"):
        return "FP_ALU"
    if u in ("FENCE", "FENCEI", "SFENCE", "CFLSH"):
        return "SYS"
    return "INT_ALU"


def power_ma(counts, w=None, i0=I0_MA):
    """Linear mix: counts is dict category -> N issued/in-EX this cycle."""
    w = w or DEFAULT_W
    return i0 + sum(w.get(c, 0.0) * float(n) for c, n in counts.items())


def energy_token_nj(counts, tclk_ns=3.0, vdd=1.1, w=None):
    """Window energy (nJ) = I(A)*V*dt. counts over the window, one cycle here."""
    i_a = power_ma(counts, w) * 1e-3
    return i_a * vdd * (tclk_ns * 1e-9) * 1e9


def high_current_ma(counts, w=None):
    w = w or DEFAULT_W
    high = ("INT_MUL", "INT_DIV", "MEM_AMO", "FP_ALU", "FP_FMA", "FP_DIV")
    return sum(w[c] * float(counts.get(c, 0)) for c in high)


def grant_with_budget(ready, fu_types_ports, budget_ma=HIGH_BUDGET_MA, w=None):
    """Age-ordered grant (BOOM default) plus a HIGH-current knapsack.

    ready: list of dicts oldest-first {cat, fu_code_bit, uopc}
    fu_types_ports: list of fu bitmasks the ports can take this cycle
    Returns indices granted.
    """
    w = w or DEFAULT_W
    port_taken = [False] * len(fu_types_ports)
    granted = []
    spent = 0.0
    for idx, uop in enumerate(ready):
        issued = False
        extra = w.get(uop["cat"], 0.0)
        is_high = uop["cat"] in (
            "INT_MUL", "INT_DIV", "MEM_AMO", "FP_ALU", "FP_FMA", "FP_DIV")
        if is_high and spent + extra > budget_ma:
            continue
        for p, mask in enumerate(fu_types_ports):
            if port_taken[p]:
                continue
            if uop["fu"] & mask:
                port_taken[p] = True
                granted.append(idx)
                if is_high:
                    spent += extra
                issued = True
                break
        if issued:
            continue
    return granted


def pack_windows(classes):
    """Powering-PDF policy: emit HIGH run, then LOW run. Do not mix edges."""
    high = [c for c in classes if c["token"] == "HIGH"]
    mid = [c for c in classes if c["token"] == "MID"]
    low = [c for c in classes if c["token"] == "LOW"]
    return high + mid + low


def main():
    rows = load_categories()
    print("BOOM Medium (this sim / LACPo):", BOOM_PARAMS["medium_chipyard13"])
    print("Figure (Mega-like):           ", BOOM_PARAMS["figure_mega_like"])
    print()
    print("%-10s %-6s %-4s %-28s %s" % ("cat", "token", "iq", "units", "w_mA"))
    for r in rows:
        print("%-10s %-6s %-4s %-28s %s" % (
            r["category"], r["token"], r["iq"], r["hw_units"][:28], r["prior_w_mA"]))
    print()
    idle = {}
    step = {"INT_ALU": 2, "MEM_LD": 1}
    burst = {"INT_MUL": 1, "FP_FMA": 1, "MEM_LD": 1}
    for name, c in (("idle", idle), ("alu+ld", step), ("mul+fma+ld", burst)):
        i = power_ma(c)
        e = energy_token_nj(c)
        print("%-12s  I=%.1f mA  E/clk=%.3f nJ  HIGH=%.1f mA" % (
            name, i, e, high_current_ma(c)))
    print()
    print("Grant: age-order + HIGH budget %.0f mA (default BOOM has budget=inf)." % HIGH_BUDGET_MA)


if __name__ == "__main__":
    main()
