Zero Tolerance HD for Windows (RetroArch)
=========================================

Files
  genesis_plus_gx_zt_hd_libretro.dll  Genesis Plus GX core with the HD renderer (64-bit)
  Zero Tolerance (high fps).gen       the game with the high-fps patch (10 Hz fixed logic)
  zt_high_fps.ips                     the same patch as IPS, for "Zero Tolerance (USA, Europe) (Rev A).gen"
  zt_sky_1553E6.png                   full sky for the planet levels (complete planet, more stars);
                                      keep it next to the game (or in RetroArch's saves folder)
  zt-hd-core-options.cfg              the core's settings (HD on, 1920x1080, FOV 106, ...)
  play_zt_hd.bat                      starts RetroArch with all of the above

Use
  1. Install 64-bit RetroArch (retroarch.com) if you haven't.
  2. Double-click play_zt_hd.bat. If it says RetroArch wasn't found, open the .bat in Notepad and set RA
     to the full path of retroarch.exe.

In game
  M     settings menu (pauses): resolution, field of view, original screen layout, switch key, HUD scale,
        weapon, sky, sky beyond band, shading, menu key. Saved to zt_hd.cfg in RetroArch's saves folder.
  G     switch between the HD view and the original screen (when layout = switch with key)

To use the core in RetroArch without the .bat: copy the .dll into RetroArch's "cores" folder and load the
game with it (Load Core, then Load Content). Its options are under Quick Menu > Core Options.
