@echo off
rem Zero Tolerance HD: runs the game in RetroArch with the HD core from this folder.
rem Set RA below if RetroArch isn't in one of the usual places.
setlocal
set "HERE=%~dp0"
set "RA="
if exist "C:\RetroArch-Win64\retroarch.exe" set "RA=C:\RetroArch-Win64\retroarch.exe"
if exist "C:\RetroArch\retroarch.exe" set "RA=C:\RetroArch\retroarch.exe"
if exist "%APPDATA%\RetroArch\retroarch.exe" set "RA=%APPDATA%\RetroArch\retroarch.exe"
if exist "C:\Program Files (x86)\Steam\steamapps\common\RetroArch\retroarch.exe" set "RA=C:\Program Files (x86)\Steam\steamapps\common\RetroArch\retroarch.exe"
if "%RA%"=="" (
  echo RetroArch not found. Edit play_zt_hd.bat and set RA to your retroarch.exe.
  pause
  exit /b 1
)
rem RetroArch settings for this game only (written next to this file, absolute paths)
set "CFG=%HERE%zt-hd-retroarch.cfg"
>"%CFG%" echo global_core_options = "true"
>>"%CFG%" echo core_options_path = "%HERE%zt-hd-core-options.cfg"
>>"%CFG%" echo video_fullscreen = "false"
>>"%CFG%" echo video_window_save_positions = "true"
>>"%CFG%" echo video_scale_integer = "false"
>>"%CFG%" echo video_window_custom_size_enable = "true"
>>"%CFG%" echo video_window_width = "1280"
>>"%CFG%" echo video_window_height = "720"
rem the game: your own ROM next to this file; RetroArch applies the .ips of the same name as it loads it.
rem Another game: drop its ROM on this file, or pass it (play_zt_hd.bat ZTU.bin).
set "ROM=%HERE%Zero Tolerance (USA, Europe) (Rev A).gen"
if exist "%HERE%Zero Tolerance (high fps).gen" set "ROM=%HERE%Zero Tolerance (high fps).gen"
if not "%~1"=="" set "ROM=%~f1"
if not "%~1"=="" if not exist "%ROM%" if exist "%HERE%%~1" set "ROM=%HERE%%~1"
if not exist "%ROM%" (
  echo Put your copy of the game, named "Zero Tolerance (USA, Europe) (Rev A).gen", in this folder.
  pause
  exit /b 1
)
rem keys for the modern keyboard (W A S D C E free, Space = A) and the mouse: a RetroArch game override for
rem this ROM, refreshed while it is ours (first line)
set "KEYS=%HERE%zt-hd-keys.cfg"
if not exist "%KEYS%" set "KEYS=%HERE%..\tools\zt-hd-keys.cfg"
for %%I in ("%RA%") do set "RADIR=%%~dpI"
for %%I in ("%ROM%") do set "ROMNAME=%%~nI"
set "OVR=%RADIR%config\Genesis Plus GX"
if not exist "%OVR%" mkdir "%OVR%"
if not exist "%OVR%\%ROMNAME%.cfg" (copy /y "%KEYS%" "%OVR%\%ROMNAME%.cfg" >nul) else (findstr /b /c:"# Zero Tolerance HD" "%OVR%\%ROMNAME%.cfg" >nul && copy /y "%KEYS%" "%OVR%\%ROMNAME%.cfg" >nul)
start "" "%RA%" -L "%HERE%genesis_plus_gx_zt_hd_libretro.dll" --appendconfig "%HERE%zt-hd-retroarch.cfg" "%ROM%"
