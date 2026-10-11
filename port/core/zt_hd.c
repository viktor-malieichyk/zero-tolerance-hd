/*
 * Zero Tolerance HD renderer for Genesis Plus GX (libretro).
 *
 * The game runs unchanged in emulation (with the zt_high_fps patch: fixed 10 Hz logic). At the end of
 * each logic tick's render, a snapshot of work RAM and that render's sprite draw calls is taken.
 * Every video frame, the 3D view is re-rendered natively at high resolution from the last two
 * snapshots (interpolated), with the game's own textures, shading, sprites and sky plane, and a
 * compact HUD cut from the emulated screen is composed on top. Non-gameplay screens are shown
 * scaled. See port/NOTES.md for the formats.
 */
#include "shared.h"
#include <math.h>
#include "zt_hd.h"
#include "zt_font.h"
#include <zlib.h>

extern uint16 zt_vdp_pixel(int index);

int zt_hd_enabled = 0;
int zt_hd_w = 1280, zt_hd_h = 720;
int zt_hd_layout = 0;                /* 0 HD only, 1 side by side, 2 top/bottom, 3 switch with a key */
float zt_hd_ui_scale = 0;            /* HUD scale; 0 = automatic (output height / 360) */
int zt_hd_weapon = 1;                /* draw the player's weapon sprite in the HD view */
int zt_hd_smooth = 1;                /* shading dither: 1 blend each pixel pair's two colours, 0 draw the pattern */
int zt_hd_sky_fill = 0;              /* scale the sky to fill the view height (aspect kept) */
int zt_hd_sky_ext = 2;               /* beyond the original sky band: 0 black, 1 the level's stars repeated,
                                        2 stars and the planet completed */
unsigned zt_hd_toggle_key = 'g';     /* RETROK code (letters are lowercase ASCII) */
unsigned zt_hd_menu_key = 'm';
int (*zt_hd_key)(unsigned retrok);   /* set by libretro.c: is this key held? */
void (*zt_hd_av_changed)(void);      /* set by libretro.c: output size changed */
char zt_hd_cfg_path[1024];           /* settings file written by the in-game menu */
char zt_hd_rom_dir[1024];            /* the game's folder: second place for the sky PNG */
static int show_original;            /* layout 3: currently showing the original screen */
static int menu_open, menu_sel;
static int rw, rh;                  /* current render panel size */
static int ow, oh;                  /* current output size */
float zt_hd_fov = 106.0f;
unsigned int zt_hd_after_pc = 0;
unsigned int zt_hd_dbg[8];
unsigned char zt_hd_dbg_regs[0x20], zt_hd_dbg_bg[0xA0];
double zt_hd_dbg_cam[8];
unsigned char *zt_hd_dbg_idx(void);          /* debug counters: hooks, ticks, sprites, commits, gameplay checks */

#define ORG_TABLE 0x1D0000
#define TEX_BASE  0x12EF26

/* ---------------------------------------------------------------- ROM / RAM access */
static uint8 *rom_be;               /* big-endian copy of the ROM */
static uint32 rom_size;
static int solid[256], door[256];   /* door: 0 none, 1 east-west, 2 north-south, +2 = sliding (3, 4) */
static int item_type[256];          /* cell types drawn as map items (handler $944E) */
static uint32 level_hnd[256];       /* multi-level wall types (stairs, pits, upper floors): handler address;
                                       1 = lift shaft walls ($9862) */
static int shade_of_h[82];          /* shade level per even native wall height (-1 none) */
static uint32 shaded_table;         /* $4392 */

static inline uint32 R8(uint32 a) { return a < rom_size ? rom_be[a] : 0; }
static inline uint32 R16(uint32 a) { return (R8(a) << 8) | R8(a + 1); }
static inline uint32 R32(uint32 a) { return (R16(a) << 16) | R16(a + 2); }

typedef struct {
  uint8 ram[0x10000];               /* big-endian image of $FF0000-$FFFFFF */
  int hor_walls, hor_spr;           /* horizon the game used for walls and edges / for sprites this tick */
  int nedge;                        /* floor/ceiling edges ($9D42/$9D4A list at $FF1182): corners in cells */
  struct { int8 x0, y0, x1, y1; uint8 flag; } edge[32];
  int npc;                          /* sprite pieces drawn by this tick's render ($EDA0 calls) */
  struct { uint32 obj, data, shade, list, rec; int16 x, y, col, row, w, h, acol, arow, ascale; uint8 mirror, type, gr, gc; } pc[256];
                                    /* obj: anchor id; x, y: anchor (8.8); type: map item type (0 = object) */
  uint32 vbl;
  int valid;
} snap_t;

static snap_t snaps[3];             /* [0] older, [1] newer, [2] being built */
static int building;
static uint32 anchor_id;            /* what the pieces being drawn belong to: object address or item cell */
static int16 anchor_x, anchor_y;
static int anchor_type;
static int16 anchor_col, anchor_row, anchor_scale;   /* map item: the game's exact centre column, row, scale */
static uint32 anchor_rec, anchor_pbase;              /* object sprite: sub-frame record and piece base ($1BCB4) */
static uint16 anchor_used;                           /* grid cells of the record already matched to pieces */

static inline uint32 M8(const snap_t *s, uint32 a) { return s->ram[a & 0xFFFF]; }
static inline uint32 M16(const snap_t *s, uint32 a) { return (M8(s, a) << 8) | M8(s, a + 1); }
static inline int32 S16(const snap_t *s, uint32 a) { return (int16)M16(s, a); }
static inline uint32 M32(const snap_t *s, uint32 a) { return (M16(s, a) << 16) | M16(s, a + 2); }

static inline uint32 A8(const snap_t *s, uint32 a) { return a >= 0xFF0000 ? M8(s, a) : R8(a); }   /* ROM or RAM */
static inline uint32 live_w(uint32 a) { return (READ_BYTE(work_ram, a & 0xFFFF) << 8) | READ_BYTE(work_ram, (a + 1) & 0xFFFF); }
static inline uint32 live_l(uint32 a) { return (live_w(a) << 16) | live_w(a + 2); }

static int prepare_rom(void)
{
  uint32 i, h;
  if (rom_be) return 1;
  if (cart.romsize < 0x1D0100) return 0;
  rom_size = cart.romsize;
  rom_be = malloc(rom_size);
  for (i = 0; i < rom_size; i++) rom_be[i] = READ_BYTE(cart.rom, i);
  if (memcmp(rom_be + 0x150, "ZERO TOLERANCE", 14) || R16(ORG_TABLE) != 0x6000)
  {
    free(rom_be); rom_be = NULL; return 0;          /* not the patched Zero Tolerance ROM */
  }
  zt_hd_after_pc = R32(ORG_TABLE + 52);
  /* cell type handlers ($9226 dispatch table at $923A) */
  for (i = 0; i < 256; i++)
  {
    uint32 hnd = i < 133 ? R32(0x923A + i * 4) : 0x9454;
    level_hnd[i] = (i >= 6 && hnd >= 0x945E && hnd < 0x9862) ? hnd : (i >= 6 && hnd == 0x9862) ? 1 : 0;
    solid[i] = (i == 1) || (i >= 6 && hnd == 0x9458) || level_hnd[i];
    item_type[i] = hnd == 0x944E;
    door[i] = (hnd == 0xAF5E) ? 1 : (hnd == 0xAD8C) ? 2 : (hnd == 0xB000) ? 3 : (hnd == 0xAE2E) ? 4 : 0;
  }
  /* shade level per height: first "movea.l -$71xx(a6),a3" (266E xxxx) in each column routine */
  shaded_table = 0x4392;
  for (h = 0; h < 82; h++) shade_of_h[h] = -1;
  for (h = 2; h <= 80; h += 2)
  {
    uint32 a = R32(shaded_table + h * 2), k;
    for (k = 0; k < 64; k += 2)
      if (R16(a + k) == 0x266E)
      {
        int32 d = (int16)R16(a + k + 2);
        if (d <= -0x715A && d >= -0x7176) { shade_of_h[h] = (0x7176 + d) / 4; break; }
      }
  }
  return 1;
}

/* ---------------------------------------------------------------- 68k hooks */
void zt_hd_hook(unsigned int pc, unsigned int *regs)
{
  snap_t *s = &snaps[2];
  uint32 i;
  if (!zt_hd_enabled || !prepare_rom()) return;
  zt_hd_dbg[0]++;
  if (pc == 0xB9A6)                                   /* render start */
  {
    if (live_w(0xFF7762)) return;                     /* between-ticks render: not a tick */
    zt_hd_dbg[1]++;
    building = 1; s->npc = 0; s->nedge = 0; anchor_id = 0;
    s->hor_walls = s->hor_spr = (int16)live_w(0xFF0E1A);
  }
  else if (pc == 0x9D72 && building)                  /* edge pass: list of corner pairs (relative to the camera cell) */
  {
    int n = live_w(0xFF1180), k, cx = (int16)live_w(0xFF0E06), cy = (int16)live_w(0xFF0E08);
    s->nedge = 0;
    s->hor_walls = (int16)live_w(0xFF0E1A);
    for (k = 0; k < n && k < 32; k++)
    {
      uint32 e = 0xFF1182 + k * 6;
      s->edge[k].x0 = (int8)READ_BYTE(work_ram, e & 0xFFFF) + cx; s->edge[k].y0 = (int8)READ_BYTE(work_ram, (e + 1) & 0xFFFF) + cy;
      s->edge[k].x1 = (int8)READ_BYTE(work_ram, (e + 2) & 0xFFFF) + cx; s->edge[k].y1 = (int8)READ_BYTE(work_ram, (e + 3) & 0xFFFF) + cy;
      s->edge[k].flag = live_w(e + 4) != 0;
      s->nedge++;
    }
  }
  else if (pc == 0x1329A && building)                 /* sprite projection: horizon now includes the elevation fix-up */
    s->hor_spr = (int16)live_w(0xFF0E1A);
  else if ((pc == 0x13360 || pc == 0x13388) && building)   /* object draw routine: a0 = object */
  {
    anchor_id = regs[8] & 0xFFFFFF; anchor_type = 0; anchor_rec = 0;
    anchor_x = live_w(anchor_id + 0x20); anchor_y = live_w(anchor_id + 0x22);
  }
  else if (pc == 0x1BCB4 && building && anchor_id && !(anchor_id & 0x1000000))
  {
    /* object sprite routine: a1 = sub-frame record (+0/+1 x/y anchor, +2/+3 piece width/height factors,
       +4/+5 grid columns/rows, +6 attributes, +$16 piece ids), a2 = piece base. Its pieces' layout is
       computed exactly from the record instead of from the rounded rectangles */
    anchor_rec = regs[9] & 0xFFFFFF; anchor_pbase = regs[10] & 0xFFFFFF; anchor_used = 0;
  }
  else if (pc == 0x113EE && building)                 /* map item (pickup): a3 = record (cell relative to $FF0E06/08) */
  {
    uint32 r = regs[11] & 0xFFFFFF;
    int cx = (live_w(r + 2) + live_w(0xFF0E06)) & 31, cy = (live_w(r) + live_w(0xFF0E08)) & 31;   /* +0 dy, +2 dx */
    anchor_id = 0x1000000 | cy << 8 | cx;              /* items don't move: the cell is the id */
    anchor_rec = 0;
    anchor_x = (cx << 8) + 0x80; anchor_y = (cy << 8) + 0x80;
    anchor_type = READ_BYTE(work_ram, (r + 5) & 0xFFFF);
    anchor_col = regs[1]; anchor_row = regs[2]; anchor_scale = regs[5];   /* d1, d2 ($113E8), d5 */
  }
  else if (pc == 0xEDA0 && building)                  /* sprite piece: d1/d2 column/row, d4 x d0 size, a1 texels */
  {
    int16 h = regs[0], w = regs[4];
    uint32 list = live_l(0xFF1096), shade;
    zt_hd_dbg[2]++;
    if (h <= 0 || w <= 0 || s->npc >= 256 || !anchor_id) return;
    if (list == 0xED50) shade = R32(0xED50);          /* unshaded */
    else
    {
      int d3 = ((int16)live_w(0xFF1094) >> 3) - 1;    /* the drawer's level from the scale; too far = not drawn */
      if (d3 < 0) return;
      d3 = 4 - d3; if (d3 < 0) d3 = 0;
      shade = (list + d3 * 4) >= 0xFF0000 ? live_l(list + d3 * 4) : R32(list + d3 * 4);
    }
    s->pc[s->npc].type = anchor_type; s->pc[s->npc].list = list;
    s->pc[s->npc].acol = anchor_col; s->pc[s->npc].arow = anchor_row; s->pc[s->npc].ascale = anchor_scale;
    s->pc[s->npc].rec = 0;
    if (anchor_rec)                                    /* which grid cell of the record this piece is */
    {
      uint32 pid = ((regs[9] & 0xFFFFFF) - anchor_pbase) >> 9;
      int cols = R8(anchor_rec + 4), rows = R8(anchor_rec + 5), r, c;
      for (r = 0; r < rows && r < 4; r++)
        for (c = 0; c < cols && c < 4; c++)
          if (!(anchor_used & (1 << (r * 4 + c))) && R8(anchor_rec + 0x16 + r * 4 + c) == pid)
          {
            anchor_used |= 1 << (r * 4 + c);
            s->pc[s->npc].rec = anchor_rec; s->pc[s->npc].gr = r; s->pc[s->npc].gc = c;
            r = c = 99;
          }
    }
    s->pc[s->npc].obj = anchor_id; s->pc[s->npc].x = anchor_x; s->pc[s->npc].y = anchor_y;
    s->pc[s->npc].data = regs[9] & 0xFFFFFF; s->pc[s->npc].shade = shade;
    s->pc[s->npc].col = regs[1]; s->pc[s->npc].row = regs[2]; s->pc[s->npc].w = w; s->pc[s->npc].h = h;
    s->pc[s->npc].mirror = live_w(0xFF1088) != 0;
    s->npc++;
  }
  else if (pc == zt_hd_after_pc && building)          /* tick render finished: commit */
  {
    for (i = 0; i < 0x10000; i++) s->ram[i] = READ_BYTE(work_ram, i);
    s->vbl = M16(s, 0xFF0000);
    s->valid = 1;
    snaps[0] = snaps[1];
    snaps[1] = *s;
    building = 0;
    zt_hd_dbg[3]++;
  }
}

