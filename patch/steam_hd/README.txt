Zero Tolerance HD for the Steam release (QUByte Classics)
=========================================================

A drop-in replacement for the game's emulator: Genesis Plus GX with the Zero Tolerance HD renderer
(large 3D view at up to 4K, a redesigned HUD built from the original's pieces, in-game settings) and the fixed-rate patch (smooth view,
original game speed). No ROM is included and no game file is changed: the patch is applied in memory
to the game's own res\game each time it starts.

Install
  1. In Steam: Zero Tolerance > Manage > Browse local files.
  2. Rename ew_core.dll to ew_core.dll.bak (or copy it somewhere safe).
  3. Copy ew_core.dll, ew_core_options.cfg and ztcrt.fs from this package into the game folder.
  To undo: put the original ew_core.dll back, or use Steam's "Verify integrity of game files".

  Only the Steam release's res\game is patched (it is identified by checksum). With any other ROM the
  game runs as it is, without the HD view. A patched copy of the game is written to your temp folder at
  each start (zt_hd_game.md); nothing in the game folder is changed.

Other games: Zero Tolerance: Underground and Beyond Zero Tolerance
  Put your own copies of their ROMs in the game folder (or its res folder), named anything. They are
  recognised by size and checksum (CRC32), not by name; files that don't match exactly are ignored. The
  ROMs this works with:
    Zero Tolerance: Underground          1955536 bytes  CRC32 E2288416
    Beyond Zero Tolerance (062393a)      2537924 bytes  CRC32 EF2F803B
    Zero Tolerance cartridge (Rev A)     2097152 bytes  CRC32 23F603F5
    Zero Tolerance, Sega Mouse hack      2097152 bytes  CRC32 E52EF46C
  When more than one game is found, the M menu has a "Game" line: pick one and close the menu to switch
  (the game restarts). The choice is kept for the next start (zt_hd_game.cfg). Save states remember their
  game and switch to it when loaded. zt_hd_log.txt lists the games found.

In game
  M     settings menu (pauses): resolution, field of view, original screen layout, switch key, HUD scale,
        weapon, out of ammo (switch weapon / keep), sky, sky beyond band, shading, menu key, and the game
        when there is a choice (see above).
        Saved to zt_hd.cfg in the game folder.
  Controller: Z opens and closes the menu (the frontend's Z button: LB on an Xbox pad, D on the
        keyboard; rebind it in the frontend's Set input), D-pad up/down select, left/right or C change,
        B closes.
  Space fast forward while held (the frontend's Mode button; 4x, shown by a fast-forward sign at the top
        right; zt_fast_forward in ew_core_options.cfg sets the speed, 2-8, or 1 to turn it off).
  G     switch between the HD view and the original screen
  When a weapon runs out of ammo the next best one is selected for you (guns first, fists last); turn it
  off with "Out of ammo" in the menu.
  The controller and keyboard buttons are the frontend's, as before.

The frontend's own menu (display, Set input, ...)
  Opens with the right mouse button, or the right stick click on the controller (this package moves it
  there from the Guide button, which Steam's overlay usually takes). To use another controller button, set
  zt_frontend_menu_button in ew_core_options.cfg to its SDL joystick number (Xbox-style pad: 0 A, 1 B, 2 X,
  3 Y, 4 LB, 5 RB, 6 Back, 7 Start, 8 left stick click, 9 right stick click, 10 Guide). LB (4) is the HD
  menu's button by default, so pick another one.
  Frontend keys: F1-F3 load state 1-3, Shift+F1-F3 save, Alt+Enter fullscreen, Pause pauses.

Notes
  - ew_core_options.cfg holds the starting settings; the menu's zt_hd.cfg overrides them.
  - The picture takes your desktop's shape (genesis_plus_gx_zt_hd_res = "auto" in ew_core_options.cfg: 720
    rows, as wide as the desktop's shape needs, e.g. 1152x720 on a 16:10 screen or a Steam Deck), so it fills
    the screen in fullscreen. A fixed size such as "1920x1080" can be set there or in the M menu instead.
    The frontend's Stretch is patched (in memory) to fit the picture inside the window: it is never cut off,
    and keeps its shape with bars when the window's shape differs. Stretch also stretches the original
    320x224 screens (title, menus, original view) to the full picture.
  - zt_hd_log.txt (written next to the DLL at each start) records what the DLL found and the window and
    picture sizes; include it when reporting a display problem.
  - Save states from the original emulator can't be loaded by this one.
  - The -turbo launch option isn't needed (and is ignored): the patched game keeps its normal speed.
  - If the game runs slowly, lower the resolution in the M menu (e.g. 1280x720).
  - The frontend's "CRT mask" uses ztcrt.fs from this package instead of its own filter (which blurs the
    HD view down to 320 pixels): scanlines and an RGB mask at screen resolution, full detail kept.
    Its strengths are numbers at the top of ztcrt.fs (edit in Notepad); without the file the original
    filter is used.

Source, licence (MIT) and build instructions: https://github.com/viktor-malieichyk/zero-tolerance-hd
Genesis Plus GX is by Eke-Eke and contributors under its own non-commercial licence, which applies to this
DLL. Zero Tolerance is (c) 1994 Technopop / Accolade; this package contains no part of the game.
