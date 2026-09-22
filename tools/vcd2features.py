#!/usr/bin/env python
"""Convert a BOOM VCD into LACPo feature columns (values, Hamming, history)."""
from __future__ import print_function

import argparse
import os
import re
import sys

import numpy as np
import pandas as pd

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "common", "vcd2csv"))
from Verilog_VCD import list_sigs, parse_vcd  # noqa: E402

HD_PREFIXES = ("d2_", "d1_", "d_")
HIST_PREFIXES = ("v2_", "v1_")


def die(msg):
    sys.stderr.write(msg + "\n")
    sys.exit(1)


def hamming(a, b):
    x = int(a) ^ int(b)
    n = 0
    while x:
        n += x & 1
        x >>= 1
    return n


def strip_engineered(name):
    for p in HD_PREFIXES + HIST_PREFIXES:
        if name.startswith(p):
            return name[len(p):]
    return name


def split_slice(name):
    m = re.search(r"^(.*)\[(\d+):(\d+)\]$", name)
    if m:
        return m.group(1), (int(m.group(2)), int(m.group(3)))
    m = re.search(r"^(.*)\[(\d+)\]$", name)
    if m:
        bit = int(m.group(2))
        return m.group(1), (bit, bit)
    return name, None


def raw_net(feature):
    base, _ = split_slice(strip_engineered(feature))
    return base


def needed_nets(features):
    nets = []
    seen = set()
    for f in features:
        n = raw_net(f)
        if n not in seen:
            seen.add(n)
            nets.append(n)
    return nets


def slice_value(val, slc):
    if slc is None:
        return int(val)
    hi, lo = slc
    width = abs(hi - lo) + 1
    return (int(val) >> min(hi, lo)) & ((1 << width) - 1)


def sample_at_clock(vcd, clock_net, period_hint=None):
    mappings = {}
    for code, data in vcd.items():
        for net in data.get("nets", []):
            mappings[net["hier"] + "." + net["name"]] = code
    if clock_net not in mappings:
        die("Clock %s not in VCD. Have %d nets." % (clock_net, len(mappings)))
    clock_tv = vcd[mappings[clock_net]].get("tv", [])
    edges = []
    for t, val in clock_tv:
        try:
            v = int(str(val), 2) if set(str(val)) <= set("01xzXZ") and len(str(val)) > 1 else int(val)
        except ValueError:
            v = 0 if str(val) in "xzXZ" else int(str(val), 2) if str(val).startswith("b") else 0
        if str(val) in ("1", "b1"):
            edges.append(int(t))
        elif str(val) not in ("0", "1", "x", "X", "z", "Z") and v == 1:
            edges.append(int(t))
    if len(edges) < 2:
        # falling/rising encoded as 0/1 only
        last = None
        edges = []
        for t, val in clock_tv:
            s = str(val).lower().replace("b", "")
            bit = 1 if s.endswith("1") else 0
            if last == 0 and bit == 1:
                edges.append(int(t))
            last = bit
    if not edges:
        die("No rising clock edges on %s" % clock_net)
    if period_hint:
        period = period_hint
    elif len(edges) > 1:
        period = edges[1] - edges[0]
    else:
        period = 3
    return mappings, edges, period


def value_at(tv, t, default=0):
    if not tv:
        return default
    cur = default
    for ts, val in tv:
        if int(ts) > t:
            break
        s = str(val).lower()
        if s.startswith("b"):
            s = s[1:]
        s = s.replace("x", "0").replace("z", "0")
        try:
            cur = int(s, 2) if s else 0
        except ValueError:
            cur = 0
    return cur


def traces_for_nets(vcd, mappings, nets, sample_times):
    out = {}
    for net in nets:
        tv = []
        if net in mappings:
            tv = vcd[mappings[net]].get("tv", [])
        out[net] = [value_at(tv, t, 0) for t in sample_times]
    return out


