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
start "" "%RA%" -L "%HERE%genesis_plus_gx_zt_hd_libretro.dll" --appendconfig "%HERE%zt-hd-retroarch.cfg" "%HERE%Zero Tolerance (high fps).gen"
