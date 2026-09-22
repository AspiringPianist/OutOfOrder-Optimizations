#!/usr/bin/env python3
"""Abstract MediumBoom IQ reorder aimed at PDN first-droop.

Same arrival stream, two grant policies:

  default  — age-order, first legal port (BOOM IssueUnitCollapsing)
  pack     — among legal grants, pick the set whose predicted I is
             closest to last-cycle I (fast edge) and to a slow VRM
             EMA (~48 ns). Caps supply I − I_vrm; we shrink that.

Tokens are CSV priors. I[n] = I0 + Σ w_c min(N_c, FU width).
Average energy is not the score. Σ|ΔI|, HF RMS, and plateau length are.
"""
from __future__ import print_function

import csv
import json
import os
import random
import sys
from collections import Counter, defaultdict

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from isa_hw_tokens import DEFAULT_W, I0_MA, power_ma  # noqa: E402

VDD = 1.1
TCLK_NS = 3.0
# VRM / board LC cannot follow faster than ~50 ns → 16 cycles at 3 ns.
VRM_TAU_CYC = 16.0
EDGE_QUIET_MA = 8.0  # |ΔI| below this is a plateau (caps idle)
OUT = os.path.join(ROOT, "results", "iq_reorder")
SEED = 20260922

# FU bits — MediumBoom port masks (decode.scala / config-mixins).
ALU, JMP, MUL, DIV, CSR, MEM, FPU, FDV, I2F, F2I = (
    1, 2, 4, 8, 16, 32, 64, 128, 256, 512)
HIGH = {"INT_MUL", "INT_DIV", "MEM_AMO", "FP_ALU", "FP_FMA", "FP_DIV"}
TOKEN = {
    "INT_ALU": "LOW", "INT_BR": "LOW", "SYS": "LOW",
    "INT_CSR": "MID", "MEM_LD": "MID", "MEM_ST": "MID", "FP_MOV": "MID",
    "INT_MUL": "HIGH", "INT_DIV": "HIGH", "MEM_AMO": "HIGH",
    "FP_ALU": "HIGH", "FP_FMA": "HIGH", "FP_DIV": "HIGH",
}
LAT = {
    "INT_ALU": 1, "INT_BR": 1, "SYS": 1, "INT_CSR": 1,
    "MEM_ST": 1, "FP_MOV": 2, "INT_MUL": 3, "MEM_LD": 3, "MEM_AMO": 4,
    "FP_ALU": 4, "FP_FMA": 4, "INT_DIV": 16, "FP_DIV": 16,
}
CAT_FU = {
    "INT_ALU": ALU, "INT_BR": ALU | JMP, "INT_MUL": MUL, "INT_DIV": DIV,
    "INT_CSR": CSR, "MEM_LD": MEM, "MEM_ST": MEM, "MEM_AMO": MEM,
    "FP_ALU": FPU, "FP_FMA": FPU, "FP_DIV": FDV, "FP_MOV": I2F, "SYS": ALU,
}
CAT_IQ = {
    "INT_ALU": "INT", "INT_BR": "INT", "INT_MUL": "INT", "INT_DIV": "INT",
    "INT_CSR": "INT", "SYS": "INT", "FP_MOV": "INT",
    "MEM_LD": "MEM", "MEM_ST": "MEM", "MEM_AMO": "MEM",
    "FP_ALU": "FP", "FP_FMA": "FP", "FP_DIV": "FP",
}
IQ_PORTS = {
    "INT": [("INT0", ALU | JMP | MUL | I2F), ("INT1", ALU | CSR | DIV)],
    "MEM": [("MEM0", MEM)],
    "FP": [("FP0", FPU | FDV | F2I)],
}
IQ_CAP = {"INT": 20, "MEM": 12, "FP": 16}
DECODE_W = 2
# One occupant per FU (IDiv/IMul/FPU are 1-wide). ALU can be 2-wide.
FU_WIDTH = {
    "INT_ALU": 2, "INT_BR": 2, "SYS": 1,
    "INT_MUL": 1, "INT_DIV": 1, "INT_CSR": 1,
    "MEM_LD": 1, "MEM_ST": 1, "MEM_AMO": 1,
    "FP_ALU": 1, "FP_FMA": 1, "FP_DIV": 1, "FP_MOV": 1,
}


