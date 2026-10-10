#!/bin/sh
# Zero Tolerance HD on macOS: runs the game in RetroArch (/Applications/RetroArch.app) with the HD core.
# Expects the patched ROM next to this script (python3 make_patch.py) and the core(s) in tools/
# (see port/core/README.md).
HERE=$(cd "$(dirname "$0")" && pwd)
T="$HERE/tools"
case "$(uname -m)" in arm64) CORE=genesis_plus_gx_zt_hd.dylib ;; *) CORE=genesis_plus_gx_zt_hd_x86_64.dylib ;; esac
# an Intel-only RetroArch needs the x86_64 core even on Apple Silicon (it runs under Rosetta)
if [ "$(file -b /Applications/RetroArch.app/Contents/MacOS/RetroArch | grep -c arm64)" = 0 ]; then CORE=genesis_plus_gx_zt_hd_x86_64.dylib; fi
# RetroArch settings for this game only: the template plus the core options file's absolute path
CFG="$T/retroarch-zt-hd.local.cfg"
{ cat "$T/retroarch-zt-hd.cfg"; echo "core_options_path = \"$T/zt-hd-core-options.cfg\""; } > "$CFG"
open -a /Applications/RetroArch.app --args -L "$T/$CORE" --appendconfig "$CFG" "$HERE/Zero Tolerance (high fps).gen"
