"""The ROMs the patch and the HD core support, and where each keeps what they use.

Every game is the same engine (Technopop's Zero Tolerance), rebuilt: code moves, some RAM moves. Addresses are
named after their role and given per game. They were found by aligning each ROM's disassembly with Rev A's
(instruction by instruction, operands ignored) and checked by hand at every site; the hook builders in
make_patch.py check the original instructions again when patching.

  code   ROM addresses (routines, hook sites, tables)
  ram    work RAM ($FFxxxx), absolute
"""

REV_A = dict(
    # routines
    INPUT_A=0x079A, INPUT_B=0x0D36,          # per-tick input handlers (bsr'd from the main loop)
    LOGIC_CONT=0x1634,                       # rest of the logic block
    SUBMIT=0x146A,                           # "frame ready" + vblank wait + sky scroll
    HORIZON=0xD49A,                          # rebuild the floor/ceiling buffer if the horizon changed
    RENDER=0xB9A6,                           # 3D view renderer (walls + objects)
    RENDER_CALL=0xB9A6,                      # what the main loop calls to render (Underground: a governor)
    CELL_LOGIC=0xB4E4,                       # floor-cell events (lifts, stairs, sounds), called by RENDER
    DIRTABLE=0x8124,                         # angle (0..511) -> (cos, sin) words
    Z80_BUSREQ=0xC5BB6, Z80_BUSREL=0xC5BF4,  # sound driver handshake around DMA
    EXIT_TGT=0x1A40,                         # main loop: level exit
    DEATH_TGT=0x17AE,                        # main loop: death, no lives left
    HINT_OLD=0x0BAC,                         # level 4 vector (an RTE)
    VRAM_RESTORE=0x73600002,                 # VDP command the VBlank ends with
    # hook sites
    S_DECIDE=0x162C,                         # bsr INPUT_A; bsr INPUT_B
    S_LOGIC_RENDER=0x16CE,                   # jsr RENDER (logic block)
    S_INIT_RENDER=0x13F6,                    # jsr RENDER (level start)
    S_RESPAWN_RENDER=0x1964,                 # jsr RENDER (respawn)
    S_SKY=0x1470,                            # move.w CAM_A(a6),d2; neg.w d2
    S_CELL=0xBAE6,                           # bsr CELL_LOGIC; move.w BOB(a6),d0
    S_VBLANK=0x0AC2,                         # tst.w FB_PENDING
    S_EXIT=0x173A,                           # tst.w EXIT_FLAG(a6); bne.w EXIT_TGT
    S_DEATH=0x1788,                          # move.w LIVES(a6),d7; beq.b DEATH_TGT
    S_QDMA_ON=0x07A4, S_QDMA_OFF=0x07F6,     # HUD DMA queue: move.w #$8174/#$8164,$C00004
    S_SR_BOOT=0x0A18, S_SR_SOUND=0xD7AE, S_SR_LINK=0x1C016,   # move.w #$2500,sr
    S_SR_LINK_SAVE=0x1C010,                  # move.w #$2500,d16(a6)
    S_DISP_ON=[0x134E, 0x1432, 0x1624, 0x199C, 0x2E3E],       # move.w #$8164,$C00004
    S_DISP_OFF=[0x11A6, 0x139A, 0x1830, 0x29DE, 0x2CF4],      # move.w #$8124,$C00004
    # RAM
    VBL=0xFF0000,                            # vblank counter
    FB_PENDING=0xFF0002,                     # framebuffer upload request (2 = both halves)
    FLASH=0xFF1072, FLASH_MODE=0xFF0DE2,     # damage flash colour
    CAM_X=0xFF0DEC, CAM_Y=0xFF0DEE,          # 8.8 map position, wraps at $2000
    CAM_A=0xFF0E04,                          # angle, 0..511
    CAM_H=0xFF0E1A,                          # horizon offset
    CAM_DX=0xFF0E00, CAM_DY=0xFF0E02,        # direction vector (from DIRTABLE)
    BOB=0xFF116E,                            # vertical bob set by CELL_LOGIC
    EXIT_FLAG=0xFF2722,                      # level exit requested
    LIVES=0xFF24E8,
    FB=0xFF3926,                             # 3D view framebuffer, two $A00-word halves
    ZT_VARS=0xFFF800,                        # our variables ($40 bytes): RAM above the stack, never touched by
                                             # any of the games (the cell table at $FF7740 was: level data)
)

def derive(base, **changes):
    g = dict(base)
    g.update(changes)
    return g

# Rev A with the Sega Mouse hack (mouse turning): its code at $1F8000, joypad hook at $8EC, and the VBlank
# ends with "jmp $1F8012" (restore the VRAM address, read the mouse, RTE), which our VBlank must end with too.
MOUSE = derive(REV_A, MOUSE_TAIL=0x1F8012)

