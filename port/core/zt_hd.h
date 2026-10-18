#ifndef ZT_HD_H
#define ZT_HD_H
/* Zero Tolerance HD renderer (see zt_hd.c) */
extern int zt_hd_enabled;
extern int zt_hd_w, zt_hd_h;
extern float zt_hd_fov;
extern int zt_hd_layout;
extern float zt_hd_ui_scale;
void zt_hd_output_size(int *w, int *h);
extern int zt_hd_weapon, zt_hd_autoswitch, zt_hd_sky_fill, zt_hd_sky_ext, zt_hd_smooth, zt_hd_stretch_native;
extern unsigned zt_hd_toggle_key, zt_hd_menu_key;
extern int (*zt_hd_key)(unsigned retrok);
extern int (*zt_hd_joy)(unsigned id);
extern int (*zt_hd_analog)(unsigned index, unsigned id);
extern int zt_hd_sticks, zt_hd_turn_speed;
extern void (*zt_hd_av_changed)(void);
extern char zt_hd_cfg_path[1024], zt_hd_rom_dir[1024];
int zt_hd_input(void);
void zt_hd_pad(unsigned short *pad);
void zt_hd_load_cfg(void);
void zt_hd_save_cfg(void);
extern unsigned int zt_hd_after_pc, zt_hd_after_init_pc, zt_hd_hook_pc[11];
void zt_hd_hook(unsigned int pc, unsigned int *regs);
extern const char *zt_hd_games[8];
extern int zt_hd_ngames, zt_hd_game_cur, zt_hd_game_req;
void zt_hd_rom_changed(void);
unsigned short *zt_hd_compose(const unsigned short *native, int npitch, int nw, int nh);
#endif
