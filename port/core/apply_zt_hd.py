#!/usr/bin/env python3
"""Apply the Zero Tolerance HD renderer to a Genesis Plus GX (libretro) checkout.

    python3 apply_zt_hd.py <Genesis-Plus-GX dir>
    make -f Makefile.libretro            (in that dir)

Adds core options: "Zero Tolerance HD renderer", resolution, field of view; and CPU speeds up to 1500%.
"""
import sys, shutil, pathlib, re

HERE = pathlib.Path(__file__).resolve().parent
G = pathlib.Path(sys.argv[1])

def patch(path, old, new, count=1, done_if=None):
    p = G / path; s = p.read_text()
    if new in s or (done_if and done_if in s): return    # already applied (done_if: a block later patches edit)
    assert s.count(old) >= 1, f"{path}: anchor not found: {old[:60]!r}"
    p.write_text(s.replace(old, new, count))

shutil.copy(HERE / "zt_hd.c", G / "core" / "zt_hd.c")
shutil.copy(HERE / "zt_hd.h", G / "core" / "zt_hd.h")
shutil.copy(HERE / "zt_font.h", G / "core" / "zt_font.h")
shutil.copy(HERE / "zt_hud_font.h", G / "core" / "zt_hud_font.h")

# palette accessor
patch("core/vdp_render.c", "static PIXEL_OUT_T pixel[0x100];",
      "static PIXEL_OUT_T pixel[0x100];\nPIXEL_OUT_T zt_vdp_pixel(int index) { return pixel[index & 0xFF]; }")

# 68k hooks (render start, sprite pieces and their anchors, edge pass, sprite projection, render end);
# an older build's hook line is updated in place
HOOK = ("    if (zt_hd_enabled && (REG_PC == 0xB9A6 || REG_PC == 0xEDA0 || REG_PC == 0x13360 || REG_PC == 0x13388 || "
        "REG_PC == 0x113EE || REG_PC == 0x1BCB4 || REG_PC == 0x9D72 || REG_PC == 0x1329A || REG_PC == zt_hd_after_pc || REG_PC == zt_hd_after_init_pc))\n")
_m = G / "core/m68k/m68kcpu.c"; _s = _m.read_text()
_s = re.sub(r"    if \(zt_hd_enabled && \(REG_PC == 0xB9A6[^\n]*\n", lambda _: HOOK, _s)
_m.write_text(_s)
patch("core/m68k/m68kcpu.c", "    /* Decode next instruction */\n    REG_IR = m68ki_read_imm_16();\n\n    /* 68K bus access refresh delay (Mega Drive / Genesis specific) */",
      HOOK +
      "      zt_hd_hook(REG_PC, REG_DA);\n\n"
      "    /* Decode next instruction */\n    REG_IR = m68ki_read_imm_16();\n\n    /* 68K bus access refresh delay (Mega Drive / Genesis specific) */")
patch("core/m68k/m68kcpu.c", '#include "m68kcpu.h"', '#include "m68kcpu.h"\n#include "../zt_hd.h"')

