#!/bin/sh
# Build ew_core.dll (32-bit Windows) for the Steam release: Genesis Plus GX + Zero Tolerance HD renderer
# behind the Steam frontend's ew_* interface. Needs mingw-w64 (i686-w64-mingw32-gcc) and a clean
# Genesis-Plus-GX checkout:   sh build_steam.sh <Genesis-Plus-GX dir>
set -e
HERE=$(cd "$(dirname "$0")" && pwd)
G=$1
python3 "$HERE/../apply_zt_hd.py" "$G"
cd "$G"
# SSE2 floating point: the default x87 code made the HD renderer far too slow
CC="i686-w64-mingw32-gcc -march=pentium4 -mfpmath=sse"
make -f Makefile.libretro platform=win CC="$CC" CXX=i686-w64-mingw32-g++ AR=i686-w64-mingw32-ar -j8 > build.log 2>&1
$CC -O2 -Ilibretro/libretro-common/include -c "$HERE/ew_wrap.c" -o ew_wrap.o
OBJS=$(tail -1 build.log | sed -e "s/^.*-o genesis_plus_gx_libretro.dll //" -e 's/ -shared.*//')
# shellcheck disable=SC2086
$CC -shared -o ew_core.dll $OBJS ew_wrap.o -static-libgcc -lm
echo "built $G/ew_core.dll"
