/* The original's sound, as state (the spec, "Sound"; the remaster's game/sounds.py): which effect is
   playing and for how long, the mood noise's pitch and the thunder's rumbles. The SNES's own sound
   (docs/plan.md, step 3) plays from what happens; these bytes are kept because the game's rules read them -
   a bump never cuts an effect short, say - and the check compares them. */
#include "state.h"
#include "mansion.h"
#include "engine.h"

/* Start an effect ($F88C): the same one already playing isn't restarted, and a bump never cuts another
   effect short. */
void start_effect(u8 effect)
{
    if (effect == RAM(SOUND)) {
        return;
    }
    if (effect == EFFECT_BUMP && RAM(SOUND)) {
        return;
    }
    RAM(SOUND) = effect;
    RAM(SOUND_TIME) = sound_lengths[effect];
}

/* The mood noise's pitch walks up or down a step a frame; at every multiple of 16 it may turn, at random
   ($F773). */
static void wander_mood(void)
{
    u8 pitch = RAM(MOOD_PITCH);
    u8 at_a_turn = (pitch & 0x0F) == 0;
    if (pitch == MOOD_SILENT || (at_a_turn && (pitch == 0 || (pitch & 0x80)))) {
        RAM(MOOD_DIRECTION) = pitch;
    } else if (at_a_turn) {
        RAM(MOOD_DIRECTION) = random_bit(RAM(RANDOM_LOW));
    }
    RAM(MOOD_PITCH) = RAM(MOOD_DIRECTION) ? pitch - 1 : pitch + 1;
}

/* Dying: rumbles of random length with a silent frame between. (Winning's tune keeps no state.) */
static void thunder_or_tune(void)
{
    if (!(RAM(GAME_STATE) & DYING)) {
        return;
    }
    if (RAM(THUNDER) == 0) {
        RAM(THUNDER) = ((RAM(RANDOM_LOW) & 0x70) >> 2) + 0x10;
        return;
    }
    RAM(THUNDER) -= 1;
}

/* Channel 0: a monster in the room makes a noise that wanders, fading after it's gone. */
static void mood(void)
{
    if (RAM(GAME_STATE)) {
        thunder_or_tune();
        return;
    }
    if (!RAM(MONSTERS_HERE)) {
        if (RAM(MOOD_PITCH) == MOOD_SILENT) {
            return;
        }
        RAM(MOOD_DIRECTION) = 0;   /* nobody here: drift back up to silence */
    }
    wander_mood();
}

/* Channel 1: the effect's frames count down; at 0 it's over. */
static void effects(void)
{
    u8 time;
    if (RAM(GAME_STATE)) {
        return;
    }
    time = RAM(SOUND_TIME);
    if (time == 0) {
        RAM(SOUND) = 0;
        return;
    }
    RAM(SOUND_TIME) = time - 1;
}

void sound_frame(void)
{
    mood();
    effects();
}
