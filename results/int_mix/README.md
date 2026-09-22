# Verilator MediumBoom — `int_mix`

HTIF kernel (`programs/int_mix.c`): 64-iter ALU + MUL + occasional DIV so the 2-wide INT IQ sees HIGH and LOW together. Same procedure as hello: `htif_nano.specs`, `tohost`, no pk, no UART.

```text
wsl -d Ubuntu -e bash sim/run_htif_int_mix.sh        # smoke, 200k cap
wsl -d Ubuntu -e bash sim/run_htif_int_mix_full.sh   # tohost + VCD (keep VCD off-git)
```

Sim binary: `D:\chipyard\sims\verilator\simulator-chipyard-MediumBoomConfig-debug`.

## 2026-09-22 run

**Did not execute.** This machine no longer has `D:\` (Windows has only `C:`). WSL `/mnt/d` is an empty stub (`cy-tmp/boom_real` and `libgloss-build` exist, no ELF, no `libgloss_htif.a`). `/mnt/d/chipyard` is missing, so there is no Verilator MediumBoom binary and no RISC-V gcc.

Re-run the scripts when that disk is mounted. Do not treat this page as a completed VCD.
