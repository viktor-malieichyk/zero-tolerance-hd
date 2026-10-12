Zero Tolerance HD for the Steam release (QUByte Classics)
=========================================================

A drop-in replacement for the game's emulator: Genesis Plus GX with the Zero Tolerance HD renderer
(large 3D view at up to 4K, a redesigned HUD built from the original's pieces, in-game settings) and the fixed-rate patch (smooth view,
original game speed). No ROM is included and no game file is changed: the patch is applied in memory
to the game's own res\game each time it starts.

Install
  1. In Steam: Zero Tolerance > Manage > Browse local files.
  2. Rename ew_core.dll to ew_core.dll.bak (or copy it somewhere safe).
  3. Copy ew_core.dll and ew_core_options.cfg from this package into the game folder.
  To undo: put the original ew_core.dll back, or use Steam's "Verify integrity of game files".

  Only the Steam release's res\game is patched (it is identified by checksum). With any other ROM the
  game runs as it is, without the HD view. A patched copy of the game is written to your temp folder at
  each start (zt_hd_game.md); nothing in the game folder is changed.

In game
  M     settings menu (pauses): resolution, field of view, original screen layout, switch key, HUD scale,
        weapon, out of ammo (switch weapon / keep), sky, sky beyond band, shading, menu key.
        Saved to zt_hd.cfg in the game folder.
  Controller: Mode opens and closes the menu (the frontend's Mode button: Back / View on an Xbox pad,
        Space on the keyboard; rebind it in the frontend's Set input), D-pad up/down select, left/right or
        C change, B closes.
  G     switch between the HD view and the original screen
  When a weapon runs out of ammo the next best one is selected for you (guns first, fists last); turn it
  off with "Out of ammo" in the menu.
  The controller and keyboard buttons are the frontend's, as before.

Notes
  - ew_core_options.cfg holds the starting settings; the menu's zt_hd.cfg overrides them.
  - The window takes its shape (16:9 by default) from the resolution and layout in ew_core_options.cfg.
    The frontend's Stretch fits the picture to the window's height only, so a window narrower than 16:9
    (or a 16:10 screen) cuts the sides; with Stretch off it letterboxes correctly. Stretch also stretches
    the original 320x224 screens (title, menus, original view) to the full width.
  - Save states from the original emulator can't be loaded by this one.
  - The -turbo launch option isn't needed (and is ignored): the patched game keeps its normal speed.
  - If the game runs slowly, lower the resolution in the M menu (e.g. 1280x720).
  - If the frontend's CRT filter is on, turn it off for a sharp HD image.

Source, licence (MIT) and build instructions: https://github.com/viktor-malieichyk/zero-tolerance-hd
Genesis Plus GX is by Eke-Eke and contributors under its own non-commercial licence, which applies to this
DLL. Zero Tolerance is (c) 1994 Technopop / Accolade; this package contains no part of the game.