# libretro: options, geometry, output, keyboard, in-game menu (pauses emulation)
L = "libretro/libretro.c"
patch(L, '#include "libretro_core_options.h"', '#include "libretro_core_options.h"\n#include "zt_hd.h"')
patch(L, '''static bool update_viewport(void)
{''', '''static int zt_key_fn(unsigned k) { return input_state_cb ? input_state_cb(0, RETRO_DEVICE_KEYBOARD, 0, k) : 0; }
static int zt_joy_fn(unsigned id) { return input_state_cb ? input_state_cb(0, RETRO_DEVICE_JOYPAD, 0, id) : 0; }
static void zt_av_fn(void)
{
  struct retro_system_av_info info;
  retro_get_system_av_info(&info);
  environ_cb(RETRO_ENVIRONMENT_SET_SYSTEM_AV_INFO, &info);
}

static bool update_viewport(void)
{''')
patch(L, '''  var.key = "genesis_plus_gx_no_sprite_limit";''', done_if='"genesis_plus_gx_zt_hd_res"', new='''  {
    int old_en = zt_hd_enabled, old_w = zt_hd_w, old_h = zt_hd_h;
    var.key = "genesis_plus_gx_zt_hd"; var.value = NULL;
    environ_cb(RETRO_ENVIRONMENT_GET_VARIABLE, &var);
    zt_hd_enabled = var.value && !strcmp(var.value, "enabled");
    var.key = "genesis_plus_gx_zt_hd_res"; var.value = NULL;
    environ_cb(RETRO_ENVIRONMENT_GET_VARIABLE, &var);
    if (var.value) sscanf(var.value, "%dx%d", &zt_hd_w, &zt_hd_h);
    var.key = "genesis_plus_gx_zt_hd_fov"; var.value = NULL;
    environ_cb(RETRO_ENVIRONMENT_GET_VARIABLE, &var);
    if (var.value) zt_hd_fov = (float)atof(var.value);
    if (zt_hd_fov < 60 || zt_hd_fov > 150) zt_hd_fov = 106;
    var.key = "genesis_plus_gx_zt_hd_ui_scale"; var.value = NULL;
    environ_cb(RETRO_ENVIRONMENT_GET_VARIABLE, &var);
    zt_hd_ui_scale = (var.value && strcmp(var.value, "auto")) ? (float)atof(var.value) : 0;
    var.key = "genesis_plus_gx_zt_hd_layout"; var.value = NULL;
    environ_cb(RETRO_ENVIRONMENT_GET_VARIABLE, &var);
    {
      int old_layout = zt_hd_layout;
      zt_hd_layout = !var.value ? 0 : !strcmp(var.value, "side_by_side") ? 1 : !strcmp(var.value, "top_bottom") ? 2
                   : !strcmp(var.value, "toggle") ? 3 : 0;
      if (old_layout != zt_hd_layout) old_w = -1;      /* output size changes */
    }
    var.key = "genesis_plus_gx_zt_hd_toggle_key"; var.value = NULL;
    environ_cb(RETRO_ENVIRONMENT_GET_VARIABLE, &var);
    if (var.value) zt_hd_toggle_key = !strcmp(var.value, "tab") ? 9 : !strcmp(var.value, "backquote") ? 96 : (unsigned char)var.value[0];
    var.key = "genesis_plus_gx_zt_hd_menu_key"; var.value = NULL;
    environ_cb(RETRO_ENVIRONMENT_GET_VARIABLE, &var);
    if (var.value) zt_hd_menu_key = !strcmp(var.value, "tab") ? 9 : !strcmp(var.value, "backquote") ? 96 : (unsigned char)var.value[0];
    var.key = "genesis_plus_gx_zt_hd_weapon"; var.value = NULL;
    environ_cb(RETRO_ENVIRONMENT_GET_VARIABLE, &var);
    if (var.value) zt_hd_weapon = strcmp(var.value, "hidden") != 0;
    var.key = "genesis_plus_gx_zt_hd_autoswitch"; var.value = NULL;
    environ_cb(RETRO_ENVIRONMENT_GET_VARIABLE, &var);
    if (var.value) zt_hd_autoswitch = strcmp(var.value, "off") != 0;
    var.key = "genesis_plus_gx_zt_hd_sky"; var.value = NULL;
    environ_cb(RETRO_ENVIRONMENT_GET_VARIABLE, &var);
    if (var.value) zt_hd_sky_fill = !strcmp(var.value, "fill");
    zt_hd_key = zt_key_fn; zt_hd_joy = zt_joy_fn; zt_hd_av_changed = zt_av_fn;
    if (first_run)
    {
      const char *sd = NULL;
      if (environ_cb(RETRO_ENVIRONMENT_GET_SAVE_DIRECTORY, &sd) && sd)
        fill_pathname_join(zt_hd_cfg_path, sd, "zt_hd.cfg", sizeof(zt_hd_cfg_path));
      zt_hd_load_cfg();                                /* settings changed in the in-game menu win */
    }
    if (zt_hd_w < 320 || zt_hd_w > 7680 || zt_hd_h < 224 || zt_hd_h > 4320) { zt_hd_w = 1280; zt_hd_h = 720; }
    if (!first_run && (old_en != zt_hd_enabled || old_w != zt_hd_w || old_h != zt_hd_h))
    {
      struct retro_system_av_info info;
      retro_get_system_av_info(&info);
      environ_cb(RETRO_ENVIRONMENT_SET_SYSTEM_AV_INFO, &info);
    }
  }

  var.key = "genesis_plus_gx_no_sprite_limit";''')