/* ---------------------------------------------------------------- camera */
typedef struct { double x, y, ang, hor, dx, dy, px, py; } cam_t;

static double wrapd(double d, double m) { while (d >= m / 2) d -= m; while (d < -m / 2) d += m; return d; }

static void snap_cam(const snap_t *s, double *x, double *y, double *a, double *h)
{
  /* ZT_CUR ($FF774C): this tick's camera as the game rendered it (x, y, angle, horizon) */
  *x = M16(s, 0xFF774C); *y = M16(s, 0xFF774E); *a = M16(s, 0xFF7750) & 511; *h = S16(s, 0xFF7752);
}

static void make_cam(cam_t *c, double t)
{
  double x0, y0, a0, h0, x1, y1, a1, h1, th;
  snap_cam(&snaps[1], &x1, &y1, &a1, &h1);
  if (snaps[0].valid) snap_cam(&snaps[0], &x0, &y0, &a0, &h0); else { x0 = x1; y0 = y1; a0 = a1; h0 = h1; }
  if (fabs(wrapd(x1 - x0, 8192)) > 512 || fabs(wrapd(y1 - y0, 8192)) > 512 || fabs(wrapd(a1 - a0, 512)) > 96)
    t = 1;                                            /* teleport: no interpolation */
  c->x = x0 + wrapd(x1 - x0, 8192) * t; c->y = y0 + wrapd(y1 - y0, 8192) * t;
  c->ang = a0 + wrapd(a1 - a0, 512) * t; c->hor = h0 + (h1 - h0) * t;
  th = c->ang * 2 * M_PI / 512;
  c->dx = sin(th); c->dy = -cos(th);                  /* angle 0 = -Y, 128 = +X */
  c->px = (c->x - c->dx * 32) / 256.0;                /* the game pulls back by dir/8 */
  c->py = (c->y - c->dy * 32) / 256.0;
}

/* ---------------------------------------------------------------- frame buffers */
static uint8 *idx;          /* per pixel colour index 0..15, 0 = transparent (sky) */
static uint8 *dark_col;     /* per column: the floor and ceiling around the wall are solid colour 1 */
/* idx holds the game's pixel-pair byte (two 4-bit colours; the game's shading and floor gradient use
   different colours in the two halves as a dither). Smooth: kept whole and blended when composed.
   Dither: one half picked by the pattern `sel`, stored in both halves. */
#define PIX(b, sel) (zt_hd_smooth ? (uint8)(b) : (uint8)((((sel) ? ((b) & 15) : ((b) >> 4))) * 0x11))
static float *wdist;        /* per column wall distance */
static uint16 *hd;          /* output RGB565 */

void zt_hd_output_size(int *w, int *h)
{
  int pw = zt_hd_w / 2, ph = (pw * 9 / 16) & ~1;                                 /* 16:9 panels */
  if (zt_hd_layout == 1) { *w = zt_hd_w; *h = ph; }
  else if (zt_hd_layout == 2) { *w = pw; *h = 2 * ph; }
  else { *w = zt_hd_w; *h = zt_hd_h; }
}

static void ensure_buffers(void)
{
  static int bw, bh;
  if (bw == zt_hd_w && bh == zt_hd_h && hd) return;
  free(idx); free(wdist); free(hd); free(dark_col);
  idx = malloc(zt_hd_w * zt_hd_h); wdist = malloc(sizeof(float) * zt_hd_w); dark_col = malloc(zt_hd_w); hd = malloc(2 * zt_hd_w * zt_hd_h);
  bw = zt_hd_w; bh = zt_hd_h;
}

unsigned char *zt_hd_dbg_idx(void) { return idx; }

/* ---------------------------------------------------------------- doors */
/* open offset (0 closed .. $80 open) of a sliding door: list of moving doors at $FF0EC6 (14-byte
   entries: map cell address, offset word), end pointer at $FF0EC2 ($B33A) */
static int door_offset(const snap_t *s, uint32 cell_addr)
{
  uint32 p = 0xFF0EC6, end = M32(s, 0xFF0EC2);
  int k;
  for (k = 0; p < end && k < 64; p += 14, k++)
    if (M32(s, p) == cell_addr) return S16(s, p + 4);
  return 0;
}

/* ---------------------------------------------------------------- walls */
static inline int texel(uint32 tid, int col, int v) { return R8(TEX_BASE + tid * 512 + col * 32 + v); }

/* Face modes of a multi-level wall cell: per face (N, S, E, W) two signed bytes, the vertical offset at the
   face's left and right ends as the viewer sees it (64 = one wall height). The cell handlers ($945E-$9861)
   only test the player's elevation ($FF116E) or the cell's side (d0/d1 = cell - camera cell) and store
   constants; they are interpreted here. Lift walls ($9862) are offset by the elevation's low byte. */
static int face_modes(const snap_t *s, uint32 hnd, int d0, int d1, uint16 m[4])
{
  int z = S16(s, 0xFF116E), v = 0, n, i;
  uint32 pc = hnd;
  m[0] = m[1] = m[2] = m[3] = 0;
  if (hnd == 1)
  {
    int b = (z & 0xFF) | 1;
    m[0] = m[1] = m[2] = m[3] = b << 8 | b;
    return 1;
  }
  for (n = 0; n < 32; n++)
  {
    uint32 op = R16(pc);
    if (op == 0x4A6E && R16(pc + 2) == 0x916E) { v = z; pc += 4; }                    /* tst.w -$6e92(a6) */
    else if (op == 0x4A40) { v = d0; pc += 2; }                                       /* tst.w d0 */
    else if (op == 0x4A41) { v = d1; pc += 2; }                                       /* tst.w d1 */
    else if ((op >> 12) == 6)                                                         /* bxx.b */
    {
      int cc = (op >> 8) & 15, t = 0;
      if (cc == 0) t = 1;                       /* bra */
      else if (cc == 7) t = v == 0;             /* beq */
      else if (cc == 15) t = v <= 0;            /* ble */
      else if (cc == 11) t = v < 0;             /* bmi */
      else if (cc == 10) t = v >= 0;            /* bpl */
      else if (cc == 6) t = v != 0;             /* bne */
      else if (cc == 14) t = v > 0;             /* bgt */
      else if (cc == 12) t = v >= 0;            /* bge */
      else if (cc == 13) t = v < 0;             /* blt */
      else return 0;
      pc = t ? pc + 2 + (int8)(op & 0xFF) : pc + 2;
    }
    else if (op == 0x2D7C)                                                            /* move.l #imm, d16(a6) */
    {
      uint32 imm = R32(pc + 2); int d = (int16)R16(pc + 6);
      i = (d + 0x6E8C) / 2;                     /* -$6e8c N, -$6e8a S, -$6e88 E, -$6e86 W */
      if (i >= 0 && i < 3) { m[i] = imm >> 16; m[i + 1] = imm & 0xFFFF; }
      pc += 8;
    }
    else if (op == 0x363C) pc += 4;                                                   /* move.w #imm, d3 */
    else if (op == 0x4E75) return 1;                                                  /* rts */
    else return 0;
  }
  return 0;
}

static void draw_column(const snap_t *s, int x, double dist, uint32 cell, int face_word, double u,
                        double focal, double hor, int H, int mode)
{
  double k = focal / 2, h = k / dist, mid, y0;
  if (mode)
  {
    int hi = (int8)(mode >> 8), lo = (int8)mode;
    hor += hi + (lo - hi) * u;                  /* the game adds the offset to the horizon ($D0C4) */
    dark_col[x] = 1;
  }
  mid = H / 2.0 + h * hor / 64.0;               /* native: shift = height * horizon / 64 rows ($D202) */
  y0 = mid - h / 2;
  int sub = (int)(u * 128), ucol, half, y, ystart, yend, sh = -1;
  uint32 fw, top, bot, st;
  if (sub < 0) sub = 0; if (sub > 127) sub = 127;
  ucol = sub >> 1; half = sub & 1;               /* a texel byte is two pixels side by side (hi, lo nibble) */
  fw = face_word;
  st = 0xFF63C6 + fw * 16 + (ucol >> 4) * 4;
  top = M16(s, st); bot = M16(s, st + 2);
  if (M32(s, 0xFF0EAA) == shaded_table)
  {
    int hn = ((int)(64.0 / dist)) & ~1;
    if (hn >= 2 && hn <= 80) sh = shade_of_h[hn];
  }
  ystart = (int)ceil(y0); if (ystart < 0) ystart = 0;
  yend = (int)ceil(y0 + h); if (yend > H) yend = H;
  if (ystart < yend)
  {
    uint8 colc[64];                              /* the column's 64 texels: this half's colour, shaded */
    uint32 shade = sh >= 0 ? M32(s, 0xFF0E8A + sh * 4) : 0;
    double tv = (ystart - y0) * 64 / h, step = 64 / h;
    uint8 *dst = idx + ystart * rw + x;
    int v;
    for (v = 0; v < 64; v++)
    {
      int b = v < 32 ? texel(top, ucol & 15, v) : texel(bot, ucol & 15, v - 32);
      b = (half ? b & 15 : b >> 4) * 0x11;       /* 0 = transparent (sky) */
      if (shade && b) b = R8(shade + b);         /* shading may dither two levels */
      colc[v] = b;
    }
    {
      /* 16.16 fixed point texel row; the dither choice (smooth or pattern) hoisted out of the loop */
      int32 fv = (int32)(tv * 65536), fs = (int32)(step * 65536);
      if (zt_hd_smooth)
        for (y = ystart; y < yend; y++, fv += fs, dst += rw) { int t = fv >> 16; *dst = colc[t > 63 ? 63 : t]; }
      else
        for (y = ystart; y < yend; y++, fv += fs, dst += rw)
        {
          int t = fv >> 16, b = colc[t > 63 ? 63 : t];
          *dst = (uint8)((((x + y) & 1) ? (b & 15) : (b >> 4)) * 0x11);
        }
    }
  }
  if (mode)                                     /* multi-level walls: floor and ceiling from $D074 (colour 1) */
  {
    for (y = 0; y < ystart; y++) idx[y * rw + x] = 0x11;
    for (y = yend < 0 ? 0 : yend; y < H; y++) idx[y * rw + x] = 0x11;
  }
}

