# Future direction — Verilator `int_mix`

Not run yet. Planned HTIF kernel (`programs/int_mix.c`): 64-iter ALU + MUL + occasional DIV so the 2-wide INT IQ sees HIGH and LOW together. Same procedure as hello when we do it: `htif_nano.specs`, `tohost`, no pk, no UART.

```text
wsl -d Ubuntu -e bash sim/run_htif_int_mix.sh        # smoke, 200k cap
wsl -d Ubuntu -e bash sim/run_htif_int_mix_full.sh   # tohost + VCD (keep VCD off-git)
```

Sim binary: `D:\chipyard\sims\verilator\simulator-chipyard-MediumBoomConfig-debug`.
