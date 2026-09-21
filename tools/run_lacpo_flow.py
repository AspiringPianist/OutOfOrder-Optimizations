#!/usr/bin/env python
"""Run LACPo BOOM pretrained models in the isolated sklearn 0.20 env.

Loads every block pickle, evaluates a cycle-level activity waveform, composes
hierarchical P(t), and writes I(t)=P(t)/VDD plus a SIMPLIS PWL.

If BOOM/power_modeling/input_csvs/*.csv exist they are used. Otherwise a
synthetic activity schedule is generated from the invoke feature lists so the
documented invoc path still runs. Synthetic traces are labeled as such.
"""
from __future__ import print_function

import argparse
import csv
import json
import os
import random
import re
import sys

import numpy as np
import pandas as pd

try:
    from sklearn.externals import joblib
except ImportError:
    import joblib


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
BOOM = os.path.join(ROOT, "BOOM")
MODELS = os.path.join(BOOM, "power_modeling", "power_models")
INVOKE_SH = os.path.join(BOOM, "DT_plots", "invoke_model_shell_files")
USED_SIGNALS = os.path.join(BOOM, "power_modeling", "used_signals")
INPUT_CSVS = os.path.join(BOOM, "power_modeling", "input_csvs")
TRACES = os.path.join(ROOT, "traces")

VDD_V = 1.1
TCLK_NS = 3.0
N_CYCLES_DEFAULT = 4096
RNG_SEED = 20260826

# Prefixes LACPo uses in engineered feature names.
HD_PREFIXES = ("d2_", "d1_", "d_")
HIST_PREFIXES = ("v2_", "v1_")


def die(msg):
    sys.stderr.write(msg + "\n")
    sys.exit(1)


def feature_bitwidth(name):
    m = re.search(r"\[(\d+):(\d+)\]", name)
    if m:
        hi, lo = int(m.group(1)), int(m.group(2))
        return abs(hi - lo) + 1
    m = re.search(r"\[(\d+)\]", name)
    if m:
        return 1
    return 1


def feature_max_value(name):
    width = feature_bitwidth(name)
    stripped = name
    for prefix in HD_PREFIXES + HIST_PREFIXES:
        if name.startswith(prefix):
            stripped = name[len(prefix):]
            break
    if name.startswith(HD_PREFIXES):
        return width
    if any(name.startswith(p) for p in HIST_PREFIXES):
        return (1 << width) - 1
    if "[" in stripped:
        return (1 << width) - 1
    return 1


def parse_invoke_shell(path):
    with open(path, "r") as f:
        text = f.read().replace("\\\n", "").replace("\n", " ")
    features = []
    m_fl = re.search(r"-fl\s+(\S+)", text)
    if m_fl:
        features = [x.strip() for x in m_fl.group(1).split(",") if x.strip()]
    m_model = re.search(r"-m\s+(\S+)", text)
    model_rel = m_model.group(1) if m_model else None
    m_te = re.search(r"-te\s+(\S+)", text)
    test_rel = m_te.group(1) if m_te else None
    m_out = re.search(r"-o\s+(\S+)", text)
    out_name = m_out.group(1) if m_out else os.path.splitext(os.path.basename(path))[0]
    return {
        "shell": path,
        "features": features,
        "model_rel": model_rel,
        "test_rel": test_rel,
        "out_name": out_name,
    }


def used_signals_for(stem):
    candidates = [
        os.path.join(USED_SIGNALS, stem + "_used_signals.csv"),
        os.path.join(USED_SIGNALS, stem + ".csv"),
    ]
    # common mismatches between pkl stem and used_signals filename
    aliases = {
        "core_glue_1": "core_glue_for_top",
        "core__mem_issue_unit_1": "core__mem_issue_unit_handpicked_signals",
        "core__int_issue_unit_handpicked_signals_3_1": "core__int_issue_unit_handpicked_signals_3",
        "core__fp_pipeline_handpicked_signals_2_1": "core__fp_pipeline_handpicked_signals_2",
        "core__rename_stage__freelist_history_1_1": "core__rename_stage__freelist_history_1",
        "core__rename_stage___maptable_history_1_1": "core__rename_stage___maptable_history_1",
    }
    if stem in aliases:
        candidates.insert(0, os.path.join(USED_SIGNALS, aliases[stem] + "_used_signals.csv"))
    stripped = stem[:-2] if stem.endswith("_1") else stem
    candidates.append(os.path.join(USED_SIGNALS, stripped + "_used_signals.csv"))
    for c in candidates:
        if os.path.isfile(c):
            with open(c, "r") as f:
                return [ln.strip() for ln in f if ln.strip()]
    return []


