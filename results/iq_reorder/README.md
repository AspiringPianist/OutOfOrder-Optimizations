# How much of the issue queue can reorder

Part of the repo flow: [ISA → units](../../README.md#how-instructions-map-onto-hardware-and-how-current-is-modelled) → [hello VCD current](../../README.md#findings-hello-vcd--hardware-current) → **this page**. Also on the front page: [README — IQ reorder](../../README.md#how-much-of-the-issue-queue-can-reorder).

MediumBoom legal grant only (`fu_code` ∩ free port). Age-order vs PDN pack (prefer a legal set that holds last-cycle current). **The number that matters is the percentage of issue decisions that can legally change.** Current / power traces below are experimental token math, not a measurement.

## Reorder possible (%)

MEM IQ and FP IQ are 1-wide: **0%** — there is no second port to swap onto.

INT IQ is 2-wide (20 entries, issue 2). Only *ready* uops can move. Pack still only reaches the 3rd–4th oldest ready slot, not the tail of the 20.

**Share of ready INT windows where pack picks a different pair than age-order**


| Ready uops in INT IQ | hello-like (mostly ALU) | INT chatter (ALU+MUL+DIV) | HIGH-heavy | full mix |
| -------------------- | ----------------------- | ------------------------- | ---------- | -------- |
| 3                    | 23%                     | 43%                       | 37%        | 46%      |
| 6                    | 40%                     | **71%**                   | 72%        | **77%**  |
| 10                   | 51%                     | **76%**                   | 83%        | **82%**  |


**Share of packed INT grants that are not one of the two oldest ready uops** (slot ≥ 2): ~23% hello-like, **44%** chatter, 48% HIGH-heavy, 48% full mix — at 6 ready.

**Share of runtime cycles that actually issue a different set** (12k-cycle pipeline, same arrivals):


| Workload     | Cycles pack ≠ age-order |
| ------------ | ----------------------- |
| hello_like   | 14%b                    |
| int_chatter  | 20%                     |
| int_port_mix | **83%**                 |
| high_heavy   | 12%                     |


So: **about 70–80% of mixed INT ready windows can reorder**; a hello-like ALU window only **20–50%**; the physical 20-entry queue is not 70% mvable — only the ready head, a few slots deep. All-HIGH or all-LOW windows have almost no legal alternative.

Figures for the % vs ready depth: `01_reorder_vs_ready.png`, `02_legal_sets_vs_ready.png`.

## Experimental: token current (not a measurement)

These I(t) numbers use abstracted priors `I = I0 + Σ w_c · min(N_c, FU width)`, not LACPo and not a VCD. Treat them as a qualitative check that the reorder policy is aimed at plateaus, **not** as mA or % C saved.


| Scenario     | Σ|ΔI| vs age-order  | HF RMS | IPC |
| ------------ | ------------------- | ------ | --- |
| hello_like   | (experimental) −5%  | −0.5%  | 0%  |
| int_chatter  | (experimental) −8%  | −2%    | 0%  |
| int_port_mix | (experimental) −86% | −57%   | 0%  |
| high_heavy   | (experimental) −6%  | −3%    | 0%  |


Kept for the experiment log: `03_I_t_chatter.png`, `04_I_t_high_heavy.png`, `05_peak_and_edges.png`, `06_energy_ipc.png`, `pipeline_stats.csv`. Do not quote them as PDN savings.