def style():
    plt.rcParams.update({
        "font.size": 10, "axes.grid": True, "grid.alpha": 0.3,
        "figure.facecolor": "white", "axes.facecolor": "white",
        "savefig.bbox": "tight", "savefig.dpi": 140,
    })


def save(fig, path):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    fig.savefig(path)
    print("wrote", path)
    plt.close(fig)


def make_uop(cat, uid, disp):
    return {
        "id": uid, "cat": cat, "tok": TOKEN[cat], "fu": CAT_FU[cat],
        "iq": CAT_IQ[cat], "disp": disp, "ready": True, "age": uid,
    }


def default_grant(ready, ports):
    """Oldest first, first free legal port."""
    taken = [False] * len(ports)
    granted = []
    for u in ready:
        for p, (_name, mask) in enumerate(ports):
            if taken[p] or not (u["fu"] & mask):
                continue
            taken[p] = True
            granted.append(u)
            break
    return granted


def occupancy_of(ex, extra_cats=None):
    c = Counter()
    for _remain, cat in ex:
        c[cat] += 1
    for cat in extra_cats or []:
        c[cat] += 1
    for cat in list(c):
        c[cat] = min(c[cat], FU_WIDTH[cat])
    return c


def pred_I(ex, granted):
    return power_ma(occupancy_of(ex, [u["cat"] for u in granted]))


def legal_grants(ready, ports):
    """Full-width legal sets, else singles. Never skip a free port."""
    singles = []
    for u in ready:
        for _n, mask in ports:
            if u["fu"] & mask:
                singles.append((u,))
                break
    if len(ports) < 2:
        return singles
    pairs = []
    for i, u in enumerate(ready):
        for v in ready[i + 1:]:
            for a, b in ((0, 1), (1, 0)):
                if (u["fu"] & ports[a][1]) and (v["fu"] & ports[b][1]):
                    pairs.append((u, v))
                    break
    return pairs or singles


def pick_pdn(cands, ex, already, i_last, i_vrm):
    """Min |I_pred − I_last| (fast edge the caps eat), then stay near VRM."""
    if not cands:
        return []
    best = None
    best_key = None
    for g in cands:
        combo = list(already) + list(g)
        ip = pred_I(ex, combo)
        key = (
            -len(g),
            abs(ip - i_last),
            abs(ip - i_vrm),
            sum(u["age"] for u in g),
        )
        if best_key is None or key < best_key:
            best_key = key
            best = g
    return list(best)


def pack_grant(ready, ports, last_toks, ex=None, i_last=None, i_vrm=None):
    """PDN pack: hold tile current on a plateau the VRM can follow."""
    if not ready:
        return []
    if i_last is None:
        high = bool(last_toks) and last_toks[0] == "HIGH"
        i_last = I0_MA + (DEFAULT_W["INT_MUL"] + DEFAULT_W["INT_ALU"] if high
                          else 2.0 * DEFAULT_W["INT_ALU"])
        i_vrm = i_last
    return pick_pdn(legal_grants(ready, ports), ex or [], [], i_last,
                    i_vrm if i_vrm is not None else i_last)


def n_legal_sets(ready, ports):
    """Distinct legal issue-id sets (width ≤ 2)."""
    seen = set()
    for u in ready:
        for _n, mask in ports:
            if u["fu"] & mask:
                seen.add(frozenset([u["id"]]))
                break
    if len(ports) >= 2:
        for i, u in enumerate(ready):
            for v in ready[i + 1:]:
                ok = False
                for a, b in ((0, 1), (1, 0)):
                    if (u["fu"] & ports[a][1]) and (v["fu"] & ports[b][1]):
                        ok = True
                        break
                if ok:
                    seen.add(frozenset([u["id"], v["id"]]))
    return max(len(seen), 1)