PKL_ALIASES = {
    "core__mem_issue_unit_handpicked_signals": "core__mem_issue_unit_1.pkl",
    "core_glue": "core_glue_1.pkl",
}


def resolve_model_path(stem, spec):
    if spec.get("model_rel"):
        p = os.path.normpath(os.path.join(INVOKE_SH, spec["model_rel"]))
        if os.path.isfile(p) and p.endswith(".pkl"):
            return p
    for name in (
        PKL_ALIASES.get(stem),
        stem + "_1.pkl",
        stem + ".pkl",
    ):
        if not name:
            continue
        p = os.path.join(MODELS, name)
        if os.path.isfile(p):
            return p
    return None


def discover_blocks():
    pkls = sorted(
        os.path.join(MODELS, n)
        for n in os.listdir(MODELS)
        if n.endswith(".pkl")
    )
    shells = {}
    if os.path.isdir(INVOKE_SH):
        for n in os.listdir(INVOKE_SH):
            if n.endswith(".sh"):
                spec = parse_invoke_shell(os.path.join(INVOKE_SH, n))
                shells[os.path.splitext(n)[0]] = spec

    blocks = []
    used_pkls = set()
    for stem, spec in shells.items():
        model = resolve_model_path(stem, spec)
        if model is None:
            print("WARN: no pickle for shell", stem)
            continue
        model = os.path.normpath(model)
        if model in used_pkls:
            continue
        features = spec["features"]
        if not features:
            features = used_signals_for(os.path.splitext(os.path.basename(model))[0])
        blocks.append({
            "name": os.path.splitext(os.path.basename(model))[0],
            "model_path": model,
            "features": features,
            "test_csv": (
                os.path.normpath(os.path.join(INVOKE_SH, spec["test_rel"]))
                if spec.get("test_rel") else None
            ),
        })
        used_pkls.add(model)

    for p in pkls:
        p = os.path.normpath(p)
        if p in used_pkls:
            continue
        stem = os.path.splitext(os.path.basename(p))[0]
        blocks.append({
            "name": stem,
            "model_path": p,
            "features": used_signals_for(stem),
            "test_csv": None,
        })
    return blocks


def activity_schedule(n_cycles):
    """Piecewise activity in [0, 1]: idle, ramp, burst, second burst, idle."""
    a = np.zeros(n_cycles, dtype=float)
    t0 = int(n_cycles * 0.12)
    t1 = int(n_cycles * 0.20)
    t2 = int(n_cycles * 0.45)
    t3 = int(n_cycles * 0.55)
    t4 = int(n_cycles * 0.78)
    t5 = int(n_cycles * 0.88)
    if t1 > t0:
        a[t0:t1] = np.linspace(0.0, 1.0, t1 - t0)
    a[t1:t2] = 1.0
    a[t2:t3] = 0.25
    a[t3:t4] = 0.85
    if t5 > t4:
        a[t4:t5] = np.linspace(0.85, 0.0, t5 - t4)
    return a


def synthesize_features(features, activity, rng):
    n = len(activity)
    cols = {}
    for name in features:
        mx = max(int(feature_max_value(name)), 1)
        # Hamming-distance features scale with switching; control/value features
        # turn on with activity. Keep integer-valued like the original CSVs.
        if name.startswith(HD_PREFIXES):
            hi = np.maximum(np.round(mx * activity).astype(np.int32), 0)
            vals = np.array([rng.randint(0, int(h) + 1) for h in hi], dtype=np.int32)
        elif mx == 1:
            vals = (rng.rand(n) < activity).astype(np.int32)
        else:
            raw = rng.randint(0, mx + 1, size=n).astype(np.int32)
            vals = np.where(rng.rand(n) < activity, raw, 0).astype(np.int32)
        cols[name] = vals
    return pd.DataFrame(cols)