static void render_walls(const snap_t *s, const cam_t *c, int W, int H, double focal)
{
  double half = (W / 2.0) / focal;
  double plx = -c->dy * half, ply = c->dx * half;
  uint32 mapp = M32(s, 0xFF1024);
  int x;
  for (x = 0; x < W; x++)
  {
    double camx = 2 * (x + 0.5) / W - 1, rx = c->dx + plx * camx, ry = c->dy + ply * camx;
    int mx = (int)floor(c->px), my = (int)floor(c->py), stepx, stepy, side = 0, it;
    double ddx = rx ? fabs(1 / rx) : 1e30, ddy = ry ? fabs(1 / ry) : 1e30, sdx, sdy;
    wdist[x] = 1e9f; dark_col[x] = 0;
    if (rx > 0) { stepx = 1; sdx = (mx + 1 - c->px) * ddx; } else { stepx = -1; sdx = (c->px - mx) * ddx; }
    if (ry > 0) { stepy = 1; sdy = (my + 1 - c->py) * ddy; } else { stepy = -1; sdy = (c->py - my) * ddy; }
    if (mx >= 0 && mx < 32 && my >= 0 && my < 32)
    {
      /* the camera's own cell: a diagonal wall in it (the player can stand in the open half) is hit before
         the ray leaves the cell. The original doesn't test it and draws an empty view there. */
      uint32 cell = M8(s, mapp + my * 32 + mx), ct = M8(s, 0xFF7BC6 + cell);
      if (ct >= 2 && ct <= 5)
      {
        static const int dw[6] = {0, 0, 3, 0, 0, 3};
        static const double d[6][4] = {{0}, {0}, {0, 0, 1, 1}, {1, 0, 0, 1}, {1, 1, 0, 0}, {0, 1, 1, 0}};
        double ax = mx + d[ct][0], ay = my + d[ct][1], bx = mx + d[ct][2], by = my + d[ct][3];
        double den = rx * (by - ay) - ry * (bx - ax), tout = sdx < sdy ? sdx : sdy, t;
        int open = (bx - ax) * (c->py - ay) - (by - ay) * (c->px - ax) >= 0;
        if (open && fabs(den) > 1e-12)
        {
          t = ((ax - c->px) * (by - ay) - (ay - c->py) * (bx - ax)) / den;
          if (t > 1e-6 && t <= tout + 1e-9)
          {
            double hx = c->px + rx * t, hy = c->py + ry * t;
            double u = sqrt((hx - ax) * (hx - ax) + (hy - ay) * (hy - ay)) / sqrt(2.0);
            draw_column(s, x, t, cell, M16(s, 0xFF73C6 + cell * 8 + dw[ct] * 2), u, focal, c->hor, H, 0);
            wdist[x] = (float)t;
            continue;
          }
        }
      }
    }
    for (it = 0; it < 64; it++)
    {
      uint32 cell, ct;
      double tin;
      if (sdx < sdy) { sdx += ddx; mx += stepx; side = 0; } else { sdy += ddy; my += stepy; side = 1; }
      if (mx < 0 || mx > 31 || my < 0 || my > 31) break;
      cell = M8(s, mapp + my * 32 + mx); ct = M8(s, 0xFF7BC6 + cell);
      tin = side == 0 ? sdx - ddx : sdy - ddy;
      if (solid[ct])
      {
        int face; double u;
        if (side == 0) { double wy = c->py + tin * ry; face = stepx > 0 ? 1 : 2; u = wy - floor(wy); if (face == 2) u = 1 - u; }
        else { double wx = c->px + tin * rx; face = stepy > 0 ? 0 : 3; u = wx - floor(wx); if (face == 0) u = 1 - u; }
        int mode = 0;
        if (level_hnd[ct])
        {
          static const int mi[4] = {0, 3, 2, 1};      /* our faces N W E S -> mode words N S E W */
          uint16 m[4];
          if (face_modes(s, level_hnd[ct], mx - S16(s, 0xFF0E06), my - S16(s, 0xFF0E08), m)) mode = m[mi[face]];
        }
        draw_column(s, x, tin, cell, M16(s, 0xFF73C6 + cell * 8 + face * 2), u, focal, c->hor, H, mode);
        wdist[x] = (float)tin;
        break;
      }
      if (door[ct])
      {
        /* door: two half-panels across the cell middle, each slid away from the centre by the open
           offset; the u 0..0.5 half (strips 0-1) moves towards the viewer's-left end. Rays pass. */
        double ax, ay, bx, by, o = 0, tout = sdx < sdy ? sdx : sdy, best = 1e30, bu = 0;
        int p;
        if (door[ct] >= 3)
        {
          int d3 = door_offset(s, mapp + my * 32 + mx);
          if (d3 >= 0x80) continue;
          o = d3 / 256.0;
        }
        if (door[ct] == 1 || door[ct] == 3) { ax = mx; ay = my + .5; bx = mx + 1; by = my + .5; }
        else { ax = mx + .5; ay = my; bx = mx + .5; by = my + 1; }
        if ((bx - ax) * (c->py - ay) - (by - ay) * (c->px - ax) < 0)
        { double tx = ax, ty = ay; ax = bx; ay = by; bx = tx; by = ty; }       /* u=0 on the viewer's left */
        for (p = 0; p < 2; p++)
        {
          double ux = bx - ax, uy = by - ay;                   /* unit vector along the face */
          double p0 = p ? 0.5 + o : -o, p1 = p ? 1 + o : 0.5 - o;
          double qax = ax + ux * p0, qay = ay + uy * p0, qbx = ax + ux * p1, qby = ay + uy * p1;
          double den = rx * (qby - qay) - ry * (qbx - qax), t, sp;
          if (fabs(den) < 1e-12) continue;
          t = ((qax - c->px) * (qby - qay) - (qay - c->py) * (qbx - qax)) / den;
          if (t < tin - 1e-9 || t > tout + 1e-9 || t >= best) continue;
          sp = ((c->px + rx * t - qax) * ux + (c->py + ry * t - qay) * uy) / (p1 - p0);
          if (sp < 0 || sp > 1) continue;
          best = t; bu = p * 0.5 + sp * 0.5;
        }
        if (best < 1e29)
        {
          draw_column(s, x, best, cell, 0x12, bu, focal, c->hor, H, 0);
          wdist[x] = (float)best; break;
        }
        continue;
      }
      if (ct >= 2 && ct <= 5)
      {
        static const int dw[6] = {0, 0, 3, 0, 0, 3};
        static const double d[6][4] = {{0}, {0}, {0, 0, 1, 1}, {1, 0, 0, 1}, {1, 1, 0, 0}, {0, 1, 1, 0}};
        double ax = mx + d[ct][0], ay = my + d[ct][1], bx = mx + d[ct][2], by = my + d[ct][3];
        double ex = c->px + rx * tin, ey = c->py + ry * tin, den, t, tout = sdx < sdy ? sdx : sdy;
        int fw = M16(s, 0xFF73C6 + cell * 8 + dw[ct] * 2);
        if ((bx - ax) * (ey - ay) - (by - ay) * (ex - ax) < -1e-9)        /* entered the solid half */
        {
          int face; double u;
          if (side == 0) { face = stepx > 0 ? 1 : 2; u = ey - floor(ey); if (face == 2) u = 1 - u; }
          else { face = stepy > 0 ? 0 : 3; u = ex - floor(ex); if (face == 0) u = 1 - u; }
          draw_column(s, x, tin, cell, M16(s, 0xFF73C6 + cell * 8 + face * 2), u, focal, c->hor, H, 0);
          wdist[x] = (float)tin; break;
        }
        den = rx * (by - ay) - ry * (bx - ax);
        if (fabs(den) > 1e-12)
        {
          t = ((ax - c->px) * (by - ay) - (ay - c->py) * (bx - ax)) / den;
          if (t >= tin - 1e-9 && t <= tout + 1e-9)
          {
            double hx = c->px + rx * t, hy = c->py + ry * t;
            double u = sqrt((hx - ax) * (hx - ax) + (hy - ay) * (hy - ay)) / sqrt(2.0);
            draw_column(s, x, t, cell, fw, u, focal, c->hor, H, 0);
            wdist[x] = (float)t; break;
          }
        }
      }
    }
  }
}

/* ---------------------------------------------------------------- floor / ceiling */
static void render_background(const snap_t *s, int W, int H, double f)
{
  int x, y;
  for (y = 0; y < H; y++)
  {
    /* a row repeats every 4 pixels: two bytes (even/odd buffer column), each two halves */
    int r = (int)floor(40 + (y + 0.5 - H / 2.0) / f + 0.5);
    uint32 b0, b1, pat;
    uint8 *row = idx + y * W, p4[4];
    if (r < 0) r = 0; if (r > 79) r = 79;
    b0 = M8(s, 0xFF6226 + 0x50 + r); b1 = M8(s, 0xFF6226 + r);
    p4[0] = PIX(b0, 0); p4[1] = PIX(b0, 1); p4[2] = PIX(b1, 0); p4[3] = PIX(b1, 1);
    memcpy(&pat, p4, 4);
    for (x = 0; x + 4 <= W; x += 4) memcpy(row + x, &pat, 4);
    for (; x < W; x++) row[x] = p4[x & 3];
  }
}

/* Floor/ceiling edges (map types $31-$5B, e.g. the line where a roofed room starts): in each column where
   the edge is nearer than the wall, the floor and ceiling between the viewer and the edge are repainted
   with the normal background (flag) or solid colour 1 ($D5CE). Columns without a wall get the normal
   background afterwards ($7F92) unless the player's cell type says otherwise (table $BB90). */
static void render_edges(const snap_t *s, const cam_t *c, int W, int H, double focal)
{
  double half = (W / 2.0) / focal, plx = -c->dy * half, ply = c->dx * half, f = (focal / 2) / 64.0;
  uint32 pcell = M32(s, 0xFF0E12);
  int k, x, y, empty_last = R8(0xBB90 + M8(s, 0xFF7BC6 + M8(s, pcell))) != 0;
  for (k = 0; k < s->nedge; k++)
  {
    double ax = s->edge[k].x0, ay = s->edge[k].y0, bx = s->edge[k].x1, by = s->edge[k].y1;
    for (x = 0; x < W; x++)
    {
      double camx = 2 * (x + 0.5) / W - 1, rx = c->dx + plx * camx, ry = c->dy + ply * camx;
      double den = rx * (by - ay) - ry * (bx - ax), t, sp, he, mid;
      int y0, y1;
      if (fabs(den) < 1e-12) continue;
      t = ((ax - c->px) * (by - ay) - (ay - c->py) * (bx - ax)) / den;
      sp = ((c->px - ax) * ry - (c->py - ay) * rx) / -den;
      if (t <= 0.01 || sp < 0 || sp > 1 || t >= wdist[x]) continue;
      if (wdist[x] > 1e8f && !empty_last) continue;
      he = (focal / 2) / t; mid = H / 2.0 + he * c->hor / 64.0;
      y0 = (int)ceil(mid - he / 2); y1 = (int)ceil(mid + he / 2);
      for (y = 0; y < H; y++)
      {
        if (y >= y0 && y < y1) { y = y1 - 1; continue; }
        if (s->edge[k].flag)
        {
          int r = (int)floor(40 + (y + 0.5 - H / 2.0) / f + 0.5);
          uint32 b;
          if (r < 0) r = 0; if (r > 79) r = 79;
          b = M8(s, 0xFF6226 + (((x >> 1) & 1) ? 0 : 0x50) + r);
          idx[y * W + x] = PIX(b, x & 1);
        }
        else idx[y * W + x] = 0x11;
      }
    }
  }
}

/* ---------------------------------------------------------------- sprites */
/* a piece's anchor position (cells); interpolated when the previous tick drew the same anchor */
static void piece_pos(const snap_t *s, const snap_t *s0, int i, double t, double *x, double *y)
{
  int k;
  *x = s->pc[i].x / 256.0; *y = s->pc[i].y / 256.0;
  if (!s0->valid || t >= 1) return;
  for (k = 0; k < s0->npc; k++)
    if (s0->pc[k].obj == s->pc[i].obj)
    {
      double x0 = s0->pc[k].x / 256.0, y0 = s0->pc[k].y / 256.0;
      if (fabs(*x - x0) < 2 && fabs(*y - y0) < 2) { *x = x0 + (*x - x0) * t; *y = y0 + (*y - y0) * t; }
      return;
    }
}

/* shade table for a piece drawn at native scale sc with shade list `list` (as the drawer at $EDD0); 0 = not drawn */
static uint32 piece_shade(const snap_t *s, uint32 list, double sc)
{
  int d3;
  if (list == 0xED50) return R32(0xED50);
  d3 = ((int)sc >> 3) - 1;
  if (d3 < 0) return 0;
  d3 = 4 - d3; if (d3 < 0) d3 = 0;
  return (list + d3 * 4) >= 0xFF0000 ? M32(s, list + d3 * 4) : R32(list + d3 * 4);
}

/* a sprite piece to draw: anchor position (cells), offset and size in units of 1/scale (native columns
   and rows at scale 1), 16x32 texels */
typedef struct { double x, y, depth, du, dv, pw, ph; uint32 data, shade; int mirror, item; } dpiece_t;
double zt_hd_dbg_piece[8];          /* debug: first map item piece drawn this frame */
double zt_hd_dbg_obj[8];            /* debug: first object piece drawn this frame */

/* map items the game didn't list this tick (outside its 90 degree cast at a wider HD FOV) are drawn with
   the last pieces seen for their type */
#define ITEM_CACHE 8
static struct { int n; double du[ITEM_CACHE], dv[ITEM_CACHE], pw[ITEM_CACHE], ph[ITEM_CACHE], best[ITEM_CACHE];
                uint32 data[ITEM_CACHE], list[ITEM_CACHE]; int mirror[ITEM_CACHE]; uint32 tick; } item_cache[256];
/* An item piece's layout (offset from the item's centre column and floor row, and size, in units of the
   item's scale) is a fixed fraction of the scale per item type (e.g. 1/4 wide, 1/8 left of centre), but the
   game's rect is in whole native columns and rows: one tick's measurement can be off by 1.5/scale, which is
   a lot for distant items. Each measurement (exact game values: anchor column, row and scale from $113EE)
   narrows an interval per quantity; the value used is the coarsest of 1/8, 1/16, 1/32 steps inside it, so it
   stays put instead of jumping with every tick's rounding. */
static struct { double lo, hi; } item_geo[256][ITEM_CACHE][4];