patch(L, '''   if (!retro_fps)
      retro_fps = info->timing.fps;''', '''   if (zt_hd_enabled)
   {
      int ow, oh;
      zt_hd_output_size(&ow, &oh);
      info->geometry.base_width = ow;
      info->geometry.base_height = oh;
      info->geometry.max_width = zt_hd_w;
      info->geometry.max_height = zt_hd_h > oh ? zt_hd_h : oh;
      info->geometry.aspect_ratio = (float)ow / (float)oh;
   }

   if (!retro_fps)
      retro_fps = info->timing.fps;''')
patch(L, '''   if (!do_skip)
      video_cb(bitmap.data + bmdoffset, vwidth - vwoffset, vheight, 720 * 2);''', '''   if (zt_hd_enabled && !do_skip)
   {
      unsigned short *hdout = zt_hd_compose((const unsigned short *)(bitmap.data + bmdoffset), 720, vwidth - vwoffset, vheight);
      if (hdout)
      {
         int ow, oh;
         zt_hd_output_size(&ow, &oh);
         video_cb(hdout, ow, oh, ow * 2);
         audio_cb(soundbuffer, soundbuffer_size);
         return;
      }
   }
   if (!do_skip)
      video_cb(bitmap.data + bmdoffset, vwidth - vwoffset, vheight, 720 * 2);''')

patch(L, '''   is_running = true;

#ifdef HAVE_OVERCLOCK
  /* update overclock delay */''', '''   is_running = true;

   if (zt_hd_enabled && input_poll_cb)
   {
      input_poll_cb();
      if (zt_hd_input())               /* in-game HD menu open: emulation paused, redraw with the menu */
      {
         static int16_t zt_silence[2 * 1024];
         unsigned short *hdout = zt_hd_compose((const unsigned short *)(bitmap.data + bmdoffset), 720, vwidth - vwoffset, vheight);
         if (hdout)
         {
            int ow, oh;
            zt_hd_output_size(&ow, &oh);
            video_cb(hdout, ow, oh, ow * 2);
         }
         else
            video_cb(NULL, vwidth - vwoffset, vheight, 720 * 2);
         audio_cb(zt_silence, 735);
         return;
      }
   }

#ifdef HAVE_OVERCLOCK
  /* update overclock delay */''')

patch(L, '''  if (libretro_supports_bitmasks)
     osd_input_update_internal_bitmasks();
  else
     osd_input_update_internal();
}''', '''  if (libretro_supports_bitmasks)
     osd_input_update_internal_bitmasks();
  else
     osd_input_update_internal();

  if (zt_hd_enabled)
     zt_hd_pad(&input.pad[0]);          /* weapon auto-switch */
}''')

# core options
O = "libretro/libretro_core_options.h"
patch(O, '''         { "500", "500%" },
         { NULL, NULL },''', '''         { "500", "500%" },
         { "600", "600%" },
         { "800", "800%" },
         { "1000", "1000%" },
         { "1200", "1200%" },
         { "1500", "1500%" },
         { NULL, NULL },''')