def tree_stats(model):
    tree = model.tree_
    values = tree.value[:, 0, 0]
    leaves = values[tree.children_left == -1]
    n_features = getattr(model, "n_features_", None)
    if n_features is None:
        n_features = getattr(model, "n_features_in_", None)
    return {
        "type": type(model).__name__,
        "n_features": int(n_features) if n_features is not None else None,
        "n_nodes": int(tree.node_count),
        "n_leaves": int(np.sum(tree.children_left == -1)),
        "max_depth": int(model.tree_.max_depth) if hasattr(model.tree_, "max_depth") else None,
        "leaf_min_mW": float(np.min(leaves)),
        "leaf_max_mW": float(np.max(leaves)),
        "leaf_mean_mW": float(np.mean(leaves)),
    }


def load_features_for_block(block, n_cycles, activity, rng, features_df=None):
    if features_df is not None:
        missing = [f for f in block["features"] if f not in features_df.columns]
        if missing:
            die("%s missing columns: %s" % (block["name"], missing[:5]))
        return features_df, "features_csv"
    test_csv = block.get("test_csv")
    if test_csv and os.path.isfile(test_csv):
        df = pd.read_csv(test_csv)
        missing = [f for f in block["features"] if f not in df.columns]
        if missing:
            die("%s missing columns: %s" % (test_csv, missing[:5]))
        return df, "input_csv"
    if not block["features"]:
        die("No feature list for %s" % block["name"])
    feat = synthesize_features(block["features"], activity, rng)
    feat.insert(0, "Cycle", np.arange(n_cycles))
    feat["Benchmark"] = "synthetic_activity"
    feat["Power_mW"] = 0.0
    return feat, "synthetic"


def write_pwl(path, time_s, current_a):
    with open(path, "w") as f:
        f.write("* LACPo-derived load current. VDD=%.2f V, Tclk=%.1f ns\n" % (VDD_V, TCLK_NS))
        f.write("* PWL(t, I) for SIMPLIS current source\n")
        for t, i in zip(time_s, current_a):
            f.write("%.12e %.12e\n" % (t, i))