static double item_value(int ty, int m, int q, int n, int scale)
{
  double lo = (n - 1.5) / scale, hi = (n + 1.5) / scale, c, v;
  if (item_geo[ty][m][q].hi > item_geo[ty][m][q].lo)                /* intersect with what is known */
  {
    double l2 = lo > item_geo[ty][m][q].lo ? lo : item_geo[ty][m][q].lo;
    double h2 = hi < item_geo[ty][m][q].hi ? hi : item_geo[ty][m][q].hi;
    if (l2 <= h2) { lo = l2; hi = h2; }                              /* else: the layout changed, restart */
  }
  item_geo[ty][m][q].lo = lo; item_geo[ty][m][q].hi = hi;
  c = (lo + hi) / 2;
  {
    static const int den[3] = {8, 16, 32};      /* the coarsest step that fits (the game uses shifts) */
    int d;
    for (d = 0; d < 3; d++)
    {
      v = floor(c * den[d] + 0.5) / den[d];
      if (v >= lo && v <= hi) return v;
    }
  }
  return c;
}

static void draw_piece(const dpiece_t *p, const cam_t *c, int W, int H, double focal, double bob)
{
  double lat = (p->y - c->py) * c->dx - (p->x - c->px) * c->dy, sc, kx, ky, xc, yc, ax, ay, pw, ph;
  int xx, yy, x1, y1;
  if (p->depth < 0.05 || !p->shade) return;
  sc = 64.0 / p->depth; if (sc > 300) sc = 300;    /* the game caps the scale at $12C (point-blank sprites) */
  kx = sc * focal / 64; ky = sc * focal / 128;
  xc = W / 2.0 + focal * lat / p->depth;
  yc = H / 2.0 + (c->hor - bob) * sc / 64 * focal / 128;
  ax = xc + p->du * kx; ay = yc + p->dv * ky; pw = p->pw * kx; ph = p->ph * ky;
  if (!p->item && zt_hd_dbg_obj[7] == 0)
  {
    zt_hd_dbg_obj[0] = p->x; zt_hd_dbg_obj[1] = p->y; zt_hd_dbg_obj[2] = ax; zt_hd_dbg_obj[3] = pw;
    zt_hd_dbg_obj[4] = p->du; zt_hd_dbg_obj[5] = p->pw; zt_hd_dbg_obj[6] = p->depth; zt_hd_dbg_obj[7] = 1;
  }
  if (p->item && zt_hd_dbg_piece[7] == 0)
  {
    zt_hd_dbg_piece[0] = p->du; zt_hd_dbg_piece[1] = p->dv; zt_hd_dbg_piece[2] = p->pw; zt_hd_dbg_piece[3] = p->ph;
    zt_hd_dbg_piece[4] = p->mirror; zt_hd_dbg_piece[5] = xc; zt_hd_dbg_piece[6] = p->depth; zt_hd_dbg_piece[7] = 1;
  }
  x1 = (int)ceil(ax + pw); if (x1 > W) x1 = W;
  y1 = (int)ceil(ay + ph); if (y1 > H) y1 = H;
  for (xx = ax < 0 ? 0 : (int)ceil(ax); xx < x1; xx++)
  {
    int u, half;
    if (p->depth >= wdist[xx]) continue;
    u = (int)((xx - ax) / pw * 32); if (u < 0) u = 0; if (u > 31) u = 31;
    if (p->mirror) u = 31 - u;
    half = u & 1; u >>= 1;                       /* a texel byte is two pixels side by side (hi, lo nibble) */
    for (yy = ay < 0 ? 0 : (int)ceil(ay); yy < y1; yy++)
    {
      int v = (int)((yy - ay) / ph * 32), b;
      if (v > 31) v = 31;
      b = A8(&snaps[1], p->data + u * 32 + v);
      b = half ? b & 15 : b >> 4;
      if (!b) continue;                          /* transparent */
      b = A8(&snaps[1], p->shade + b * 0x11);
      idx[yy * W + xx] = PIX(b, (xx + yy) & 1);
    }
  }
}

/* Sprites: every piece the game drew this tick ($EDA0: native column/row rect, 16x32 texels), placed
   relative to its anchor (object or map item). The native rect is converted to anchor-relative units
   with the tick's own camera (offset / native scale), then projected with the interpolated HD camera. */
static void render_sprites(const snap_t *s, const snap_t *s0, const cam_t *c, double t, int W, int H, double focal)
{
  static dpiece_t list[512];
  cam_t nc;
  /* sprite rows: 40 + (horizon - $FF116E - z) * scale / 64, with the horizon as it was at $1329A (the render
     adjusts it for the player's elevation); the HD camera's horizon is offset by the same amount */
  double bob = S16(s, 0xFF116E), nhor = s->hor_spr;
  uint32 mapp = M32(s, 0xFF1024);
  int i, j, n = 0, rad = M16(s, 0xFF0EB4), mx, my, cx = (int)floor(c->px), cy = (int)floor(c->py);
  make_cam(&nc, 1);                                   /* the camera the game rendered this tick with */
  zt_hd_dbg_piece[7] = 0; zt_hd_dbg_obj[7] = 0;
  for (i = 0; i < s->npc; i++)
  {
    double ox, oy, nd, nl, nsc, ccol, row0;
    dpiece_t *p = &list[n];
    piece_pos(s, s0, i, 1, &ox, &oy);
    nd = (ox - nc.px) * nc.dx + (oy - nc.py) * nc.dy;
    nl = (oy - nc.py) * nc.dx - (ox - nc.px) * nc.dy;
    if (nd < 0.05) continue;
    nsc = 64.0 / nd; if (nsc > 300) nsc = 300;          /* the game caps the scale at $12C */
    ccol = 64 + 64 * nl / nd; row0 = 40 + (nhor - bob) * nsc / 64;
    p->du = (s->pc[i].col - ccol) / nsc; p->dv = (s->pc[i].row - row0) / nsc;
    p->pw = s->pc[i].w / nsc; p->ph = s->pc[i].h / nsc;
    if (s->pc[i].rec)
    {
      /* exact layout from the sub-frame record ($1BCB4): piece width factor*scale/32 columns, height
         factor*scale/16 rows, the grid anchored at the object's centre column and its row
         ((horizon - bob - z) * scale / 64 + 40) by +0/+1 (0 left/top, 1 centre, 2 right/bottom) */
      uint32 rec = s->pc[i].rec;
      double pwu = R8(rec + 2) / 32.0, phu = R8(rec + 3) / 16.0;
      int cols = R8(rec + 4), rows = R8(rec + 5);
      double x0 = R8(rec) == 1 ? -cols * pwu / 2 : R8(rec) ? -cols * pwu : 0;
      double y0 = R8(rec + 1) == 1 ? -rows * phu / 2 : R8(rec + 1) ? -rows * phu : 0;
      p->du = x0 + s->pc[i].gc * pwu; p->pw = pwu;
      p->dv = -S16(s, s->pc[i].obj + 0x24) / 64.0 + y0 + s->pc[i].gr * phu; p->ph = phu;
    }
    p->data = s->pc[i].data; p->mirror = s->pc[i].mirror; p->shade = s->pc[i].shade; p->item = s->pc[i].type != 0;
    piece_pos(s, s0, i, t, &p->x, &p->y);
    p->depth = (p->x - c->px) * c->dx + (p->y - c->py) * c->dy;
    n++;
    if (s->pc[i].type)                                  /* map item: stable layout, remember its pieces */
    {
      int ty = s->pc[i].type, k, m = 0;
      for (k = 0; k < i; k++) if (s->pc[k].obj == s->pc[i].obj) m++;      /* piece number within the item */
      if (m < ITEM_CACHE && s->pc[i].ascale > 0)
      {
        int sc = s->pc[i].ascale;
        /* relative to the item's centre column and its floor row (row0 + 32/64 of the scale, $113E0) */
        p->du = item_value(ty, m, 0, s->pc[i].col - s->pc[i].acol, sc);
        p->dv = item_value(ty, m, 1, s->pc[i].row - s->pc[i].arow, sc) + 0.5;
        p->pw = item_value(ty, m, 2, s->pc[i].w, sc);
        p->ph = item_value(ty, m, 3, s->pc[i].h, sc);
        item_cache[ty].du[m] = p->du; item_cache[ty].dv[m] = p->dv; item_cache[ty].pw[m] = p->pw; item_cache[ty].ph[m] = p->ph;
      }
      if (item_cache[ty].tick != s->vbl) { item_cache[ty].tick = s->vbl; item_cache[ty].n = 0; }
      for (k = 0; k < i; k++) if (s->pc[k].type == ty && s->pc[k].obj != s->pc[i].obj) break;
      if (k == i && m < ITEM_CACHE && item_cache[ty].n == m)  /* frames of the first item of this type */
      {
        item_cache[ty].n = m + 1;
        item_cache[ty].data[m] = p->data; item_cache[ty].list[m] = s->pc[i].list; item_cache[ty].mirror[m] = p->mirror;
      }
    }
  }
  if (rad < 1 || rad > 16) rad = 12;
  for (my = cy - rad; my <= cy + rad; my++)
    for (mx = cx - rad; mx <= cx + rad; mx++)
    {
      uint32 id, ty;
      int k;
      double depth;
      if (mx < 0 || mx > 31 || my < 0 || my > 31) continue;
      ty = M8(s, 0xFF7BC6 + M8(s, mapp + my * 32 + mx));
      if (!item_type[ty] || !item_cache[ty].n) continue;
      id = 0x1000000 | my << 8 | mx;
      for (k = 0; k < s->npc; k++) if (s->pc[k].obj == id) break;
      if (k < s->npc) continue;                          /* the game drew it */
      depth = (mx + 0.5 - c->px) * c->dx + (my + 0.5 - c->py) * c->dy;
      for (k = 0; k < item_cache[ty].n && n < 512; k++)
      {
        dpiece_t *p = &list[n++];
        p->x = mx + 0.5; p->y = my + 0.5; p->depth = depth; p->item = 2;
        p->du = item_cache[ty].du[k]; p->dv = item_cache[ty].dv[k]; p->pw = item_cache[ty].pw[k]; p->ph = item_cache[ty].ph[k];
        p->data = item_cache[ty].data[k]; p->mirror = item_cache[ty].mirror[k];
        p->shade = depth > 0.05 ? piece_shade(s, item_cache[ty].list[k], 64.0 / depth) : 0;
      }
    }
  for (i = 1; i < n; i++)                               /* far to near, stable */
  {
    dpiece_t tmp = list[i];
    for (j = i; j > 0 && list[j - 1].depth < tmp.depth; j--) list[j] = list[j - 1];
    list[j] = tmp;
  }
  {
    cam_t cs = *c;
    cs.hor += s->hor_spr - S16(s, 0xFF7752);
    for (i = 0; i < n; i++) draw_piece(&list[i], &cs, W, H, focal, bob);
  }
}

/* ---------------------------------------------------------------- sky (VDP plane A: the starfield;
   the HUD and the 3D view tiles are on plane B) */
static inline uint32 vram_b(uint32 a) { return READ_BYTE(vram, a & 0xFFFF); }

/* colour index (palette * 16 + colour, 0 = backdrop) of pixel (cx, cy) of a name table entry */
static int entry_index(int entry, int cx, int cy)
{
  int b, col;
  if (entry & 0x800) cx = 7 - cx;
  if (entry & 0x1000) cy = 7 - cy;
  b = vram_b((entry & 0x7FF) * 32 + cy * 4 + (cx >> 1));
  col = (cx & 1) ? (b & 15) : (b >> 4);
  return col ? ((entry >> 13) & 3) * 16 + col : 0;
}

static int plane_w(void) { int pw = 32 << (reg[16] & 3); return pw == 96 ? 128 : pw; }
static int plane_h(void) { int ph = 32 << ((reg[16] >> 4) & 3); return ph == 96 ? 128 : ph; }

static int plane_entry(uint32 base, int tx, int ty)
{
  uint32 a = base + ((ty & (plane_h() - 1)) * plane_w() + (tx & (plane_w() - 1))) * 2;
  return (vram_b(a) << 8) | vram_b(a + 1);
}

static uint16 plane_pixel(uint32 base, int px, int py)
{
  return zt_vdp_pixel(entry_index(plane_entry(base, px >> 3, py >> 3), px & 7, py & 7));
}

/* The sky panorama is 1024 px (128 tiles) wide, 2 px per angle unit, but plane A holds only 512 px: the
   game streams tile columns in as the view turns, so only the columns on the native screen are current.
   The panorama is normally read whole from the game's sky map (sky_from_map); this capture of the columns
   on screen into a host panorama indexed by world tile column is the fallback, with plane A for columns
   never seen. The sky tiles and palette don't animate. */
#define PAN_H 64
uint16 sky_pan[PAN_H][128];
static uint32 sky_gen;              /* bumped when the captured (non-map) panorama changes */
uint8 sky_known[128];

/* The game streams the sky from a 128 x 16 tile map (pointer at $FF271E, set at level start: $153106, or
   $1553E6 for the planet sky; streamer at $156C): world tile column = map column. Read whole, the sky is
   complete from the first frame. */
