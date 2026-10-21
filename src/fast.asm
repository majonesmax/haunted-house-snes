; The loops this compiler's code can't afford every frame, in 65816 assembly (docs/decisions.md, "The
; hard parts"): placing a cast picture on the screen and putting its sprites into the sprite table,
; building the match's light's window rows, checking whether the status band has anything new to show,
; and hearing what's just happened for the sound effects. Each takes its arguments in C variables (src/cast.c, src/light.c declare them), so there's
; no calling convention to get wrong; each keeps every register and flag it touches. The data bank is set
; to $7E, work RAM, where the C variables and the sprite table are; ROM tables are read with long
; addresses.
.include "hdr.asm"
.include "src/audio_ids.inc"     ; the effects' numbers (tools/make_sound.py)

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
; frame's table takes). Out: the rows at light_table + light_table_offset + 10, 5 bytes a row: the row's two lines, then
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
    ldy.w light_table_offset ; Y: the table being built (there are two), its rows from +10
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

; --- audio_events: the sound effect for what's just happened ------------------------------------------
; The remaster's music/events.py, as the NES game's audio.s hear_events: what's changed in the game's
; state since last frame - a match lit or out, the stairs, a doorway, a new room, footsteps, picking up
; and putting down, urn pieces joining, a monster coming in, being caught, the lightning's thunder, a
; bump, a locked door. In: the state (game_ram), lightning_flashing (src/light.c), and last frame's bytes
; (the was_ variables, src/audio.c). Out: audio_effect, the effect wanted (the driver plays one a frame,
; the lowest-numbered: tools/make_sound.py orders them), $FF for none; the was_ bytes brought up to date.
.define AT_MATCHES_USED $82 - $80   ; (the state's bytes: their 2600 addresses, src/state.h, less $80)
.define AT_FLAGS $8A - $80
.define AT_FLOOR $8D - $80
.define AT_MONSTERS_HERE $83 - $80
.define AT_SOUND $93 - $80
.define AT_ROOM_BEYOND $97 - $80
.define AT_GAME_STATE $99 - $80
.define AT_CARRIED $9A - $80
.define AT_ROOM $9C - $80
.define AT_URN_SHAPES $9D - $80
.define AT_MONSTER_FLOOR $A5 - $80
.define AT_POS_X $AA - $80
.define AT_POS_Y $B5 - $80
.define AT_MONSTER_ROOM $C5 - $80
.define AT_LAST_MONSTER $EA - $80
.define MATCH_LIT $40
.define NOTHING $FF
.define PLAYING $00
.define DYING $01
.define SELECTING $40
.define STARTING $02
.define SCEPTER 1
.define BAT 1
.define LAST_SHAPE 8
.define WHOLE_URN 3
.define STEP_EVERY 14               ; frames of walking between footsteps
.define THUNDER_GAP 90              ; frames: one roll of thunder a strike, though the lightning flickers
.define EFFECT_BLOCKED 2            ; the game's own sound byte: a locked door...
.define EFFECT_BUMP 3               ; ...a bump into a wall
audio_events:
    php
    phb
    sep #$30                 ; A, X, Y 8-bit
    lda #$7E
    pha
    plb
    lda #NOTHING
    sta.w audio_effect
    jsr _biggest_group
    sta.w group_now
    lda.w game_ram + AT_GAME_STATE
    cmp #SELECTING
    beq _audio_remember
    cmp #STARTING            ; (the frame after RESET: everything's changed, nothing's happened)
    beq _audio_remember
    lda.w was_state
    cmp #SELECTING
    beq _audio_remember
    jsr _hear_match
    jsr _hear_moving
    jsr _hear_carrying
    jsr _hear_urn
    jsr _hear_danger
    jsr _hear_game_sounds
_audio_remember:
    jsr _remember
    plb
    plp
    rtl

; A = an effect: wanted, if it's numbered lower than the one wanted so far.
_want:
    cmp.w audio_effect
    bcs _want_done
    sta.w audio_effect
_want_done:
    rts

_hear_match:
    lda.w game_ram + AT_MATCHES_USED
    cmp.w was_matches
    beq _match_not_lit
    lda #SFX_match_strike
    jmp _want
_match_not_lit:
    lda.w was_lit
    beq _match_done
    lda.w game_ram + AT_FLAGS
    and #MATCH_LIT
    bne _match_done
    lda #SFX_match_out
    jmp _want
_match_done:
    rts

; The stairs; else a doorway, a new room, and footsteps: one as walking starts, then one every
; STEP_EVERY frames of it.
_hear_moving:
    lda.w game_ram + AT_FLOOR
    cmp.w was_floor
    beq _same_floor
    stz.w walking
    bcc _went_down           ; (the floor's number is lower)
    lda #SFX_stairs_up
    jmp _want
_went_down:
    lda #SFX_stairs_down
    jmp _want
_same_floor:
    lda.w game_ram + AT_ROOM_BEYOND
    cmp #NOTHING
    beq _no_doorway
    lda.w was_beyond
    cmp #NOTHING
    bne _no_doorway
    lda #SFX_door_open
    jsr _want
_no_doorway:
    lda.w game_ram + AT_ROOM
    cmp.w was_room
    beq _steps
    lda #SFX_door_close
    jsr _want
_steps:
    lda.w game_ram + AT_GAME_STATE
    bne _standing
    lda.w game_ram + AT_POS_X
    cmp.w was_x
    bne _walking
    lda.w game_ram + AT_POS_Y
    cmp.w was_y
    beq _standing
_walking:
    inc.w walking
    lda.w walking
    cmp #1
    bne _step_counted
    lda #SFX_footstep
    jsr _want
_step_counted:
    lda.w walking
    cmp #STEP_EVERY
    bcc _moving_done
_standing:
    stz.w walking
_moving_done:
    rts

; Picked up: the key, the scepter or an urn piece; put down (not when it's taken from you).
_hear_carrying:
    lda.w game_ram + AT_CARRIED
    cmp.w was_carried
    beq _carrying_done
    cmp #NOTHING
    beq _put_down
    lda.w was_carried
    cmp #NOTHING
    bne _carrying_done
    lda.w game_ram + AT_CARRIED
    beq _picked_key          ; (the key is item 0)
    cmp #SCEPTER
    beq _picked_scepter
    lda #SFX_pickup_urn
    jmp _want
_picked_key:
    lda #SFX_pickup_key
    jmp _want
_picked_scepter:
    lda #SFX_pickup_scepter
    jmp _want
_put_down:
    lda.w game_ram + AT_GAME_STATE
    ora.w was_state
    bne _carrying_done
    lda #SFX_drop
    jmp _want
_carrying_done:
    rts

; Urn pieces joined: the biggest group grew to two pieces, or to the whole urn.
_hear_urn:
    lda.w group_now
    cmp.w was_group
    beq _urn_done
    bcc _urn_done
    cmp #2
    bcc _urn_done
    cmp #WHOLE_URN
    beq _urn_whole
    lda #SFX_urn_join
    jmp _want
_urn_whole:
    lda #SFX_urn_whole
    jmp _want
_urn_done:
    rts

; Out: A = how many pieces the biggest group of urn pieces has (0 when they're all apart).
_biggest_group:
    stz.w group_biggest
    ldy #2                   ; Y: the urn piece, 2 down to 0
_group_piece:
    lda.w game_ram + AT_URN_SHAPES,y
    cmp #(LAST_SHAPE + 1)
    bcs _group_next          ; (joined into another: $FF)
    tax
    lda.l _shape_pieces,x
    cmp.w group_biggest
    bcc _group_next
    sta.w group_biggest
_group_next:
    dey
    bpl _group_piece
    lda.w group_biggest
    rts
_shape_pieces:
    .db 0, 0, 1, 1, 1, 2, 2, 2, 3   ; an urn shape's pieces (shapes 2-8)

; Caught (the moment it happens); else a monster come into the room; and the lightning's thunder.
_hear_danger:
    lda.w game_ram + AT_GAME_STATE
    cmp #DYING
    bne _not_caught
    lda.w was_state
    cmp #DYING
    beq _not_caught          ; (dying since before: not the moment of being caught)
    lda #SFX_caught
    jsr _want
    bra _lightning
_not_caught:
    lda.w game_ram + AT_MONSTERS_HERE
    beq _lightning
    lda.w was_here
    bne _lightning
    jsr _monster_here
    jsr _want
_lightning:
    lda.w lightning_flashing
    beq _danger_done
    lda.w was_flash
    bne _danger_done
    lda.w since_thunder
    cmp #THUNDER_GAP
    bcc _danger_done
    stz.w since_thunder
    lda #SFX_thunder
    jmp _want
_danger_done:
    rts

; Out: A = the effect for the first monster in the room (or through its doorway): the ghost, the bat
; or a tarantula.
_monster_here:
    ldx #0                   ; X: the monster
_monster_next:
    lda.w game_ram + AT_MONSTER_FLOOR,x
    cmp.w game_ram + AT_FLOOR
    bne _monster_skip
    lda.w game_ram + AT_MONSTER_ROOM,x
    cmp.w game_ram + AT_ROOM
    beq _monster_found
    cmp.w game_ram + AT_ROOM_BEYOND
    beq _monster_found
_monster_skip:
    inx
    cpx.w game_ram + AT_LAST_MONSTER
    beq _monster_next
    bcc _monster_next
    lda #SFX_monster_tarantula
    rts
_monster_found:
    txa
    beq _monster_ghost       ; (the ghost is monster 0)
    cmp #BAT
    beq _monster_bat
    lda #SFX_monster_tarantula
    rts
_monster_ghost:
    lda #SFX_monster_ghost
    rts
_monster_bat:
    lda #SFX_monster_bat
    rts

; What only the game knows: a bump into a wall, a door that won't open.
_hear_game_sounds:
    lda.w game_ram + AT_SOUND
    cmp.w was_sound
    beq _game_sounds_done
    cmp #EFFECT_BUMP
    bne _not_bump
    lda #SFX_bump
    jmp _want
_not_bump:
    cmp #EFFECT_BLOCKED
    bne _game_sounds_done
    lda #SFX_locked
    jmp _want
_game_sounds_done:
    rts

; This frame's bytes, for next frame to compare with.
_remember:
    lda.w game_ram + AT_MATCHES_USED
    sta.w was_matches
    lda.w game_ram + AT_FLAGS
    and #MATCH_LIT
    sta.w was_lit
    lda.w game_ram + AT_FLOOR
    sta.w was_floor
    lda.w game_ram + AT_ROOM
    sta.w was_room
    lda.w game_ram + AT_ROOM_BEYOND
    sta.w was_beyond
    lda.w game_ram + AT_POS_X
    sta.w was_x
    lda.w game_ram + AT_POS_Y
    sta.w was_y
    lda.w game_ram + AT_GAME_STATE
    sta.w was_state
    lda.w game_ram + AT_CARRIED
    sta.w was_carried
    lda.w group_now
    sta.w was_group
    lda.w game_ram + AT_MONSTERS_HERE
    sta.w was_here
    lda.w lightning_flashing
    sta.w was_flash
    lda.w game_ram + AT_SOUND
    sta.w was_sound
    lda.w since_thunder
    cmp #$FF
    beq _remembered          ; (held at 255)
    inc.w since_thunder
_remembered:
    rts

.ends
