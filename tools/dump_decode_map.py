#!/usr/bin/env python3
"""Parse BOOM decode.scala into a per-instruction hardware map."""
from __future__ import print_function
import csv
import os
import re

DECODE = r"D:\chipyard\generators\boom\src\main\scala\exu\decode.scala"
OUT = os.path.join(os.path.dirname(__file__), "..", "sim", "isa_uop_map.csv")

# fu_code from decode -> category / token / MediumBoom ports that can take it.
# Medium INT issueWidth=2, is_nth(n) = (w == n % 2):
#   INT0: ALU + JMP + MUL + I2F
#   INT1: ALU + CSR + DIV
#   MEM0: MEM (1-wide)
#   FP0:  FPU + FDV + F2I
FU = {
    "FU_ALU":   dict(cat="INT_ALU", token="LOW",  iq="INT", ports="INT0,INT1", units="ALU,intRF", demand="short", w=8),
    "FU_JMP":   dict(cat="INT_BR",  token="LOW",  iq="INT", ports="INT0",      units="ALU/BRU,BTB,gshare,RAS,intRF", demand="short", w=10),
    "FU_MUL":   dict(cat="INT_MUL", token="HIGH", iq="INT", ports="INT0",      units="IMul,intRF", demand="medium", w=28),
    "FU_DIV":   dict(cat="INT_DIV", token="HIGH", iq="INT", ports="INT1",      units="IDiv,intRF", demand="long", w=35),
    "FU_CSR":   dict(cat="INT_CSR", token="MID",  iq="INT", ports="INT1",      units="CSR pipe,intRF", demand="short", w=12),
    "FU_MEM":   dict(cat="MEM_LD",  token="MID",  iq="MEM", ports="MEM0",      units="AGU,LDQ/STQ,D$,MSHR", demand="medium", w=22),
    "FU_F2IMEM":dict(cat="MEM_ST",  token="MID",  iq="MEM", ports="MEM0,FP0",  units="F2I + AGU,STQ,D$,fpRF", demand="medium", w=18),
    "FU_FPU":   dict(cat="FP_ALU",  token="HIGH", iq="FP",  ports="FP0",       units="FPU,fpRF", demand="medium", w=32),
    "FU_FDV":   dict(cat="FP_DIV",  token="HIGH", iq="FP",  ports="FP0",       units="FDiv/Sqrt,fpRF", demand="long", w=45),
    "FU_I2F":   dict(cat="FP_MOV",  token="MID",  iq="INT", ports="INT0",      units="IntToFP,intRF,fpRF", demand="short", w=16),
    "FU_F2I":   dict(cat="FP_MOV",  token="MID",  iq="FP",  ports="FP0",       units="FPToInt,fpRF,intRF", demand="short", w=16),
    "FU_X":     dict(cat="SYS",     token="LOW",  iq="INT", ports="none",      units="pipeline serialize", demand="long", w=6),
}

SPECIAL_UOP = {
    "uopSTA": "MEM_ST",
    "uopSTD": "MEM_ST",
    "uopAMO_AG": "MEM_AMO",
    "uopLD": "MEM_LD",
    "uopFMADD_S": "FP_FMA", "uopFMSUB_S": "FP_FMA", "uopFNMADD_S": "FP_FMA", "uopFNMSUB_S": "FP_FMA",
    "uopFMADD_D": "FP_FMA", "uopFMSUB_D": "FP_FMA", "uopFNMADD_D": "FP_FMA", "uopFNMSUB_D": "FP_FMA",
    "uopFENCE": "SYS", "uopSFENCE": "SYS", "uopNOP": "SYS",
    "uopBEQ": "INT_BR", "uopBNE": "INT_BR", "uopBGE": "INT_BR", "uopBGEU": "INT_BR",
    "uopBLT": "INT_BR", "uopBLTU": "INT_BR",
}

TOKEN = {
    "INT_ALU": "LOW", "INT_BR": "LOW", "SYS": "LOW",
    "INT_CSR": "MID", "MEM_LD": "MID", "MEM_ST": "MID", "FP_MOV": "MID",
    "INT_MUL": "HIGH", "INT_DIV": "HIGH", "MEM_AMO": "HIGH",
    "FP_ALU": "HIGH", "FP_FMA": "HIGH", "FP_DIV": "HIGH",
}

W = {
    "INT_ALU": 8, "INT_BR": 10, "INT_MUL": 28, "INT_DIV": 35, "INT_CSR": 12,
    "MEM_LD": 22, "MEM_ST": 18, "MEM_AMO": 30, "FP_ALU": 32, "FP_FMA": 40,
    "FP_DIV": 45, "FP_MOV": 16, "SYS": 6,
}

ROW = re.compile(
    r"^\s*([A-Z][A-Z0-9_]*)\s*->\s*List\(.*?,\s*(uop[A-Z0-9_]+)\s*,\s*(IQT_\w+)\s*,\s*(FU_\w+)",
    re.M,
)


def main():
    text = open(DECODE, "r").read()
    rows = []
    seen = set()
    for m in ROW.finditer(text):
        riscv, uopc, iqt, fu = m.group(1), m.group(2), m.group(3), m.group(4)
        key = (riscv, uopc)
        if key in seen:
            continue
        seen.add(key)
        meta = dict(FU.get(fu, FU["FU_X"]))
        cat = SPECIAL_UOP.get(uopc, meta["cat"])
        meta["cat"] = cat
        meta["token"] = TOKEN[cat]
        meta["w"] = W[cat]
        rows.append({
            "riscv": riscv,
            "uopc": uopc,
            "iq": iqt.replace("IQT_", ""),
            "fu": fu,
            "category": cat,
            "token": meta["token"],
            "medium_ports": meta["ports"],
            "hw_units": meta["units"],
            "demand": meta["demand"],
            "prior_w_mA": meta["w"],
        })
    os.makedirs(os.path.dirname(os.path.abspath(OUT)), exist_ok=True)
    fields = ["riscv", "uopc", "iq", "fu", "category", "token",
              "medium_ports", "hw_units", "demand", "prior_w_mA"]
    with open(OUT, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    counts = {}
    for r in rows:
        counts[r["token"]] = counts.get(r["token"], 0) + 1
    print("wrote %d opcodes to %s" % (len(rows), os.path.abspath(OUT)))
    print("tokens:", counts)


if __name__ == "__main__":
    main()
