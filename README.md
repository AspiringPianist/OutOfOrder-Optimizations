This repository hosts scripts and setup for learning-based power modeling of CPUs (`BOOM/`, `RI5CY/`, `common/`) and the issue-queue current-shaping work on top of it.

# Goal

Associate a **power token** and an **energy token** with every RISC-V instruction *category* from the hardware units that category actually uses (IQ, FU, RF ports, cache/MSHR). Use those tokens at **issue**, on top of BOOM’s default port-conflict grant, so the scheduler packs high-energy / long-demand uops together and low-energy uops together.

The PDN then sees **current plateaus** instead of HIGH–LOW–HIGH chatter. First-droop decoupling C exists to supply VRM-slew mismatch; fewer `di/dt` edges means less C, not less average energy.

`I(t)` is lumped BoomTile equivalent current at 1.1 V (LACPo composed sum, including glue). Clock is 3 ns.

# Machine (do not silently change)

LACPo pickles and the built Verilator sim are **Chipyard 1.3.0 `MediumBoomConfig`** only:

| | MediumBoom (this repo) |
|---|---|
| Decode / ROB / int RF | 2 / 64 / 80 |
| INT IQ | 20 entries, issue 2 |
| MEM IQ | 12 entries, issue 1 |
| FP IQ | 16 entries, issue 1 |
| LDQ / STQ | 16 / 16 |
| I$ / D$ | 16 KiB 4-way, 2 MSHR |

A 4-wide / ROB-128 / 2-AGU / 512 KiB L2 picture is **MegaBoom-class**. ICPP08 Table 2 is an 8-wide Alpha SMT (ACE tags, not BOOM). Do not retarget Chisel to either until LACPo is retrained.

# Hardware categories → tokens

Every opcode in BOOM `decode.scala` maps to a class. Classes are the token grain because many uops issue in the same cycle; a per-dynamic-instruction joule is ill-posed.

Full opcode map: [`sim/isa_uop_map.csv`](sim/isa_uop_map.csv) (188 ops). Category rollup: [`sim/isa_hw_categories.csv`](sim/isa_hw_categories.csv). Code: [`tools/isa_hw_tokens.py`](tools/isa_hw_tokens.py), [`tools/dump_decode_map.py`](tools/dump_decode_map.py).

| Class | Token | Units used | Medium ports | Demand |
|---|---|---|---|---|
| INT_ALU | LOW | ALU + int RF | INT0, INT1 | 1 clk |
| INT_BR | LOW | ALU/BRU, BTB, gshare, RAS | INT0 (JAL); INT0/1 (BR) | 1 clk |
| SYS | LOW | fence serialize | — | long |
| INT_CSR | MID | CSR pipe | INT1 | 1 clk |
| MEM_LD | MID | AGU, LDQ, D$, MSHR | MEM0 | ~3 clk |
| MEM_ST | MID | AGU, STQ, D$ | MEM0 | 1 clk issue |
| FP_MOV | MID | IntToFP / FPToInt | INT0 or FP0 | ~2 clk |
| INT_MUL | HIGH | IMul | INT0 only | ~3 clk |
| INT_DIV | HIGH | IDiv | INT1 only | long |
| MEM_AMO | HIGH | AGU, LDQ, STQ, D$ | MEM0 | long |
| FP_ALU | HIGH | FPU + fp RF | FP0 | 4 clk |
| FP_FMA | HIGH | FPU 3R/1W | FP0 | 4 clk |
| FP_DIV | HIGH | FDiv/Sqrt | FP0 | long |

Token composition (concurrent issue is the model, not a bug):

```
I[n]  ≈  I0 + Σ_c  w_c · N_c[n]
E[n]  =  I[n] · 1.1 V · 3 ns
```

`N_c[n]` is how many class-`c` uops are issued or still in EX this cycle. `w_c` is the per-class **power token** (mA of extra tile current). The scheduler spends the **sum**. `E[n]` is the **energy token** for that cycle; a long-demand uop (DIV, FDIV, AMO) keeps charging `E` for every cycle it occupies the FU.

`w_c` values in the CSV are **relative priors**. Replace them by OLS of LACPo `I[n]` on occupancy. The hello VCD now gives a real `I[n]`; occupancy `N_c[n]` is the remaining fit input.

# Default grant, then current-class packing

Default BOOM (`IssueUnitCollapsing`, age-ordered): oldest ready slot whose `(fu_code & fu_types(port))` is nonzero takes the first free port. MediumBoom ports are not symmetric:

