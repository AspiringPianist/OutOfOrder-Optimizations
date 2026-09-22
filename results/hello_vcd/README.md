# MediumBoom HTIF hello — hardware-current traces

Cycle-level BoomTile current from a real Verilator VCD (`hello.vcd`, 17 262 cycles, Tclk = 3 ns, VDD = 1.1 V). LACPo decision trees predict per-block power; `I = P / 1.1`. Unmatched nets (flat BPD / LSU leaves) are zero-filled, so those traces look constant.

| | Tile |
|---|---|
| Mean / peak | **72.7 / 146.6 mA** |
| Energy | **4141 nJ** |
| Nets matched | 204 / 326 LACPo features |

| Group | Mean (mA) | Peak (mA) | Share |
|---|---:|---:|---:|
| frontend | 26.08 | 30.62 | 35.9% |
| INT EX | 16.36 | 65.44 | 22.5% |
| glue | 9.89 | 18.76 | 13.6% |
| FP | 8.07 | 19.37 | 11.1% |
| MEM | 6.01 | 16.59 | 8.3% |
| rename / ROB | 5.98 | 26.66 | 8.2% |
| decode | 0.30 | 2.34 | 0.4% |

The hello burst sits after ~30 µs. INT EX + rename carry the peak; frontend is the floor.

## Figures

| File | What |
|---|---|
| [`01_tile_I.png`](01_tile_I.png) | Composed tile I(t) |
| [`07_tile_I_active.png`](07_tile_I_active.png) | Tile I(t), t ≥ 30 µs |
| [`08_tile_P.png`](08_tile_P.png) | Tile P(t) = I × 1.1 V |
| [`02_groups_stacked.png`](02_groups_stacked.png) | 7 groups stacked |
| [`04_groups_stacked_active.png`](04_groups_stacked_active.png) | Stacked, active window |
| [`03_groups_lines.png`](03_groups_lines.png) / [`09_groups_lines_active.png`](09_groups_lines_active.png) | Groups overlaid |
| [`10_groups_I_t.png`](10_groups_I_t.png) / [`11_groups_I_t_active.png`](11_groups_I_t_active.png) | One I(t) panel per group |
| [`12_blocks_I_t.png`](12_blocks_I_t.png) / [`13_blocks_I_t_active.png`](13_blocks_I_t_active.png) | One I(t) panel per LACPo block |
| [`05_blocks_mean_peak.png`](05_blocks_mean_peak.png) | 20-block mean vs peak |
| [`06_groups_mean_peak.png`](06_groups_mean_peak.png) | Group mean vs peak |

Per-block means: [`hw_current_summary.csv`](hw_current_summary.csv). Full-rate `hw_I_t.csv` / `composed_P_t.csv` / VCD stay local (`traces/hello_vcd/`, `D:\cy-tmp\boom_real\`) — they are too large for git.

## Reproduce

```text
# 1. HTIF hello + VCD (WSL, MediumBoom debug sim)
wsl -d Ubuntu -e bash /mnt/c/Users/unnat/Documents/DecouplingCap/sim/run_htif_hello.sh
wsl -d Ubuntu -e bash /mnt/c/Users/unnat/Documents/DecouplingCap/sim/run_htif_hello_full.sh

# 2. LACPo compose  (sklearn 0.20 / .envs/py37)
python tools/run_lacpo_flow.py --vcd D:\cy-tmp\boom_real\hello.vcd

# 3. Split P_u → I_u and write PNGs
python tools/decompose_hw_current.py D:\cy-tmp\boom_real\lacpo_hello\composed_P_t.csv D:\cy-tmp\boom_real\lacpo_hello
python tools/export_hw_current_plots.py D:\cy-tmp\boom_real\lacpo_hello traces\hello_vcd
```