def weighted_cat(rng, weights):
    cats, w = zip(*weights)
    tot = float(sum(w))
    x = rng.random() * tot
    acc = 0.0
    for c, wi in zip(cats, w):
        acc += wi
        if x <= acc:
            return c
    return cats[-1]


def window_study(rng, n_trials=4000):
    """Random ready windows: how often pack ≠ default, how deep we reach."""
    mixes = {
        "hello_like": [("INT_ALU", 70), ("MEM_LD", 0), ("INT_BR", 8),
                       ("INT_CSR", 4), ("INT_MUL", 2), ("INT_DIV", 1)],
        "int_chatter": [("INT_ALU", 50), ("INT_MUL", 20), ("INT_DIV", 15),
                        ("INT_BR", 10), ("INT_CSR", 5)],
        "int_high_heavy": [("INT_ALU", 30), ("INT_MUL", 35), ("INT_DIV", 25),
                           ("INT_CSR", 10)],
        "full_mix": [("INT_ALU", 25), ("INT_BR", 8), ("INT_MUL", 10),
                     ("INT_DIV", 8), ("INT_CSR", 5), ("MEM_LD", 12),
                     ("MEM_ST", 8), ("MEM_AMO", 4), ("FP_ALU", 8),
                     ("FP_FMA", 7), ("FP_DIV", 3), ("FP_MOV", 2)],
    }
    rows = []
    uid = 1
    for mix_name, weights in mixes.items():
        # INT IQ is the only 2-wide queue — that is where reorder lives.
        int_w = [(c, w) for c, w in weights if CAT_IQ[c] == "INT"]
        if not int_w:
            continue
        for R in range(2, 13):
            disagree = 0
            alt_sets = 0
            depth_sum = 0
            n_grant_diff = 0
            n_issued = 0
            reachable = 0
            for _ in range(n_trials):
                ready = []
                for _i in range(R):
                    ready.append(make_uop(weighted_cat(rng, int_w), uid, 0))
                    uid += 1
                ready.sort(key=lambda u: u["age"])
                ports = IQ_PORTS["INT"]
                d = default_grant(ready, ports)
                # previous token: 50% chance we are in a HIGH plateau
                last = ["HIGH"] if rng.random() < 0.45 else ["LOW"]
                p = pack_grant(ready, ports, last)
                sets = n_legal_sets(ready, ports)
                alt_sets += sets
                if {u["id"] for u in d} != {u["id"] for u in p}:
                    disagree += 1
                issued = p or d
                n_issued += len(issued)
                ages = [ready.index(u) for u in issued]
                if ages:
                    depth_sum += max(ages)
                    reachable += sum(1 for a in ages if a >= 2)
                n_grant_diff += len({u["id"] for u in d}.symmetric_difference(
                    {u["id"] for u in p}))
            rows.append({
                "mix": mix_name, "ready": R, "trials": n_trials,
                "disagree_frac": disagree / float(n_trials),
                "mean_legal_sets": alt_sets / float(n_trials),
                "mean_max_age_rank": depth_sum / float(n_trials),
                "frac_grant_from_slot_ge2": reachable / float(max(1, n_issued)),
                "mean_ids_changed": n_grant_diff / float(n_trials),
            })
    return rows