static struct { uint32 ptr; int loaded, w, h, art_row, map_row, indexed; uint8 *idx8; uint16 *rgb; uint8 *opaque; } sky_png;
static void sky_png_load(uint32 ptr);
static int sky_from_map(void)
{
  uint32 ptr = live_l(0xFF271E);
  int ty, wt;
  if (zt_hd_sky_ext == 2 && ptr != sky_png.ptr) sky_png_load(ptr);
  if (!((ptr >= 0x200 && ptr + 16 * 256 <= rom_size) || (ptr >= 0xFF0000 && ptr <= 0xFFF000)) || (ptr & 1)) return 0;
  for (ty = 0; ty < PAN_H; ty++)
    for (wt = 0; wt < 128; wt++)
    {
      uint32 a = ptr + ty * 256 + wt * 2;
      sky_pan[ty][wt] = ty >= 16 ? plane_entry((reg[2] & 0x38) << 10, wt, ty)            /* rows below the map */
                      : ptr >= 0xFF0000 ? live_w(a) : R16(a);
    }
  memset(sky_known, 1, sizeof sky_known);
  return 1;
}

static void sky_capture(void)
{
  if (sky_from_map()) return;
  sky_gen++;
  uint32 base = (reg[2] & 0x38) << 10, hsb = (reg[13] & 0x3F) << 10, ha;
  int mode = reg[11] & 3, line = 60, hs, two_a, live2a, sx, y;
  ha = hsb + (mode == 3 ? line * 4 : mode == 2 ? (line & ~7) * 4 : 0);
  hs = ((vram_b(ha) << 8) | vram_b(ha + 1)) & 0x3FF;
  live2a = 2 * (live_w(0xFF0E04) & 511);
  two_a = (16 - hs) & 511;                            /* scroll = -2*angle + 16: angle mod 256 */
  if (abs(((two_a + 512 - live2a + 512) & 1023) - 512) < abs(((two_a - live2a + 512) & 1023) - 512)) two_a += 512;
  for (sx = 8; sx < 336; sx += 8)                     /* the native view (32..288) and the columns the game
                                                         keeps current beyond it (measured -160..+184 of centre) */
  {
    int px = (sx - hs) & 511, wt = ((144 + two_a + sx - 160) & 1023) >> 3;
    for (y = 0; y < PAN_H && y < plane_h(); y++) sky_pan[y][wt] = plane_entry(base, px >> 3, y);
    sky_known[wt] = 1;
  }
}

/* Sky beyond the original band. The level's sky art is a band of rows in the panorama (art_top, art_rows);
   above and below it the band is repeated (star columns only, so the planet isn't copied), and the planet,
   which the art cuts off at the band's top, can be completed: a circle is fitted to its visible rim and the
   missing rows are taken from the reflection about the circle's centre row (same distance from the centre,
   so the same limb shading), blended to the art's brightness at the cut. */
static int art_top, art_rows = 80;   /* plane row where the sky art starts, its height */
static uint8 planet_col[128];        /* world tile columns holding the planet (a tile with 40+ of 64 pixels
                                        lit, widened by 2 tiles for the rim); star tiles have at most ~20 */
static uint8 star_cols[128];         /* seen columns without the planet: sources for the repeated bands */
static int nstar_cols;
#define OV_H 96
#define OV_W 256
static struct { int valid, tried, x0, w, top; uint8 px[OV_H][OV_W]; } planet_ov;   /* completed planet rows */

static int tile_lit(int entry)
{
  static uint8 lit[2048], stamp[2048];
  static uint8 gen;
  int t = entry & 0x7FF, i, n = 0;
  if (entry < 0) { gen++; return 0; }        /* new frame: tiles may have changed */
  if (stamp[t] == gen) return lit[t];
  for (i = 0; i < 32; i++) { int b = vram_b(t * 32 + i); n += (b >> 4 != 0) + ((b & 15) != 0); }
  stamp[t] = gen; lit[t] = n;
  return n;
}

/* colour index of the panorama at world pixel column wx, plane row y */
static int pan_index(int wx, int y)
{
  int wt = (wx & 1023) >> 3;
  return entry_index(sky_pan[(y >> 3) & (PAN_H - 1) & (plane_h() - 1)][wt], wx & 7, y & 7);
}

static int lum_of(int ci)
{
  uint16 c = zt_vdp_pixel(ci);
  return ((c >> 11) & 31) * 2 * 30 + ((c >> 5) & 63) * 59 + (c & 31) * 2 * 11;
}

static void build_planet(void)
{
  int ws = -1, n = 0, wt, k, x, y, i, np = 0, W, nlev = 0, rank[64];
  uint8 dense_c[64] = {0}, star_c[64] = {0}, isp[64] = {0}, lev_of[64];
  static uint8 mask[80 * 8][OV_W];
  double sxx = 0, sxy = 0, syy = 0, sx = 0, sy = 0, sn = 0, sxz = 0, syz = 0, sz = 0, cx, cy, r, det;
  double m[3][3], v[3];
  planet_ov.tried = 1; planet_ov.valid = 0;
  for (wt = 0; wt < 128; wt++)                /* the planet's column run (all of it and one column around seen) */
    if (planet_col[wt] && !planet_col[(wt + 127) & 127]) { ws = wt; break; }
  if (ws < 0) return;
  while (n < 64 && planet_col[(ws + n) & 127]) n++;
  for (k = -1; k <= n; k++) if (!sky_known[(ws + k) & 127]) { planet_ov.tried = 0; return; }   /* try again later */
  W = n * 8; if (W > OV_W) return;
  /* planet colours: in dense tiles, never in star columns */
  for (k = 0; k < n; k++)
    for (y = art_top >> 3; y < (art_top + art_rows) >> 3; y++)
    {
      int e = sky_pan[y & (PAN_H - 1) & (plane_h() - 1)][(ws + k) & 127];
      if (tile_lit(e) >= 40) for (i = 0; i < 64; i++) { int ci = entry_index(e, i & 7, i >> 3); if (ci) dense_c[ci] = 1; }
    }
  for (k = 0; k < nstar_cols; k++)
    for (y = 0; y < art_rows; y++) for (x = 0; x < 8; x++) { int ci = pan_index(star_cols[k] * 8 + x, art_top + y); if (ci) star_c[ci] = 1; }
  for (i = 1; i < 64; i++) if (dense_c[i] && !star_c[i]) { isp[i] = 1; rank[nlev++] = i; }
  if (nlev < 2) return;
  for (i = 0; i < nlev; i++) for (k = i + 1; k < nlev; k++)
    if (lum_of(rank[k]) < lum_of(rank[i])) { int t = rank[i]; rank[i] = rank[k]; rank[k] = t; }
  for (i = 0; i < nlev; i++) lev_of[rank[i]] = i;
  /* mask and rim points: left/right ends of each row below the cut rows, bottom end of each column */
  for (y = 0; y < art_rows && y < 80 * 8; y++) for (x = 0; x < W; x++) mask[y][x] = isp[pan_index(ws * 8 + x, art_top + y)];
#define RIM(px_, py_) do { double X = px_, Y = py_, Z = X * X + Y * Y; sxx += X * X; sxy += X * Y; syy += Y * Y; sx += X; sy += Y; \
                           sn += 1; sxz += X * Z; syz += Y * Z; sz += Z; np++; } while (0)
  for (y = 3; y < art_rows; y++)
  {
    int l = -1, rr = -1, c = 0;
    for (x = 0; x < W; x++) if (mask[y][x]) { if (l < 0) l = x; rr = x; c++; }
    if (c > 2) { RIM(l, y + 0.5); RIM(rr + 1, y + 0.5); }
  }
  for (x = 0; x < W; x++)
  {
    int bot = -1;
    for (y = 0; y < art_rows; y++) if (mask[y][x]) bot = y;
    if (bot >= 0 && bot < art_rows - 2) RIM(x + 0.5, bot + 1);
  }
  if (np < 10) return;
  /* least squares circle: 2a*x + 2b*y + c = x^2 + y^2 */
  m[0][0] = 4 * sxx; m[0][1] = 4 * sxy; m[0][2] = 2 * sx; v[0] = 2 * sxz;
  m[1][0] = 4 * sxy; m[1][1] = 4 * syy; m[1][2] = 2 * sy; v[1] = 2 * syz;
  m[2][0] = 2 * sx;  m[2][1] = 2 * sy;  m[2][2] = sn;     v[2] = sz;
  det = m[0][0] * (m[1][1] * m[2][2] - m[1][2] * m[2][1]) - m[0][1] * (m[1][0] * m[2][2] - m[1][2] * m[2][0])
      + m[0][2] * (m[1][0] * m[2][1] - m[1][1] * m[2][0]);
  if (fabs(det) < 1e-9) return;
  cx = (v[0] * (m[1][1] * m[2][2] - m[1][2] * m[2][1]) - m[0][1] * (v[1] * m[2][2] - m[1][2] * v[2]) + m[0][2] * (v[1] * m[2][1] - m[1][1] * v[2])) / det;
  cy = (m[0][0] * (v[1] * m[2][2] - m[1][2] * v[2]) - v[0] * (m[1][0] * m[2][2] - m[1][2] * m[2][0]) + m[0][2] * (m[1][0] * v[2] - v[1] * m[2][0])) / det;
  r = (m[0][0] * (m[1][1] * v[2] - v[1] * m[2][1]) - m[0][1] * (m[1][0] * v[2] - v[1] * m[2][0]) + v[0] * (m[1][0] * m[2][1] - m[1][1] * m[2][0])) / det;
  r = sqrt(r + cx * cx + cy * cy);
  if (!(r > 8 && r < 200) || cy - r > -2) return;   /* not a cut-off disc */
  {
    /* the fit's centre is pulled sideways by the ragged shadow edge: the widest art row gives the true
       centre and radius */
    int best = 0, bl = 0, br = 0;
    for (y = 0; y < art_rows; y++)
    {
      int l = -1, rr = -1, c = 0;
      for (x = 0; x < W; x++) if (mask[y][x]) { if (l < 0) l = x; rr = x; c++; }
      if (c > best) { best = c; bl = l; br = rr; }
    }
    if (best > 16) { cx = (bl + br + 1) / 2.0; r = (br + 1 - bl) / 2.0; }
  }
  planet_ov.top = (int)floor(cy - r) - 1; if (planet_ov.top < -OV_H) planet_ov.top = -OV_H;
  planet_ov.x0 = (ws * 8 + (int)floor(cx - r) - 1) & 1023;
  planet_ov.w = (int)ceil(2 * r) + 3; if (planet_ov.w > OV_W) planet_ov.w = OV_W;
  memset(planet_ov.px, 0, sizeof planet_ov.px);
  for (x = 0; x < planet_ov.w; x++)
  {
    int lx = (int)floor(cx - r) - 1 + x, na = 0, ns = 0;     /* column in mask coordinates */
    double a = 0, sm = 0, d = 0;
    for (y = 0; y < 3; y++)
    {
      int ys = (int)floor(2 * cy - y - 1 + 0.5);
      if (lx >= 0 && lx < W && mask[y][lx]) { a += lev_of[pan_index(ws * 8 + lx, art_top + y)]; na++; }
      if (lx >= 0 && lx < W && ys >= 0 && ys < art_rows && mask[ys][lx]) { sm += lev_of[pan_index(ws * 8 + lx, art_top + ys)]; ns++; }
    }
    if (na && ns) d = a / na - sm / ns;
    for (y = planet_ov.top; y < 0; y++)
    {
      int ys = (int)floor(2 * cy - y - 1 + 0.5), lv;
      double f = 1 - (-y - 1) / 14.0, val;
      if ((lx + 0.5 - cx) * (lx + 0.5 - cx) + (y + 0.5 - cy) * (y + 0.5 - cy) > r * r) continue;
      lv = (lx >= 0 && lx < W && ys >= 0 && ys < art_rows && mask[ys][lx]) ? lev_of[pan_index(ws * 8 + lx, art_top + ys)] : 0;
      if (f < 0) f = 0;
      val = lv + d * f + (((y & 1) * 2 + (lx & 1) * 3) % 4 - 1.5) / 4;   /* 2x2 ordered dither */
      i = (int)floor(val + 0.5); if (i < 0) i = 0; if (i >= nlev) i = nlev - 1;
      planet_ov.px[y - planet_ov.top][x] = rank[i];
    }
  }
  planet_ov.valid = 1;
#undef RIM
}

static void find_planet(void)
{
  uint8 dense[128], nonblank[32];
  int wt, ty, k, ph = plane_h(), best = 0, run = 0, start = 0;
  tile_lit(-1);
  /* the art rows: the longest run of tile rows with anything lit (wrapping) */
  for (ty = 0; ty < ph && ty < 32; ty++)
  {
    nonblank[ty] = 0;
    for (wt = 0; wt < 128 && !nonblank[ty]; wt++) if (sky_known[wt] && tile_lit(sky_pan[ty & (PAN_H - 1)][wt])) nonblank[ty] = 1;
  }
  for (k = 0; k < 2 * ph; k++)
  {
    if (nonblank[k % ph]) { if (!run) start = k % ph; run++; if (run > best && run <= ph) { best = run; art_top = start * 8; } }
    else run = 0;
  }
  art_rows = best ? best * 8 : 80; if (art_rows > 640) art_rows = 640;
  for (wt = 0; wt < 128; wt++)
  {
    dense[wt] = 0;
    if (!sky_known[wt]) continue;
    for (ty = art_top >> 3; ty < (art_top + art_rows) >> 3 && !dense[wt]; ty++)
      if (tile_lit(sky_pan[ty & (PAN_H - 1) & (ph - 1)][wt]) >= 40) dense[wt] = 1;
  }
  nstar_cols = 0;
  for (wt = 0; wt < 128; wt++)
  {
    planet_col[wt] = 0;
    for (k = -2; k <= 2; k++) if (dense[(wt + k) & 127]) planet_col[wt] = 1;
    if (sky_known[wt] && !planet_col[wt]) star_cols[nstar_cols++] = wt;
  }
  if (zt_hd_sky_ext == 2 && !planet_ov.tried) build_planet();
}


