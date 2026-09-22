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

# Hello VCD → hardware current (landed)

Canonical path: HTIF `hello` ELF (fesvr `printf` + `tohost`, **no pk**, **no UART**), full Verilator dump, LACPo compose, then `I_u = P_u / 1.1`.

- 17 262 cycles · tile **72.7 mA mean / 146.6 mA peak / 4141 nJ**
- 204 / 326 LACPo nets remapped from flattened `TOP.TestHarness.dut.system.boom_tile...`
- 7 hardware groups, 20 LACPo blocks
- Hello activity after ~30 µs; peak is INT EX + rename. gshare/BPD and LSU leaves are **flat** (unmatched features, not true constant power)

Figures and the per-block table: [`results/hello_vcd/`](results/hello_vcd/README.md).

![BoomTile I(t), hello active window](results/hello_vcd/07_tile_I_active.png)

![Hardware-group I(t)](results/hello_vcd/10_groups_I_t.png)

![Per-block I(t)](results/hello_vcd/12_blocks_I_t.png)

![Per-block mean vs peak](results/hello_vcd/05_blocks_mean_peak.png)

Reproduce: `sim/run_htif_hello.sh` → `sim/run_htif_hello_full.sh` → `tools/run_lacpo_flow.py --vcd` → `tools/decompose_hw_current.py` → `tools/export_hw_current_plots.py`. Full-rate CSVs and the 213 MB VCD stay off-git (`traces/hello_vcd/`, `D:\cy-tmp\boom_real\`).

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
