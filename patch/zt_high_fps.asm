; Zero Tolerance - high frame rate patch (Rev A, the mouse hack ROM, Underground; see games.py)
;
; Addresses in comments are Rev A's; each game's are in games.py.
;
; 1. Fixed-rate logic. The original main loop runs game logic once per rendered
;    frame, so game speed scales with frame rate. This splits the loop:
;    - logic (input, movement, AI, timers) runs at a fixed tick (LOGIC_PERIOD vblanks)
;    - frames between ticks only re-render, with the camera interpolated between
;      the last two ticks' camera states (one tick of display latency)
; 2. Single-VBlank framebuffer DMA. The original uploads the 10,240-byte 3D
;    framebuffer in two halves on consecutive VBlanks (30 fps cap). This does it
;    in one, with the display blanked so the DMA can run past VBlank at full
;    speed. On NTSC that overruns ~14 lines into the next frame, so during
;    gameplay the top BAND_LINES lines are blanked on every frame (a line
;    interrupt re-enables the display) to keep the band from flickering.
;
; Assembled with vasm (vasmm68k_mot -Fbin -m68000) and placed at ORG in free ROM.
; Hooks into the original code are applied by make_patch.py.

; --- per game (make_patch.py passes these, from games.py) ---
; ORG_ADDR                          free ROM space for this code
; INPUT_A, INPUT_B                  per-tick input handlers (bsr'd from the main loop)
; LOGIC_CONT                        rest of the original logic block
; SUBMIT                            "frame ready" + vblank wait + sky scroll
; HORIZON                           rebuild floor/ceiling buffer if horizon changed
; RENDER                            3D view renderer (walls + objects)
; CELL_LOGIC                        floor-cell events (lifts, stairs, sounds), called by RENDER
; DIRTABLE                          angle (0..511) -> (cos, sin) words
; Z80_BUSREQ, Z80_BUSREL            sound driver handshake around DMA
; EXIT_TGT, DEATH_TGT               main loop exits (level exit, game over)
; VBL, FB_PENDING, FLASH, FLASH_MODE, CAM_X, CAM_Y, CAM_A, CAM_H, CAM_DX, CAM_DY, BOB, EXIT_FLAG, LIVES, FB
;                                   game variables (absolute; see games.py)
; ZT_VARS                           $40 bytes of RAM the game never uses, for ours
; MOUSE_TAIL                        (mouse hack ROM only) its VBlank end

VDP_CTRL        equ $C00004
VDP_DATA        equ $C00000
VDP_HV          equ $C00008

; game variables as a6 displacements (a6 = $FF8000)
A6              equ $FF8000
VBL_W           equ VBL-A6
CAM_X_W         equ CAM_X-A6
CAM_Y_W         equ CAM_Y-A6
CAM_A_W         equ CAM_A-A6
CAM_H_W         equ CAM_H-A6
CAM_DX_W        equ CAM_DX-A6
CAM_DY_W        equ CAM_DY-A6
BOB_W           equ BOB-A6
EXIT_FLAG_W     equ EXIT_FLAG-A6
LIVES_W         equ LIVES-A6
VBL_COUNT       equ VBL

; --- our variables (ZT_VARS, $40 bytes) ---
ZT_LAST         equ ZT_VARS+$00-A6      ; vblank count of the last logic tick
ZT_VALID        equ ZT_VARS+$02-A6      ; 0 = no camera history (level start)
ZT_PREV         equ ZT_VARS+$04-A6      ; x, y, a, h of tick n-1
ZT_CUR          equ ZT_VARS+$0C-A6      ; x, y, a, h of tick n
ZT_SAVE         equ ZT_VARS+$14-A6      ; real x, y, a, h, dx, dy while rendering
ZT_RA           equ ZT_VARS+$20-A6      ; angle used for the last render (sky scroll)
ZT_RONLY        equ ZT_VARS+$22-A6      ; nonzero while rendering a between-ticks frame
ZT_DISP         equ ZT_VARS+$24         ; game wants display on (mirrors hooked reg 1 writes)
ZT_BANDCNT      equ ZT_VARS+$26         ; vblanks of band mode left since the last framebuffer DMA
ZT_HPEND        equ ZT_VARS+$28         ; band end armed but not yet reached
ZT_NOBAND       equ ZT_VARS+$2A         ; vblanks to stay out of band mode after a missed line interrupt
ZT_IEON         equ ZT_VARS+$2C         ; line interrupt enabled by us
ZT_ARMVBL       equ ZT_VARS+$2E         ; vblank count when the band end was armed
ZT_INGAME       equ ZT_VARS+$30         ; main gameplay loop is running (band allowed)
ZT_HD           equ ZT_VARS+$32         ; set by an HD-renderer emulator: skip 68k rendering between ticks
BAND_LINES      equ 16              ; display re-enabled after this many lines
BAND_HOLD       equ 30
NOBAND_HOLD     equ 120

        ifnd LOGIC_PERIOD_NTSC
LOGIC_PERIOD_NTSC equ 6             ; 60 / 6 = 10 Hz (original runs ~7-11 fps in play)
        endif
        ifnd LOGIC_PERIOD_PAL
LOGIC_PERIOD_PAL  equ 5             ; 50 / 5 = 10 Hz
        endif
SNAP_POS        equ $200            ; position jump (per tick) treated as teleport
SNAP_ANG        equ 96              ; angle jump (per tick) treated as teleport

        org ORG_ADDR

; Entry points at fixed offsets (make_patch.py jumps here)
        bra.w   ZT_Decide               ; +0
        bra.w   ZT_LogicRender          ; +4
        bra.w   ZT_InitRender           ; +8
        bra.w   ZT_SkyAngle             ; +12
        bra.w   ZT_Cell                 ; +16
        bra.w   ZT_VBlankTail           ; +20
        bra.w   ZT_HInt                 ; +24
        bra.w   ZT_DispOn               ; +28
        bra.w   ZT_DispOff              ; +32
        bra.w   ZT_QueueDmaOn           ; +36
        bra.w   ZT_QueueDmaOff          ; +40
        bra.w   ZT_ExitCheck            ; +44
        bra.w   ZT_DeathExit            ; +48
        dc.l    ZT_AfterRender          ; +52 (data) end of the logic-tick render, for emulator hooks
        dc.l    ZT_AfterInitRender      ; +56 (data) end of the level-start render (shown while the screen fades in)
        dc.b    "ZTHD"                  ; +60 (data) marks this table for emulators
        dc.w    GAME_ID                 ; +64 which game (games.py)
        dc.w    0                       ; +66
        dc.l    ZT_VARS                 ; +68 our variables

; ---------------------------------------------------------------------------
; Hook at $162C (replaces "bsr $79A; bsr $D36"): run logic or render-only.
; ---------------------------------------------------------------------------
ZT_Decide:
        move.w  #1,ZT_INGAME
        bsr     ZT_Period               ; d1 = period
        move.w  VBL_W(a6),d0
        sub.w   ZT_LAST(a6),d0          ; d0 = vblanks since last tick
        tst.w   ZT_VALID(a6)
        beq   .resync
        cmp.w   d1,d0
        bcs   ZT_RenderOnly           ; tick not due yet
        add.w   d1,d1
        cmp.w   d1,d0
        bcc   .resync                 ; >= 2 periods behind: don't catch up
        lsr.w   #1,d1
        add.w   d1,ZT_LAST(a6)
        bra   .logic
.resync:
        move.w  VBL_W(a6),ZT_LAST(a6)
.logic:
        jsr     INPUT_A
        jsr     INPUT_B
        jmp     LOGIC_CONT

ZT_RenderOnly:
        tst.w   ZT_HD
        beq   .draw
        move.w  VBL_W(a6),d0              ; HD emulator draws the in-between frames itself:
.hdw:   cmp.w   VBL_W(a6),d0              ; just wait for the next vblank and decide again
        beq   .hdw
        bra     ZT_Decide
.draw:
        movem.l d0-d7/a0-a5,-(sp)
        bsr     ZT_Apply
        jsr     HORIZON
        move.w  #1,ZT_RONLY(a6)
        jsr     RENDER
        clr.w   ZT_RONLY(a6)
        bsr     ZT_Restore
        movem.l (sp)+,d0-d7/a0-a5
        jmp     SUBMIT

; ---------------------------------------------------------------------------
; Hook at $16CE (replaces "jsr RENDER" in the logic block): record this tick's
; camera (after wobble), then render the interpolated camera.
; ---------------------------------------------------------------------------
ZT_LogicRender:
        clr.w   ZT_RONLY(a6)            ; a tick render is never a between-ticks one
        movem.l d0-d7/a0-a5,-(sp)
        lea     ZT_PREV(a6),a0
        lea     ZT_CUR(a6),a1
        move.l  (a1),(a0)               ; prev = cur
        move.l  4(a1),4(a0)
        move.w  CAM_X_W(a6),(a1)          ; cur = camera now
        move.w  CAM_Y_W(a6),2(a1)
        move.w  CAM_A_W(a6),4(a1)
        move.w  CAM_H_W(a6),6(a1)
        tst.w   ZT_VALID(a6)
        beq   .snap
        move.w  (a1),d0                 ; teleport checks
        sub.w   (a0),d0
        bsr     ZT_WrapPos
        bsr     ZT_Abs
        cmp.w   #SNAP_POS,d0
        bcc   .snap
        move.w  2(a1),d0
        sub.w   2(a0),d0
        bsr     ZT_WrapPos
        bsr     ZT_Abs
        cmp.w   #SNAP_POS,d0
        bcc   .snap
        move.w  4(a1),d0
        sub.w   4(a0),d0
        bsr     ZT_WrapAng
        bsr     ZT_Abs
        cmp.w   #SNAP_ANG,d0
        bcs   .go
.snap:
        move.l  (a1),(a0)
        move.l  4(a1),4(a0)
        move.w  #1,ZT_VALID(a6)
.go:
        bsr     ZT_Apply
        jsr     HORIZON
        jsr     RENDER
ZT_AfterRender:
        bsr     ZT_Restore
        movem.l (sp)+,d0-d7/a0-a5
        rts

; ---------------------------------------------------------------------------
; Hook at $13F6 / $1964 (level start / respawn "jsr RENDER"): drop history.
; ---------------------------------------------------------------------------
ZT_InitRender:
        clr.w   ZT_VALID(a6)
        clr.w   ZT_RONLY(a6)            ; a full render (a stale flag would hide it from emulator hooks)
        move.w  CAM_A_W(a6),ZT_RA(a6)
        jsr     RENDER
ZT_AfterInitRender:
        rts

; ---------------------------------------------------------------------------
; Hook at $BAE6 inside RENDER (replaces "bsr CELL_LOGIC; move.w BOB(a6),d0"):
; floor-cell game logic only runs on logic ticks.
; ---------------------------------------------------------------------------
ZT_Cell:
        tst.w   ZT_RONLY(a6)
        bne   .skip
        jsr     CELL_LOGIC
.skip:  move.w  BOB_W(a6),d0
        rts

; ---------------------------------------------------------------------------
; Hook at $1470 (replaces "move.w CAM_A(a6),d2; neg.w d2"): sky scroll angle.
; ---------------------------------------------------------------------------
ZT_SkyAngle:
        move.w  ZT_RA(a6),d2
        tst.w   ZT_VALID(a6)
        bne   .ok
        move.w  CAM_A_W(a6),d2
.ok:    neg.w   d2
        rts

; ---------------------------------------------------------------------------
; Save the real camera and replace it with lerp(prev, cur, t / period).
; ---------------------------------------------------------------------------
ZT_Apply:
        lea     ZT_SAVE(a6),a2
        move.w  CAM_X_W(a6),(a2)+
        move.w  CAM_Y_W(a6),(a2)+
        move.w  CAM_A_W(a6),(a2)+
        move.w  CAM_H_W(a6),(a2)+
        move.w  CAM_DX_W(a6),(a2)+
        move.w  CAM_DY_W(a6),(a2)+
        bsr     ZT_Period               ; d1 = period
        move.w  VBL_W(a6),d2
        sub.w   ZT_LAST(a6),d2          ; d2 = t
        bpl   .t1
        moveq   #0,d2
.t1:    cmp.w   d1,d2
        bls   .t2
        move.w  d1,d2
.t2:    lea     ZT_PREV(a6),a0
        lea     ZT_CUR(a6),a1
        ; x
        move.w  (a1),d0
        sub.w   (a0),d0
        bsr     ZT_WrapPos
        bsr     ZT_Scale
        add.w   (a0),d0
        and.w   #$1FFF,d0
        move.w  d0,CAM_X_W(a6)
        ; y
        move.w  2(a1),d0
        sub.w   2(a0),d0
        bsr     ZT_WrapPos
        bsr     ZT_Scale
        add.w   2(a0),d0
        and.w   #$1FFF,d0
        move.w  d0,CAM_Y_W(a6)
        ; angle + direction vector
        move.w  4(a1),d0
        sub.w   4(a0),d0
        bsr     ZT_WrapAng
        bsr     ZT_Scale
        add.w   4(a0),d0
        and.w   #$1FF,d0
        move.w  d0,CAM_A_W(a6)
        move.w  d0,ZT_RA(a6)
        lea     DIRTABLE,a3
        add.w   d0,d0
        add.w   d0,d0
        move.w  (a3,d0.w),CAM_DX_W(a6)
        move.w  2(a3,d0.w),CAM_DY_W(a6)
        ; horizon
        move.w  6(a1),d0
        sub.w   6(a0),d0
        bsr     ZT_Scale
        add.w   6(a0),d0
        move.w  d0,CAM_H_W(a6)
        rts

ZT_Restore:
        lea     ZT_SAVE(a6),a2
        move.w  (a2)+,CAM_X_W(a6)
        move.w  (a2)+,CAM_Y_W(a6)
        move.w  (a2)+,CAM_A_W(a6)
        move.w  (a2)+,CAM_H_W(a6)
        move.w  (a2)+,CAM_DX_W(a6)
        move.w  (a2)+,CAM_DY_W(a6)
        rts

; d0 = d0 * d2 / d1 (signed d0, 0 <= d2 <= d1)
ZT_Scale:
        muls    d2,d0
        divs    d1,d0
        rts

; d0 -> signed delta in [-$1000, $1000) for positions wrapping at $2000
ZT_WrapPos:
        add.w   #$1000,d0
        and.w   #$1FFF,d0
        sub.w   #$1000,d0
        rts

; d0 -> signed delta in [-256, 256) for angles wrapping at 512
ZT_WrapAng:
        add.w   #$100,d0
        and.w   #$1FF,d0
        sub.w   #$100,d0
        rts

ZT_Abs:
        tst.w   d0
        bpl   .p
        neg.w   d0
.p:     rts

; d1 = logic period in vblanks (PAL consoles report bit 6 of the version port)
ZT_Period:
        moveq   #LOGIC_PERIOD_NTSC,d1
        btst    #6,$A10001
        beq   .n
        moveq   #LOGIC_PERIOD_PAL,d1
.n:     rts

; ---------------------------------------------------------------------------
; VBlank, jumped to from $AC2 after the original counters.
; ---------------------------------------------------------------------------
ZT_VBlankTail:
        movem.l d0/a0,-(sp)
        lea     VDP_CTRL,a0
        tst.w   ZT_HPEND                ; band end never arrived last frame?
        beq   .hok
        clr.w   ZT_HPEND
        move.w  VBL_COUNT,d0
        sub.w   ZT_ARMVBL,d0
        subq.w  #1,d0
        bne   .hok                    ; VBlank was blocked too (loading): not a miss
        move.w  #NOBAND_HOLD,ZT_NOBAND  ; line interrupt masked: don't rely on it for a while
.hok:   tst.w   ZT_NOBAND
        beq   .nb
        subq.w  #1,ZT_NOBAND
        clr.w   ZT_BANDCNT
.nb:    tst.w   FB_PENDING
        beq   .nodma
        tst.w   ZT_HD
        bne.w   ZT_SplitDma
        move.w  #$8134,(a0)             ; display off, DMA on
        clr.w   FB_PENDING
        jsr     Z80_BUSREQ
        move.w  #$9300,(a0)             ; 2 x $A00 words: FB -> VRAM $0020
        move.w  #$940A,(a0)
        move.w  #$9500+((FB>>1)&$FF),(a0)
        move.w  #$9600+((FB>>9)&$FF),(a0)
        move.w  #$9700+((FB>>17)&$7F),(a0)
        move.w  #$4020,(a0)
        move.w  #$0080,(a0)
        move.w  #$9300,(a0)             ;                  FB+$1400 -> VRAM $1420
        move.w  #$940A,(a0)
        move.w  #$9500+(((FB+$1400)>>1)&$FF),(a0)
        move.w  #$9600+(((FB+$1400)>>9)&$FF),(a0)
        move.w  #$9700+(((FB+$1400)>>17)&$7F),(a0)
        move.w  #$5420,(a0)
        move.w  #$0080,(a0)
        jsr     Z80_BUSREL
        bsr.w   ZT_Flash
        move.w  #BAND_HOLD,ZT_BANDCNT
        bsr.w   ZT_BandOK
        beq   .plain
        move.w  #$8124,(a0)             ; stay blank until the line interrupt
        bsr.w   ZT_Arm
        bra   .done
.plain: move.w  #$8164,(a0)             ; display on, DMA off (original)
        clr.w   ZT_HPEND                ; no band this frame (a stale flag would blank the HUD DMA queue)
        bra   .done
.nodma:
        tst.w   ZT_BANDCNT
        beq   .idle
        subq.w  #1,ZT_BANDCNT
        bsr.w   ZT_BandOK
        beq   .idle
        move.w  #$8124,(a0)             ; same band as DMA frames
        bsr.w   ZT_Arm
        bra   .done
.idle:  clr.w   ZT_HPEND                ; outside gameplay: leave the VDP alone
        bra   .out
.done:
        ifd MOUSE_TAIL
        movem.l (sp)+,d0/a0
        jmp     MOUSE_TAIL              ; mouse hack ROM: its VBlank end (restores the VRAM address, reads the mouse)
        else
        move.l  #$73600002,(a0)         ; restore VRAM write address (as original)
        endif
.out:   movem.l (sp)+,d0/a0
        rte

; HD emulator: the native view only changes at the logic tick, so upload it like the original, half
; per VBlank with the display on (no overrun, no band). Exits through the VBlank tail.
ZT_SplitDma:
        move.w  #$8174,(a0)             ; display on, DMA on
        jsr     Z80_BUSREQ
        subq.w  #1,FB_PENDING
        beq   .second
        move.w  #$9300,(a0)             ; first half: FB -> VRAM $0020
        move.w  #$940A,(a0)
        move.w  #$9500+((FB>>1)&$FF),(a0)
        move.w  #$9600+((FB>>9)&$FF),(a0)
        move.w  #$9700+((FB>>17)&$7F),(a0)
        move.w  #$4020,(a0)
        move.w  #$0080,(a0)
        jsr     Z80_BUSREL
        bsr     ZT_Flash
        bra   .end
.second:
        move.w  #$9300,(a0)             ; second half: FB+$1400 -> VRAM $1420
        move.w  #$940A,(a0)
        move.w  #$9500+(((FB+$1400)>>1)&$FF),(a0)
        move.w  #$9600+(((FB+$1400)>>9)&$FF),(a0)
        move.w  #$9700+(((FB+$1400)>>17)&$7F),(a0)
        move.w  #$5420,(a0)
        move.w  #$0080,(a0)
        jsr     Z80_BUSREL
.end:   move.w  #$8164,(a0)             ; display on, DMA off
        ifd MOUSE_TAIL
        movem.l (sp)+,d0/a0
        jmp     MOUSE_TAIL
        else
        move.l  #$73600002,(a0)
        movem.l (sp)+,d0/a0
        rte
        endif

; NE if the top band should be blanked this frame (PAL VBlank fits the DMA: never)
ZT_BandOK:
        btst    #6,$A10001
        bne   .no
        tst.w   ZT_HD                   ; HD emulator: the native view isn't shown, keep the HUD whole
        bne   .no
        tst.w   ZT_NOBAND
        bne   .no
        tst.w   ZT_INGAME
        beq   .no
        tst.w   ZT_DISP
        rts
.no:    cmp.w   d0,d0                   ; Z = 1
        rts

ZT_Arm:
        move.w  #$8A00+BAND_LINES-1,(a0)
        move.w  #$8014,(a0)             ; line interrupt on
        move.w  #1,ZT_IEON
        move.w  #1,ZT_HPEND
        move.w  VBL_COUNT,ZT_ARMVBL
        rts

; Line interrupt off, from main code only (where the game itself writes VDP registers).
ZT_Disarm:
        clr.w   ZT_INGAME
        clr.w   ZT_HPEND
        tst.w   ZT_IEON
        beq   .x
        clr.w   ZT_IEON
        move.w  #$8004,VDP_CTRL         ; game's reg 0 value
.x:     rts

; Once-per-frame damage flash (original code from $B12)
ZT_Flash:
        tst.w   FLASH
        beq   .x
        tst.w   FLASH_MODE
        beq   .slow
        cmpi.w  #$F,FLASH
        bhi   .big
        subq.w  #1,FLASH
        bpl   .w
        clr.w   FLASH
        bra   .w
.big:   subi.w  #$110,FLASH
        bra   .w
.slow:  subq.w  #3,FLASH
        bpl   .w
        clr.w   FLASH
.w:     move.l  #$C07E0000,VDP_CTRL
        move.w  FLASH,VDP_DATA
.x:     rts

; ---------------------------------------------------------------------------
; Line interrupt (level 4): end of the blank band.
; ---------------------------------------------------------------------------
ZT_HInt:
        tst.w   ZT_HPEND
        beq   .rte
        move.w  d0,-(sp)
        move.w  VDP_HV,d0               ; V counter in the high byte
        lsr.w   #8,d0
        cmp.w   #BAND_LINES-1,d0        ; a stale pending interrupt fires as soon as
        bcs   .ign                    ; it is enabled (in VBlank): ignore those
        cmp.w   #$E0,d0
        bcc   .ign
        clr.w   ZT_HPEND
        tst.w   ZT_DISP
        beq   .ign
        move.w  #$8164,VDP_CTRL         ; display on
        move.l  #$73600002,VDP_CTRL
.ign:   move.w  (sp)+,d0
.rte:   rte

; ---------------------------------------------------------------------------
; Replacements for the game's "move.w #$8164/#$8124,$C00004" in gameplay flow.
; ---------------------------------------------------------------------------
ZT_DispOn:
        move.w  #1,ZT_DISP
        move.w  #$8164,VDP_CTRL
        rts

ZT_DispOff:
        clr.w   ZT_DISP
        bsr     ZT_Disarm
        move.w  #$8124,VDP_CTRL
        rts

; ---------------------------------------------------------------------------
; Main loop exits: level exit at $173A, death at $1788.
; ---------------------------------------------------------------------------
ZT_ExitCheck:                           ; replaces "tst.w EXIT_FLAG(a6); bne.w EXIT_TGT"
        tst.w   EXIT_FLAG_W(a6)
        beq   .x
        bsr     ZT_Disarm
        move.l  #EXIT_TGT,(sp)             ; leave the loop as the original does
.x:     rts

ZT_DeathExit:                           ; replaces "move.w LIVES(a6),d7; beq.b DEATH_TGT"
        bsr     ZT_Disarm
        move.w  LIVES_W(a6),d7
        bne   .x
        move.l  #DEATH_TGT,(sp)
.x:     rts

; ---------------------------------------------------------------------------
; The HUD DMA queue at $79A turns the display on around its transfers; keep it
; blank if that happens inside the band (logic ticks run right after VBlank).
; ---------------------------------------------------------------------------
ZT_QueueDmaOn:
        tst.w   ZT_HD
        bne   .orig
        tst.w   ZT_HPEND
        bne   .band
.orig:
        move.w  #$8174,VDP_CTRL         ; display on, DMA on (original)
        rts
.band:  move.w  #$8134,VDP_CTRL         ; display off, DMA on
        rts

ZT_QueueDmaOff:
        tst.w   ZT_HD
        bne   .orig
        tst.w   ZT_HPEND
        bne   .band
.orig:
        move.w  #$8164,VDP_CTRL         ; display on, DMA off (original)
        rts
.band:  move.w  #$8124,VDP_CTRL         ; display off, DMA off
        rts
