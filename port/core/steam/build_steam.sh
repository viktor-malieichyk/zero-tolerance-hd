#!/bin/sh
# Build ew_core.dll (32-bit Windows) for the Steam release: Genesis Plus GX + Zero Tolerance HD renderer
# behind the Steam frontend's ew_* interface, with the ROM patch built in (applied in memory to the
# game's untouched res/game). Needs mingw-w64 (i686-w64-mingw32-gcc), vasm (see the top-level README),
# a clean Genesis-Plus-GX checkout and the Steam game folder. The ROMs of the other supported games in this
# repo's root (patch/games.py) are built in as patches too, so the DLL can switch to them (in-game menu, Game)
# when a player puts those ROMs in the Steam game folder:
#   sh build_steam.sh <Genesis-Plus-GX dir> <Steam game folder>
set -e
HERE=$(cd "$(dirname "$0")" && pwd)
G=$(cd "$1" && pwd)
STEAM=$(cd "$2" && pwd)
P="$HERE/../../../patch"
python3 "$P/make_patch.py" --steam "$STEAM"
# the other games the DLL can switch to (Underground, Beyond...): the ROMs in this repo's root (games.py)
python3 "$P/make_patch.py" || true
# shellcheck disable=SC2046
eval set -- $(cd "$P" && python3 -c '
import shlex, pathlib, games
args = []
for key, g in games.GAMES.items():
    rom, ips = pathlib.Path("..", g["file"]), pathlib.Path(g["ips"])
    if rom.exists() and ips.exists():
        args += [g["menu"], str(rom.resolve()), str(ips.resolve())]
print(" ".join(shlex.quote(a) for a in args))')
python3 "$HERE/gen_ips_header.py" "$G/zt_steam_ips.h" "Zero Tolerance" "$STEAM/res/game" "$P/steam/zt_high_fps_steam.ips" "$@"
python3 "$HERE/../apply_zt_hd.py" "$G"
cd "$G"
# SSE2 floating point: the default x87 code made the HD renderer far too slow
CC="i686-w64-mingw32-gcc -march=pentium4 -mfpmath=sse"
make -f Makefile.libretro platform=win CC="$CC" CXX=i686-w64-mingw32-g++ AR=i686-w64-mingw32-ar -j8 > build.log 2>&1
$CC -O2 -DZT_STEAM_IPS -I. -Ilibretro/libretro-common/include -Ilibretro/deps/zlib-1.2.11 -c "$HERE/ew_wrap.c" -o ew_wrap.o
OBJS=$(tail -1 build.log | sed -e "s/^.*-o genesis_plus_gx_libretro.dll //" -e 's/ -shared.*//')
# shellcheck disable=SC2086
$CC -shared -o ew_core.dll $OBJS ew_wrap.o -static-libgcc -lm
echo "built $G/ew_core.dll"
