Zero Tolerance HD for macOS (RetroArch)
=======================================

Zero Tolerance (Mega Drive / Genesis, 1994) with a native HD renderer: the 3D view re-rendered at up to 4K
and any field of view, a redesigned HUD built from the original's pieces, smooth movement at the original
game speed (fixed-rate patch), in-game settings. No game data is included: you need your own copy of the
cartridge ROM.

Files
  play_mac.sh                              starts RetroArch with the HD core and these settings
  Zero Tolerance (USA, Europe) (Rev A).ips the fixed-rate patch; RetroArch applies it to the ROM of the
                                           same name as it loads it (your ROM file is not changed)
  tools/genesis_plus_gx_zt_hd.dylib        the core for Apple Silicon RetroArch
  tools/genesis_plus_gx_zt_hd_x86_64.dylib the core for Intel RetroArch (also Apple Silicon under Rosetta)
  tools/zt-hd-core-options.cfg             the core's settings (HD on, 1280x720, FOV 106, ...)
  tools/retroarch-zt-hd.cfg                RetroArch settings for this game (window size)

Use
  1. Install RetroArch (retroarch.com) in /Applications.
  2. Put your ROM in this folder, named exactly "Zero Tolerance (USA, Europe) (Rev A).gen"
     (the Rev A cartridge, SHA-1 d6d9733a619ba6be0dd76591d8dec621e4fdc17e).
  3. In Terminal: sh play_mac.sh (drag the file into the Terminal window after "sh ").
     The script picks the core that matches your RetroArch and clears macOS's download quarantine on it.

In game
  M     settings menu (pauses): resolution, field of view, original screen layout, switch key, HUD scale,
        weapon, out of ammo (switch weapon / keep), sky, sky beyond band, shading, menu key.
        Saved to zt_hd.cfg in RetroArch's saves folder.
  G     switch between the HD view and the original screen (when layout = switch with key)
  When a weapon runs out of ammo the next best one is selected for you (guns first, fists last); turn it
  off with "Out of ammo" in the menu.

Source, licence (MIT) and build instructions: https://github.com/viktor-malieichyk/zero-tolerance-hd
Genesis Plus GX is by Eke-Eke and contributors under its own non-commercial licence, which applies to the
cores. Zero Tolerance is (c) 1994 Technopop / Accolade; this package contains no part of the game.
