#!/bin/sh
# Zero Tolerance HD on macOS: runs the game in RetroArch (/Applications/RetroArch.app) with the HD core.
# The game: "Zero Tolerance (high fps).gen" next to this script (python3 make_patch.py), or your own
# "Zero Tolerance (USA, Europe) (Rev A).gen" with the .ips of the same name, which RetroArch applies as it
# loads it. The core(s) in tools/ (see port/core/README.md). Another game: pass its patched ROM, e.g.
#   sh play_mac.sh "ZTU (high fps).bin"      (Underground; also "ZT (high fps).bin", "BZT (high fps).bin")
HERE=$(cd "$(dirname "$0")" && pwd)
T="$HERE/tools"
if [ -n "$1" ]; then
  case "$1" in /*) ROM="$1" ;; *) ROM="$HERE/$1"; [ -f "$ROM" ] || ROM="$PWD/$1" ;; esac
else
  ROM="$HERE/Zero Tolerance (high fps).gen"
  [ -f "$ROM" ] || ROM="$HERE/Zero Tolerance (USA, Europe) (Rev A).gen"
fi
if [ ! -f "$ROM" ]; then
  echo "No game: put your copy, named \"Zero Tolerance (USA, Europe) (Rev A).gen\", next to this script, or pass a ROM."
  exit 1
fi
case "$(uname -m)" in arm64) CORE=genesis_plus_gx_zt_hd.dylib ;; *) CORE=genesis_plus_gx_zt_hd_x86_64.dylib ;; esac
# an Intel-only RetroArch needs the x86_64 core even on Apple Silicon (it runs under Rosetta)
if [ "$(file -b /Applications/RetroArch.app/Contents/MacOS/RetroArch | grep -c arm64)" = 0 ]; then CORE=genesis_plus_gx_zt_hd_x86_64.dylib; fi
# a downloaded core is quarantined and RetroArch would refuse to load it
xattr -d com.apple.quarantine "$T/$CORE" 2>/dev/null
# RetroArch settings for this game only: the template plus the core options file's absolute path
CFG="$T/retroarch-zt-hd.local.cfg"
{ cat "$T/retroarch-zt-hd.cfg"; echo "core_options_path = \"$T/zt-hd-core-options.cfg\""; } > "$CFG"
open -a /Applications/RetroArch.app --args -L "$T/$CORE" --appendconfig "$CFG" "$ROM"