| Port | Can issue |
|---|---|
| INT0 | ALU, JMP, MUL, IntToFP |
| INT1 | ALU, CSR, DIV |
| MEM0 | load / store / AMO |
| FP0 | FPU, FMA, FDiv/Sqrt, FPToInt |

Packing keeps that legal-move generator and adds a current budget (Powering Superscalar Processors):

1. Grant HIGH next to HIGH (and long-demand next to long-demand: DIV / FDIV / AMO) so the PDN sees a high plateau.
2. Cap extra HIGH current per cycle (MediumBoom: typically one HIGH, not two stacked on the same edge).
3. Then grant LOW next to LOW for a low plateau.
4. MID (loads/stores) fill leftover ports; they are the AGU/D$ floor.

Do **not** mix a heavy with a light to “average” current. Averaging in the IQ is what creates the transients the capacitors absorb.

The ICPP08 VISA paper is the same *knob* (a decode tag that reorders grant) aimed at IQ AVF, not current. ACE ≠ HIGH.

# Layout

| Path | Role |
|---|---|
| `BOOM/` | LACPo pretrained DTs, PTPX, feature lists. See `BOOM/README.md`. |
| `RI5CY/` | In-order core power models. |
| `common/vcd2csv/` | VCD → cycle features. |
| `programs/` | `hello` (HTIF / `tohost`), plus `idle`, `load_step`, `matmul`, `branch_storm` (pk, no `tohost`). |
| `sim/` | WSL Verilator wrappers, HTIF hello scripts, signal list, ISA maps. |
| `tools/` | LACPo invoke, Verilator→LACPo VCD remap, HW-current decomp, I(t) PNG export. |
| `results/hello_vcd/` | Hello-run I(t) figures + per-block summary. |
| `slides/iq-current-support.html` | Advisor B&W deck. |

Sim binary: `D:\chipyard\sims\verilator\simulator-chipyard-MediumBoomConfig-debug`. sklearn 0.20 only (`.envs/py37` / `environment.yml`).

# Findings: hello VCD → hardware current

First **real** MediumBoom cycle-level current: HTIF `hello` (fesvr `printf` + `tohost`, **no pk**, **no UART**), full Verilator dump, 20 LACPo trees, then `I_u = P_u / 1.1 V`. This is lumped **BoomTile equivalent supply current**, not a probed VDD net. Glue is `P_parent − Σ P_child` (tile leftover after the child DTs). Clock is 3 ns. sklearn 0.20.4, all 20 trees `source=features_csv`.

