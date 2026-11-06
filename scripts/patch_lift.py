#!/usr/bin/env python3
"""Post-lift source patches for A Crack in Time (re-run after every lift).

1. Guest setjmp/longjmp (Lua error handling: luaD_rawrunprotected at 0x50ACE4
   calls setjmp 0x90B738; luaD_throw at 0x50AE64 calls longjmp 0x90B85C).
   A static lift turns longjmp into "restore guest regs, return to caller",
   which falls through with r3=1 and dereferences garbage. Here the protected
   frame does a real host setjmp in its own C frame (registered on a
   per-thread stack keyed by the guest jmp_buf), and the lifted longjmp, after
   restoring guest registers exactly as before, host-longjmps to it. The
   target is always an ancestor frame on the same host stack, as on hardware.

2. GPU-idle wait in func_005CB6AC (0x5CB7D4): the title reads ctrl->get ONCE
   and spins until ctrl->put equals it (Insomniac's control struct is not
   volatile, so the compiler hoisted the get load out of "while (put != get)").
   On hardware the RSX has long consumed the last flush by then; our paced
   FIFO drain sometimes has not, and the snapshot never matches again. Re-read
   get inside the loop, which is what the source meant.

3. End-of-frame blit in func_005F4478: the title moves put past a return JUMP
   that lives in scratch memory and reuses the scratch at once, relying on the
   RSX having taken the JUMP (microseconds on hardware). Tell the runtime at
   both put writes so the FIFO walker catches up first (game/stubs.cpp
   racacit_gcm_put_moved has the full account).

11. Vector instructions whose destination is also a source (vcmpequh. v0,
   v1, v0): the lifted lane loop overwrote the source as it went. Rewritten
   by scripts/fix_vmx_alias.py to read a snapshot -- the cause of the
   striped textures (the texture streamer's vectorised id search failed).

Usage: scripts/patch_lift.py [game/src/recomp]
"""
import glob, os, re, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RECOMP = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "game", "src", "recomp")

DECLS = '''
/* racacit: guest setjmp/longjmp support (scripts/patch_lift.py) */
#include "ps3_setjmp.h"   /* non-unwinding on Windows (tools/ps3recomp/runtime/platform) */
typedef struct RacJbFrame { jmp_buf env; uint32_t guest_buf; struct RacJbFrame* prev; } RacJbFrame;
extern "C" void racacit_jb_push(RacJbFrame* f, uint32_t guest_buf);
extern "C" void racacit_jb_pop(RacJbFrame* f);
extern "C" void racacit_longjmp(uint32_t guest_buf);
'''


# Script (Lua C) functions traced by RACACIT_LUA_CTRACE; addresses from the
# title's registration table of (name, function descriptor) pairs at ~0xC8D000.
LUA_CTRACE = (
    ('func_0027A088', 'actor_speak'), ('func_00279FF8', 'actor_is_speaking'),
    ('func_0027A1B4', 'make_actor'), ('func_00279A08', 'actor_move'),
    ('func_002909E4', 'queue_scene'), ('func_00290C0C', 'queue_movie'),
    ('func_00290B78', 'queue_cinematic'), ('func_0029106C', 'on_next_cine_end'),
    ('func_00291AA8', 'on_elapsed'), ('func_00290DB8', 'unset_event'),
    ('func_00288B08', 'set_follow_cam'), ('func_00288490', 'activate_cam'),
    ('func_00281954', 'hero_lockout_control'), ('func_00282F80', 'hero_give_weapon'),
    ('func_00293064', 'has_valid_checkpoint'), ('func_002930A8', 'checkpoint'),
    ('func_0028B578', 'warp'), ('func_00279530', 'scene_show_subtitle'),
    ('func_002794CC', 'scene_hide_subtitle'), ('func_005084EC', 'print'),
    ('func_0051C670', 'stop_all_vo'), ('func_00521E2C', 'run_script'),
    ('func_00292D3C', 'add_mission'), ('func_00292F24', 'request_auto_save'),
    ('func_0026DE44', 'qwark_door_enable_break'), ('func_00521F74', 'screen_out'),
    ('func_0007DEE0', 'screen_out2'),
    # space: what makes a planet / moon landable, and the ship radio
    ('func_0026C8FC', 'space_enable_planet'), ('func_0026C9CC', 'space_enable_moon'),
    ('func_0026CB44', 'space_land_ship'), ('func_0026C280', 'space_unlock_level'),
    ('func_0026C7B4', 'space_set_planet_tag'), ('func_0026C858', 'space_set_moon_tag'),
    ('func_0026C76C', 'space_enable_takeoff'), ('func_0026C448', 'space_set_objective'),
    ('func_0026B7C4', 'space_show_radio'), ('func_0026BC04', 'space_set_radio_channel'),
    # the radio's chain (global space_radio.lua): each track's end starts the next
    ('func_00285D34', 'play_music'), ('func_00285CBC', 'stop_music'),
    ('func_00291624', 'on_audio_end'), ('func_0051D598', 'play_explicit_dialog_spec'),
    ('func_0051D6A0', 'play_explicit_sound_spec'), ('func_0051CB00', 'stop_vo'),
)