/* ---------------------------------------------------------------- sky panorama PNG (make_sky.py)
   zt_sky_<map address>.png next to zt_hd.cfg: 1024 px = 360 degrees; 8-bit indexed with CRAM indices as
   pixel values (palette fades apply; 0 = backdrop), or RGB/RGBA (fixed colours, alpha < 128 = backdrop).
   Text chunks: zt_art_row = PNG row of the sky map's first art row, zt_map_row = that map row. */

static uint32 be32(const uint8 *p) { return (uint32)p[0] << 24 | p[1] << 16 | p[2] << 8 | p[3]; }

static void sky_png_free(void)
{
  free(sky_png.idx8); free(sky_png.rgb); free(sky_png.opaque);
  sky_png.idx8 = NULL; sky_png.rgb = NULL; sky_png.opaque = NULL; sky_png.loaded = 0;
}

static void sky_png_load(uint32 ptr)
{
  char path[1100], name[32], *sl;
  FILE *f;
  long n;
  uint8 *file = NULL, *z = NULL, *raw = NULL;
  uint32 pos, zlen = 0, ct = 0, bd = 0, bpp, stride, y, x, i;
  z_stream zs;
  sky_png_free();
  sky_png.ptr = ptr; sky_png.art_row = 0; sky_png.map_row = 0;
  strncpy(path, zt_hd_cfg_path, sizeof path - 32); path[sizeof path - 32] = 0;
  sl = strrchr(path, '/'); if (!sl) sl = strrchr(path, '\\');
  if (sl) sl[1] = 0; else path[0] = 0;
  snprintf(name, sizeof name, "zt_sky_%06X.png", (unsigned)ptr);
  strcat(path, name);
  if (!(f = fopen(path, "rb")) && zt_hd_rom_dir[0])          /* else next to the game */
  {
    snprintf(path, sizeof path, "%s%c%s", zt_hd_rom_dir, strchr(zt_hd_rom_dir, '\\') ? '\\' : '/', name);
    f = fopen(path, "rb");
  }
  if (!f) return;
  fseek(f, 0, SEEK_END); n = ftell(f); fseek(f, 0, SEEK_SET);
  if (n < 57 || n > (32 << 20) || !(file = malloc(n)) || fread(file, 1, n, f) != (size_t)n) { fclose(f); free(file); return; }
  fclose(f);
  if (memcmp(file, "\x89PNG\r\n\x1a\n", 8)) goto done;
  z = malloc(n);
  for (pos = 8; pos + 12 <= (uint32)n; )
  {
    uint32 len = be32(file + pos);
    const uint8 *type = file + pos + 4, *d = file + pos + 8;
    if (pos + 12 + len > (uint32)n) break;
    if (!memcmp(type, "IHDR", 4)) { sky_png.w = be32(d); sky_png.h = be32(d + 4); bd = d[8]; ct = d[9]; if (d[12]) goto done; }
    else if (!memcmp(type, "IDAT", 4)) { memcpy(z + zlen, d, len); zlen += len; }
    else if (!memcmp(type, "tEXt", 4))
    {
      if (len > 11 && !memcmp(d, "zt_art_row", 11)) sky_png.art_row = atoi((const char *)d + 11);
      if (len > 11 && !memcmp(d, "zt_map_row", 11)) sky_png.map_row = atoi((const char *)d + 11);
    }
    else if (!memcmp(type, "IEND", 4)) break;
    pos += 12 + len;
  }
  if (bd != 8 || (ct != 3 && ct != 2 && ct != 6) || sky_png.w < 64 || sky_png.w > 8192 || sky_png.h < 1 || sky_png.h > 4096) goto done;
  bpp = ct == 3 ? 1 : ct == 2 ? 3 : 4; stride = sky_png.w * bpp;
  raw = malloc((stride + 1) * sky_png.h);
  memset(&zs, 0, sizeof zs);
  if (inflateInit(&zs) != Z_OK) goto done;
  zs.next_in = z; zs.avail_in = zlen; zs.next_out = raw; zs.avail_out = (stride + 1) * sky_png.h;
  i = inflate(&zs, Z_FINISH); inflateEnd(&zs);
  if (i != Z_STREAM_END) goto done;
  for (y = 0; y < (uint32)sky_png.h; y++)          /* undo the row filters, in place */
  {
    uint8 *r = raw + y * (stride + 1) + 1, *pr = y ? raw + (y - 1) * (stride + 1) + 1 : NULL, ft = r[-1];
    for (x = 0; x < stride; x++)
    {
      int a = x >= bpp ? r[x - bpp] : 0, b = pr ? pr[x] : 0, c = (pr && x >= bpp) ? pr[x - bpp] : 0, p, pa, pb, pc;
      switch (ft)
      {
        case 1: r[x] += a; break;
        case 2: r[x] += b; break;
        case 3: r[x] += (a + b) >> 1; break;
        case 4: p = a + b - c; pa = abs(p - a); pb = abs(p - b); pc = abs(p - c);
                r[x] += (pa <= pb && pa <= pc) ? a : pb <= pc ? b : c; break;
      }
    }
  }
  sky_png.indexed = ct == 3;
  if (ct == 3)
  {
    sky_png.idx8 = malloc(sky_png.w * sky_png.h);
    for (y = 0; y < (uint32)sky_png.h; y++) for (x = 0; x < (uint32)sky_png.w; x++)
      sky_png.idx8[y * sky_png.w + x] = raw[y * (stride + 1) + 1 + x] & 63;
  }
  else
  {
    sky_png.rgb = malloc(2 * sky_png.w * sky_png.h); sky_png.opaque = malloc(sky_png.w * sky_png.h);
    for (y = 0; y < (uint32)sky_png.h; y++) for (x = 0; x < (uint32)sky_png.w; x++)
    {
      const uint8 *q = raw + y * (stride + 1) + 1 + x * bpp;
      sky_png.rgb[y * sky_png.w + x] = ((q[0] >> 3) << 11) | ((q[1] >> 2) << 5) | (q[2] >> 3);
      sky_png.opaque[y * sky_png.w + x] = bpp == 3 || q[3] >= 128;
    }
  }
  sky_png.loaded = 1;
done:
  free(file); free(z); free(raw);
}

/* a sky pixel at world column px (2 px per angle unit), plane row py (both unwrapped); band0: the first
   plane row the native view shows */
static uint16 sky_pixel(uint32 base, int px, int py, int band0)
{
  int wt, ty;
  if (zt_hd_sky_ext == 2 && sky_png.loaded)
  {
    /* the panorama PNG: plane row map_row (unwrapped near the view band) is PNG row art_row */
    int span = plane_h() * 8, r0 = sky_png.map_row;
    int a0 = band0 + ((((r0 - band0) % span) + span + span / 2) % span - span / 2);
    int iy = py - a0 + sky_png.art_row, ix = (px & 1023) * sky_png.w / 1024;
    if (iy < 0 || iy >= sky_png.h) return zt_vdp_pixel(0);
    if (sky_png.indexed) return zt_vdp_pixel(sky_png.idx8[iy * sky_png.w + ix]);
    return sky_png.opaque[iy * sky_png.w + ix] ? sky_png.rgb[iy * sky_png.w + ix] : zt_vdp_pixel(0);
  }
  if (zt_hd_sky_ext)
  {
    int span = plane_h() * 8, a0 = band0 + ((((art_top - band0) % span) + span + span / 2) % span - span / 2);
    int rel = py - a0, k = rel >= 0 ? rel / art_rows : -((art_rows - 1 - rel) / art_rows);
    if (zt_hd_sky_ext == 2 && planet_ov.valid && rel < 0 && rel >= planet_ov.top)
    {
      int lx = (px - planet_ov.x0) & 1023;
      if (lx < planet_ov.w && planet_ov.px[rel - planet_ov.top][lx]) return zt_vdp_pixel(planet_ov.px[rel - planet_ov.top][lx]);
    }
    if (k)
    {
      /* outside the art: the art again, shifted sideways per repeat so the copies don't line up, from
         seen columns without the planet */
      py -= k * art_rows; px += k * 296;
      wt = (px & 1023) >> 3;
      if (planet_col[wt] || !sky_known[wt])
      {
        if (!nstar_cols) return zt_vdp_pixel(0);
        wt = star_cols[(wt * 37 + k * 11 + 1024) % nstar_cols];
        px = (wt << 3) | (px & 7);
      }
    }
  }
  wt = (px & 1023) >> 3; ty = (py >> 3) & (plane_h() - 1);
  if (!sky_known[wt] || ty >= PAN_H) return plane_pixel(base, px, py);
  return zt_vdp_pixel(entry_index(sky_pan[ty][wt], px & 7, py & 7));
}

/* The sky as seen this frame only depends on (world column 0..1023, plane row): it is rendered into a
   1024-wide RGB565 strip covering the visible rows, rebuilt only when something it depends on changes
   (palette, vertical scroll, sky settings and sources), so a sky pixel on screen is one array read. */
static uint16 *skytex;
static int skytex_r0 = 0, skytex_rows = 0, skytex_cap = 0;
static uint32 skytex_key;

static void sky_texture(uint32 base, int r0, int r1, int band0)
{
  uint32 key = 2166136261u;
  int i, r, x, rows = r1 - r0 + 1;
#define MIX(v) (key = (key ^ (uint32)(v)) * 16777619u)
  for (i = 0; i < 64; i++) MIX(zt_vdp_pixel(i));
  MIX(r0); MIX(r1); MIX(band0); MIX(base); MIX(zt_hd_sky_ext); MIX(sky_png.loaded); MIX(sky_png.ptr);
  MIX(planet_ov.valid); MIX(planet_ov.top); MIX(art_top); MIX(art_rows); MIX(nstar_cols); MIX(sky_gen);
  MIX(live_l(0xFF271E));
#undef MIX
  if (key == skytex_key && skytex && rows == skytex_rows && r0 == skytex_r0) return;
  if (rows * 1024 > skytex_cap) { free(skytex); skytex = malloc(sizeof(uint16) * rows * 1024); skytex_cap = skytex ? rows * 1024 : 0; }
  if (!skytex) return;
  for (r = 0; r < rows; r++)
    for (x = 0; x < 1024; x++) skytex[r * 1024 + x] = sky_pixel(base, x, r0 + r, band0);
  skytex_key = key; skytex_r0 = r0; skytex_rows = rows;
}

/* ---------------------------------------------------------------- palette of the 3D view tiles */
static int view_palette(void)
{
  uint32 base = (reg[4] & 7) << 13;               /* plane B: HUD + view; the view's first tile is 1 */
  int i;
  for (i = 0; i < 64 * 32; i++)
  {
    uint32 e = (vram_b(base + i * 2) << 8) | vram_b(base + i * 2 + 1);
    if ((e & 0x7FF) == 1) return (e >> 13) & 3;
  }
  return 0;
}

/* ---------------------------------------------------------------- HUD and composition */
/* nearest-neighbour blit of a source rectangle into a destination rectangle of the output */
static void blit_fit(const uint16 *src, int spitch, int sx, int sy, int sw, int sh, int dx, int dy, int dw, int dh)
{
  int x, y;
  for (y = 0; y < dh; y++)
  {
    int yy = dy + y, syy;
    if (yy < 0 || yy >= oh) continue;
    syy = sy + y * sh / dh;
    for (x = 0; x < dw; x++)
    {
      int xx = dx + x;
      if (xx < 0 || xx >= ow) continue;
      hd[yy * ow + xx] = src[syy * spitch + sx + x * sw / dw];
    }
  }
}

static void fill(int dx, int dy, int dw, int dh, uint16 c)
{
  int x, y;
  for (y = dy; y < dy + dh && y < oh; y++) for (x = dx; x < dx + dw && x < ow; x++) hd[y * ow + x] = c;
}

/* the emulated screen, scaled to fit a panel with its aspect kept */
static void panel_native(const uint16 *native, int npitch, int nw, int nh, int px, int py, int pw, int ph)
{
  double sc = (double)pw / nw < (double)ph / nh ? (double)pw / nw : (double)ph / nh;
  int dw = (int)(nw * sc), dh = (int)(nh * sc);
  fill(px, py, pw, ph, 0);
  blit_fit(native, npitch, 0, 0, nw, nh, px + (pw - dw) / 2, py + (ph - dh) / 2, dw, dh);
}

static int in_gameplay(void)
{
  if (!snaps[1].valid) { zt_hd_dbg[4]++; return 0; }
  if (!live_w(0xFF7770)) { zt_hd_dbg[5]++; return 0; }                                     /* ZT_INGAME */
  if (((live_w(0xFF0000) - snaps[1].vbl) & 0xFFFF) > 60) { zt_hd_dbg[6]++; return 0; }    /* no tick for a second */
  zt_hd_dbg[7]++;
  return 1;
}