def engineer_features(traces, features):
    n = len(next(iter(traces.values()))) if traces else 0
    cols = {"Cycle": np.arange(n, dtype=np.int32)}
    cache = {}

    def series(net, slc):
        key = (net, slc)
        if key not in cache:
            raw = traces.get(net)
            if raw is None:
                cache[key] = np.zeros(n, dtype=np.int64)
            else:
                cache[key] = np.array([slice_value(v, slc) for v in raw], dtype=np.int64)
        return cache[key]

    def delay(arr, k):
        if k <= 0:
            return arr
        out = np.zeros_like(arr)
        if k < len(arr):
            out[k:] = arr[:-k]
        return out

    for feat in features:
        engineered = strip_engineered(feat)
        net, slc = split_slice(engineered)
        vals = series(net, slc)
        hd = np.zeros(n, dtype=np.int64)
        if n:
            hd[1:] = np.array([hamming(vals[i - 1], vals[i]) for i in range(1, n)], dtype=np.int64)
        if feat.startswith("v2_"):
            cols[feat] = delay(vals, 2)
        elif feat.startswith("v1_"):
            cols[feat] = delay(vals, 1)
        elif feat.startswith("d2_"):
            cols[feat] = delay(hd, 1)
        elif feat.startswith("d1_"):
            cols[feat] = hd
        elif feat.startswith("d_"):
            cols[feat] = hd
        else:
            cols[feat] = vals
    return pd.DataFrame(cols)


def boom_rel(name):
    if "boom_tile." in name:
        return name.split("boom_tile.", 1)[1]
    return name


def build_vcd_index(vcd_sigs):
    rel_to_full = {}
    by_leaf = {}
    by2 = {}
    for s in vcd_sigs:
        if ".boom_tile." not in s:
            continue
        rel = s.split(".boom_tile.", 1)[1]
        rel_to_full[rel] = s
        leaf = rel.split(".")[-1]
        by_leaf.setdefault(leaf, []).append(s)
        parts = rel.split(".")
        if len(parts) >= 2:
            by2.setdefault(".".join(parts[-2:]), []).append(s)
    return rel_to_full, by_leaf, by2


def map_lacpo_net(lacpo_net, rel_to_full, by_leaf, by2):
    """Map a LACPo TestDriver path onto a flattened Verilator boom_tile net."""
    rel = boom_rel(lacpo_net)
    tries = [rel]
    if rel.startswith("core.lsu"):
        tries.append(rel[len("core."):])
    if "ALUExeUnit" in rel:
        tries.append(rel.replace("ALUExeUnit", "jmp_unit"))
    if "brinfo" in rel:
        tries.append(rel.replace("brinfo", "brupdate"))
        if rel.startswith("core.lsu"):
            tries.append(rel[len("core."):].replace("brinfo", "brupdate"))
    for t in tries:
        if t in rel_to_full:
            return rel_to_full[t]
    key2 = ".".join(rel.split(".")[-2:])
    hits = by2.get(key2, [])
    if len(hits) == 1:
        return hits[0]
    leaf = rel.split(".")[-1]
    hits = by_leaf.get(leaf, [])
    if len(hits) == 1:
        return hits[0]
    return None


def parse_signal_list(path):
    clock = None
    nets = []
    with open(path, "r") as f:
        for line in f:
            parts = line.strip().split()
            if not parts:
                continue
            if parts[-1] == "CLOCK":
                clock = parts[0]
                continue
            nets.append(parts[0])
    return clock, nets


def collect_invoke_features(root=ROOT):
    sys.path.insert(0, os.path.join(root, "tools"))
    from run_lacpo_flow import discover_blocks
    feats = []
    seen = set()
    for block in discover_blocks():
        for f in block["features"]:
            if f not in seen:
                seen.add(f)
                feats.append(f)
    return feats