def predict_blocks(blocks, features_df=None, n_cycles=N_CYCLES_DEFAULT, out_dir=TRACES, vdd=VDD_V, name="run"):
    rng = np.random.RandomState(RNG_SEED)
    activity = activity_schedule(n_cycles)
    if features_df is not None and "Cycle" in features_df.columns:
        n_cycles = int(len(features_df))
        activity = activity_schedule(n_cycles)
    os.makedirs(out_dir, exist_ok=True)

    metadata = []
    composed = np.zeros(n_cycles, dtype=float)
    per_block = {}
    n_real = 0
    source_used = "synthetic"

    for block in blocks:
        print("Loading", block["name"])
        model = joblib.load(block["model_path"])
        stats = tree_stats(model)
        df, source = load_features_for_block(block, n_cycles, activity, rng, features_df)
        source_used = source
        if source != "synthetic":
            n_real += 1
        feats = list(block["features"])
        if stats["n_features"] is not None and len(feats) != stats["n_features"]:
            print(
                "  WARN feature count %d vs model n_features_ %d"
                % (len(feats), stats["n_features"])
            )
            if len(feats) > stats["n_features"]:
                feats = feats[: stats["n_features"]]
            else:
                die("Not enough features for %s" % block["name"])
        X = df[feats].to_numpy(dtype=float)
        pred = model.predict(X)
        if composed.shape[0] != len(pred) and not per_block:
            n_cycles = len(pred)
            composed = np.zeros(n_cycles, dtype=float)
            activity = activity_schedule(n_cycles)
        pred = pred[:n_cycles]
        per_block[block["name"]] = pred
        composed += pred
        out_csv = os.path.join(out_dir, block["name"] + ".dt_pred.csv")
        cycles = df["Cycle"].to_numpy()[:n_cycles] if "Cycle" in df.columns else np.arange(n_cycles)
        pd.DataFrame({"Cycle": cycles, "Power_mW": pred}).to_csv(out_csv, index=False)
        stats.update({
            "name": block["name"],
            "model_path": block["model_path"],
            "n_invoke_features": len(block["features"]),
            "source": source,
            "pred_min_mW": float(np.min(pred)),
            "pred_max_mW": float(np.max(pred)),
            "pred_mean_mW": float(np.mean(pred)),
        })
        metadata.append(stats)
        print(
            "  leaves %d  leaf_range %.3f..%.3f mW  pred_mean %.3f mW  source=%s"
            % (stats["n_leaves"], stats["leaf_min_mW"], stats["leaf_max_mW"], stats["pred_mean_mW"], source)
        )

    time_ns = np.arange(n_cycles) * TCLK_NS
    time_s = time_ns * 1e-9
    i_a = (composed * 1e-3) / vdd
    composed_df = pd.DataFrame({
        "Cycle": np.arange(n_cycles),
        "time_ns": time_ns,
        "activity": activity[:n_cycles],
        "P_mW": composed,
        "I_A": i_a,
    })
    for bname, pred in per_block.items():
        composed_df[bname] = pred
    composed_path = os.path.join(out_dir, "composed_P_t.csv")
    composed_df.to_csv(composed_path, index=False)
    pwl_path = os.path.join(out_dir, "load_current.pwl")
    write_pwl(pwl_path, time_s, i_a)
    try:
        import sklearn
        sk_ver = sklearn.__version__
    except Exception:
        sk_ver = "?"
    meta = {
        "name": name,
        "sklearn": sk_ver,
        "python": sys.version.replace("\n", " "),
        "vdd_V": vdd,
        "tclk_ns": TCLK_NS,
        "n_cycles": n_cycles,
        "n_blocks": len(blocks),
        "source": source_used,
        "n_real_input_csvs": n_real,
        "composed_min_mW": float(np.min(composed)),
        "composed_max_mW": float(np.max(composed)),
        "composed_mean_mW": float(np.mean(composed)),
        "composed_max_A": float(np.max(i_a)),
        "blocks": metadata,
    }
    meta_path = os.path.join(out_dir, "model_stats.json")
    with open(meta_path, "w") as f:
        json.dump(meta, f, indent=2)
    print("--------------------------------------------------------------------------------")
    print("name:", name, "blocks:", len(blocks), "source:", source_used)
    print("composed P: min %.3f  mean %.3f  max %.3f mW" % (
        np.min(composed), np.mean(composed), np.max(composed)))
    print("composed I: max %.4f A  (VDD=%.2f V)" % (np.max(i_a), vdd))
    print("wrote", composed_path)
    print("wrote", pwl_path)
    return meta


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--n-cycles", type=int, default=N_CYCLES_DEFAULT)
    parser.add_argument("--vdd", type=float, default=VDD_V)
    parser.add_argument("--out", default=TRACES)
    parser.add_argument("--name", default="run")
    parser.add_argument("--features-csv", default=None, help="Wide feature CSV from vcd2features")
    parser.add_argument("--vcd", default=None, help="BOOM VCD; converted then predicted")
    parser.add_argument("--clock", default="TestDriver.testHarness.TestHarness.boom_tile.core.lsu.clock")
    args = parser.parse_args()

    try:
        import sklearn
        sk_ver = sklearn.__version__
    except Exception:
        sk_ver = "?"
    print("python:", sys.version.replace("\n", " "))
    print("sklearn:", sk_ver)
    if not sk_ver.startswith("0.20"):
        die("Need sklearn 0.20.x to load LACPo pickles, got %s" % sk_ver)
    if not os.path.isdir(MODELS):
        die("Missing %s" % MODELS)

    blocks = discover_blocks()
    if not blocks:
        die("No block models found")

    features_df = None
    if args.vcd:
        from vcd2features import vcd_to_features
        feats = []
        for b in blocks:
            feats.extend(b["features"])
        features_df, _ = vcd_to_features(args.vcd, feats, args.clock)
        os.makedirs(args.out, exist_ok=True)
        feat_path = os.path.join(args.out, args.name + ".features.csv")
        features_df.to_csv(feat_path, index=False)
        print("features", feat_path, "cycles", len(features_df))
    elif args.features_csv:
        features_df = pd.read_csv(args.features_csv)

    predict_blocks(
        blocks,
        features_df=features_df,
        n_cycles=args.n_cycles,
        out_dir=args.out,
        vdd=args.vdd,
        name=args.name,
    )
    if features_df is None:
        print("NOTE: no VCD/features-csv; P(t) is LACPo trees on synthetic activity.")


if __name__ == "__main__":
    main()
