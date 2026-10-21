/* The SNES's sound (docs/plan.md, step 3; the 2600's own sound state is sounds.c): the Terrific Audio
   Driver playing the effects tools/make_sound.py made from the remaster's orchestra, on the events the
   remaster hears (its music/events.py; the NES game's audio.s, hear_events): a match lit or going out,
   through a doorway, into a room, footsteps, up or down the stairs, picking things up and putting them
   down, urn pieces joining, a monster coming into the room, being caught, the lightning's thunder, and the
   two only the game knows - a bump, a locked door. The hearing is audio_events in src/fast.asm (in C it
   took 14 scanlines a frame). Everything here only reads the state. */
#include <snes.h>
#include "tad-audio.h"
#include "audio.h"
#include "state.h"
#include "engine.h"

#define THUNDER_GAP 90         /* frames: the lightning flickers, but one roll of thunder a strike */
#define NO_EFFECT 0xFF

/* What audio_events (src/fast.asm) works with: what the state was last frame (what's changed since is
   what's heard), its counters, and the effect it wants this frame. */
u8 was_matches;
u8 was_lit;
u8 was_floor;
u8 was_room;
u8 was_beyond;
u8 was_x;
u8 was_y;
u8 was_state;
u8 was_carried;
u8 was_group;
u8 was_here;
u8 was_flash;
u8 was_sound;
u8 walking;                    /* frames walked since the last footstep */
u8 since_thunder;              /* frames since the last roll of thunder (held at 255) */
u8 group_now;                  /* the biggest group of urn pieces this frame... */
u8 group_biggest;              /* ...and audio_events's working byte for it */
u8 audio_effect;               /* the effect wanted this frame, or NO_EFFECT */
void audio_events(void);

/* Start the driver: before the console's own set-up, with interrupts off (tad-audio.h); then the silent
   song, with the samples and effects, into sound memory before play begins (the driver plays effects only
   once a song is loaded). */
void set_up_audio(void)
{
    tad_init();
    tad_loadSong(SONG_BLANK);
    while (tad_isSongLoaded() == 0) {
        tad_process();
        tad_finishLoadingData();
    }
    was_state = SELECTING;     /* (nothing is heard until a game is under way) */
    walking = 0;
    since_thunder = THUNDER_GAP;
}

/* Each frame, once the game's frame is worked out: the effect for what's just happened, then the
   driver's turn (it sends the effect, or a piece of data, to the sound chip). */
void audio_frame(void)
{
    audio_events();
    if (audio_effect != NO_EFFECT) {
        tad_queueSoundEffect(audio_effect);
    }
    tad_process();
}
