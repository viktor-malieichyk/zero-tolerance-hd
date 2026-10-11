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
  zt-hd-core-options.cfg                   the core's settings (HD on, 1280x720, FOV 106, ...)
  play_zt_hd.bat                           starts RetroArch with all of the above

Use
  1. Install 64-bit RetroArch (retroarch.com) if you haven't.
  2. Put your ROM in this folder, named exactly "Zero Tolerance (USA, Europe) (Rev A).gen"
     (the Rev A cartridge, SHA-1 d6d9733a619ba6be0dd76591d8dec621e4fdc17e).
  3. Double-click play_zt_hd.bat. If it says RetroArch wasn't found, open the .bat in Notepad and set RA
     to the full path of retroarch.exe.

In game
  M     settings menu (pauses): resolution, field of view, original screen layout, switch key, HUD scale,
        weapon, out of ammo (switch weapon / keep), sky, sky beyond band, shading, menu key.
        Saved to zt_hd.cfg in RetroArch's saves folder.
  G     switch between the HD view and the original screen (when layout = switch with key)
  When a weapon runs out of ammo the next best one is selected for you (guns first, fists last); turn it
  off with "Out of ammo" in the menu.

To use the core in RetroArch without the .bat: copy the .dll into RetroArch's "cores" folder and load the
ROM with it (Load Core, then Load Content), with the .ips next to the ROM. Its options are under
Quick Menu > Core Options.

Source, licence (MIT) and build instructions: https://github.com/viktor-malieichyk/zero-tolerance-hd
Genesis Plus GX is by Eke-Eke and contributors under its own non-commercial licence, which applies to the
core. Zero Tolerance is (c) 1994 Technopop / Accolade; this package contains no part of the game.