if '"genesis_plus_gx_zt_hd_res",' not in (G / O).read_text(): patch(O, '''#ifdef HAVE_OVERCLOCK
   {
      "genesis_plus_gx_overclock",''', '''   {
      "genesis_plus_gx_zt_hd",
      "Zero Tolerance HD Renderer",
      NULL,
      "Re-render Zero Tolerance's 3D view natively at high resolution with a wide field of view and a compact HUD. Needs the zt_high_fps patched ROM.",
      NULL,
      "hacks",
      {
         { "disabled", NULL },
         { "enabled",  NULL },
         { NULL, NULL },
      },
      "disabled"
   },
   {
      "genesis_plus_gx_zt_hd_res",
      "Zero Tolerance HD Resolution",
      NULL,
      "Output resolution of the HD renderer.",
      NULL,
      "hacks",
      {
         { "960x540",   NULL },
         { "1280x720",  NULL },
         { "1600x900",  NULL },
         { "1920x1080", NULL },
         { "2560x1440", NULL },
         { NULL, NULL },
      },
      "1280x720"
   },
   {
      "genesis_plus_gx_zt_hd_layout",
      "Zero Tolerance HD Layout",
      NULL,
      "HD only, or the original screen and the HD render side by side (two 16:9 panels, each half the resolution width).",
      NULL,
      "hacks",
      {
         { "hd",           "HD only" },
         { "side_by_side", "Side by side (left / right)" },
         { "top_bottom",   "Top / bottom" },
         { "toggle",       "Switch with key" },
         { NULL, NULL },
      },
      "hd"
   },
   {
      "genesis_plus_gx_zt_hd_toggle_key",
      "Zero Tolerance HD Switch Key",
      NULL,
      "Keyboard key that switches between the HD view and the original screen (layout: Switch with key).",
      NULL,
      "hacks",
      {
         { "g", "G" }, { "j", "J" }, { "k", "K" }, { "l", "L" }, { "n", "N" }, { "t", "T" },
         { "u", "U" }, { "y", "Y" }, { "b", "B" }, { "v", "V" }, { "tab", "Tab" }, { "backquote", "`" },
         { NULL, NULL },
      },
      "g"
   },
   {
      "genesis_plus_gx_zt_hd_menu_key",
      "Zero Tolerance HD Menu Key",
      NULL,
      "Keyboard key that opens the in-game HD settings menu (pauses the game; arrows change settings).",
      NULL,
      "hacks",
      {
         { "m", "M" }, { "j", "J" }, { "k", "K" }, { "l", "L" }, { "n", "N" }, { "t", "T" },
         { "u", "U" }, { "y", "Y" }, { "b", "B" }, { "v", "V" }, { "tab", "Tab" }, { "backquote", "`" },
         { NULL, NULL },
      },
      "m"
   },
   {
      "genesis_plus_gx_zt_hd_weapon",
      "Zero Tolerance HD Weapon",
      NULL,
      "Draw the player's weapon sprite in the HD view.",
      NULL,
      "hacks",
      {
         { "shown",  "Shown" },
         { "hidden", "Hidden" },
         { NULL, NULL },
      },
      "shown"
   },
   {
      "genesis_plus_gx_zt_hd_autoswitch",
      "Zero Tolerance HD Out of Ammo",
      NULL,
      "On: when the current weapon runs out of ammo, switch to the next weapon that has some (presses C for you). Off: the original (stay on the empty slot).",
      NULL,
      "hacks",
      {
         { "on",  "Switch weapon" },
         { "off", "Keep (original)" },
         { NULL, NULL },
      },
      "on"
   },
   {
      "genesis_plus_gx_zt_hd_sky",
      "Zero Tolerance HD Sky",
      NULL,
      "Original: the star band at its original size. Fill: scaled uniformly (planet stays round) to fill the view height.",
      NULL,
      "hacks",
      {
         { "original", "Original band" },
         { "fill",     "Fill view height" },
         { NULL, NULL },
      },
      "original"
   },
   {
      "genesis_plus_gx_zt_hd_ui_scale",
      "Zero Tolerance HD HUD Scale",
      NULL,
      "Size of the HUD pieces (radar, weapons, portrait, health, armour) along the bottom. Auto scales with the output height.",
      NULL,
      "hacks",
      {
         { "auto", "Auto" },
         { "1",    "1x" },
         { "1.5",  "1.5x" },
         { "2",    "2x" },
         { "2.5",  "2.5x" },
         { "3",    "3x" },
         { "4",    "4x" },
         { NULL, NULL },
      },
      "auto"
   },
   {
      "genesis_plus_gx_zt_hd_fov",
      "Zero Tolerance HD Field of View",
      NULL,
      "Horizontal field of view in degrees (the original is 90).",
      NULL,
      "hacks",
      {
         { "90",  NULL },
         { "100", NULL },
         { "106", NULL },
         { "110", NULL },
         { "120", NULL },
         { NULL, NULL },
      },
      "106"
   },
#ifdef HAVE_OVERCLOCK
   {
      "genesis_plus_gx_overclock",''')

