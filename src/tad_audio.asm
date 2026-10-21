; The Terrific Audio Driver's 65816 side (tools/tad, fetched by tools/get_tools.py), brought in whole so
; it always matches the driver and the compiler. It wants LOROM defined; PVSnesLib's header doesn't.
.define LOROM 1
.include "tools/tad/audio-driver/pvsneslib-api/tad-audio.asm"

; Nothing after the include: it leaves the bank set to 0.