/* hardware sprites inside the native 3D view (the player's weapon/figure; enemies are drawn into the
   frame buffer, not as sprites): drawn scaled by g, the view's bottom row (native y 120) at ybase */
static void view_sprites(int px, int py, int W, int H, int ybase, double g)
{
  uint32 base = (reg[5] & 0x7E) << 9;
  int list[80], n = 0, link = 0, i;
  while (n < 80)
  {
    uint32 e = base + link * 8;
    list[n++] = link;
    link = vram_b(e + 3) & 0x7F;
    if (!link) break;
  }
  for (i = n - 1; i >= 0; i--)                          /* lowest priority first */
  {
    uint32 e = base + list[i] * 8;
    int y = (((vram_b(e) << 8) | vram_b(e + 1)) & 0x3FF) - 128;
    int sz = vram_b(e + 2), hs = ((sz >> 2) & 3) + 1, vs = (sz & 3) + 1;
    int at = (vram_b(e + 4) << 8) | vram_b(e + 5);
    int x = (((vram_b(e + 6) << 8) | vram_b(e + 7)) & 0x1FF) - 128;
    int tile = at & 0x7FF, pal = (at >> 13) & 3, hf = (at >> 11) & 1, vf = (at >> 12) & 1, sx, sy;
    if (x <= -64 || x + hs * 8 <= 32 || x >= 288 || y + vs * 8 <= 40 || y >= 120) continue;
    for (sy = 0; sy < vs * 8; sy++)
      for (sx = 0; sx < hs * 8; sx++)
      {
        int tx = hf ? hs * 8 - 1 - sx : sx, ty = vf ? vs * 8 - 1 - sy : sy;
        int t = tile + (tx >> 3) * vs + (ty >> 3), b = vram_b(t * 32 + (ty & 7) * 4 + ((tx & 7) >> 1));
        int col = (tx & 1) ? (b & 15) : (b >> 4), X0, X1, Y0, Y1, xx, yy;
        uint16 c;
        if (!col) continue;
        c = zt_vdp_pixel(pal * 16 + col);
        X0 = px + W / 2 + (int)floor((x + sx - 160) * g); X1 = px + W / 2 + (int)floor((x + sx + 1 - 160) * g);
        Y0 = ybase - (int)ceil((120 - (y + sy)) * g);     Y1 = ybase - (int)ceil((120 - (y + sy + 1)) * g);
        for (yy = Y0 < py ? py : Y0; yy < Y1 && yy < py + H && yy < oh; yy++)
          for (xx = X0 < px ? px : X0; xx < X1 && xx < px + W && xx < ow; xx++)
            hd[yy * ow + xx] = c;
      }
  }
}

/* The ammo count of each weapon box, drawn bigger over the box's bottom-left corner: the box's own yellow
   text (native rows 29-35 of the bar, 5 px font) at up to 3x the bar's scale (within the box's width) on a
   dark plate. Boxes start
   at bar x 0, 46, 102, 158, 205 (the bar is native x 40-280, y 0-36), drawn at (bx, by) with scale k. */
static void ammo_counts(const uint16 *native, int npitch, int bx, int by, double k)
{
  static const int box_x[5] = {0, 46, 102, 158, 205};
  int b, x, y;
  double g = 2 * k;
  int o = (int)(g / 3) > 1 ? (int)(g / 3) : 1;  /* outline width */
  for (b = 0; b < 5; b++)
  {
    int tx0 = 40 + box_x[b] + 1, tw = 30, ty0 = 29, th = 7, minx = tw, maxy = -1;
#define YELLOW(c) (((c) >> 11) >= 22 && (((c) >> 5) & 63) >= 44 && ((c) & 31) < 12)
    for (y = 0; y < th; y++)
      for (x = 0; x < tw; x++)
        if (YELLOW(native[(ty0 + y) * npitch + tx0 + x])) { if (x < minx) minx = x; if (y > maxy) maxy = y; }
    if (maxy < 0) continue;                      /* no count in this box */
    {
      int maxx = minx, X0, Y0, X1, Y1, xx, yy;
      double gb;
      for (y = 0; y <= maxy; y++) for (x = minx; x < tw; x++) if (YELLOW(native[(ty0 + y) * npitch + tx0 + x]) && x > maxx) maxx = x;
      gb = 3 * k;                                /* 3x the bar's scale, at most the box's width (33 native px) */
      if ((maxx - minx + 1) * gb > 31 * k) gb = 31 * k / (maxx - minx + 1);
      if (gb < g) gb = g;
      /* dark plate: the text's box plus the outline, so the small count underneath doesn't show through */
      X0 = bx + (int)((box_x[b] + 2) * k) - o; X1 = bx + (int)((box_x[b] + 2) * k + (maxx - minx + 1) * gb) + o;
      Y1 = by + (int)(35 * k) + o;              Y0 = by + (int)(35 * k - (maxy + 1) * gb) - o;
      for (yy = Y0 < 0 ? 0 : Y0; yy < Y1 && yy < oh; yy++)
        for (xx = X0 < 0 ? 0 : X0; xx < X1 && xx < ow; xx++) hd[yy * ow + xx] = 0;
      for (y = 0; y <= maxy; y++)
        for (x = minx; x <= maxx; x++)
        {
          uint16 c = native[(ty0 + y) * npitch + tx0 + x];
          if (!YELLOW(c)) continue;
          /* the text's left edge 2 native px inside the box, its bottom on the box's bottom (bar row 35) */
          X0 = bx + (int)((box_x[b] + 2) * k + (x - minx) * gb); X1 = bx + (int)((box_x[b] + 2) * k + (x - minx + 1) * gb);
          Y1 = by + (int)(35 * k - (maxy - y) * gb);   Y0 = by + (int)(35 * k - (maxy - y + 1) * gb);
          for (yy = Y0 < 0 ? 0 : Y0; yy < Y1 && yy < oh; yy++)
            for (xx = X0 < 0 ? 0 : X0; xx < X1 && xx < ow; xx++) hd[yy * ow + xx] = c;
        }
    }
#undef YELLOW
  }
}

/* the HD 3D view plus compact HUD, rendered into a panel of the output */
static void panel_hd(const uint16 *native, int npitch, int px, int py, int W, int H)
{
  cam_t c;
  double t, half = tan(zt_hd_fov * M_PI / 360), focal = (W / 2.0) / half, f = (focal / 2) / 64.0;
  uint32 period = snaps[0].valid ? ((snaps[1].vbl - snaps[0].vbl) & 0xFFFF) : 6;
  uint16 pal[16], pal2[256];
  uint32 sky_base; int sky_vs, x, y, i, vp;
  double sky_s;
  rw = W; rh = H;
  if (period < 1 || period > 30) period = 6;
  t = (double)((live_w(0xFF0000) - snaps[1].vbl) & 0xFFFF) / period;
  if (t > 1) t = 1;
  make_cam(&c, t);
  zt_hd_dbg_cam[0] = c.x; zt_hd_dbg_cam[1] = c.y; zt_hd_dbg_cam[2] = c.ang; zt_hd_dbg_cam[3] = c.hor; zt_hd_dbg_cam[7] = t;
  render_background(&snaps[1], W, H, f);
  {
    cam_t cw = c;                               /* walls and edges use the horizon as the game drew them */
    cw.hor += snaps[1].hor_walls - S16(&snaps[1], 0xFF7752);
    render_walls(&snaps[1], &cw, W, H, focal);
    render_edges(&snaps[1], &cw, W, H, focal);
  }
  render_sprites(&snaps[1], &snaps[0], &c, t, W, H, focal);
  vp = view_palette();
  sky_base = (reg[2] & 0x38) << 10;
  sky_vs = ((READ_BYTE(vsram, 0) << 8) | READ_BYTE(vsram, 1)) & 0x3FF;
  for (i = 0; i < 16; i++) pal[i] = zt_vdp_pixel(vp * 16 + i);
  for (i = 1; i < 256; i++)                     /* pixel pair -> colour: the two halves blended */
  {
    int hi = i >> 4, lo = i & 15;
    uint16 a = pal[hi ? hi : lo], b = pal[lo ? lo : hi];
    pal2[i] = a == b ? a : (((((a >> 11) + (b >> 11)) >> 1) << 11) | (((((a >> 5) & 63) + ((b >> 5) & 63)) >> 1) << 5)
                           | (((a & 31) + (b & 31)) >> 1));
  }
  if (zt_hd_sky_ext) find_planet();
  /* sky fill: scale the 80-row star band uniformly so it spans the view height even at the screen
     edges (cylinder height at the top corner = (H/2/focal)/sqrt(1+half^2)) */
  sky_s = 1;
  if (zt_hd_sky_fill)
  {
    sky_s = 1024 / (2 * M_PI) * (H / 2.0 / focal) / sqrt(1 + half * half) / 40.0;
    if (sky_s < 1) sky_s = 1;
  }
  /* sky: plane A as a cylinder at infinity. The game scrolls it by -2*angle+16 ($1470), with the view centre
     at screen x 160, row 80. A pixel's ray has horizontal angle atan(xs) and height on the cylinder
     ys/sqrt(1+xs^2). Plane pixels stay square: 2 px per angle unit horizontally = 1024/(2*pi) px per radian,
     so the same vertically. Both terms depend only on the column: computed once per column. */
  {
    static double *col_x, *col_k;
    static int ncol;
    double row_scale = 1024 / (2 * M_PI) / sky_s / focal;
    if (ncol < W) { free(col_x); free(col_k); col_x = malloc(sizeof(double) * W); col_k = malloc(sizeof(double) * W); ncol = W; }
    for (x = 0; x < W; x++)
    {
      double xs = (x + 0.5 - W / 2.0) / focal;
      col_x[x] = 144 + 2 * (c.ang + atan(xs) * 512 / (2 * M_PI)) / sky_s;   /* plane column */
      col_k[x] = row_scale / sqrt(1 + xs * xs);                             /* plane rows per screen row */
    }
    {
      /* plane rows the view can show (col_k is largest at the centre column) */
      double kmax = 0;
      int r0, r1, *colw = NULL;
      for (x = 0; x < W; x++) if (col_k[x] > kmax) kmax = col_k[x];
      r0 = (int)floor(80 - (H / 2.0) * kmax) + sky_vs - 1;
      r1 = (int)floor(80 + (H / 2.0) * kmax) + sky_vs + 1;
      sky_texture(sky_base, r0, r1, 40 + sky_vs);
      colw = malloc(sizeof(int) * W);
      for (x = 0; x < W; x++) colw[x] = ((int)floor(col_x[x])) & 1023;   /* texture column per screen column */
      for (y = 0; y < H; y++)
      {
        double dy = y + 0.5 - H / 2.0, base_row = 80 + sky_vs - r0 + 4096;   /* +4096: truncation = floor */
        uint16 *out = hd + (py + y) * ow + px;
        const uint8 *iv = idx + y * W;
        for (x = 0; x < W; x++)
        {
          int v = iv[x];
          if (v) out[x] = pal2[v];
          else if (skytex)
          {
            int r = (int)(base_row + dy * col_k[x]) - 4096;
            out[x] = (r >= 0 && r < skytex_rows) ? skytex[r * 1024 + colw[x]] : zt_vdp_pixel(0);
          }
          else out[x] = sky_pixel(sky_base, (int)floor(col_x[x]), (int)floor(80 + dy * col_k[x]) + sky_vs, 40 + sky_vs);
        }
      }
      free(colw);
    }
  }
  /* compact HUD from the emulated screen, along the bottom: radar left, portrait right, and in the middle the
     health box, the weapons bar and the armour box side by side, the boxes as tall as the bar; the
     player's weapon above the weapons bar */
  {
    double sc = zt_hd_ui_scale > 0 ? zt_hd_ui_scale : H / 360.0, k;
    int m, rw2, rh2, pw2, ww, wh, bw, mid, by, cx;
    if (sc < 0.5) sc = 0.5;
    if (zt_hd_weapon) view_sprites(px, py, W, H, py + H - (int)(6 * sc) - (int)(36 * sc) - (int)(4 * sc), 3.2 * sc);
    m = (int)(6 * sc);
    rw2 = (int)(92 * sc); rh2 = (int)(92 * sc); pw2 = (int)(126 * sc);
    /* middle group: box (28x18 scaled to the bar's 36 rows: 56 wide), gap, bar 240x36, gap, box */
    k = sc;
    mid = W - rw2 - pw2 - 4 * m;                  /* room between radar and portrait */
    if ((240 + 2 * 56) * k + 2 * m > mid) k = (mid - 2 * m) / (double)(240 + 2 * 56);
    ww = (int)(240 * k); wh = (int)(36 * k); bw = (int)(56 * k);
    by = py + H - m - rh2;
    cx = px + W / 2;
    blit_fit(native, npitch, 100, 130, 92, 92, px + m, by, rw2, rh2);                                  /* radar */
    blit_fit(native, npitch, 192, 130, 126, 92, px + W - m - pw2, by, pw2, rh2);                       /* portrait */
    if (ww > 0)
    {
      int wy = py + H - m - wh;
      blit_fit(native, npitch, 40, 0, 240, 36, cx - ww / 2, wy, ww, wh);                               /* weapons */
      ammo_counts(native, npitch, cx - ww / 2, wy, k);
      blit_fit(native, npitch, 2, 66, 28, 18, cx - ww / 2 - m - bw, wy, bw, wh);                       /* health */
      blit_fit(native, npitch, 290, 66, 28, 18, cx + (ww + 1) / 2 + m, wy, bw, wh);                    /* armour */
    }
  }
}