def write_vcd(path, clock_net, traces, period_ns=3):
    """Write a 4-state VCD from integer traces. traces[net] = list of values."""
    nets = [clock_net] + [n for n in traces if n != clock_net]
    n = len(next(iter(traces.values())))
    codes = {}
    charset = [chr(c) for c in range(33, 127) if chr(c) not in " \t"]
    def code_at(i):
        s = ""
        x = i
        while True:
            s = charset[x % len(charset)] + s
            x = x // len(charset) - 1
            if x < 0:
                return s
    for i, net in enumerate(nets):
        codes[net] = code_at(i)

    def width_of(net):
        if net == clock_net:
            return 1
        mx = max(traces[net]) if traces[net] else 1
        return max(1, int(mx).bit_length())

    scopes_open = []
    with open(path, "w") as f:
        f.write("$timescale 1ns $end\n")
        for net in nets:
            parts = net.split(".")
            # close/open scopes
            i = 0
            while i < len(scopes_open) and i < len(parts) - 1 and scopes_open[i] == parts[i]:
                i += 1
            while len(scopes_open) > i:
                f.write("$upscope $end\n")
                scopes_open.pop()
            while len(scopes_open) < len(parts) - 1:
                name = parts[len(scopes_open)]
                f.write("$scope module %s $end\n" % name)
                scopes_open.append(name)
            w = width_of(net)
            leaf = parts[-1]
            if w > 1:
                f.write("$var wire %d %s %s [%d:0] $end\n" % (w, codes[net], leaf, w - 1))
            else:
                f.write("$var wire %d %s %s $end\n" % (w, codes[net], leaf))
        while scopes_open:
            f.write("$upscope $end\n")
            scopes_open.pop()
        f.write("$enddefinitions $end\n")
        last = {net: None for net in nets}
        for cyc in range(n):
            t0 = cyc * period_ns
            # clock low then high within the period, sample on rising at t0
            f.write("#%d\n" % t0)
            if last[clock_net] != 1:
                f.write("1%s\n" % codes[clock_net])
                last[clock_net] = 1
            for net in nets:
                if net == clock_net:
                    continue
                val = int(traces[net][cyc])
                if last[net] == val:
                    continue
                last[net] = val
                w = width_of(net)
                if w == 1:
                    f.write("%d%s\n" % (val & 1, codes[net]))
                else:
                    bits = format(val & ((1 << w) - 1), "0%db" % w)
                    f.write("b%s %s\n" % (bits, codes[net]))
            f.write("#%d\n" % (t0 + period_ns // 2))
            f.write("0%s\n" % codes[clock_net])
            last[clock_net] = 0
    return path


def vcd_to_features(vcd_path, features, clock_net, period_ns=3):
    nets = needed_nets(features)
    vcd_sigs = list_sigs(vcd_path)
    rel_to_full, by_leaf, by2 = build_vcd_index(vcd_sigs)
    rename = {}
    for n in [clock_net] + list(nets):
        mapped = map_lacpo_net(n, rel_to_full, by_leaf, by2)
        if mapped:
            rename[n] = mapped
    clock_vcd = rename.get(clock_net)
    if not clock_vcd:
        # last-resort: tile LSU clock on this Verilator dump
        clock_vcd = rel_to_full.get("lsu.clock")
        if clock_vcd:
            rename[clock_net] = clock_vcd
    if not clock_vcd:
        die("Clock %s not in VCD after remap. Have %d boom_tile nets." % (
            clock_net, len(rel_to_full)))
    siglist = sorted(set(rename.values()))
    print("vcd map: %d/%d nets (+clock) matched" % (len(rename) - (1 if clock_net in rename else 0), len(nets)))
    print("clock", clock_net, "->", clock_vcd)
    vcd = parse_vcd(vcd_path, siglist=siglist)
    mappings, edges, period = sample_at_clock(vcd, clock_vcd, period_ns)
    # traces keyed by LACPo names so feature columns stay model-facing
    vcd_traces = traces_for_nets(vcd, mappings, siglist, edges)
    traces = {}
    for n in nets:
        src = rename.get(n)
        traces[n] = vcd_traces[src] if src else [0] * len(edges)
    df = engineer_features(traces, features)
    return df, period


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--vcd", required=True)
    parser.add_argument("--clock", default="TestDriver.testHarness.TestHarness.boom_tile.core.lsu.clock")
    parser.add_argument("--out", required=True)
    parser.add_argument("--benchmark", default="")
    parser.add_argument("--period-ns", type=int, default=3)
    args = parser.parse_args()
    features = collect_invoke_features()
    df, period = vcd_to_features(args.vcd, features, args.clock, args.period_ns)
    if args.benchmark:
        df["Benchmark"] = args.benchmark
    os.makedirs(os.path.dirname(os.path.abspath(args.out)) or ".", exist_ok=True)
    df.to_csv(args.out, index=False)
    print("cycles", len(df), "columns", len(df.columns), "period", period)
    print("wrote", args.out)


if __name__ == "__main__":
    main()