class Core(object):
    def __init__(self, rng, stream_fn, policy):
        self.rng = rng
        self.stream_fn = stream_fn
        self.policy = policy
        self.iqs = {k: [] for k in IQ_CAP}
        self.ex = []  # (remain, cat)
        self.last_toks = []
        self.i_last = I0_MA
        self.i_vrm = I0_MA
        self.uid = 0
        self.issued_n = 0
        self.disp_n = 0
        self.stall_disp = 0
        self.cycles = 0
        self.I = []
        self.reorders = 0
        self.grant_cycles = 0
        self.changed_ids = 0

    def dispatch(self):
        for _ in range(DECODE_W):
            cat = self.stream_fn(self.rng)
            iq = CAT_IQ[cat]
            if len(self.iqs[iq]) >= IQ_CAP[iq]:
                self.stall_disp += 1
                return
            self.uid += 1
            # Independent with p=0.65 so several ready uops sit in the IQ.
            ready = self.rng.random() < 0.65
            u = make_uop(cat, self.uid, self.cycles)
            u["ready"] = ready
            if not ready:
                u["wake"] = self.cycles + 1 + self.rng.randint(0, 3)
            self.iqs[iq].append(u)
            self.disp_n += 1

    def wakeup(self):
        for iq in self.iqs.values():
            for u in iq:
                if not u["ready"] and self.cycles >= u.get("wake", 0):
                    u["ready"] = True

    def issue(self):
        all_granted = []
        cycle_reorder = False
        had_ready = False
        already = []
        for name in ("INT", "MEM", "FP"):
            q = self.iqs[name]
            ports = IQ_PORTS[name]
            ready = [u for u in q if u["ready"]]
            ready.sort(key=lambda u: u["age"])
            if ready:
                had_ready = True
            d = default_grant(ready, ports)
            if self.policy == "default":
                g = d
            else:
                g = pick_pdn(
                    legal_grants(ready, ports), self.ex, already,
                    self.i_last, self.i_vrm)
            if {u["id"] for u in d} != {u["id"] for u in g}:
                cycle_reorder = True
                self.changed_ids += len(
                    {u["id"] for u in d}.symmetric_difference({u["id"] for u in g}))
            already.extend(g)
            gids = {u["id"] for u in g}
            self.iqs[name] = [u for u in q if u["id"] not in gids]
            all_granted.extend(g)
        if had_ready:
            self.grant_cycles += 1
        if cycle_reorder:
            self.reorders += 1
        for u in all_granted:
            self.ex.append([LAT[u["cat"]], u["cat"]])
            self.issued_n += 1
        self.last_toks = [u["tok"] for u in all_granted]
        return all_granted

    def retire_ex(self):
        live = []
        for remain, cat in self.ex:
            if remain > 1:
                live.append([remain - 1, cat])
        self.ex = live

    def occupancy(self):
        c = Counter()
        for remain, cat in self.ex:
            c[cat] += 1
        for cat in list(c):
            c[cat] = min(c[cat], FU_WIDTH[cat])
        return c

    def step(self):
        self.wakeup()
        self.dispatch()
        self.issue()
        occ = self.occupancy()
        i_now = power_ma(occ)
        self.I.append(i_now)
        self.i_last = i_now
        self.i_vrm += (i_now - self.i_vrm) / VRM_TAU_CYC
        self.retire_ex()
        self.cycles += 1


def stream_hello(rng):
    return weighted_cat(rng, [
        ("INT_ALU", 72), ("INT_BR", 8), ("MEM_LD", 10), ("MEM_ST", 6),
        ("INT_CSR", 3), ("INT_MUL", 1),
    ])


def stream_chatter(rng):
    """HIGH sandwiched in LOW — the pattern packing is meant to kill."""
    return weighted_cat(rng, [
        ("INT_ALU", 40), ("INT_MUL", 18), ("INT_DIV", 12), ("INT_BR", 8),
        ("MEM_LD", 10), ("MEM_ST", 4), ("FP_FMA", 5), ("FP_ALU", 3),
    ])


def stream_high_heavy(rng):
    return weighted_cat(rng, [
        ("INT_ALU", 20), ("INT_MUL", 22), ("INT_DIV", 16), ("MEM_AMO", 6),
        ("FP_FMA", 14), ("FP_ALU", 10), ("FP_DIV", 4), ("MEM_LD", 8),
    ])


def stream_int_ports(rng):
    return weighted_cat(rng, [
        ("INT_ALU", 35), ("INT_MUL", 25), ("INT_DIV", 20),
        ("INT_CSR", 10), ("INT_BR", 10),
    ])


STREAMS = [
    ("hello_like", stream_hello),
    ("int_chatter", stream_chatter),
    ("int_port_mix", stream_int_ports),
    ("high_heavy", stream_high_heavy),
]


