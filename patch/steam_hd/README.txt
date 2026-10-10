Zero Tolerance HD for the Steam release (QUByte Classics)
=========================================================

A drop-in replacement for the game's emulator: Genesis Plus GX with the HD renderer (large 3D view, HD
resolution, compact HUD) and the fixed-rate patch (smooth view, original game speed). No RetroArch needed.

Install
  1. In Steam: Zero Tolerance > Manage > Browse local files.
  2. Back up ew_core.dll and res\game (e.g. copy them to a "backup" folder).
  3. Copy everything from this folder into the game folder, replacing ew_core.dll and res\game.
  To undo: copy the backups back, or use Steam's "Verify integrity of game files".

In game
  M     settings menu (pauses): resolution, field of view, original screen layout, switch key, HUD scale,
        weapon, sky, sky beyond band, shading, menu key. Saved to zt_hd.cfg in the game folder.
  G     switch between the HD view and the original screen
  The controller and keyboard buttons are the frontend's, as before.

Notes
  - ew_core_options.cfg holds the starting settings; the menu's zt_hd.cfg overrides them.
  - zt_sky_1553E6.png is the full sky for the planet levels (complete planet, more stars). It can be edited.
  - Save states from the original emulator can't be loaded by this one.
  - The -turbo launch option isn't needed (and is ignored): the patched game keeps its normal speed.
  - The window takes its shape (16:9 by default) from the resolution and layout in ew_core_options.cfg.
    Use the frontend's windowed or integer-scale mode: its stretch mode fits the picture to the window's
    height only, so a window narrower than 16:9 (or a 16:10 screen) cuts the sides.
  - If the game runs slowly, lower the resolution in the M menu (e.g. 1280x720).
  - If the frontend's CRT filter is on, turn it off for a sharp HD image.