def func_span(src, name):
    m = re.search(r'void %s\(ppu_context\* ctx\) \{\n' % name, src)
    if not m:
        return None
    end = src.index('\n}\n', m.end())
    return m.start(), m.end(), end


def patch_file(path):
    src = open(path).read()
    changed = False

    # Each half is tested on its own function: the lifter may put the setjmp
    # caller and longjmp in different chunks.
    sp = func_span(src, 'func_0050ACE4')
    if sp and 'racacit_jb_push' not in src[sp[0]:sp[2]]:
        a, body, end = sp
        fn = src[a:end]
        call = 'ctx->lr = 0x0050AD20; func_0090B738(ctx); DRAIN_TRAMPOLINE(ctx);'
        assert call in fn, 'rawrunprotected setjmp call not found'
        fn = fn.replace('void func_0050ACE4(ppu_context* ctx) {\n',
                        'void func_0050ACE4(ppu_context* ctx) {\n        RacJbFrame _jbf;\n', 1)
        fn = fn.replace(call,
            'ctx->lr = 0x0050AD20;\n'
            '        racacit_jb_push(&_jbf, (uint32_t)ctx->gpr[3]);\n'
            '        if (setjmp(_jbf.env) == 0) { func_0090B738(ctx); DRAIN_TRAMPOLINE(ctx); }\n'
            '        else { g_trampoline_fn = 0; /* longjmp landed: guest regs restored, r3 = val */ }', 1)
        # pop the frame on the (only) normal exit
        tail = fn.rindex('        return;')
        fn = fn[:tail] + '        racacit_jb_pop(&_jbf);\n' + fn[tail:]
        src = src[:a] + fn + src[end:]
        changed = True

    sp = func_span(src, 'func_0090B85C')
    if sp and 'racacit_longjmp' not in src[sp[0]:sp[2]]:
        a, body, end = sp
        fn = src[a:end]
        fn = fn.replace('void func_0090B85C(ppu_context* ctx) {\n',
                        'void func_0090B85C(ppu_context* ctx) {\n        uint32_t _jb = (uint32_t)ctx->gpr[3];\n', 1)
        first_ret = fn.index('        return;')
        fn = fn[:first_ret] + '        racacit_longjmp(_jb);\n' + fn[first_ret:]
        src = src[:a] + fn + src[end:]
        changed = True

    sp = func_span(src, 'func_005CB6AC')
    if sp and '/* racacit: get re-read */' not in src:
        a, body, end = sp
        fn = src[a:end]
        old = ('        ctx->gpr[29] = vm_read32(ctx->gpr[12] + 0x4);\n'
               'loc_005CB7E4:\n')
        assert old in fn, 'GPU idle wait not found in func_005CB6AC'
        fn = fn.replace(old, 'loc_005CB7E4:\n'
                             '        ctx->gpr[29] = vm_read32(ctx->gpr[12] + 0x4);   /* racacit: get re-read */\n', 1)
        src = src[:a] + fn + src[end:]
        changed = True

    sp = func_span(src, 'func_0050AE64')
    if sp and 'racacit_lua_throw_hook' not in src:
        a, body, end = sp
        fn = src[a:end]
        fn = fn.replace('void func_0050AE64(ppu_context* ctx) {\n',
                        'void func_0050AE64(ppu_context* ctx) {\n        racacit_lua_throw_hook(ctx);   /* racacit: log Lua errors */\n', 1)
        src = src[:a] + fn + src[end:]
        if 'void racacit_lua_throw_hook' not in src:
            i = src.index('\n', src.index('#include')) + 1
            src = src[:i] + 'extern "C" void racacit_lua_throw_hook(ppu_context* ctx);\n' + src[i:]
        changed = True

    sp = func_span(src, 'func_000506E0')
    if sp and 'racacit_lua_exec_hook' not in src:
        a, body, end = sp
        fn = src[a:end]
        fn = fn.replace('void func_000506E0(ppu_context* ctx) {\n',
                        'void func_000506E0(ppu_context* ctx) {\n        racacit_lua_exec_hook(ctx);   /* racacit: log Lua execute() strings */\n', 1)
        src = src[:a] + fn + src[end:]
        i = src.index('\n', src.index('#include')) + 1
        src = src[:i] + 'extern "C" void racacit_lua_exec_hook(ppu_context* ctx);\n' + src[i:]
        changed = True

    # 12. Sound starts (game/stubs.cpp racacit_snd_play_hook): func_00578500 is
    #     the engine's play-a-sound-spec entry (33 call sites; the script
    #     bindings play_explicit_sound_spec / _dialog_spec reach it through
    #     func_004FB020 / func_004FB6FC); func_0057B4E8 is the virtual it ends
    #     in (vtable 0xC53208 + 0x20), which the lower sound-instance layer
    #     (0x94F39C) calls directly. Their callers and arguments say what is
    #     playing -- the DualSense speaker routing keys on them.
    for fname, tag in (('func_00578500', 0), ('func_0057B4E8', 1), ('func_006DE290', 2), ('func_0097A2F0', 3)):
        sp = func_span(src, fname)
        if sp and 'racacit_snd_play_hook' not in src[sp[0]:sp[2]]:
            a, body, end = sp
            fn = src[a:end]
            head = 'void %s(ppu_context* ctx) {\n' % fname
            assert fn.count(head) == 1, fname + ' head not found'
            fn = fn.replace(head, head + '        racacit_snd_play_hook(ctx, %d);   /* racacit: sound starts (DualSense routing) */\n' % tag, 1)
            src = src[:a] + fn + src[end:]
            if 'void racacit_snd_play_hook' not in src:
                i = src.index('\n', src.index('#include')) + 1
                src = src[:i] + 'extern "C" void racacit_snd_play_hook(ppu_context* ctx, int tag);\n' + src[i:]
            changed = True

    #     func_006DE290 starts one Insomniac sound instance (name at
    #     [[inst+0xC]]) through SCREAM's func_0097A2F0 (bank r3, sound r4);
    #     a routed sound is handed to the controller's player between the
    #     two, and racacit_snd_start_end clears that state on the way out.
    #     The instance's stops (racacit_snd_stop_hook, r3 = the instance):
    #     func_006DEA78 sets its stopping flag and stops its SCREAM sound,
    #     func_006DE258 stops it at once -- the controller's copy ends too.
    for fname, tag in (('func_006DEA78', 0), ('func_006DE258', 1)):
        sp = func_span(src, fname)
        if sp and 'racacit_snd_stop_hook' not in src[sp[0]:sp[2]]:
            a, body, end = sp
            fn = src[a:end]
            head = 'void %s(ppu_context* ctx) {\n' % fname
            assert fn.count(head) == 1, fname + ' head not found'
            fn = fn.replace(head, head + '        racacit_snd_stop_hook(ctx, %d);   /* racacit: sound stops (DualSense speaker) */\n' % tag, 1)
            src = src[:a] + fn + src[end:]
            if 'void racacit_snd_stop_hook' not in src:
                i = src.index('\n', src.index('#include')) + 1
                src = src[:i] + 'extern "C" void racacit_snd_stop_hook(ppu_context* ctx, int tag);\n' + src[i:]
            changed = True
    sp = func_span(src, 'func_006DE290')
    if sp and 'racacit_snd_start_end' not in src[sp[0]:sp[2]]:
        a, body, end = sp
        fn = src[a:end]
        assert fn.count('        return;') == 1, 'func_006DE290: expected exactly one return'
        tail = fn.rindex('        return;')
        fn = fn[:tail] + '        racacit_snd_start_end();\n' + fn[tail:]
        src = src[:a] + fn + src[end:]
        if 'void racacit_snd_start_end' not in src:
            i = src.index('\n', src.index('#include')) + 1
            src = src[:i] + 'extern "C" void racacit_snd_start_end(void);\n' + src[i:]
        changed = True

    # 4. Start skips movies (game/stubs.cpp): the movie-slot update's
    #    "still playing" result and every BinkOpen go through hooks.
    sp = func_span(src, 'func_006517BC')
    if sp and 'racacit_movie_update_hook' not in src[sp[0]:sp[2]]:
        a, body, end = sp
        fn = src[a:end]
        anchor = '        ctx->gpr[28] = ctx->gpr[3] + ctx->gpr[0];\n'
        assert anchor in fn, 'movie slot computation not found in func_006517BC'
        fn = fn.replace('void func_006517BC(ppu_context* ctx) {\n',
                        'void func_006517BC(ppu_context* ctx) {\n        uint32_t _rac_slot = 0;\n', 1)
        fn = fn.replace(anchor, anchor + '        _rac_slot = (uint32_t)ctx->gpr[28];   /* racacit: movie slot */\n', 1)
        tail = fn.rindex('        return;')
        fn = (fn[:tail] + '        ctx->gpr[3] = racacit_movie_update_hook(_rac_slot, (uint32_t)ctx->gpr[3]);\n'
              + fn[tail:])
        src = src[:a] + fn + src[end:]
        if 'uint32_t racacit_movie_update_hook' not in src:
            i = src.index('\n', src.index('#include')) + 1
            src = src[:i] + ('extern "C" uint32_t racacit_movie_update_hook(uint32_t slot, uint32_t playing);\n'
                             'extern "C" void racacit_bink_opened(uint32_t bink, uint32_t path_ea);\n') + src[i:]
        changed = True

    sp = func_span(src, 'func_00652E2C')
    if sp and 'racacit_bink_opened' not in src[sp[0]:sp[2]]:
        a, body, end = sp
        fn = src[a:end]
        n_calls = 0
        for lr in ('0x00652F8C', '0x00652FE4'):
            call = f'ctx->lr = {lr}; func_009A8D98(ctx); DRAIN_TRAMPOLINE(ctx);'
            assert call in fn, 'BinkOpen call not found in func_00652E2C'
            fn = fn.replace(call, '{ uint32_t _rac_path = (uint32_t)ctx->gpr[3]; ' + call +
                            ' racacit_bink_opened((uint32_t)ctx->gpr[3], _rac_path); }', 1)
            n_calls += 1
        src = src[:a] + fn + src[end:]
        if 'void racacit_bink_opened' not in src:
            i = src.index('\n', src.index('#include')) + 1
            src = src[:i] + ('extern "C" uint32_t racacit_movie_update_hook(uint32_t slot, uint32_t playing);\n'
                             'extern "C" void racacit_bink_opened(uint32_t bink, uint32_t path_ea);\n') + src[i:]
        changed = True

    # 5. Every cutscene skippable (game/stubs.cpp racacit_force_abort).
    for fname, kind in (('func_0004E7B8', 0), ('func_0004E598', 1), ('func_0004E6F0', 2)):
        sp = func_span(src, fname)
        if sp and 'racacit_force_abort' not in src[sp[0]:sp[2]]:
            a, body, end = sp
            fn = src[a:end]
            head = f'void {fname}(ppu_context* ctx) {{\n'
            fn = fn.replace(head, head + f'        racacit_force_abort((uint32_t)ctx->gpr[5], {kind});   /* racacit */\n', 1)
            src = src[:a] + fn + src[end:]
            if 'void racacit_force_abort' not in src:
                i = src.index('\n', src.index('#include')) + 1
                src = src[:i] + 'extern "C" void racacit_force_abort(uint32_t opts, int kind);\n' + src[i:]
            changed = True

    # 6. End-of-frame blit (game/stubs.cpp racacit_gcm_put_moved): the two
    #    ctrl->put writes at the tail of func_005F4478.
    sp = func_span(src, 'func_005F4478')
    if sp and 'racacit_gcm_put_moved' not in src[sp[0]:sp[2]]:
        a, body, end = sp
        fn = src[a:end]
        # put = end of the scratch packet; the title then waits for idle itself
        first = ('        vm_write32(ctx->gpr[28] + 0x0, ctx->gpr[7]);\n'
                 '        ctx->lr = 0x005F494C; func_0066177C(ctx); DRAIN_TRAMPOLINE(ctx);\n')
        # put = the other main buffer (the return JUMP's target); no wait follows
        second = ('        vm_write32(ctx->gpr[24] + 0x0, ctx->gpr[25]);\n'
                  '        vm_write32(ctx->gpr[23] + 0x0, ctx->gpr[21]);\n')
        assert fn.count(first) == 1, 'first put write not found in func_005F4478'
        assert fn.count(second) == 1, 'second put write not found in func_005F4478'
        l1, l2 = first.split('\n')[0] + '\n', first.split('\n')[1] + '\n'
        fn = fn.replace(first, l1 + '        racacit_gcm_put_moved(0);   /* racacit: wake the FIFO walker */\n' + l2, 1)
        s1, s2 = second.split('\n')[0] + '\n', second.split('\n')[1] + '\n'
        fn = fn.replace(second, s1 + '        racacit_gcm_put_moved(1);   /* racacit: RSX takes the return JUMP now */\n' + s2, 1)
        src = src[:a] + fn + src[end:]
        if 'void racacit_gcm_put_moved' not in src:
            i = src.index('\n', src.index('#include')) + 1
            src = src[:i] + 'extern "C" void racacit_gcm_put_moved(int wait);\n' + src[i:]
        changed = True

    # 7. Test hook RACACIT_START_LEVEL (game/stubs.cpp racacit_level_change):
    #    the level id argument of the level change func_0029A6D4.
    sp = func_span(src, 'func_0029A6D4')
    if sp and 'racacit_level_change' not in src[sp[0]:sp[2]]:
        a, body, end = sp
        fn = src[a:end]
        head = 'void func_0029A6D4(ppu_context* ctx) {\n'
        fn = fn.replace(head, head + '        ctx->gpr[3] = racacit_level_change((uint32_t)ctx->gpr[3]);   /* racacit */\n', 1)
        src = src[:a] + fn + src[end:]
        if 'uint32_t racacit_level_change' not in src:
            i = src.index('\n', src.index('#include')) + 1
            src = src[:i] + 'extern "C" uint32_t racacit_level_change(uint32_t level);\n' + src[i:]
        changed = True

    # 13. The game's GPU watchdog (func_005C56D4, its wait for a kick's end label): past
    #     2.5 s it prints "GPU sit and spin timeout", then, while the get pointer "is still
    #     moving", a line every 50 ms for 5 s, sleeping, on the main thread. A retail PS3's RSX
    #     never gets there; one 2.9 s hitch here cost a 12 s freeze and the boss music (owner,
    #     0.9.4). 20 s, as a real hang still has to get out: 0x5F2EDC00 ticks at 79.8 MHz.
    sp = func_span(src, 'func_005C56D4')
    if sp and '0xBE4 << 16' in src[sp[0]:sp[2]]:
        a_, body_, end_ = sp
        fn = src[a_:end_]
        fn = fn.replace('(uint32_t)0xBE4 << 16', '(uint32_t)0x5F2E << 16', 1).replace('ctx->gpr[8] | 0x20E0', 'ctx->gpr[8] | 0xDC00', 1)
        src = src[:a_] + fn + src[end_:]
        changed = True

    # 14. SCREAM's stream pause callback (game/stubs.cpp racacit_stream_pause_hook): the
    #     controller's dialogue lines hold with the game's streams.
    sp = func_span(src, 'func_0099BAE0')
    if sp and 'racacit_stream_pause_hook' not in src[sp[0]:sp[2]]:
        a_, body_, end_ = sp
        fn = src[a_:end_]
        head = 'void func_0099BAE0(ppu_context* ctx) {\n'
        fn = fn.replace(head, head + '        racacit_stream_pause_hook(ctx);   /* racacit */\n', 1)
        src = src[:a_] + fn + src[end_:]
        if 'void racacit_stream_pause_hook' not in src:
            i = src.index('\n', src.index('#include')) + 1
            src = src[:i] + 'extern "C" void racacit_stream_pause_hook(ppu_context* ctx);\n' + src[i:]
        changed = True

    # 8. Diagnostic RACACIT_LUA_CTRACE (game/stubs.cpp racacit_luac_trace): the
    #    entry of the script functions that drive scenes, speech and control.
    for fname, lname in LUA_CTRACE:
        sp = func_span(src, fname)
        if sp and 'racacit_luac_trace' not in src[sp[0]:sp[2]]:
            a, body, end = sp
            fn = src[a:end]
            head = f'void {fname}(ppu_context* ctx) {{\n'
            fn = fn.replace(head, head + f'        racacit_luac_trace(ctx, "{lname}");   /* racacit */\n', 1)
            src = src[:a] + fn + src[end:]
            if 'void racacit_luac_trace' not in src:
                i = src.index('\n', src.index('#include')) + 1
                src = src[:i] + 'extern "C" void racacit_luac_trace(ppu_context* ctx, const char* name);\n' + src[i:]
            changed = True

    # 9. Per-object shadow maps (game/stubs.cpp racacit_caster_box): refresh a
    #    caster's stale camera-space box (moby in r17) before func_005EE510
    #    fits its shadow map to it, at loc_005EE810.
    sp = func_span(src, 'func_005EE510')
    if sp and 'racacit_caster_box' not in src[sp[0]:sp[2]]:
        a, body, end = sp
        fn = src[a:end]
        lab = 'loc_005EE810:\n'
        assert fn.count(lab) == 1, 'loc_005EE810 not found in func_005EE510'
        fn = fn.replace(lab, lab + '        racacit_caster_box((uint32_t)ctx->gpr[17]);   /* racacit */\n', 1)
        src = src[:a] + fn + src[end:]
        if 'void racacit_caster_box' not in src:
            i = src.index('\n', src.index('#include')) + 1
            src = src[:i] + 'extern "C" void racacit_caster_box(uint32_t moby);\n' + src[i:]
        changed = True

    # 10. SPU kick on wait (runtime/spu/spu_coherency.c racacit_spu_kick): the
    #     game posts SPU jobs with plain stores, then waits on them -- the job
    #     handle wait func_00696C10 and the batch-counter wait func_00660F24
    #     (~9 round trips per view per frame in func_004E03A4). Waking the
    #     parked SPU lanes as the wait begins gets the job picked up at once
    #     instead of at the end of an idle lane's spu_lr_wait bound.
    #     func_005564D4 is the third wait: a spin on an async object's ready
    #     bit (halfword +0x18 < 0, objects from func_00929544's 0xA0-byte
    #     pool), 36% of the main thread at Galacton -- timed the same way
    #     (RACACIT_WAIT_STATS; callers 0x0067A81C, 0x00686FE8, 0x0092A618).
    for fname in ('func_00696C10', 'func_00660F24', 'func_005564D4'):
        sp = func_span(src, fname)
        if sp and 'racacit_wait_begin' not in src[sp[0]:sp[2]]:
            a, body, end = sp
            fn = src[a:end]
            head = f'void {fname}(ppu_context* ctx) {{\n'
            assert fn.count(head) == 1, f'{fname} head not found'
            assert fn.count('        return;') == 1, f'{fname}: expected exactly one return'
            fn = fn.replace(head, head + '        racacit_wait_begin(ctx);   /* racacit: wake parked SPUs, time the wait */\n', 1)
            tail = fn.rindex('        return;')
            fn = fn[:tail] + '        racacit_wait_end();\n' + fn[tail:]
            src = src[:a] + fn + src[end:]
            if 'void racacit_wait_begin' not in src:
                i = src.index('\n', src.index('#include')) + 1
                src = src[:i] + ('extern "C" void racacit_wait_begin(ppu_context* ctx);\n'
                                 'extern "C" void racacit_wait_end(void);\n') + src[i:]
            changed = True

    # 15. The game's per-title language list (func_0066CB18): a BCUS disc allows only
    #     English, French and Spanish and falls back to English, though it holds the
    #     full German, Italian and Dutch text and speech (RACACIT_LANGUAGE, game/stubs.cpp).
    sp = func_span(src, 'func_0066CB18')
    if sp and 'racacit: on the disc' not in src[sp[0]:sp[2]]:
        a_, body_, end_ = sp
        fn = src[a_:end_]
        read = 'ctx->gpr[10] = vm_read8(ctx->gpr[9] + 0x70);\n'
        fn = fn.replace(read, read + '        if ((uint32_t)ctx->gpr[11] - 4 <= 2) ctx->gpr[10] = 1;   /* racacit: on the disc */\n', 1)
        src = src[:a_] + fn + src[end_:]
        changed = True

    # 16. Ratchet's armor look (game/stubs.cpp racacit_armor_look): func_00170A88 builds
    #     the hero's part mask from the equipped skin, or with none from the armor level
    #     (player record +0x5BC; 1 Holoflux .. 4 Hyperflux). Its one read of the level
    #     goes through the setting; the damage taken stays the real armor's (hero
    #     +0x17F8, set with the armor by func_0016AFA0).
    sp = func_span(src, 'func_00170A88')
    if sp and 'racacit_armor_look' not in src[sp[0]:sp[2]]:
        a_, body_, end_ = sp
        fn = src[a_:end_]
        read = 'ctx->gpr[8] = vm_read32(ctx->gpr[12] + 0x5BC);\n'
        if fn.count(read) == 1:
            fn = fn.replace(read, 'ctx->gpr[8] = racacit_armor_look(vm_read32(ctx->gpr[12] + 0x5BC));   /* racacit */\n', 1)
            src = src[:a_] + fn + src[end_:]
            if 'uint32_t racacit_armor_look' not in src:
                i = src.index('\n', src.index('#include')) + 1
                src = src[:i] + 'extern "C" uint32_t racacit_armor_look(uint32_t armor);\n' + src[i:]
            changed = True

    # 17. The armor looks in the game's Extras > Skins menu (game/stubs.cpp): the skin
    #     list builder func_004A4258 marks the look as equipped (its skinSelected value,
    #     sp+0x80, set after the list's loop at loc_004A5258) and appends four entries
    #     after its own six arrays (after the last, skinValues); the EquipSkin command
    #     (func_004A2C9C, the value parsed by func_00906E28) turns an armor entry into
    #     the look and equips "None".
    sp = func_span(src, 'func_004A4258')
    if sp and 'racacit_skin_armor_rows' not in src[sp[0]:sp[2]]:
        a_, body_, end_ = sp
        fn = src[a_:end_]
        lab = '\nloc_004A5258:\n'
        last = '        ctx->lr = 0x004A538C; func_0095D90C(ctx); DRAIN_TRAMPOLINE(ctx);\n'
        if fn.count(lab) == 1 and fn.count(last) == 1:
            fn = fn.replace(lab, lab + '        racacit_skin_armor_selected(ctx);   /* racacit */\n', 1)
            fn = fn.replace(last, last + '        racacit_skin_armor_rows(ctx);   /* racacit */\n', 1)
            src = src[:a_] + fn + src[end_:]
            if 'void racacit_skin_armor_rows' not in src:
                i = src.index('\n', src.index('#include')) + 1
                src = src[:i] + ('extern "C" void racacit_skin_armor_selected(ppu_context* ctx);\n'
                                 'extern "C" void racacit_skin_armor_rows(ppu_context* ctx);\n') + src[i:]
            changed = True
    sp = func_span(src, 'func_004A2C9C')
    if sp and 'racacit_equip_skin' not in src[sp[0]:sp[2]]:
        a_, body_, end_ = sp
        fn = src[a_:end_]
        parse = '        ctx->lr = 0x004A2FF8; func_00906E28(ctx); DRAIN_TRAMPOLINE(ctx);\n'
        if fn.count(parse) == 1:
            fn = fn.replace(parse, parse + '        ctx->gpr[3] = racacit_equip_skin((uint32_t)ctx->gpr[3]);   /* racacit */\n', 1)
            src = src[:a_] + fn + src[end_:]
            if 'uint32_t racacit_equip_skin' not in src:
                i = src.index('\n', src.index('#include')) + 1
                src = src[:i] + 'extern "C" uint32_t racacit_equip_skin(uint32_t skin);\n' + src[i:]
            changed = True

    # 18. Field of view and camera distance (Settings > General > Camera; game/stubs.cpp),
    #     both on the follow camera (Ratchet's gameplay camera), so cutscenes and other
    #     cameras keep the game's own. Its target angle (+0x1D4) where its angle (+0x90)
    #     eases toward it (func_0003E874), and get_follow_cam_fov (func_0022CF28, after its
    #     call to func_0003E874 at 0x0022CFC8) handing the angle back to the scripts. (The
    #     view setups that copy the current camera's +0x90 into a view -- func_00201B54,
    #     func_00330D00, func_004AB824, func_004E5AC0 -- run once or never in play.)
    #     The follow camera's target distance
    #     (+0x1D0) where its distance (+0x1CC) eases toward it (func_00042558 inline,
    #     before func_006253BC at 0x000426D4, and func_0003E9F0); and get_follow_cam_dist
    #     (func_0022D1C0) reading +0x1CC back for the scripts.
    hooks18 = (
        ('func_0003E874', 'racacit_follow_fov',
         '        { uint32_t tmp = vm_read32(ctx->gpr[3] + 0x1D4); float ftmp; memcpy(&ftmp, &tmp, 4); ctx->fpr[13] = ftmp; }\n',
         '        ctx->fpr[13] = racacit_follow_fov(ctx->fpr[13]);   /* racacit */\n'),
        ('func_0022CF28', 'racacit_follow_fov_unscale',
         '        ctx->lr = 0x0022CFC8; func_0003E874(ctx); DRAIN_TRAMPOLINE(ctx);\n',
         '        ctx->fpr[1] = racacit_follow_fov_unscale(ctx->fpr[1]);   /* racacit */\n'),
        ('func_00042558', 'racacit_follow_dist',
         '        { uint32_t tmp = vm_read32(ctx->gpr[31] + 0x1D0); float ftmp; memcpy(&ftmp, &tmp, 4); ctx->fpr[2] = ftmp; }\n'
         '        { uint32_t tmp = vm_read32(ctx->gpr[31] + 0x1CC); float ftmp; memcpy(&ftmp, &tmp, 4); ctx->fpr[1] = ftmp; }\n',
         '        ctx->fpr[2] = racacit_follow_dist(ctx->fpr[2]);   /* racacit */\n'),
        ('func_0003E9F0', 'racacit_follow_dist',
         '        { uint32_t tmp = vm_read32(ctx->gpr[3] + 0x1D0); float ftmp; memcpy(&ftmp, &tmp, 4); ctx->fpr[2] = ftmp; }\n',
         '        ctx->fpr[2] = racacit_follow_dist(ctx->fpr[2]);   /* racacit */\n'),
        ('func_0022D1C0', 'racacit_follow_dist_unscale',
         '        { uint32_t tmp = vm_read32(ctx->gpr[3] + 0x1CC); float ftmp; memcpy(&ftmp, &tmp, 4); ctx->fpr[1] = ftmp; }\n',
         '        ctx->fpr[1] = racacit_follow_dist_unscale(ctx->fpr[1]);   /* racacit */\n'),
    )
    for name, hook, anchor, add in hooks18:
        sp = func_span(src, name)
        if not sp or hook + '(' in src[sp[0]:sp[2]]:
            continue
        a_, body_, end_ = sp
        fn = src[a_:end_]
        if fn.count(anchor) != 1:
            print('patch_lift #18: %s: anchor not found once (%d)' % (name, fn.count(anchor)))
            continue
        fn = fn.replace(anchor, anchor + add, 1)
        src = src[:a_] + fn + src[end_:]
        if 'double ' + hook + '(' not in src:
            i = src.index('\n', src.index('#include')) + 1
            decl = 'extern "C" double %s(double d);\n' % hook
            src = src[:i] + decl + src[i:]
        changed = True

    if (('racacit_jb_push(' in src or 'racacit_longjmp(' in src)
            and 'racacit: guest setjmp' not in src):
        # declarations after the first include
        i = src.index('\n', src.index('#include')) + 1
        src = src[:i] + DECLS + src[i:]
        changed = True
    if changed:
        open(path, 'w').write(src)
    return changed


