#!/bin/sh
# Release packages (no game data) into release/:
#   sh make_release.sh <version> <steam ew_core.dll> <windows x64 core .dll> <macOS arm64 core .dylib> <macOS x86_64 core .dylib>
# Build the binaries first (README.md); patch/zt_high_fps.ips comes from python3 patch/make_patch.py.
set -e
V=$1; STEAM_DLL=$2; WIN_DLL=$3; MAC_ARM=$4; MAC_X86=$5
HERE=$(cd "$(dirname "$0")" && pwd)
OUT="$HERE/release"; IPS="$HERE/patch/zt_high_fps.ips"
ROMIPS="Zero Tolerance (USA, Europe) (Rev A).ips"
[ -f "$IPS" ] || { echo "no $IPS: run python3 patch/make_patch.py"; exit 1; }
rm -rf "$OUT/$V"; mkdir -p "$OUT/$V"
crlf() { sed 's/$/\r/' "$1" > "$2"; }

# Steam drop-in
D="$OUT/$V/zero_tolerance_hd_steam"; mkdir -p "$D"
i686-w64-mingw32-strip -o "$D/ew_core.dll" "$STEAM_DLL"
crlf "$HERE/patch/steam_hd/README.txt" "$D/README.txt"
crlf "$HERE/patch/steam_hd/ew_core_options.cfg" "$D/ew_core_options.cfg"
crlf "$HERE/patch/steam_hd/ztcrt.fs" "$D/ztcrt.fs"
crlf "$HERE/LICENSE" "$D/LICENSE.txt"

# Windows RetroArch
D="$OUT/$V/zero_tolerance_hd_windows_retroarch"; mkdir -p "$D"
x86_64-w64-mingw32-strip -o "$D/genesis_plus_gx_zt_hd_libretro.dll" "$WIN_DLL"
cp "$IPS" "$D/$ROMIPS"
cp "$HERE/patch/windows/play_zt_hd.bat" "$D/"
crlf "$HERE/patch/windows/README.txt" "$D/README.txt"
crlf "$HERE/patch/windows/zt-hd-core-options.cfg" "$D/zt-hd-core-options.cfg"
crlf "$HERE/LICENSE" "$D/LICENSE.txt"

# macOS RetroArch
D="$OUT/$V/zero_tolerance_hd_macos_retroarch"; mkdir -p "$D/tools"
strip -x -o "$D/tools/genesis_plus_gx_zt_hd.dylib" "$MAC_ARM"
strip -x -o "$D/tools/genesis_plus_gx_zt_hd_x86_64.dylib" "$MAC_X86"
cp "$IPS" "$D/$ROMIPS"
cp "$HERE/patch/play_mac.sh" "$D/"
cp "$HERE/patch/tools/retroarch-zt-hd.cfg" "$HERE/patch/tools/zt-hd-core-options.cfg" "$D/tools/"
cp "$HERE/patch/mac/README.txt" "$D/README.txt"
cp "$HERE/LICENSE" "$D/LICENSE.txt"

cd "$OUT/$V"
for p in zero_tolerance_hd_steam zero_tolerance_hd_windows_retroarch zero_tolerance_hd_macos_retroarch; do
  rm -f "$p-$V.zip"; zip -qr -X "$p-$V.zip" "$p"
done
ls -la "$OUT/$V"/*.zip
