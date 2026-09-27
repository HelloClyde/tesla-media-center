#ifndef GAM4980_CORE_H
#define GAM4980_CORE_H

#include "bda_sdk.h"

#define GAM4980_LCD_WIDTH 159
#define GAM4980_LCD_HEIGHT 96
#define GAM4980_LCD_STRIDE (GAM4980_LCD_WIDTH + 1)
#define GAM4980_LCD_PACKED_STRIDE (GAM4980_LCD_STRIDE / 8)
#define GAM4980_LCD_PACKED_SIZE \
    (GAM4980_LCD_PACKED_STRIDE * GAM4980_LCD_HEIGHT)
#define GAM4980_ROM_SIZE 0x200000u
#define GAM4980_RAM_SIZE 0x8000u
#define GAM4980_FLASH_SIZE 0x200000u
#define GAM4980_SAVE_SIZE 0x14000u
#define GAM4980_GAME_MAX_SIZE 0x1e0000u
#define GAM4980_GAME_HEADER_SIZE 0x46u

enum gam4980_key {
    GAM4980_KEY_POWER = 0x00,
    GAM4980_KEY_MENU = 0x01,
    GAM4980_KEY_EC_SJ = 0x02,
    GAM4980_KEY_EC_SW = 0x03,
    GAM4980_KEY_CE = 0x04,
    GAM4980_KEY_DIALOG = 0x05,
    GAM4980_KEY_DOWNLOAD = 0x06,
    GAM4980_KEY_SPEAK = 0x07,
    GAM4980_KEY_1 = 0x08,
    GAM4980_KEY_2 = 0x09,
    GAM4980_KEY_3 = 0x0a,
    GAM4980_KEY_4 = 0x0b,
    GAM4980_KEY_5 = 0x0c,
    GAM4980_KEY_6 = 0x0d,
    GAM4980_KEY_7 = 0x0e,
    GAM4980_KEY_8 = 0x0f,
    GAM4980_KEY_Q = 0x10,
    GAM4980_KEY_W = 0x11,
    GAM4980_KEY_E = 0x12,
    GAM4980_KEY_R = 0x13,
    GAM4980_KEY_T = 0x14,
    GAM4980_KEY_Y = 0x15,
    GAM4980_KEY_U = 0x16,
    GAM4980_KEY_I = 0x17,
    GAM4980_KEY_A = 0x18,
    GAM4980_KEY_S = 0x19,
    GAM4980_KEY_D = 0x1a,
    GAM4980_KEY_F = 0x1b,
    GAM4980_KEY_G = 0x1c,
    GAM4980_KEY_H = 0x1d,
    GAM4980_KEY_J = 0x1e,
    GAM4980_KEY_K = 0x1f,
    GAM4980_KEY_INPUT = 0x20,
    GAM4980_KEY_Z = 0x21,
    GAM4980_KEY_X = 0x22,
    GAM4980_KEY_C = 0x23,
    GAM4980_KEY_V = 0x24,
    GAM4980_KEY_B = 0x25,
    GAM4980_KEY_N = 0x26,
    GAM4980_KEY_M = 0x27,
    GAM4980_KEY_SHIFT = 0x28,
    GAM4980_KEY_HELP = 0x29,
    GAM4980_KEY_SEARCH = 0x2a,
    GAM4980_KEY_INSERT = 0x2b,
    GAM4980_KEY_MODIFY = 0x2c,
    GAM4980_KEY_DELETE = 0x2d,
    GAM4980_KEY_EXIT = 0x2e,
    GAM4980_KEY_ENTER = 0x2f,
    GAM4980_KEY_9 = 0x30,
    GAM4980_KEY_0 = 0x31,
    GAM4980_KEY_O = 0x32,
    GAM4980_KEY_P = 0x33,
    GAM4980_KEY_L = 0x34,
    GAM4980_KEY_UP = 0x35,
    GAM4980_KEY_SPACE = 0x36,
    GAM4980_KEY_LEFT = 0x37,
    GAM4980_KEY_DOWN = 0x38,
    GAM4980_KEY_RIGHT = 0x39,
    GAM4980_KEY_PAGE_UP = 0x3a,
    GAM4980_KEY_PAGE_DOWN = 0x3b,
};

enum gam4980_lcd_theme {
    GAM4980_LCD_THEME_OFF = 0,
    GAM4980_LCD_THEME_GREEN,
    GAM4980_LCD_THEME_BLUE,
    GAM4980_LCD_THEME_YELLOW,
    GAM4980_LCD_THEME_COUNT,
};

typedef struct gam4980_buffers {
    u8 *ram;
    u8 *flash;
    u8 *rom_8;
    u8 *rom_e;
    u16 *framebuffer;
} gam4980_buffers_t;

int gam4980_init(const gam4980_buffers_t *buffers);
void gam4980_deinit(void);
u8 *gam4980_game_storage(void);
int gam4980_load_game_header(const u8 *header, u32 size);
void gam4980_key_down(u8 key);
void gam4980_step_frame(void);
int gam4980_render_frame(void);
void gam4980_run_frame(void);
int gam4980_cpu_halted(void);
const u8 *gam4980_packed_frame(void);
const u16 *gam4980_expand_frame(const u8 *packed_frame);
const u16 *gam4980_framebuffer(void);
void gam4980_set_lcd_theme(u32 theme);
u16 gam4980_lcd_background_color(void);
u16 gam4980_lcd_foreground_color(void);
u8 *gam4980_save_data(void);
int gam4980_save_dirty(void);
void gam4980_save_mark_clean(void);
int gam4980_shutdown_requested(void);
u16 gam4980_shutdown_pc(void);

#endif