n = 0
for p in sorted(glob.glob(os.path.join(RECOMP, 'ppu_recomp_*.cpp'))):
    if patch_file(p):
        print('patched', os.path.basename(p)); n += 1
print(f'{n} file(s) patched')

# 13. v42-v62 hooked the SCREAM synth (nextsynth, EBOOT 0xBFDC80: the lifts
#     sub_BFDC80_04000 and spu_0001_at_00BEDC00) to copy the controller's
#     sounds out of its mix. The controller has its own player now
#     (tools/ps3recomp/libs/audio/ds_player.c): an older patched lift has
#     those hook calls removed.
SPU_DIR = os.path.join(ROOT, 'game', 'spu')
for lift in ('sub_BFDC80_04000', 'spu_0001_at_00BEDC00'):
    p = os.path.join(SPU_DIR, lift, 'spu_recomp.c')
    if not os.path.exists(p):
        continue
    src = open(p, encoding='latin-1').read()
    out = [l for l in src.split('\n')
           if not re.search(r'\bracacit_syn_(voice|mix|mix4)_hook\b', l)]
    if len(out) != src.count('\n') + 1:
        open(p, 'w', encoding='latin-1', newline='').write('\n'.join(out))
        print('unpatched', lift)

# 11. Vector instructions whose destination is also a source read that source
#     from a snapshot (scripts/fix_vmx_alias.py has the account: a lifted
#     vcmpequh. kept A Crack in Time's texture streamer from ever switching in
#     high-resolution textures, and VRAM compaction then drew the striped ones).
#     The current ppu_lifter.py does this itself; on its output this is a no-op.
import subprocess
subprocess.run([sys.executable, os.path.join(ROOT, 'scripts', 'fix_vmx_alias.py'), RECOMP], check=False)

