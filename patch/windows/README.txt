Zero Tolerance HD for Windows (RetroArch)
=========================================

Zero Tolerance (Mega Drive / Genesis, 1994) with a native HD renderer: the 3D view re-rendered at up to 4K
and any field of view, a redesigned HUD built from the original's pieces, smooth movement at the original
game speed (fixed-rate patch), in-game settings. No game data is included: you need your own copy of the
cartridge ROM.

Files
  genesis_plus_gx_zt_hd_libretro.dll       Genesis Plus GX core with the HD renderer (64-bit)
  Zero Tolerance (USA, Europe) (Rev A).ips the fixed-rate patch; RetroArch applies it to the ROM of the
                                           same name as it loads it (your ROM file is not changed)
  ZT.ips, ZTU.ips, BZT.ips                 the same for the other games (below)
  zt-hd-core-options.cfg                   the core's settings (HD on, 1280x720, FOV 106, ...)
  play_zt_hd.bat                           starts RetroArch with all of the above

Use
  1. Install 64-bit RetroArch (retroarch.com) if you haven't.
  2. Put your ROM in this folder, named exactly "Zero Tolerance (USA, Europe) (Rev A).gen"
     (the Rev A cartridge, SHA-1 d6d9733a619ba6be0dd76591d8dec621e4fdc17e).
  3. Double-click play_zt_hd.bat. If it says RetroArch wasn't found, open the .bat in Notepad and set RA
     to the full path of retroarch.exe.

Other games
  The core also plays these, each with its own .ips (RetroArch pairs a ROM with the .ips of the same name):
    ZT.bin    Zero Tolerance (Rev A) with the Sega Mouse hack  SHA-1 e0dd42d65302c62904bbbe226efc68e2c71fdfab
    ZTU.bin   Zero Tolerance: Underground                      SHA-1 9f8df85692bea0b794dbf6a5f4f3ee579840694a
    BZT.BIN   Beyond Zero Tolerance                            SHA-1 ab7791def9ad91c0f0870b1f928ceb13b76acb9c
  Put the ROM in this folder under that name and drop it on play_zt_hd.bat (or: play_zt_hd.bat ZTU.bin).

In game
  M     settings menu (pauses): resolution, field of view, original screen layout, switch key, HUD scale,
        weapon, out of ammo (switch weapon / keep), sky, sky beyond band, shading, gamepad, keyboard,
        mouse turning, turn speed, menu key.
        Saved to zt_hd.cfg in RetroArch's saves folder.
  Controller: Z (RetroPad R, e.g. RB) opens and closes the menu, D-pad up/down select, left/right or
        C (RetroPad A) change, B closes.
  G     switch between the HD view and the original screen (when layout = switch with key)
  Controls (menu: Gamepad, Keyboard, Mouse turning, Turn speed). They all work at once and can be mixed;
  the modern ones only take over while used, the D-pad and buttons always do what they did.
    Gamepad, Twin stick (default): left stick walks and strafes (together, as fast as it is pushed), right
        stick turns; A on its own jumps, L3 held crouches, R2 fires, L2 next weapon. Classic: the original
        controls only (strafe with A + Left/Right).
    Keyboard, Modern (default): W A S D walk and strafe, arrow keys turn (up / down walk), Space jumps,
        Ctrl fires, E next weapon, C crouches (held). Classic: RetroArch's key bindings only.
    Mouse turning (speed 1-5, default 3): the mouse turns, left button fires, right button or wheel next weapon.
  Turning with the right stick, the arrow keys or the mouse shows at once: the HD view turns ahead of the
  game's 10 Hz logic, which catches up within a tenth of a second.
  In Underground A only jumps with its classic control setting (its options); in its others A turns, and
  Space still jumps.
  play_zt_hd.bat sets RetroArch up for this per game (a game override: config/Genesis Plus GX/<ROM name>.cfg):
        player 1's keys off W A S D C E (Space is Genesis A, R Genesis Y, Tab Genesis Z), RetroArch's hotkeys
        on Space, E, R, M, N off, the mouse held (F11 lets it go; RetroArch's menu, F1, too). Leave
        "Analog to Digital Type" at None for the left stick.
  When a weapon runs out of ammo the next best one is selected for you (guns first, fists last); turn it
  off with "Out of ammo" in the menu.

To use the core in RetroArch without the .bat: copy the .dll into RetroArch's "cores" folder and load the
ROM with it (Load Core, then Load Content), with the .ips next to the ROM. Its options are under
Quick Menu > Core Options.

Source, licence (MIT) and build instructions: https://github.com/viktor-malieichyk/zero-tolerance-hd
Genesis Plus GX is by Eke-Eke and contributors under its own non-commercial licence, which applies to the
core. Zero Tolerance is (c) 1994 Technopop / Accolade; this package contains no part of the game.