def drain_stats(I, issued, cycles, disp, stalls, reorders, grant_cycles, changed):
    I = np.asarray(I, dtype=float)
    dI = np.diff(I)
    abs_dI = np.abs(dI)
    energy_nj = float(I.mean() * 1e-3 * VDD * cycles * TCLK_NS * 1e-3)
    # Caps supply what a slow PDN (VRM_TAU cycles) cannot follow.
    tau = int(VRM_TAU_CYC)
    if len(I) >= tau:
        ker = np.ones(tau) / float(tau)
        slow = np.convolve(I, ker, mode="same")
        hf = I - slow
    else:
        hf = I - I.mean()
    quiet = abs_dI < EDGE_QUIET_MA if len(abs_dI) else np.array([])
    plat_len = 0.0
    if len(quiet):
        runs, n = [], 0
        for q in quiet:
            if q:
                n += 1
            elif n:
                runs.append(n)
                n = 0
        if n:
            runs.append(n)
        plat_len = float(np.mean(runs)) if runs else 0.0
    return {
        "cycles": cycles,
        "issued": issued,
        "ipc": issued / float(cycles),
        "disp": disp,
        "disp_stalls": stalls,
        "reorder_frac": reorders / float(max(1, cycles)),
        "reorder_when_ready": reorders / float(max(1, grant_cycles)),
        "mean_ids_changed": changed / float(max(1, cycles)),
        "mean_mA": float(I.mean()),
        "peak_mA": float(I.max()),
        "p95_mA": float(np.percentile(I, 95)),
        "mean_mW": float(I.mean() * VDD),
        "peak_mW": float(I.max() * VDD),
        "energy_nJ": energy_nj,
        "sum_abs_dI_mA": float(abs_dI.sum()),
        "mean_abs_dI_mA": float(abs_dI.mean()) if len(abs_dI) else 0.0,
        "max_dI_mA": float(abs_dI.max()) if len(abs_dI) else 0.0,
        "n_edges_15mA": int((abs_dI >= 15.0).sum()),
        "n_edges_25mA": int((abs_dI >= 25.0).sum()),
        "hf_peak_mA": float(np.max(np.abs(hf))),
        "hf_rms_mA": float(np.sqrt(np.mean(hf * hf))),
        "plateau_cyc": plat_len,
        "quiet_frac": float(quiet.mean()) if len(quiet) else 0.0,
        "energy_nJ_per_uop": energy_nj / float(max(1, issued)),
    }


def run_pipeline(n_cycles=12000):
    rows = []
    waves = {}
    for sname, fn in STREAMS:
        pair = {}
        for policy in ("default", "pack"):
            rng = random.Random(SEED + sum(ord(c) for c in sname))
            core = Core(rng, fn, policy)
            for _ in range(n_cycles):
                core.step()
            st = drain_stats(
                core.I, core.issued_n, core.cycles, core.disp_n,
                core.stall_disp, core.reorders, core.grant_cycles,
                core.changed_ids)
            st["scenario"] = sname
            st["policy"] = policy
            rows.append(st)
            pair[policy] = np.asarray(core.I)
        waves[sname] = pair
    return rows, waves


def write_csv(path, rows, fields=None):
    if not rows:
        return
    fields = fields or list(rows[0].keys())
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fields})
    print("wrote", path)


