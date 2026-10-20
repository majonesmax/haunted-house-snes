# The ROM, with PVSnesLib's rules (tools/build.py runs this with PVSNESLIB_HOME set to the fetched copy).
# SRCDIR is where the C is; the shareable build is the default, the faithful one takes FAITHFUL=1.
ifeq ($(strip $(PVSNESLIB_HOME)),)
$(error "PVSNESLIB_HOME is not set: run python tools/build.py, which sets it")
endif

export ROMNAME := haunted_house
export ROMTITLE := HAUNTED HOUSE
export SRCDIR := src
export FASTROM := 1       # the CPU at its full 3.58 MHz reading the ROM (FastROM), not 2.68 (SlowROM)

include $(PVSNESLIB_HOME)/devkitsnes/snes_rules

# The mansion's tables, generated into build/<kind>/ (tools/make_mansion.py); MANSION_DIR says which.
CFLAGS += -I$(MANSION_DIR)

.PHONY: all
all: $(OBJS) $(ROMNAME).sfc

clean: cleanBuildRes cleanRom