# Port BCES00511: every hook must have landed. Most patches above are guarded by
# "if sp and ..." and would otherwise skip in silence on a wrong address.
REQUIRED = '''racacit_jb_push racacit_longjmp racacit_lua_throw_hook racacit_lua_exec_hook
racacit_snd_play_hook racacit_snd_stop_hook racacit_snd_start_end racacit_movie_update_hook
racacit_bink_opened racacit_force_abort racacit_gcm_put_moved racacit_level_change
racacit_stream_pause_hook racacit_luac_trace racacit_caster_box racacit_wait_begin racacit_wait_end
racacit_armor_look racacit_skin_armor_rows racacit_skin_armor_selected racacit_equip_skin
racacit_follow_fov racacit_follow_fov_unscale racacit_follow_dist racacit_follow_dist_unscale'''.split()
REQUIRED += ['racacit: get re-read', 'racacit: on the disc']
_blob = ''.join(open(p, encoding='latin-1').read() for p in glob.glob(os.path.join(RECOMP, 'ppu_recomp_*.cpp')))
_missing = [r for r in REQUIRED if r not in _blob]
if _missing:
    sys.exit('patch_lift: hooks not applied: ' + ', '.join(_missing))
print('patch_lift: all %d hooks applied' % len(REQUIRED))