# Zero Tolerance: Underground. Same code, shifted; RAM from $FF0E74 up shifted by 4; 228 cell types.
UNDERGROUND = derive(
    REV_A,
    INPUT_B=0x0DEA, LOGIC_CONT=0x170A, SUBMIT=0x153A, HORIZON=0xD736, CELL_LOGIC=0xB720,
    # the main loop renders through a pointer set at boot ($FFCD2A = $BBEC, called at $BBE2): a governor that
    # times the render ($BC4C) and skips frames after a slow one. The fixed logic tick replaces it.
    RENDER=0xBC4C, RENDER_CALL=0xBBE2,
    DIRTABLE=0x81E6, Z80_BUSREQ=0x96510, Z80_BUSREL=0x9654E, EXIT_TGT=0x1B12, DEATH_TGT=0x1884, HINT_OLD=0x0BD8,
    S_DECIDE=0x1702, S_LOGIC_RENDER=0x17A4, S_INIT_RENDER=0x14BA, S_RESPAWN_RENDER=0x1A3A, S_SKY=0x1540,
    S_CELL=0xBD8C, S_VBLANK=0x0AEE, S_EXIT=0x1810, S_DEATH=0x185E, S_SR_SOUND=0xDA4A, S_SR_LINK=0x1C9E2,
    S_SR_LINK_SAVE=0x1C9DC,
    S_DISP_ON=[0x1412, 0x14F6, 0x16FA, 0x1A72, 0x2F00],
    S_DISP_OFF=[0x126A, 0x145E, 0x1906, 0x2AA0, 0x2DB6],
    FLASH=0xFF1076, BOB=0xFF1172, EXIT_FLAG=0xFF2726, LIVES=0xFF24EC, FB=0xFF392A,
)

# Beyond Zero Tolerance (unreleased sequel, "Build: 062393a"). More rework: RAM mostly moved, the sky and
# floor-cell hook sites are arranged differently (SKY_A4, CELL_POP), the logic block calls a new routine
# ($B9B54, sets a mode word) before rendering.
BEYOND = derive(
    REV_A,
    INPUT_B=0x0D4C, LOGIC_CONT=0x1692, SUBMIT=0x1464, HORIZON=0xCE32, RENDER=0xB250, RENDER_CALL=0xB250,
    CELL_LOGIC=0xAB00, DIRTABLE=0x78EA, Z80_BUSREQ=0x6418A, Z80_BUSREL=0x641C8, EXIT_TGT=0x1A6E,
    DEATH_TGT=0x1818, HINT_OLD=0x0BCC, VRAM_RESTORE=0x67800002,
    S_DECIDE=0x168A, S_LOGIC_RENDER=0x1732, S_INIT_RENDER=0x1382, S_RESPAWN_RENDER=0x1992,
    S_SKY=0x146A, SKY_A4=True,                # move.w CAM_A(a6),d2; movea.l #$C00000,a4; (neg.w d2)
    S_CELL=0xB394, CELL_POP=True,             # (move.w x(a6),-(sp)); bsr CELL_LOGIC; move.w (sp)+,d0
    S_VBLANK=0x0AE2, S_EXIT=0x179E, S_DEATH=0x17F2, S_SR_SOUND=0xD146, S_SR_LINK=0x1A31E,
    S_SR_LINK_SAVE=0x1A318,
    S_DISP_ON=[0x12D4, 0x13BE, 0x1682, 0x19CA, 0x2D66],
    S_DISP_OFF=[0x112E, 0x1320, 0x189A, 0x2896, 0x2BA6],
    FLASH=0xFF10A2, FLASH_MODE=0xFF0DEA, CAM_X=0xFF0DF4, CAM_Y=0xFF0DF6, CAM_A=0xFF0E0C, CAM_H=0xFF0E22,
    CAM_DX=0xFF0E08, CAM_DY=0xFF0E0A, BOB=0xFF11AE, EXIT_FLAG=0xFF29E2, LIVES=0xFF27B2, FB=0xFF3BE6,
)

# id: written into the patch (the HD core reads it); file: the ROM's name in this repo's root
GAMES = {
    "zt": dict(id=1, title="Zero Tolerance (Rev A)", file="Zero Tolerance (USA, Europe) (Rev A).gen",
               sha1="d6d9733a619ba6be0dd76591d8dec621e4fdc17e", org=0x1D0000, addr=REV_A,
               out="Zero Tolerance (high fps).gen", ips="zt_high_fps.ips"),
    "zt_mouse": dict(id=2, title="Zero Tolerance (Rev A, mouse hack)", file="ZT.bin",
                     sha1="e0dd42d65302c62904bbbe226efc68e2c71fdfab", org=0x1D0000, addr=MOUSE,
                     out="ZT (high fps).bin", ips="ZT.ips"),
    "ztu": dict(id=3, title="Zero Tolerance: Underground", file="ZTU.bin",
                sha1="9f8df85692bea0b794dbf6a5f4f3ee579840694a", org=0x1E0000, addr=UNDERGROUND,
                out="ZTU (high fps).bin", ips="ZTU.ips"),
    "bzt": dict(id=4, title="Beyond Zero Tolerance", file="BZT.BIN",
                sha1="ab7791def9ad91c0f0870b1f928ceb13b76acb9c", org=0x270000, addr=BEYOND,
                out="BZT (high fps).bin", ips="BZT.ips"),
}
