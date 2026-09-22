# RISC-V64 newlib/pk-style ELF for Chipyard/BOOM.
# Requires riscv64-unknown-elf-gcc (WSL: sudo apt install gcc-riscv64-unknown-elf).

CC   ?= riscv64-unknown-elf-gcc
ABI  ?= lp64d
ARCH ?= rv64imafdc
CFLAGS ?= -O2 -static -mcmodel=medany -march=$(ARCH) -mabi=$(ABI)

# hello.c is HTIF (tohost / htif_nano.specs). Build with sim/run_htif_hello.sh,
# not this pk-style rule — the generic recipe has no tohost and will hang on fesvr.
SRC  := idle.c load_step.c matmul.c branch_storm.c
BUILD ?= build
ELFS := $(patsubst %.c,$(BUILD)/%.riscv,$(SRC))

.PHONY: all clean
all: $(ELFS)

$(BUILD)/%.riscv: %.c | $(BUILD)
	$(CC) $(CFLAGS) $< -o $@

$(BUILD):
	mkdir -p $(BUILD)

clean:
	rm -rf $(BUILD)