def compare_rows(pipe):
    by = defaultdict(dict)
    for r in pipe:
        by[r["scenario"]][r["policy"]] = r
    out = []
    for sc, d in by.items():
        a, b = d["default"], d["pack"]
        def rel(key):
            av = float(a[key])
            return (float(b[key]) - av) / av * 100.0 if av else 0.0
        out.append({
            "scenario": sc,
            "reorder_frac": b["reorder_frac"],
            "ipc_default": a["ipc"],
            "ipc_pack": b["ipc"],
            "ipc_pct": rel("ipc"),
            "peak_mA_default": a["peak_mA"],
            "peak_mA_pack": b["peak_mA"],
            "peak_mA_pct": rel("peak_mA"),
            "peak_mW_default": a["peak_mW"],
            "peak_mW_pack": b["peak_mW"],
            "peak_mW_pct": rel("peak_mW"),
            "mean_mA_default": a["mean_mA"],
            "mean_mA_pack": b["mean_mA"],
            "mean_mA_pct": rel("mean_mA"),
            "energy_nJ_default": a["energy_nJ"],
            "energy_nJ_pack": b["energy_nJ"],
            "energy_pct": rel("energy_nJ"),
            "sum_abs_dI_pct": rel("sum_abs_dI_mA"),
            "mean_abs_dI_default": a["mean_abs_dI_mA"],
            "mean_abs_dI_pack": b["mean_abs_dI_mA"],
            "edges15_default": a["n_edges_15mA"],
            "edges15_pack": b["n_edges_15mA"],
            "edges15_pct": rel("n_edges_15mA"),
            "hf_rms_pct": rel("hf_rms_mA"),
            "hf_peak_pct": rel("hf_peak_mA"),
            "max_dI_default": a["max_dI_mA"],
            "max_dI_pack": b["max_dI_mA"],
            "max_dI_pct": rel("max_dI_mA"),
            "plateau_default": a["plateau_cyc"],
            "plateau_pack": b["plateau_cyc"],
            "plateau_pct": rel("plateau_cyc"),
            "quiet_frac_default": a["quiet_frac"],
            "quiet_frac_pack": b["quiet_frac"],
            "e_per_uop_pct": rel("energy_nJ_per_uop"),
        })
    return out


def plot_all(window, pipe, waves, cmp_rows):
    style()
    # reorder vs ready depth
    fig, ax = plt.subplots(figsize=(8, 4))
    for mix in sorted(set(r["mix"] for r in window)):
        xs = [r["ready"] for r in window if r["mix"] == mix]
        ys = [100 * r["disagree_frac"] for r in window if r["mix"] == mix]
        ax.plot(xs, ys, marker="o", lw=1.2, label=mix)
    ax.set_xlabel("ready uops in INT IQ")
    ax.set_ylabel("pack ≠ default (%)")
    ax.set_title("How often the INT IQ can legally reorder")
    ax.legend(fontsize=8)
    save(fig, os.path.join(OUT, "01_reorder_vs_ready.png"))

    fig, ax = plt.subplots(figsize=(8, 4))
    for mix in sorted(set(r["mix"] for r in window)):
        xs = [r["ready"] for r in window if r["mix"] == mix]
        ys = [r["mean_legal_sets"] for r in window if r["mix"] == mix]
        ax.plot(xs, ys, marker="o", lw=1.2, label=mix)
    ax.set_xlabel("ready uops in INT IQ")
    ax.set_ylabel("distinct legal issue sets")
    ax.set_title("Legal grant choices (INT, 2 ports, fu_code match)")
    ax.legend(fontsize=8)
    save(fig, os.path.join(OUT, "02_legal_sets_vs_ready.png"))

    # I(t) overlay for chatter
    pair = waves["int_chatter"]
    sl = slice(2000, 2300)
    t = np.arange(sl.start, sl.stop) * TCLK_NS * 1e-3
    fig, ax = plt.subplots(figsize=(10, 3.6))
    ax.plot(t, pair["default"][sl], color="0.45", lw=0.9, label="age-order")
    ax.plot(t, pair["pack"][sl], color="black", lw=0.9, label="plateau pack")
    ax.set_xlabel("time (us)")
    ax.set_ylabel("I (mA)")
    ax.set_title("EXPERIMENTAL token I(t)  ·  int_chatter  ·  not a measurement")
    ax.legend()
    save(fig, os.path.join(OUT, "03_I_t_chatter.png"))

    pair = waves["high_heavy"]
    fig, ax = plt.subplots(figsize=(10, 3.6))
    ax.plot(t, pair["default"][sl], color="0.45", lw=0.9, label="age-order")
    ax.plot(t, pair["pack"][sl], color="black", lw=0.9, label="plateau pack")
    ax.set_xlabel("time (us)")
    ax.set_ylabel("I (mA)")
    ax.set_title("EXPERIMENTAL token I(t)  ·  high_heavy  ·  not a measurement")
    ax.legend()
    save(fig, os.path.join(OUT, "04_I_t_high_heavy.png"))

    labels = [r["scenario"] for r in cmp_rows]
    x = np.arange(len(labels))
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.bar(x - 0.2, [r["peak_mA_pct"] for r in cmp_rows], 0.4, color="0.35",
           label="peak I")
    ax.bar(x + 0.2, [r["sum_abs_dI_pct"] for r in cmp_rows], 0.4, color="0.7",
           label="Σ|ΔI|")
    ax.axhline(0, color="black", lw=0.6)
    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=15, ha="right")
    ax.set_ylabel("pack vs age-order (%)")
    ax.set_title("EXPERIMENTAL token dI  ·  not a measured current")
    ax.legend()
    save(fig, os.path.join(OUT, "05_peak_and_edges.png"))

    fig, ax = plt.subplots(figsize=(8, 4))
    ax.bar(x - 0.2, [r["energy_pct"] for r in cmp_rows], 0.4, color="0.35",
           label="energy")
    ax.bar(x + 0.2, [r["ipc_pct"] for r in cmp_rows], 0.4, color="0.7",
           label="IPC")
    ax.axhline(0, color="black", lw=0.6)
    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=15, ha="right")
    ax.set_ylabel("pack vs age-order (%)")
    ax.set_title("EXPERIMENTAL token energy / IPC  ·  not a measurement")
    ax.legend()
    save(fig, os.path.join(OUT, "06_energy_ipc.png"))