Gallery + CSV: [`results/hello_vcd/`](results/hello_vcd/README.md). Full-rate tables and the 213 MB VCD stay local (`traces/hello_vcd/`, `D:\cy-tmp\boom_real\`).

## Tile

| | P | I | Energy |
|---|---:|---:|---:|
| Min | 68.9 mW | 62.6 mA | |
| Mean | **80.0 mW** | **72.7 mA** | **4141 nJ** |
| Peak | **161.3 mW** | **146.6 mA** | |
| Cycles | 17 262 | Tclk 3 ns | 51.8 µs |

Hello is idle/reset for ~30 µs, then a short burst. Peak is **2.0×** mean. That burst — not the 72.7 mA floor — is what first-droop C has to cover.

![BoomTile I(t)](results/hello_vcd/01_tile_I.png)

![BoomTile I(t), t ≥ 30 µs](results/hello_vcd/07_tile_I_active.png)

![BoomTile P(t)](results/hello_vcd/08_tile_P.png)

## Hardware groups

`I_group = Σ I_block` over the LACPo trees in that group.

| Group | Units | Mean (mA) | Peak (mA) | Share | Energy (nJ) |
|---|---|---:|---:|---:|---:|
| frontend | I$ / FTQ / BTB / gshare | 26.08 | 30.62 | **35.9%** | 1486 |
| INT EX | INT IQ, ALU0/1, int RF, CSR | 16.36 | **65.44** | 22.5% | 932 |
| glue | tile leftover | 9.89 | 18.76 | 13.6% | 563 |
| FP | FP IQ / FPU / FMA / FDiv | 8.07 | 19.37 | 11.1% | 460 |
| MEM | MEM IQ, LSU | 6.01 | 16.59 | 8.3% | 342 |
| rename / ROB | maptables, freelists, ROB | 5.98 | 26.66 | 8.2% | 341 |
| decode | decode0 + decode1 | 0.30 | 2.34 | 0.4% | 17 |

Frontend is the **floor** (almost flat, 26–31 mA). The **di/dt** is INT EX (peak 65 mA) plus rename/ROB (peak 27 mA) when hello actually runs. Decode is noise. FP is ~8 mA on a program with no FP — that is leakage / unmatched-feature floor, not FMA work.

![Groups stacked](results/hello_vcd/02_groups_stacked.png)

![Groups stacked, t ≥ 30 µs](results/hello_vcd/04_groups_stacked_active.png)

![Groups overlaid](results/hello_vcd/03_groups_lines.png)

![Groups overlaid, t ≥ 30 µs](results/hello_vcd/09_groups_lines_active.png)

![One I(t) panel per group](results/hello_vcd/10_groups_I_t.png)

![Groups, t ≥ 30 µs](results/hello_vcd/11_groups_I_t_active.png)

![Group mean vs peak](results/hello_vcd/06_groups_mean_peak.png)

## Per-block (20 LACPo trees)

| Units | Group | Token prior | Mean (mA) | Peak (mA) | Share |
|---|---|---|---:|---:|---:|
| gshare / BPD | frontend | LOW | 15.82 | 15.82 | 21.8% |
| tile glue | glue | LOW | 9.89 | 18.76 | 13.6% |
| FP IQ / FPU / FMA / FDiv | fp | HIGH | 8.07 | 19.37 | 11.1% |
| int RF | int_ex | LOW | 5.51 | **37.24** | 7.6% |
| BTB | frontend | LOW | 5.45 | 5.45 | 7.5% |
| I$ / FTQ / fetch | frontend | LOW | 4.80 | 9.35 | 6.6% |
| INT0 ALU / JMP / MUL | int_ex | LOW | 4.47 | 20.17 | 6.1% |
| AGU / LDQ / STQ / D$ | mem | MID | 4.06 | 4.06 | 5.6% |
| int RF read | int_ex | LOW | 2.68 | 5.04 | 3.7% |
| ROB | rename_rob | LOW | 2.49 | 7.96 | 3.4% |
| INT IQ | int_ex | LOW | 2.10 | 14.45 | 2.9% |
| MEM IQ | mem | MID | 1.96 | 12.54 | 2.7% |
| int maptable | rename_rob | LOW | 1.21 | 7.73 | 1.7% |
| fp maptable | rename_rob | MID | 1.15 | 7.17 | 1.6% |
| CSR file | int_ex | MID | 0.80 | 3.02 | 1.1% |
| INT1 ALU / CSR / DIV | int_ex | MID | 0.80 | 7.39 | 1.1% |
| int freelist | rename_rob | LOW | 0.78 | 3.70 | 1.1% |
| fp freelist | rename_rob | MID | 0.35 | 2.36 | 0.5% |
| decode1 | decode | LOW | 0.17 | 1.28 | 0.2% |
| decode0 | decode | LOW | 0.14 | 1.36 | 0.2% |

CSV: [`results/hello_vcd/hw_current_summary.csv`](results/hello_vcd/hw_current_summary.csv).

Peak movers on this run: **int RF (37 mA)**, INT0 ALU (20 mA), INT IQ (14 mA), MEM IQ (13 mA). Those are the hardware tags the issue queue can actually see. Mean current is dominated by **gshare (constant 15.8 mA)** + glue + a dead FP pipe — that is *not* a packing knob.

![Per-block I(t)](results/hello_vcd/12_blocks_I_t.png)

![Per-block I(t), t ≥ 30 µs](results/hello_vcd/13_blocks_I_t_active.png)

![Per-block mean vs peak](results/hello_vcd/05_blocks_mean_peak.png)

## What this means for tokens / C

- A per-dynamic-instruction joule is still ill-posed (2-wide INT + MEM + FP). Tokens stay **hardware-class × occupancy**: `I[n] ≈ I0 + Σ w_c N_c[n]`.
- **I0 ≈ 64–73 mA** on hello (frontend + glue + flat BPD/LSU/FP). The scheduler only spends the **delta**.
- The units that slew are INT RF / INT0 / INT IQ / rename — i.e. the LOW integer class firing together, not the HIGH FP/DIV priors. Hello does not excite MUL/DIV/FMA/AMO, so those `w_c` are still **unmeasured**.
- Packing HIGH-with-HIGH will not show up on this trace. The useful observation is already here: INT EX peak is **4×** its mean (16 → 65 mA). That is the `di/dt` first-droop C pays for. Plateau packing of integer issue is the first lever.
- 3 tags (LOW/MID/HIGH) are enough to *name* the budget. They are **not** yet enough to claim a C reduction — need `N_c[n]` from the IQ and a workload that actually issues HIGH.

## How the current was obtained

1. **HTIF, not UART.** `printf` goes to fesvr via `tohost`/`fromhost`. TestHarness UART stays null. `*** PASSED ***` prints only with `+verbose` (and that enables huge BOOM commit printf). Look for fesvr stdout + `sim_exit=0`.
2. **No pk on hello.** `pk` + `load_step` boots bbl (~millions of cycles) and was run without `+vcdfile` on purpose. Hello is linked with `htif_nano.specs` (`sim/run_htif_hello.sh`). A 200k-cycle cap is only a watchdog; hello already exits via `tohost` in ~8 s of sim.
3. **Full VCD** (`sim/run_htif_hello_full.sh`): 213 MB, 17 262 cycles, `+vcdfile` on the debug MediumBoom sim.
4. **Name remap** (`tools/vcd2features.py`): Verilator flattens `TOP.TestHarness.dut.system.boom_tile...`. LACPo was trained on `TestDriver.testHarness.TestHarness.boom_tile.core...`. Remap: prefix swap, `core.lsu` → `lsu`, `ALUExeUnit` → `jmp_unit`, `brinfo` → `brupdate`, unique leaf fallback. Clock → `...boom_tile.lsu.clock`. **204 / 326** nets matched; unmatched traces are **zero-filled**.
5. **Compose** (`tools/run_lacpo_flow.py --vcd`): 20 DTs → `composed_P_t.csv` + `load_current.pwl`.
6. **Decompose** (`tools/decompose_hw_current.py`): `I_u = P_u / 1.1`, 7 groups. **Export** (`tools/export_hw_current_plots.py`): PNGs `01`–`13`.

Unmatched on this dump (look constant — **do not treat as measured power**):

- gshare / BPD = 15.82 mA flat
- BTB = 5.45 mA flat
- LSU (AGU/LDQ/STQ/D$) = 4.06 mA flat

Those are missing BPD/LSU leaf nets in the flattened VCD, not a physical DC load.

## Reproduce

```text
wsl -d Ubuntu -e bash sim/run_htif_hello.sh
wsl -d Ubuntu -e bash sim/run_htif_hello_full.sh
python tools/run_lacpo_flow.py --vcd D:\cy-tmp\boom_real\hello.vcd
python tools/decompose_hw_current.py D:\cy-tmp\boom_real\lacpo_hello\composed_P_t.csv D:\cy-tmp\boom_real\lacpo_hello
python tools/export_hw_current_plots.py D:\cy-tmp\boom_real\lacpo_hello traces\hello_vcd
```

# Next steps

1. ~~Finish a real MediumBoom VCD.~~ HTIF hello + dump is in `results/hello_vcd/`.
2. ~~Map Verilator VCD names to LACPo.~~ `tools/vcd2features.py` remaps `boom_tile` (204/326).
3. **Count occupancy `N_c[n]`.** From IQ `uopc` / `fu_code` / grant (and EX occupancy for long-demand), bin into the 13 classes each cycle.
4. **Fit tokens.** OLS (or non-negative least squares) of LACPo `I[n]` on `[1, N_c[n]]` → `I0` and `w_c`. That is the power token. Energy token is `w_c · V · Tclk` per occupied cycle, times measured residency for DIV/FDIV/AMO.
5. **Software grant simulator.** Replay ready/uopc streams with (a) default age-order and (b) HIGH-budget plateau packing. Compare `di/dt`, plateau run length, and peak `I`. Do this before any Chisel IQ edit.
6. **Only then Chisel.** 2-bit LOW/MID/HIGH (or 13-class) tag at decode; grant loop keeps `fu_code` match and adds the HIGH knapsack. Still MediumBoom.
7. **PDN check.** Drive the packed vs default `I(t)` into the existing PWL / first-droop C estimate. Success is fewer edges and lower required C, not lower average P.
8. **Optional later:** MegaBoom rebuild + LACPo retrain if the 4-wide / 2-AGU figure becomes the target machine. Also rerun `pk load_step` / `matmul` / `branch_storm` for occupancies that hello does not excite.

Do not start IQ RTL, do not retarget `config-mixins.scala`, and do not treat prior `w_c` as measured, until step 4 lands.
