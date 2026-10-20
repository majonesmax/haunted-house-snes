; The loops this compiler's code can't afford every frame, in 65816 assembly (docs/decisions.md, "The
; hard parts"): placing a cast picture on the screen and putting its sprites into the sprite table,
; building the match's light's window rows, and checking whether the status band has anything new to
; show. Each takes its arguments in C variables (src/cast.c, src/light.c declare them), so there's
; no calling convention to get wrong; each keeps every register and flag it touches. The data bank is set
; to $7E, work RAM, where the C variables and the sprite table are; ROM tables are read with long
; addresses.
.include "hdr.asm"

.section ".fast_asm" superfree

; --- cast_place: a picture's sprites, from where the game has it --------------------------------------
; In: place_picture (a cast picture's number), place_x and place_y (its place on the floor, in units),
; place_height (how tall it stands on the floor, in lines), place_dx and place_dy (pixels to move it by,
; signed: 0 but for the hand with the match), place_mirrored, cast_view_bottom (the view's bottom line
; this frame). The picture's middle on the screen is 1.5 pixels a unit across from the view's left (8),
; and 2 a line up from the view's bottom; its top-left comes from its blocks (cast_wide, cast_high:
; tools/make_pictures.py). If any of it is within the view's lines (32 to 191), cast_put's arguments are
; filled and it goes on to cast_put; else nothing is drawn.
cast_place:
    php
    phb
    sep #$20
    lda #$7E
    pha
    plb
    rep #$30                 ; A, X, Y 16-bit
    lda.w place_picture
    and #$00FF
    tax                      ; X: the picture
    lda.w place_x            ; the middle across: 8 + 3 * (x + 4) / 2 + dx
    and #$00FF
    clc
    adc #4
    sta.w place_centre_x
    asl
    clc
    adc.w place_centre_x
    lsr
    clc
    adc #8
    sta.w place_centre_x
    lda.w place_dx
    and #$00FF               ; (a signed byte, as a signed 16-bit number)
    cmp #$0080
    bcc +
    ora #$FF00.w
+
    clc
    adc.w place_centre_x
    sta.w place_centre_x
    lda.w cast_view_bottom   ; the middle down: 32 + 2 * (80 - (y - bottom)) - height + dy
    and #$00FF
    sta.w place_centre_y
    lda.w place_y
    and #$00FF
    eor #$FFFF
    sec
    adc.w place_centre_y     ; bottom - y
    asl
    clc
    adc #192                 ; 32 + 2 * 80
    sta.w place_centre_y
    lda.w place_height
    and #$00FF
    eor #$FFFF
    sec
    adc.w place_centre_y     ; - height
    sta.w place_centre_y
    lda.w place_dy
    and #$00FF               ; (a signed byte, as a signed 16-bit number)
    cmp #$0080
    bcc +
    ora #$FF00.w
+
    clc
    adc.w place_centre_y
    sta.w place_centre_y
    lda.l cast_high,x        ; the top: the middle less half the blocks' height
    and #$00FF
    sta.w place_blocks_high
    asl
    asl
    asl
    sta.w place_half_height  ; blocks * 8
    lda.w place_centre_y
    sec
    sbc.w place_half_height
    sta.w place_top_line
    sec                      ; off below the view: top >= 192
    sbc #192
    bpl _place_off
    lda.w place_top_line     ; off above it: top + blocks * 16 <= 32
    clc
    adc.w place_half_height
    clc
    adc.w place_half_height
    sec
    sbc #33
    bmi _place_off
    lda.l cast_wide,x
    and #$00FF
    sta.w place_blocks_wide
    asl
    asl
    asl
    sta.w place_half_width   ; blocks * 8
    lda.w place_centre_x
    sec
    sbc.w place_half_width
    sep #$20
    sta.w place_left         ; (the low byte: a sprite never reaches past the screen's left edge)
    lda.w place_top_line
    sta.w place_top
    lda.w place_blocks_high
    sta.w place_high
    lda.w place_blocks_wide
    sta.w place_wide
    lda.l cast_palette,x     ; the attributes: the palette, priority 3 (above both layers)...
    asl
    ora #$30
    sta.w place_attr
    lda.w place_mirrored
    beq _place_tile
    lda.w place_attr
    ora #$40                 ; ...flipped across...
    sta.w place_attr
_place_tile:
    rep #$20
    txa
    asl
    tax                      ; X: the picture, for the table of 16-bit tile numbers
    lda.l cast_tile,x
    sep #$20
    sta.w place_tile         ; the low byte...
    xba
    and #$01                 ; ...and the ninth bit
    ora.w place_attr
    sta.w place_attr
    plb
    plp
    jmp cast_put             ; (its rtl returns to the C)
_place_off:
    plb
    plp
    rtl

; --- cast_put: a picture's 16 x 16 blocks into the sprite table, from entry cast_slot on ---------------
; In: place_left, place_top (the picture's top-left on the screen; already inside the picture, so only
; their low bytes matter), place_wide, place_high (its blocks across and down), place_tile (its first
; block's tile number: the low byte goes in the entry, the high bit is in place_attr already),
; place_attr (the entry's fourth byte: flips, priority, palette, the tile's ninth bit), place_mirrored
; (the right block's tile goes on the left when two wide). Out: cast_slot moved on past the entries used.
; A block's four tiles are two side by side on one row of 16 and two below, so the tile number goes up by
; 2 a block across and by 32 a block down.
cast_put:
    php
    phb
    sep #$20                 ; A 8-bit
    rep #$10                 ; X, Y 16-bit
    lda #$7E
    pha
    plb
    lda.w place_high
    sta.w put_rows_left
    lda.w place_top
    sta.w put_y
    lda.w place_tile           ; the first row's tile, low byte
    sta.w put_row_tile
_cast_put_row:
    lda.w place_wide
    sta.w put_blocks_left
    lda.w place_left
    sta.w put_x
    lda.w put_row_tile
    sta.w put_tile
    lda.w place_mirrored
    beq _cast_put_block
    lda.w place_wide           ; mirrored and two wide: the right block's tile first
    cmp #2
    bne _cast_put_block
    lda.w put_tile
    clc
    adc #2
    sta.w put_tile
_cast_put_block:
    rep #$20                 ; Y = cast_slot * 4: the entry's place in the table
    lda.w cast_slot
    and #$00FF
    asl
    asl
    tay
    sep #$20
    lda.w put_x
    sta.w oamMemory,y
    lda.w put_y
    sta.w oamMemory + 1,y
    lda.w put_tile
    sta.w oamMemory + 2,y
    lda.w place_attr
    sta.w oamMemory + 3,y
    inc.w cast_slot
    lda.w put_x
    clc
    adc #16
    sta.w put_x
    lda.w place_mirrored       ; the next block's tile: 2 on, or 2 back when mirrored
    beq _cast_put_next_tile_on
    lda.w put_tile
    sec
    sbc #2
    sta.w put_tile
    bra _cast_put_next_block
_cast_put_next_tile_on:
    lda.w put_tile
    clc
    adc #2
    sta.w put_tile
_cast_put_next_block:
    dec.w put_blocks_left
    bne _cast_put_block
    lda.w put_y
    clc
    adc #16
    sta.w put_y
    lda.w put_row_tile
    clc
    adc #32
    sta.w put_row_tile
    dec.w put_rows_left
    beq _cast_put_done
    brl _cast_put_row        ; (too far back for a short branch)
_cast_put_done:
    plb
    plp
    rtl

; --- light_rows: the light's window rows for this frame ----------------------------------------------
; In: light_centre_x (the eyes' middle on the screen), light_first_row, light_row_count (which rows of
; the two shapes, light_inner_shape and light_outer_shape - a half-width a row, $FF for no window - this
; frame's table takes). Out: the rows at light_table + 10, 5 bytes a row: the row's two lines, then
; window 1's left and right (the lit disc), window 2's (the dim ring round it); a row with no window is
; left 255, right 0 - nothing.
; With the eyes well inside the screen (the shapes reach 31 pixels either way) the edges can't fall off
; it, and the quick loop below does without the checks, a window's two edges in one 16-bit add (light.h
; says how the pair tables make that work); near an edge, the careful loop holds them in.
light_rows:
    php
    phb
    sep #$20
    rep #$10
    lda #$7E
    pha
    plb
    rep #$20
    lda.w light_first_row
    and #$00FF
    tax                      ; X: the shape row
    ldy #0                   ; Y: where in the rows
    sep #$20
    lda.w light_row_count
    sta.w light_rows_left
    lda.w light_centre_x
    sta.w light_centre_pair
    sta.w light_centre_pair + 1
    cmp #32
    bcc _light_careful
    cmp #224
    bcs _light_careful
    rep #$20
    txa
    asl                      ; the pairs are two bytes each
    tax
    sep #$20
_light_quick_row:
    lda #2                   ; the row's lines
    sta.w light_table + 10,y
    rep #$20                 ; A 16-bit: a window's two edges at once
    lda.l light_inner_pairs,x
    cmp #$FF00               ; no window on this row
    beq _light_quick_no_inner
    clc
    adc.w light_centre_pair  ; (the centre in both bytes: left = centre - w, right = centre + w)
    sta.w light_table + 11,y
    bra _light_quick_outer
_light_quick_no_inner:
    lda #$00FF               ; left 255, right 0
    sta.w light_table + 11,y
_light_quick_outer:
    lda.l light_outer_pairs,x
    clc
    adc.w light_centre_pair
    sta.w light_table + 13,y
    tya                      ; Y on by a row's five bytes
    clc
    adc #5
    tay
    sep #$20
    inx
    inx                      ; (the pairs are two bytes each)
    dec.w light_rows_left
    bne _light_quick_row
    plb
    plp
    rtl
_light_careful:
    lda #2                   ; the row's lines
    sta.w light_table + 10,y
    lda.l light_inner_shape,x
    jsr _light_window        ; (the two bytes at Y + 11)
    iny
    iny
    lda.l light_outer_shape,x
    jsr _light_window
    iny
    iny
    iny
    inx
    dec.w light_rows_left
    bne _light_careful
    plb
    plp
    rtl

; A = a shape row's half-width ($FF: no window): the window's left and right into the rows at Y, held
; within the screen.
_light_window:
    cmp #$FF
    beq _light_window_none
    sta.w light_half_width
    lda.w light_centre_x
    sec
    sbc.w light_half_width
    bcs _light_window_left_fits
    lda #0
_light_window_left_fits:
    sta.w light_table + 11,y
    lda.w light_centre_x
    clc
    adc.w light_half_width
    bcc _light_window_right_fits
    lda #255
_light_window_right_fits:
    sta.w light_table + 12,y
    rts
_light_window_none:
    lda #255
    sta.w light_table + 11,y
    lda #0
    sta.w light_table + 12,y
    rts

; --- status_key_changed: whether anything the status band above the view shows has changed ------------
; In: the game's state (game_ram, which starts at the 2600's $80: src/state.h's addresses less that). Out: status_changed is 1 if any of the
; eight bytes the band is worked out from - the matches used, the match's time left (or $FF with none
; lit), what's carried, the three urn shapes, the lives, the game number - differs from status_shown_key,
; which is brought up to date; 0 if none does.
status_key_changed:
    php
    phb
    sep #$30                 ; A, X, Y 8-bit
    lda #$7E
    pha
    plb
    stz.w status_changed
    ldx #0                   ; X counts the key's bytes
    lda.w game_ram + $82 - $80   ; MATCHES_USED
    jsr _key_byte
    lda.w game_ram + $8A - $80   ; FLAGS: bit 6, a match lit
    and #$40
    beq _key_no_match
    lda.w game_ram + $DF - $80   ; MATCH_TIME
    bra _key_match
_key_no_match:
    lda #$FF
_key_match:
    jsr _key_byte
    lda.w game_ram + $9A - $80   ; CARRIED
    jsr _key_byte
    lda.w game_ram + $9D - $80   ; URN_SHAPES, three
    jsr _key_byte
    lda.w game_ram + $9E - $80
    jsr _key_byte
    lda.w game_ram + $9F - $80
    jsr _key_byte
    lda.w game_ram + $96 - $80   ; LIVES
    jsr _key_byte
    lda.w game_ram + $CC - $80   ; GAME_NUMBER
    jsr _key_byte
    plb
    plp
    rtl

; One byte of the key, in A, against the X'th shown: kept, and the change noted, if it differs.
_key_byte:
    cmp.w status_shown_key,x
    beq _key_byte_same
    sta.w status_shown_key,x
    lda #1
    sta.w status_changed
_key_byte_same:
    inx
    rts

.ends