def main():
    rng = random.Random(SEED)
    print("window study...")
    window = window_study(rng)
    print("pipeline study...")
    pipe, waves = run_pipeline()
    cmp_rows = compare_rows(pipe)
    os.makedirs(OUT, exist_ok=True)
    write_csv(os.path.join(OUT, "window_stats.csv"), window)
    write_csv(os.path.join(OUT, "pipeline_stats.csv"), pipe)
    write_csv(os.path.join(OUT, "pack_vs_default.csv"), cmp_rows)
    plot_all(window, pipe, waves, cmp_rows)

    print("\n=== INT IQ reorderability (ready window) ===")
    print("%-14s %5s %10s %10s %10s" % (
        "mix", "R", "disagree%", "legal_sets", "max_rank"))
    for r in window:
        if r["ready"] in (3, 6, 10):
            print("%-14s %5d %9.1f%% %10.1f %10.2f" % (
                r["mix"], r["ready"], 100 * r["disagree_frac"],
                r["mean_legal_sets"], r["mean_max_age_rank"]))

    print("\n=== Runtime cycles where pack != age-order ===")
    for r in cmp_rows:
        print("%-14s  %5.1f%%" % (r["scenario"], 100 * r["reorder_frac"]))
    print("\n=== EXPERIMENTAL token current (priors, not a measurement) ===")
    print("%-14s %8s %8s %8s %8s" % (
        "scenario", "d|dI|%", "dHF%", "dIPC%", "dE/uop"))
    for r in cmp_rows:
        print("%-14s %7.1f%% %7.1f%% %7.1f%% %7.1f%%" % (
            r["scenario"], r["sum_abs_dI_pct"],
            r["hf_rms_pct"], r["ipc_pct"], r["e_per_uop_pct"]))

    meta = {
        "i0_mA": I0_MA, "vdd": VDD, "tclk_ns": TCLK_NS,
        "vrm_tau_cyc": VRM_TAU_CYC, "edge_quiet_mA": EDGE_QUIET_MA,
        "w": DEFAULT_W,
        "note": "PDN pack: min |I_pred-I_last| then |I_pred-I_vrm|. Priors, not OLS.",
        "window": window, "pipeline": pipe, "compare": cmp_rows,
    }
    jp = os.path.join(OUT, "summary.json")
    with open(jp, "w") as f:
        json.dump(meta, f, indent=2)
    print("wrote", jp)


if __name__ == "__main__":
    main()