# sky beyond the original band (separate patches, so checkouts patched by an older version get it too)
patch(L, """    if (var.value) zt_hd_sky_fill = !strcmp(var.value, "fill");""",
      """    if (var.value) zt_hd_sky_fill = !strcmp(var.value, "fill");
    var.key = "genesis_plus_gx_zt_hd_sky_ext"; var.value = NULL;
    environ_cb(RETRO_ENVIRONMENT_GET_VARIABLE, &var);
    if (var.value) zt_hd_sky_ext = !strcmp(var.value, "black") ? 0 : !strcmp(var.value, "stars") ? 1 : 2;""")
patch(O, """      "original"
   },""", """      "original"
   },
   {
      "genesis_plus_gx_zt_hd_sky_ext",
      "Zero Tolerance HD Sky Beyond Band",
      NULL,
      "The original sky art is a band of rows. Enhanced: the level's improved sky (a redrawn panorama PNG when there is one, else the art extended and completed, e.g. the planet the art cuts off). Stars: the level's own stars repeated above and below the band. Black: nothing beyond the band.",
      NULL,
      "hacks",
      {
         { "enhanced", "Enhanced" },
         { "stars",       "Stars" },
         { "black",       "Black" },
         { NULL, NULL },
      },
      "enhanced"
   },""")
# shading dither option (separate, like the sky one)
patch(L, """    if (var.value) zt_hd_sky_ext = !strcmp(var.value, "black") ? 0 : !strcmp(var.value, "stars") ? 1 : 2;""",
      """    if (var.value) zt_hd_sky_ext = !strcmp(var.value, "black") ? 0 : !strcmp(var.value, "stars") ? 1 : 2;
    var.key = "genesis_plus_gx_zt_hd_shading"; var.value = NULL;
    environ_cb(RETRO_ENVIRONMENT_GET_VARIABLE, &var);
    if (var.value) zt_hd_smooth = strcmp(var.value, "dither") != 0;""")
patch(O, """      "enhanced"
   },""", """      "enhanced"
   },
   {
      "genesis_plus_gx_zt_hd_shading",
      "Zero Tolerance HD Shading",
      NULL,
      "Distance shading and the floor gradient are drawn by the game as pixel pairs of two colours (a dither). Smooth: the two colours blended. Dither: the pattern, as in the original.",
      NULL,
      "hacks",
      {
         { "smooth", "Smooth" },
         { "dither", "Dither (original)" },
         { NULL, NULL },
      },
      "smooth"
   },""")
# the game's folder, where the sky PNG may also be
patch(L, """        fill_pathname_join(zt_hd_cfg_path, sd, "zt_hd.cfg", sizeof(zt_hd_cfg_path));""",
      """        fill_pathname_join(zt_hd_cfg_path, sd, "zt_hd.cfg", sizeof(zt_hd_cfg_path));
      strncpy(zt_hd_rom_dir, g_rom_dir, sizeof(zt_hd_rom_dir) - 1);""")
print("applied to", G)