/* ---------------------------------------------------------------- settings menu */
typedef struct { const char *name; int count; const char *labels[12]; } menu_item_t;
static const char *res_list[] = {"960x540", "1280x720", "1600x900", "1920x1080", "2560x1440", "3840x2160"};
static const int fov_list[] = {90, 100, 106, 110, 120};
static const float hud_list[] = {0, 1, 1.5f, 2, 2.5f, 3, 4};
static const unsigned key_codes[] = {'g', 'j', 'k', 'l', 'm', 'n', 't', 'u', 'y', 'b', 'v', 9, '`'};
static const char *key_names[] = {"G", "J", "K", "L", "M", "N", "T", "U", "Y", "B", "V", "Tab", "`"};
#define NKEYS 13
enum { M_RES, M_FOV, M_LAYOUT, M_TOGGLE, M_HUD, M_WEAPON, M_SKY, M_SKYEXT, M_SHADE, M_MENUKEY, M_COUNT };
static const char *layout_names[] = {"HD only", "Side by side", "Top / bottom", "Switch with key"};

static int idx_of_res(void)
{
  int i; char b[32]; snprintf(b, sizeof b, "%dx%d", zt_hd_w, zt_hd_h);
  for (i = 0; i < 6; i++) if (!strcmp(b, res_list[i])) return i;
  return 3;
}
static int idx_of_key(unsigned k) { int i; for (i = 0; i < NKEYS; i++) if (key_codes[i] == k) return i; return 0; }
static int idx_of_fov(void) { int i; for (i = 0; i < 5; i++) if ((int)zt_hd_fov == fov_list[i]) return i; return 2; }
static int idx_of_hud(void) { int i; for (i = 0; i < 7; i++) if (zt_hd_ui_scale == hud_list[i]) return i; return 0; }

static void value_text(int item, char *b, int n)
{
  switch (item)
  {
    case M_RES: snprintf(b, n, "%dx%d", zt_hd_w, zt_hd_h); break;
    case M_FOV: snprintf(b, n, "%d deg%s", (int)zt_hd_fov, (int)zt_hd_fov == 90 ? " (original)" : ""); break;
    case M_LAYOUT: snprintf(b, n, "%s", layout_names[zt_hd_layout & 3]); break;
    case M_TOGGLE: snprintf(b, n, "%s", key_names[idx_of_key(zt_hd_toggle_key)]); break;
    case M_HUD: if (zt_hd_ui_scale > 0) snprintf(b, n, "%gx", zt_hd_ui_scale); else snprintf(b, n, "Auto"); break;
    case M_WEAPON: snprintf(b, n, "%s", zt_hd_weapon ? "Shown" : "Hidden"); break;
    case M_SKY: snprintf(b, n, "%s", zt_hd_sky_fill ? "Fill view height" : "Original band"); break;
    case M_SHADE: snprintf(b, n, "%s", zt_hd_smooth ? "Smooth" : "Dither (original)"); break;
    case M_SKYEXT: snprintf(b, n, "%s", zt_hd_sky_ext == 2 ? "Stars, full planet" : zt_hd_sky_ext ? "Stars" : "Black"); break;
    case M_MENUKEY: snprintf(b, n, "%s", key_names[idx_of_key(zt_hd_menu_key)]); break;
  }
}
static const char *item_names[] = {"Resolution", "Field of view", "Original screen", "Switch key", "HUD scale",
                                   "Weapon", "Sky", "Sky beyond band", "Shading", "Menu key"};

void zt_hd_save_cfg(void)
{
  FILE *f;
  if (!zt_hd_cfg_path[0] || !(f = fopen(zt_hd_cfg_path, "w"))) return;
  fprintf(f, "res=%dx%d\nfov=%g\nlayout=%d\ntoggle_key=%u\nhud=%g\nweapon=%d\nsky_fill=%d\nsky_ext=%d\nsmooth=%d\nmenu_key=%u\n",
          zt_hd_w, zt_hd_h, zt_hd_fov, zt_hd_layout, zt_hd_toggle_key, zt_hd_ui_scale, zt_hd_weapon, zt_hd_sky_fill,
          zt_hd_sky_ext, zt_hd_smooth, zt_hd_menu_key);
  fclose(f);
}

void zt_hd_load_cfg(void)
{
  FILE *f; char line[128];
  if (!zt_hd_cfg_path[0] || !(f = fopen(zt_hd_cfg_path, "r"))) return;
  while (fgets(line, sizeof line, f))
  {
    int a, b; float v; unsigned u;
    if (sscanf(line, "res=%dx%d", &a, &b) == 2 && a >= 320 && b >= 224) { zt_hd_w = a; zt_hd_h = b; }
    else if (sscanf(line, "fov=%f", &v) == 1 && v >= 60 && v <= 150) zt_hd_fov = v;
    else if (sscanf(line, "layout=%d", &a) == 1) zt_hd_layout = a & 3;
    else if (sscanf(line, "toggle_key=%u", &u) == 1) zt_hd_toggle_key = u;
    else if (sscanf(line, "hud=%f", &v) == 1) zt_hd_ui_scale = v;
    else if (sscanf(line, "weapon=%d", &a) == 1) zt_hd_weapon = a != 0;
    else if (sscanf(line, "sky_fill=%d", &a) == 1) zt_hd_sky_fill = a != 0;
    else if (sscanf(line, "smooth=%d", &a) == 1) zt_hd_smooth = a != 0;
    else if (sscanf(line, "sky_ext=%d", &a) == 1) zt_hd_sky_ext = a < 0 ? 0 : a > 2 ? 2 : a;
    else if (sscanf(line, "menu_key=%u", &u) == 1) zt_hd_menu_key = u;
  }
  fclose(f);
}

static void menu_change(int item, int dir)
{
  int i, size_change = 0;
  switch (item)
  {
    case M_RES: i = (idx_of_res() + dir + 6) % 6; sscanf(res_list[i], "%dx%d", &zt_hd_w, &zt_hd_h); size_change = 1; break;
    case M_FOV: zt_hd_fov = (float)fov_list[(idx_of_fov() + dir + 5) % 5]; break;
    case M_LAYOUT: zt_hd_layout = (zt_hd_layout + dir + 4) & 3; show_original = 0; size_change = 1; break;
    case M_TOGGLE: zt_hd_toggle_key = key_codes[(idx_of_key(zt_hd_toggle_key) + dir + NKEYS) % NKEYS]; break;
    case M_HUD: zt_hd_ui_scale = hud_list[(idx_of_hud() + dir + 7) % 7]; break;
    case M_WEAPON: zt_hd_weapon = !zt_hd_weapon; break;
    case M_SKY: zt_hd_sky_fill = !zt_hd_sky_fill; break;
    case M_SHADE: zt_hd_smooth = !zt_hd_smooth; break;
    case M_SKYEXT: zt_hd_sky_ext = (zt_hd_sky_ext + dir + 3) % 3; planet_ov.tried = planet_ov.valid = 0; sky_png.ptr = 0; break;
    case M_MENUKEY: zt_hd_menu_key = key_codes[(idx_of_key(zt_hd_menu_key) + dir + NKEYS) % NKEYS]; break;
  }
  zt_hd_save_cfg();
  if (size_change && zt_hd_av_changed) zt_hd_av_changed();
}

/* Called once per frame by libretro.c after input polling. Returns 1 while the menu is open (the
   emulation is paused then). */
int zt_hd_input(void)
{
  static int prev[8];
  unsigned keys[6];
  int now[6], hit[6], i;
  if (!zt_hd_key) return 0;
  keys[0] = zt_hd_menu_key; keys[1] = zt_hd_toggle_key; keys[2] = 273; keys[3] = 274; keys[4] = 276; keys[5] = 275;
  for (i = 0; i < 6; i++) { now[i] = zt_hd_key(keys[i]) ? 1 : 0; hit[i] = now[i] && !prev[i]; prev[i] = now[i]; }
  if (hit[0]) menu_open = !menu_open;
  if (!menu_open)
  {
    if (hit[1] && zt_hd_layout == 3) show_original = !show_original;
    return 0;
  }
  if (hit[2]) menu_sel = (menu_sel + M_COUNT - 1) % M_COUNT;    /* up */
  if (hit[3]) menu_sel = (menu_sel + 1) % M_COUNT;              /* down */
  if (hit[4]) menu_change(menu_sel, -1);                        /* left */
  if (hit[5]) menu_change(menu_sel, +1);                        /* right */
  return 1;
}

static void text(int x, int y, const char *str, int ts, uint16 col)
{
  int i, gy, gx;
  for (i = 0; str[i]; i++)
  {
    int ch = (unsigned char)str[i];
    if (ch < 32 || ch > 126) ch = '?';
    for (gy = 0; gy < 12 * ts; gy++)
      for (gx = 0; gx < 8 * ts; gx++)
      {
        int xx = x + i * 8 * ts + gx, yy = y + gy;
        if (xx < 0 || yy < 0 || xx >= ow || yy >= oh) continue;
        if (zt_font[ch - 32][gy / ts] & (0x80 >> (gx / ts))) hd[yy * ow + xx] = col;
      }
  }
}

static void draw_menu(void)
{
  int ts = oh >= 720 ? 2 : 1, lh = 16 * ts, bw = 46 * 8 * ts, bh = (M_COUNT + 5) * lh, bx = (ow - bw) / 2, by = (oh - bh) / 2;
  int i, x, y;
  char b[64];
  for (y = by; y < by + bh && y < oh; y++)          /* darkened box */
    for (x = bx; x < bx + bw && x < ow; x++)
      if (y >= 0 && x >= 0) { uint16 p = hd[y * ow + x]; hd[y * ow + x] = (p >> 2) & 0x39E7; }
  for (x = bx; x < bx + bw; x++) { if (by >= 0) hd[by * ow + x] = 0xFFE0; if (by + bh - 1 < oh) hd[(by + bh - 1) * ow + x] = 0xFFE0; }
  text(bx + 2 * 8 * ts, by + lh / 2, "ZERO TOLERANCE HD RENDERER", ts, 0xFFE0);
  for (i = 0; i < M_COUNT; i++)
  {
    uint16 col = i == menu_sel ? 0xFFFF : 0x9CF3;
    value_text(i, b, sizeof b);
    text(bx + 2 * 8 * ts, by + (i + 2) * lh, i == menu_sel ? ">" : " ", ts, 0xFFE0);
    text(bx + 4 * 8 * ts, by + (i + 2) * lh, item_names[i], ts, col);
    text(bx + 21 * 8 * ts, by + (i + 2) * lh, i == menu_sel ? "<" : " ", ts, col);
    text(bx + 23 * 8 * ts, by + (i + 2) * lh, b, ts, col);
    text(bx + 23 * 8 * ts + (int)strlen(b) * 8 * ts + 8 * ts, by + (i + 2) * lh, i == menu_sel ? ">" : " ", ts, col);
  }
  snprintf(b, sizeof b, "Up/Down select, Left/Right change, %s close", key_names[idx_of_key(zt_hd_menu_key)]);
  text(bx + 2 * 8 * ts, by + (M_COUNT + 3) * lh, b, ts, 0x7BEF);
}

/* Compose the output frame. native: the emulator's RGB565 frame (pitch in pixels).
   Returns the output buffer; its size is zt_hd_output_size(). */
uint16 *zt_hd_compose(const uint16 *native, int npitch, int nw, int nh)
{
  int game;
  if (!prepare_rom()) return NULL;
  ensure_buffers();
  zt_hd_output_size(&ow, &oh);
  /* tell the ROM patch not to render between ticks */
  WRITE_BYTE(work_ram, 0x7772, 0); WRITE_BYTE(work_ram, 0x7773, 1);
  game = in_gameplay();
  if (game) sky_capture();
  else { memset(sky_known, 0, sizeof sky_known); planet_ov.tried = planet_ov.valid = 0; sky_png.ptr = 0; }   /* a new level may have another sky */
  if (zt_hd_layout == 1 || zt_hd_layout == 2)
  {
    int sbs = zt_hd_layout == 1, pw = sbs ? ow / 2 : ow, ph = sbs ? oh : oh / 2, qx = sbs ? pw : 0, qy = sbs ? 0 : ph;
    panel_native(native, npitch, nw, nh, 0, 0, pw, ph);
    if (game) panel_hd(native, npitch, qx, qy, pw, ph);
    else panel_native(native, npitch, nw, nh, qx, qy, pw, ph);
  }
  else if (game && !(zt_hd_layout == 3 && show_original)) panel_hd(native, npitch, 0, 0, ow, oh);
  else panel_native(native, npitch, nw, nh, 0, 0, ow, oh);
  if (menu_open) draw_menu();
  return hd;
}
