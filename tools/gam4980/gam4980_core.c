#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#include "bda_sdk.h"
#include "gam4980_core.h"

#define _DATA1          0x00
#define _DATA2          0x01
#define _DATA3          0x02
#define _DATA4          0x03
#define _ISR            0x04
#define _TISR           0x05
#define _BK_SEL         0x0c
#define _BK_ADRL        0x0d
#define _BK_ADRH        0x0e
#define _IRCNT          0x1b
#define __oper1         0x20
#define __oper2         0x23
#define __addr_reg      0x26
#define _SYSCON         0x200
#define _INCR           0x207
#define _ADDR1L         0x208
#define _ADDR1M         0x209
#define _ADDR1H         0x20a
#define _ADDR2L         0x20b
#define _ADDR2M         0x20c
#define _ADDR2H         0x20d
#define _ADDR3L         0x20e
#define _ADDR3M         0x20f
#define _ADDR3H         0x210
#define _ADDR4L         0x211
#define _ADDR4M         0x212
#define _ADDR4H         0x213
#define _PB             0x21b
#define _STCON          0x226
#define _ST1LD          0x227
#define _ST2LD          0x228
#define _ST3LD          0x229
#define _ST4LD          0x22a
#define _MTCT           0x22b
#define _STCTCON        0x22e
#define _CTLD           0x22f
#define _ALMMIN         0x230
#define _ALMHR          0x231
#define _ALMDAYL        0x232
#define _ALMDAYH        0x233
#define _RTCSEC         0x234
#define _RTCMIN         0x235
#define _RTCHR          0x236
#define _RTCDAYL        0x237
#define _RTCDAYH        0x238
#define _IER            0x23a
#define _TIER           0x23b
#define _AUDCON         0x23f
#define _KEYCODE        0x24e
#define _MACCTL         0x260
#define _KeyBuffTop     0x2003
#define _KeyBuffBottom  0x2004
#define _KeyBuffer      0x2008

#define LCD_WIDTH GAM4980_LCD_WIDTH
#define LCD_HEIGHT GAM4980_LCD_HEIGHT
#define LCD_STRIDE GAM4980_LCD_STRIDE
#define LCD_PACKED_STRIDE GAM4980_LCD_PACKED_STRIDE

static uint16_t *fb;
static int shutdown_requested;
static uint16_t shutdown_pc;
static uint32_t step_cycles;
static uint32_t step_ticked;
static uint32_t step_cycle_fraction;
static uint32_t rtc_frames;
static uint32_t timer_ticks[5];
static uint32_t lcd_nibble_lut[16][2];
static uint8_t lcd_frame[GAM4980_LCD_PACKED_SIZE];
static int lcd_frame_valid;
static int lcd_dirty;
static int save_dirty;


static void sys_isr(void);
static bool sys_halt_p(void);
static void mem_bs(uint8_t sel);
static uint8_t mem_read(uint16_t addr);
static uint8_t mem_readx(uint16_t addr);
static uint16_t mem_read16(uint16_t addr);
static uint16_t mem_readx16(uint16_t addr);
static uint16_t mem_read16_wrapped(uint16_t addr);
static void mem_write(uint16_t addr, uint8_t val);

#define READ8(addr)       mem_read(addr)
#define READX8(addr)      mem_readx(addr)
#define READ16(addr)      mem_read16(addr)
#define READX16(addr)     mem_readx16(addr)
#define READ16W(addr)     mem_read16_wrapped(addr)
#define WRITE8(addr, val) mem_write(addr, val)
#define BRK_HOOK                 \
    {                            \
        executed = cycles;       \
        shutdown_pc = pc - 1u;   \
        pc = _MACCTL;            \
        shutdown_requested = 1;  \
    }
#include "s6502.c"

static struct {
    s6502_t      cpu;
    uint8_t     *mem_r[0x100];
    uint8_t    (*mem_ir[0x100])(uint16_t);
    void       (*mem_iw[0x100])(uint16_t, uint8_t);
    uint8_t     *ram;
    uint8_t     *flash;
    uint8_t      flash_cmd;
    uint8_t      flash_cycles;
    uint8_t     *rom_8;                  /* font rom */
    uint8_t     *rom_e;                  /* os rom */
    uint8_t      bk_sel;
    uint16_t     bk_tab[16];
    uint16_t     bk_sys_d;
} sys;

static const uint16_t lcd_theme_colors[GAM4980_LCD_THEME_COUNT][2] = {
    { 0xd6da, 0x0000 },
    { 0x96e1, 0x0882 },
    { 0x3edd, 0x09a8 },
    { 0xf72c, 0x2920 },
};
static uint16_t lcd_bg = 0xd6da;
static uint16_t lcd_fg = 0x0000;

static void init_lcd_lut(void)
{
    uint32_t nibble;

    for (nibble = 0; nibble < 16u; ++nibble) {
        uint16_t p0 = nibble & 0x08u ? lcd_fg : lcd_bg;
        uint16_t p1 = nibble & 0x04u ? lcd_fg : lcd_bg;
        uint16_t p2 = nibble & 0x02u ? lcd_fg : lcd_bg;
        uint16_t p3 = nibble & 0x01u ? lcd_fg : lcd_bg;

        lcd_nibble_lut[nibble][0] = (uint32_t)p0 | (uint32_t)p1 << 16;
        lcd_nibble_lut[nibble][1] = (uint32_t)p2 | (uint32_t)p3 << 16;
    }
}

void gam4980_set_lcd_theme(u32 theme)
{
    if (theme >= GAM4980_LCD_THEME_COUNT)
        theme = GAM4980_LCD_THEME_OFF;
    lcd_bg = lcd_theme_colors[theme][0];
    lcd_fg = lcd_theme_colors[theme][1];
    init_lcd_lut();
}

u16 gam4980_lcd_background_color(void)
{
    return lcd_bg;
}

u16 gam4980_lcd_foreground_color(void)
{
    return lcd_fg;
}

static void s6502_push(uint8_t val)
{
    mem_write(0x100 | sys.cpu.sp--, val);
}

static bool sys_halt_p(void)
{
    return sys.ram[_SYSCON] & 0x08;
}

static inline uint32_t PA(uint16_t addr)
{
    uint8_t bank = addr >> 12;
    return (sys.bk_tab[bank] << 12) | (addr & 0x0fff);
}

static uint8_t flash_read(uint32_t addr)
{
    static uint8_t flash_info[0x35] = {
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x51, 0x52, 0x59, 0x01, 0x07, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x27, 0x36, 0x00, 0x00, 0x04,
        0x00, 0x04, 0x06, 0x01, 0x00, 0x01, 0x01, 0x15,
        0x00, 0x00, 0x00, 0x00, 0x02, 0xff, 0x01, 0x10,
        0x00, 0x1f, 0x00, 0x00, 0x01,
    };
    if (sys.flash_cmd == 0 || sys.flash_cmd == 1) {
        // Rotate last 32KiB to the front for save.
        addr = (addr + 0x8000) % 0x200000;
        return sys.flash[addr];
    } else {
        // Software ID or CFI
        return flash_info[addr];
    }
}

static void flash_write(uint32_t addr, uint8_t val)
{
    switch (sys.flash_cycles) {
    case 0:
        // 1st Bus Write Cycle
        if (addr == 0x5555 && val == 0xaa)
            sys.flash_cycles += 1;
        else if (val == 0xf0)
            // Software ID Exit / CFI Exit
            sys.flash_cmd = 0;
        break;
    case 1:
    case 4:
        // 2nd Bus Write Cycle / 5th Bus Write Cycle
        if (addr == 0x2aaa && val == 0x55)
            sys.flash_cycles += 1;
        break;
    case 2:
        // 3rd Bus Write Cycle
        if (addr != 0x5555)
            return;
        switch (val) {
        case 0xa0:
            // Byte-Program
            sys.flash_cmd = 1;
            sys.flash_cycles += 1;
            break;
        case 0x80:
            sys.flash_cycles += 1;
            break;
        case 0x90:
            // Software ID Entry
            sys.flash_cmd = 2;
            sys.flash_cycles = 0;
            break;
        case 0x98:
            // CFI Query Entry
            sys.flash_cmd = 3;
            sys.flash_cycles = 0;
            break;
        case 0xf0:
            // Software ID Exit / CFI Exit
            sys.flash_cmd = 0;
            sys.flash_cycles = 0;
            break;
        }
        break;
    case 3:
        // 4th Bus Write Cycle
        if (sys.flash_cmd == 1) {
            sys.flash_cmd = 0;
            sys.flash_cycles = 0;
            // Rotate last 32KiB to the front for save.
            addr = (addr + 0x8000) % 0x200000;
            if (addr < GAM4980_SAVE_SIZE && sys.flash[addr] != val)
                save_dirty = 1;
            sys.flash[addr] = val;
        } else if ((addr == 0x5555) && (val == 0xaa)) {
            sys.flash_cycles += 1;
        }
        break;
    case 5:
        // 6th Bus Write Cycle
        switch (val) {
        case 0x10:
            // Chip-Erase
            if (addr == 0x5555) {
                save_dirty = 1;
                bda_memset(sys.flash, 0xff, GAM4980_FLASH_SIZE);
            }
            break;
        case 0x30:
            // Sector-Erase
            addr = (addr + 0x8000) % 0x200000;
            addr &= 0x1ff000;
            if (addr < GAM4980_SAVE_SIZE)
                save_dirty = 1;
            bda_memset(sys.flash + addr, 0xff, 0x1000);
            break;
        case 0x50:
            // Block-Erase
            addr = ((addr & 0x1f0000) + 0x8000) % 0x200000;
            if (addr < GAM4980_SAVE_SIZE)
                save_dirty = 1;
            bda_memset(sys.flash + addr, 0xff, 0x8000);
            addr = (addr + 0x8000) % 0x200000;
            if (addr < GAM4980_SAVE_SIZE)
                save_dirty = 1;
            bda_memset(sys.flash + addr, 0xff, 0x8000);
            break;
        }
        sys.flash_cmd = 0;
        sys.flash_cycles = 0;
        break;
    }

    // Read CFI/ID info via 'sys.mem_ir'.
    if (sys.flash_cmd == 2 || sys.flash_cmd == 3) {
        for (int i = 0; i < 0x100; i += 1) {
            if (sys.mem_r[i] >= sys.flash && sys.mem_r[i] < sys.flash + 0x200000) {
                sys.mem_r[i] = 0;
            }
        }
    }
}

static uint8_t invalid_read(uint16_t addr)
{
    return 0x00;
}

static void invalid_write(uint16_t addr, uint8_t val)
{
}

static uint8_t ram_read(uint16_t addr)
{
    return sys.ram[addr];
}

static void ram_write(uint16_t addr, uint8_t val)
{
    if (addr >= 0x0400u && addr <= 0x1000u && sys.ram[addr] != val)
        lcd_dirty = 1;
    sys.ram[addr] = val;

    // XXX: Disable ROM (0x400000-0x7fffff) channels and audio.
    if (addr == _PB)
        sys.ram[addr] = 0;

    // Never return 0 for AutoPowerOffCount to prevent poweroff.
    if (addr == 0x2028)
        sys.ram[addr] = 0xff;
}

static uint8_t direct_read(uint16_t addr)
{
    int _L = _ADDR1L + addr * 3;
    int _M = _L + 1;
    int _H = _M + 1;
    uint32_t paddr = sys.ram[_L] | sys.ram[_M] << 8 | sys.ram[_H] << 16;
    if (sys.ram[_INCR] & (1 << addr)) {
        sys.ram[_L] += 1;
        if (sys.ram[_L] == 0) {
            sys.ram[_M] += 1;
            if (sys.ram[_M] == 0) {
                sys.ram[_H] += 1;
            }
        }
    }
    if (paddr < 0x8000)
        return ram_read(paddr & 0x7fff);
    else if (paddr >= 0x200000 && paddr < 0x400000)
        return flash_read(paddr - 0x200000);
    else if (paddr >= 0x800000 && paddr < 0xa00000)
        return sys.rom_8[paddr - 0x800000];
    else if (paddr >= 0xe00000 && paddr < 0x1000000)
        return sys.rom_e[paddr - 0xe00000];
    else
        return 0x00;
}

static void direct_write(uint16_t addr, uint8_t val)
{
    int _L = _ADDR1L + addr * 3;
    int _M = _L + 1;
    int _H = _M + 1;
    uint32_t paddr = sys.ram[_L] | sys.ram[_M] << 8 | sys.ram[_H] << 16;
    if (sys.ram[_INCR] & (1 << addr)) {
        sys.ram[_L] += 1;
        if (sys.ram[_L] == 0) {
            sys.ram[_M] += 1;
            if (sys.ram[_M] == 0) {
                sys.ram[_H] += 1;
            }
        }
    }
    if (paddr < 0x8000)
        ram_write(paddr & 0x7fff, val);
    else if (paddr >= 0x200000 && paddr < 0x400000)
        flash_write(paddr - 0x200000, val);
}

static uint8_t page0_read(uint16_t addr)
{
    switch (addr) {
    case _DATA1:
    case _DATA2:
    case _DATA3:
    case _DATA4:
        return direct_read(addr);
    case _BK_SEL:
        return sys.bk_sel;
    case _BK_ADRL:
        return sys.bk_tab[sys.bk_sel] & 0xff;
    case _BK_ADRH:
        return sys.bk_tab[sys.bk_sel] >> 8;
    }
    return sys.ram[addr];
}

static void page0_write(uint16_t addr, uint8_t val)
{
    switch (addr) {
    case _DATA1:
    case _DATA2:
    case _DATA3:
    case _DATA4:
        direct_write(addr, val);
        return;
    case _ISR:
        sys.ram[_ISR] &= val;
        return;
    case _TISR:
        sys.ram[_TISR] &= val;
        return;
    case _BK_SEL:
        sys.bk_sel = val & 0x0f;
        return;
    case _BK_ADRL:
        sys.bk_tab[sys.bk_sel] &= 0xff00;
        sys.bk_tab[sys.bk_sel] |= val;
        mem_bs(sys.bk_sel);
        return;
    case _BK_ADRH:
        sys.bk_tab[sys.bk_sel] &= 0x00ff;
        sys.bk_tab[sys.bk_sel] |= (val & 0x0f) << 8;
        mem_bs(sys.bk_sel);
        return;
    }
    sys.ram[addr] = val;
}

static void mem_init()
{
    for (int i = 0; i < 0x100; i += 1) {
        sys.mem_r[i] = 0;
        sys.mem_ir[i] = invalid_read;
        sys.mem_iw[i] = invalid_write;
    }
    for (int i = 1; i < 16; i += 1) {
        sys.mem_r[i] = sys.ram + i * 0x100;
        sys.mem_ir[i] = ram_read;
        sys.mem_iw[i] = ram_write;
    }
    sys.mem_ir[0x00] = page0_read;
    sys.mem_iw[0x00] = page0_write;
    sys.mem_r[0x03] = sys.rom_e + 0x1fff00;
    sys.mem_iw[0x03] = invalid_write;
}

static uint8_t flash_vread(uint16_t addr)
{
    return flash_read(PA(addr) - 0x200000);
}

static void flash_vwrite(uint16_t addr, uint8_t val)
{
    return flash_write(PA(addr) - 0x200000, val);
}

static uint8_t rom_8_vread(uint16_t addr)
{
    return sys.rom_8[PA(addr) - 0x800000];
}

static uint8_t rom_e_vread(uint16_t addr)
{
    return sys.rom_e[PA(addr) - 0xe00000];
}

static uint8_t ram_vread(uint16_t addr)
{
    return ram_read(PA(addr));
}

static void ram_vwrite(uint16_t addr, uint8_t val)
{
    ram_write(PA(addr), val);
}

static void mem_bs(uint8_t sel)
{
    uint32_t paddr = PA(sel * 0x1000);
    if (sel == 0)
        return;
    if (paddr < 0x8000) {
        for (int i = 0; i < 16; i += 1) {
            sys.mem_r[sel * 16 + i] = sys.ram + paddr + i * 0x100;
            sys.mem_ir[sel * 16 + i] = ram_vread;
            sys.mem_iw[sel * 16 + i] = ram_vwrite;
        }
    } else if (paddr >= 0x200000 && paddr < 0x400000) {
        for (int i = 0; i < 16; i += 1) {
            uint32_t faddr = (paddr - 0x200000 + 0x8000) % 0x200000;
            sys.mem_r[sel * 16 + i] = sys.flash + faddr + i * 0x100;
            sys.mem_ir[sel * 16 + i] = flash_vread;
            sys.mem_iw[sel * 16 + i] = flash_vwrite;
        }
    } else if (paddr >= 0x800000 && paddr < 0xa00000) {
        for (int i = 0; i < 16; i += 1) {
            sys.mem_r[sel * 16 + i] = sys.rom_8 + (paddr - 0x800000) + i * 0x100;
            sys.mem_ir[sel * 16 + i] = rom_8_vread;
            sys.mem_iw[sel * 16 + i] = invalid_write;
        }
    } else if (paddr >= 0xe00000 && paddr < 0x1000000) {
        for (int i = 0; i < 16; i += 1) {
            sys.mem_r[sel * 16 + i] = sys.rom_e + (paddr - 0xe00000) + i * 0x100;
            sys.mem_ir[sel * 16 + i] = rom_e_vread;
            sys.mem_iw[sel * 16 + i] = invalid_write;
        }
    } else {
        for (int i = 0; i < 16; i += 1) {
            sys.mem_r[sel * 16 + i] = 0;
            sys.mem_ir[sel * 16 + i] = invalid_read;
            sys.mem_iw[sel * 16 + i] = invalid_write;
        }
    }
}

static uint8_t mem_readx(uint16_t addr)
{
    uint8_t page = addr >> 8;
    return sys.mem_r[page][addr & 0xff];
}

static uint8_t mem_read(uint16_t addr)
{
    uint8_t page = addr >> 8;
    if (sys.mem_r[page])
        return sys.mem_r[page][addr & 0xff];
    else
        return sys.mem_ir[page](addr);
}

static uint16_t mem_read16(uint16_t addr)
{
    return mem_read(addr) | (mem_read(addr + 1) << 8);
}

static uint16_t mem_readx16(uint16_t addr)
{
    return mem_readx(addr) | (mem_readx(addr + 1) << 8);
}

static uint16_t mem_read16_wrapped(uint16_t addr)
{
    return mem_read(addr) | (mem_read((addr + 1) & 0xff) << 8);
}

static void mem_write(uint16_t addr, uint8_t val)
{
    return sys.mem_iw[addr >> 8](addr, val);
}

enum _key {
    KEY_ON_OFF     = 0x00,      /* 开关 */
    KEY_HOME_MENU  = 0x01,      /* 目录 */
    KEY_EC_SJ      = 0x02,      /* 双解 */
    KEY_EC_SW      = 0x03,      /* 十万 (4988: 现代) */
    KEY_CE         = 0x04,      /* 汉英 */
    KEY_DLG        = 0x05,      /* 对话 */
    KEY_DOWNLOAD   = 0x06,      /* 下载 */
    KEY_SPK        = 0x07,      /* 发音 */
    KEY_1          = 0x08,
    KEY_2          = 0x09,
    KEY_3          = 0x0a,
    KEY_4          = 0x0b,
    KEY_5          = 0x0c,
    KEY_6          = 0x0d,
    KEY_7          = 0x0e,
    KEY_8          = 0x0f,
    KEY_9          = 0x30,
    KEY_0          = 0x31,
    KEY_Q          = 0x10,
    KEY_W          = 0x11,
    KEY_E          = 0x12,
    KEY_R          = 0x13,
    KEY_T          = 0x14,
    KEY_Y          = 0x15,
    KEY_U          = 0x16,
    KEY_I          = 0x17,
    KEY_O          = 0x32,
    KEY_P          = 0x33,
    KEY_SPACE      = 0x36,      /* 空格 */
    KEY_A          = 0x18,
    KEY_S          = 0x19,
    KEY_D          = 0x1a,
    KEY_F          = 0x1b,
    KEY_G          = 0x1c,
    KEY_H          = 0x1d,
    KEY_J          = 0x1e,
    KEY_K          = 0x1f,
    KEY_L          = 0x34,
    KEY_INPUT      = 0x20,      /* 输入法 */
    KEY_CAPS       = KEY_INPUT,
    KEY_Z          = 0x21,
    KEY_X          = 0x22,
    KEY_C          = 0x23,
    KEY_V          = 0x24,
    KEY_B          = 0x25,
    KEY_N          = 0x26,
    KEY_M          = 0x27,
    KEY_ZY         = 0x28,      /* 中英 */
    KEY_SHIFT      = KEY_ZY,
    KEY_HELP       = 0x29,      /* 帮助 */
    KEY_SEARCH     = 0x2a,      /* 查找 */
    KEY_INSERT     = 0x2b,      /* 插入 */
    KEY_MODIFY     = 0x2c,      /* 修改 */
    KEY_DEL        = 0x2d,      /* 删除 */
    KEY_SHIFT_4988 = 0x2d,
    KEY_EXIT       = 0x2e,      /* 跳出 */
    KEY_ENTER      = 0x2f,      /* 输入 */
    KEY_UP         = 0x35,
    KEY_DOWN       = 0x38,
    KEY_LEFT       = 0x37,
    KEY_RIGHT      = 0x39,
    KEY_PGUP       = 0x3a,
    KEY_PGDN       = 0x3b,
};

#if 0
static uint8_t _joyk[16] = {
    [RETRO_DEVICE_ID_JOYPAD_B]      = KEY_EXIT,
    [RETRO_DEVICE_ID_JOYPAD_Y]      = KEY_HELP,
    [RETRO_DEVICE_ID_JOYPAD_SELECT] = KEY_INSERT,
    [RETRO_DEVICE_ID_JOYPAD_START]  = KEY_SEARCH,
    [RETRO_DEVICE_ID_JOYPAD_UP]     = KEY_UP,
    [RETRO_DEVICE_ID_JOYPAD_DOWN]   = KEY_DOWN,
    [RETRO_DEVICE_ID_JOYPAD_LEFT]   = KEY_LEFT,
    [RETRO_DEVICE_ID_JOYPAD_RIGHT]  = KEY_RIGHT,
    [RETRO_DEVICE_ID_JOYPAD_A]      = KEY_ENTER,
    [RETRO_DEVICE_ID_JOYPAD_X]      = KEY_R,
    [RETRO_DEVICE_ID_JOYPAD_L]      = KEY_PGUP,
    [RETRO_DEVICE_ID_JOYPAD_R]      = KEY_PGDN,
    [RETRO_DEVICE_ID_JOYPAD_L2]     = KEY_MODIFY,
    [RETRO_DEVICE_ID_JOYPAD_R2]     = KEY_DEL,
    [RETRO_DEVICE_ID_JOYPAD_L3]     = KEY_A,
    [RETRO_DEVICE_ID_JOYPAD_R3]     = KEY_Z,
};

static uint8_t _kbdk[RETROK_LAST] = {
    [RETROK_F1]        = KEY_ON_OFF,
    [RETROK_F2]        = KEY_HOME_MENU,
    [RETROK_F3]        = KEY_EC_SJ,
    [RETROK_F4]        = KEY_EC_SW,
    [RETROK_F5]        = KEY_CE,
    [RETROK_F6]        = KEY_DLG,
    [RETROK_F7]        = KEY_DOWNLOAD,
    [RETROK_F8]        = KEY_SPK,
    [RETROK_F9]        = KEY_HELP,
    [RETROK_F10]       = KEY_SEARCH,
    [RETROK_F11]       = KEY_INSERT,
    [RETROK_F12]       = KEY_MODIFY,
    [RETROK_1]         = KEY_1,
    [RETROK_2]         = KEY_2,
    [RETROK_3]         = KEY_3,
    [RETROK_4]         = KEY_4,
    [RETROK_5]         = KEY_5,
    [RETROK_6]         = KEY_6,
    [RETROK_7]         = KEY_7,
    [RETROK_8]         = KEY_8,
    [RETROK_9]         = KEY_9,
    [RETROK_0]         = KEY_0,
    [RETROK_q]         = KEY_Q,
    [RETROK_w]         = KEY_W,
    [RETROK_e]         = KEY_E,
    [RETROK_r]         = KEY_R,
    [RETROK_t]         = KEY_T,
    [RETROK_y]         = KEY_Y,
    [RETROK_u]         = KEY_U,
    [RETROK_i]         = KEY_I,
    [RETROK_o]         = KEY_O,
    [RETROK_p]         = KEY_P,
    [RETROK_SPACE]     = KEY_SPACE,
    [RETROK_a]         = KEY_A,
    [RETROK_s]         = KEY_S,
    [RETROK_d]         = KEY_D,
    [RETROK_f]         = KEY_F,
    [RETROK_g]         = KEY_G,
    [RETROK_h]         = KEY_H,
    [RETROK_j]         = KEY_J,
    [RETROK_k]         = KEY_K,
    [RETROK_l]         = KEY_L,
    [RETROK_CAPSLOCK]  = KEY_INPUT,
    [RETROK_z]         = KEY_Z,
    [RETROK_x]         = KEY_X,
    [RETROK_c]         = KEY_C,
    [RETROK_v]         = KEY_V,
    [RETROK_b]         = KEY_B,
    [RETROK_n]         = KEY_N,
    [RETROK_m]         = KEY_M,
    [RETROK_LSHIFT]    = KEY_SHIFT,
    [RETROK_BACKSPACE] = KEY_DEL,
    [RETROK_DELETE]    = KEY_DEL,
    [RETROK_ESCAPE]    = KEY_EXIT,
    [RETROK_RETURN]    = KEY_ENTER,
    [RETROK_UP]        = KEY_UP,
    [RETROK_DOWN]      = KEY_DOWN,
    [RETROK_LEFT]      = KEY_LEFT,
    [RETROK_RIGHT]     = KEY_RIGHT,
    [RETROK_PAGEUP]    = KEY_PGUP,
    [RETROK_PAGEDOWN]  = KEY_PGDN,
};

static void error_msg(const char *msg)
{
    struct retro_message_ext m = {
        .msg = msg,
        .duration = 3000,
        .priority = 5,
        .level = RETRO_LOG_ERROR,
        .target = RETRO_MESSAGE_TARGET_ALL,
        .type = RETRO_MESSAGE_TYPE_NOTIFICATION_ALT,
        .progress = -1,
    };
    environ_cb(RETRO_ENVIRONMENT_SET_MESSAGE_EXT, &m);
}

static void sys_keydown(uint8_t key)
{
    if (key == 0)
        return;
    sys.ram[_SYSCON] &= 0xf7;
    sys.ram[_KEYCODE] = key | 0x80;
    sys.ram[_ISR] |= 0x80;
    if (sys.ram[_IER] & 0x80) {
        sys.ram[_KeyBuffTop] = 0x0;
        sys.ram[_KeyBuffBottom] = 0xf;
        sys.ram[_KeyBuffer + 0x0f] = key & 0x3f;
        sys.ram[_KEYCODE] = 0x00;
    }
}

static void keyboard_cb(bool down, unsigned keycode,
                        uint32_t character, uint16_t key_modifiers)
{
    if (!down)
        return;
    sys_keydown(_kbdk[keycode]);
}

static void sys_init(const char *romdir)
{
    static struct retro_input_descriptor inputs[] = {
        { 0, RETRO_DEVICE_JOYPAD, 0, RETRO_DEVICE_ID_JOYPAD_B, "EXIT" },
        { 0, RETRO_DEVICE_JOYPAD, 0, RETRO_DEVICE_ID_JOYPAD_Y, "HELP" },
        { 0, RETRO_DEVICE_JOYPAD, 0, RETRO_DEVICE_ID_JOYPAD_SELECT, "INSERT" },
        { 0, RETRO_DEVICE_JOYPAD, 0, RETRO_DEVICE_ID_JOYPAD_START, "SEARCH" },
        { 0, RETRO_DEVICE_JOYPAD, 0, RETRO_DEVICE_ID_JOYPAD_UP, "UP" },
        { 0, RETRO_DEVICE_JOYPAD, 0, RETRO_DEVICE_ID_JOYPAD_DOWN, "DOWN" },
        { 0, RETRO_DEVICE_JOYPAD, 0, RETRO_DEVICE_ID_JOYPAD_LEFT, "LEFT" },
        { 0, RETRO_DEVICE_JOYPAD, 0, RETRO_DEVICE_ID_JOYPAD_RIGHT, "RIGHT" },
        { 0, RETRO_DEVICE_JOYPAD, 0, RETRO_DEVICE_ID_JOYPAD_A, "ENTER" },
        { 0, RETRO_DEVICE_JOYPAD, 0, RETRO_DEVICE_ID_JOYPAD_X, "R" },
        { 0, RETRO_DEVICE_JOYPAD, 0, RETRO_DEVICE_ID_JOYPAD_L, "PGUP" },
        { 0, RETRO_DEVICE_JOYPAD, 0, RETRO_DEVICE_ID_JOYPAD_R, "PGDN" },
        { 0, RETRO_DEVICE_JOYPAD, 0, RETRO_DEVICE_ID_JOYPAD_L2, "MODIFY" },
        { 0, RETRO_DEVICE_JOYPAD, 0, RETRO_DEVICE_ID_JOYPAD_R2, "DEL" },
        { 0, RETRO_DEVICE_JOYPAD, 0, RETRO_DEVICE_ID_JOYPAD_L3, "A" },
        { 0, RETRO_DEVICE_JOYPAD, 0, RETRO_DEVICE_ID_JOYPAD_R3, "Z" },
        { 0, 0, 0, 0, NULL },
    };
    char path[512];
    FILE *stream;
    snprintf(path, 512, "%s/8.BIN", romdir);
    stream = fopen(path, "r");
    if (stream == NULL) {
        error_msg("GAM4980: Missing 8.BIN");
        environ_cb(RETRO_ENVIRONMENT_SHUTDOWN, NULL);
        return;
    }
    fread(sys.rom_8, 0x200000, 1, stream);
    fclose(stream);
    snprintf(path, 512, "%s/E.BIN", romdir);
    stream = fopen(path, "r");
    if (stream == NULL) {
        error_msg("GAM4980: Missing E.BIN");
        environ_cb(RETRO_ENVIRONMENT_SHUTDOWN, NULL);
        return;
    }
    fread(sys.rom_e, 0x200000, 1, stream);
    fclose(stream);

    memset(sys.ram, 0x00, 0x8000);
    memset(sys.flash, 0xff, 0x200000);
    sys.flash_cmd = 0;
    sys.flash_cycles = 0;
    sys.ram[_INCR] = 0x0f;

    mem_init();
    sys.cpu.pc = 0x350;
    sys.cpu.ac = 0;
    sys.cpu.ix = 0;
    sys.cpu.iy = 0;
    sys.cpu.sp = 0xff;
    sys.cpu.status = 0x04;


    // Run initialize instructions
    // XXX: SysStart set _MTCT to 0xfe just before 'main'.
    while (sys.ram[_MTCT] != 0xfe)
        s6502_exec(&sys.cpu, 0x1000);
    sys.bk_sys_d = sys.bk_tab[0xd];

    if (sys.bk_sys_d == 0x0e88) { /* 4988 */
        _joyk[RETRO_DEVICE_ID_JOYPAD_Y] = KEY_Z;
        _joyk[RETRO_DEVICE_ID_JOYPAD_SELECT] = KEY_SHIFT_4988;
        _joyk[RETRO_DEVICE_ID_JOYPAD_START] = KEY_ZY;
        _joyk[RETRO_DEVICE_ID_JOYPAD_L2] = KEY_SPACE;
        _joyk[RETRO_DEVICE_ID_JOYPAD_R2] = KEY_X;
        _joyk[RETRO_DEVICE_ID_JOYPAD_R3] = KEY_S;
        inputs[RETRO_DEVICE_ID_JOYPAD_Y].description = "Z";
        inputs[RETRO_DEVICE_ID_JOYPAD_SELECT].description = "SHIFT";
        inputs[RETRO_DEVICE_ID_JOYPAD_START].description = "ZY";
        inputs[RETRO_DEVICE_ID_JOYPAD_L2].description = "SPACE";
        inputs[RETRO_DEVICE_ID_JOYPAD_R2].description = "X";
        inputs[RETRO_DEVICE_ID_JOYPAD_R3].description = "S";
    }
    environ_cb(RETRO_ENVIRONMENT_SET_INPUT_DESCRIPTORS, &inputs);
}
#endif

static void sys_keydown(uint8_t key)
{
    sys.ram[_SYSCON] &= 0xf7;
    sys.ram[_KEYCODE] = key | 0x80;
    sys.ram[_ISR] |= 0x80;
    if (sys.ram[_IER] & 0x80) {
        sys.ram[_KeyBuffTop] = 0x0;
        sys.ram[_KeyBuffBottom] = 0xf;
        sys.ram[_KeyBuffer + 0x0f] = key & 0x3f;
        sys.ram[_KEYCODE] = 0x00;
    }
}

int gam4980_init(const gam4980_buffers_t *buffers)
{
    uint32_t blocks = 0;

    if (!buffers || !buffers->ram || !buffers->flash || !buffers->rom_8 ||
        !buffers->rom_e || !buffers->framebuffer)
        return -1;

    bda_memset(&sys, 0, sizeof(sys));
    sys.ram = buffers->ram;
    sys.flash = buffers->flash;
    sys.rom_8 = buffers->rom_8;
    sys.rom_e = buffers->rom_e;
    fb = buffers->framebuffer;
    bda_memset(sys.ram, 0x00, GAM4980_RAM_SIZE);
    bda_memset(sys.flash, 0xff, GAM4980_FLASH_SIZE);
    bda_memset(fb, 0x00, LCD_STRIDE * LCD_HEIGHT * sizeof(*fb));
    bda_memset(lcd_frame, 0x00, sizeof(lcd_frame));
    shutdown_requested = 0;
    shutdown_pc = 0;
    step_cycles = 0;
    step_ticked = 0;
    step_cycle_fraction = 0;
    rtc_frames = 0;
    bda_memset(timer_ticks, 0, sizeof(timer_ticks));
    lcd_frame_valid = 0;
    lcd_dirty = 1;
    save_dirty = 0;
    gam4980_set_lcd_theme(GAM4980_LCD_THEME_OFF);
    sys.flash_cmd = 0;
    sys.flash_cycles = 0;
    sys.ram[_INCR] = 0x0f;

    mem_init();
    sys.cpu.pc = 0x350;
    sys.cpu.ac = 0;
    sys.cpu.ix = 0;
    sys.cpu.iy = 0;
    sys.cpu.sp = 0xff;
    sys.cpu.status = 0x04;

    while (sys.ram[_MTCT] != 0xfe && blocks < 8192u) {
        (void)s6502_exec(&sys.cpu, 0x1000);
        ++blocks;
    }
    if (sys.ram[_MTCT] != 0xfe)
        return -2;

    sys.bk_sys_d = sys.bk_tab[0xd];
    if (sys.bk_sys_d != 0x0ea8 && sys.bk_sys_d != 0x0e88)
        return -3;
    return 1;
}

u8 *gam4980_game_storage(void)
{
    return sys.flash ? sys.flash + 0x15000 : 0;
}

int gam4980_load_game_header(const u8 *gam, u32 size)
{
    if (!gam || size < GAM4980_GAME_HEADER_SIZE ||
        size > GAM4980_GAME_MAX_SIZE || !sys.flash)
        return -1;

    uint16_t start = gam[0x40] | (gam[0x41] << 8);
    uint32_t data = gam[0x42] | gam[0x43] << 8 | gam[0x44] << 16 | gam[0x45] << 24;
    uint8_t sys_hdr[16] = {
        0xc0, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x10, 0x00, 0x2f,
    };
    uint8_t gam_hdr[16] = {
        0xd0, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00,
        size & 0xff, (size >> 8) & 0xff, (size >> 16) * 0xff,
        0x3d,
    };

    // Setup file headers.
    uint8_t *flash = sys.flash + 0x8000;
    bda_memcpy(gam_hdr + 2, gam + 6, 0x0a);
    bda_memcpy(flash, sys_hdr, 16);
    bda_memcpy(flash+16, gam_hdr, 16);
    /* Game bytes are streamed by the BDA front end into flash+0xd000. */
    bda_memset(flash+0x1000, 0x01, 0x100);
    for (int i = 0; i < 0x0c; i += 1) {
        flash[0x1000 + i] = 0x04;
    }

    if (sys.bk_sys_d == 0x0ea8) { /* A4980 */
        bda_memset(flash+0x7000, 0x01, 0x100);
        // Last 32 KiB for save file.
        flash[0x70f8] = 0x02;
        flash[0x70f9] = 0x02;
        flash[0x70fa] = 0x02;
        flash[0x70fb] = 0x02;
        flash[0x70fc] = 0x02;
        flash[0x70fd] = 0x02;
        flash[0x70fe] = 0x03;
        flash[0x70ff] = 0x02;
    } else if (sys.bk_sys_d == 0x0e88) { /* A4988 */
        bda_memset(flash+0x8000, 0x01, 0x100);
        // Last 32 KiB for save file.
        flash[0x80f8] = 0x02;
        flash[0x80f9] = 0x02;
        flash[0x80fa] = 0x02;
        flash[0x80fb] = 0x02;
        flash[0x80fc] = 0x02;
        flash[0x80fd] = 0x02;
        flash[0x80fe] = 0x03;
        flash[0x80ff] = 0x02;
    } else {
        return -2;
    }
    // Setup banks for the game.
    sys.bk_tab[0x5] = 0x20d;
    sys.bk_tab[0x6] = sys.bk_tab[0x05] + 1;
    sys.bk_tab[0x7] = sys.bk_tab[0x05] + 2;
    sys.bk_tab[0x8] = sys.bk_tab[0x05] + 3;
    sys.bk_tab[0x9] = 0x20d + (data >> 12);
    sys.bk_tab[0xa] = sys.bk_tab[0x09] + 1;
    sys.bk_tab[0xb] = sys.bk_tab[0x09] + 2;
    sys.bk_tab[0xc] = sys.bk_tab[0x09] + 3;
    for (int i = 0x05; i <= 0x0c; i += 1)
        mem_bs(i);
    mem_write(0x2029, 0x0d);
    mem_write(0x202a, 0x02);
    // Push game return address, 0x0260=BRK.
    s6502_push(0x02);
    s6502_push(0x60);
    // Start the game.
    sys.cpu.pc = start;
    return 1;
}

static void sys_timer(uint32_t n)
{
    for (int i = 0; i < 4; i += 1) {
        if (sys.ram[_STCON] & (1 << i)) {
            timer_ticks[i] += n;
            if (timer_ticks[i] >= 0x100) {
                timer_ticks[i] = sys.ram[_ST1LD + i];
                if (sys.ram[_TIER] & (1 << i)) {
                    sys.ram[_TISR] |= (1 << i);
                    sys.ram[_SYSCON] &= 0xf7;
                }
            }
        }
    }

    if (sys.ram[_STCTCON] & 0x10) {
        timer_ticks[4] += n;
        if (timer_ticks[4] >= 0x1000) {
            timer_ticks[4] = sys.ram[_CTLD];
            if (sys.ram[_IER] & 0x02) {
                sys.ram[_ISR] |= 0x02;
                sys.ram[_SYSCON] &= 0xf7;
            }
        }
    }

    if (sys.ram[_TIER] & 0x20u) {
        uint32_t melody = sys.ram[_MTCT] + n;

        sys.ram[_MTCT] = (uint8_t)melody;
        if (melody >= 0x100u) {
            sys.ram[_TISR] |= 0x20u;
            sys.ram[_SYSCON] &= 0xf7u;
        }
    }
 }

static uint32_t sys_ticks_until_timer_event(uint32_t maximum)
{
    uint32_t result = maximum;

    for (int i = 0; i < 4; ++i) {
        if (sys.ram[_STCON] & (1u << i)) {
            uint32_t remaining = 0x100u - timer_ticks[i];
            if (remaining < result)
                result = remaining;
        }
    }
    if (sys.ram[_STCTCON] & 0x10u) {
        uint32_t remaining = 0x1000u - timer_ticks[4];
        if (remaining < result)
            result = remaining;
    }
    if ((sys.ram[_TIER] & 0x20u) && !(sys.ram[_TISR] & 0x20u)) {
        uint32_t remaining = 0x100u - sys.ram[_MTCT];
        if (remaining < result)
            result = remaining;
    }
    return result ? result : 1u;
}

static void sys_rtc()
{
    if ((sys.ram[_STCTCON] & 0x40) == 0x00)
        return;

    if (sys.ram[_RTCSEC]++ == 59) {
        sys.ram[_RTCSEC] = 0;
        if (sys.ram[_RTCMIN]++ == 59) {
            sys.ram[_RTCMIN] = 0;
            if (sys.ram[_RTCHR]++ == 23) {
                sys.ram[_RTCHR] = 0;
                if (sys.ram[_RTCDAYL]++ == 0xff) {
                    if (sys.ram[_RTCDAYH]++ == 1) {
                        sys.ram[_RTCDAYH] = 0;
                    }
                }
            }
        }
    }
    if ((sys.ram[_STCTCON] & 0x20) == 0x00)
        return;
    if ((sys.ram[_RTCMIN] == sys.ram[_ALMMIN]) &&
        (sys.ram[_RTCHR] == sys.ram[_ALMHR]) &&
        (sys.ram[_RTCDAYL] == sys.ram[_ALMDAYL]) &&
        (sys.ram[_RTCDAYH] == sys.ram[_ALMDAYH])) {
        sys.ram[_ISR] |= 0x01;
    }
}


static void sys_isr()
{
    uint8_t idx = 0;
    if (sys.cpu.status & 0x04)
        return;
    if ((sys.ram[_ISR] & 0x80) && (sys.ram[_IER] & 0x80)) {
        idx = 0x02; // PI
        sys.ram[_ISR] &= 0x7f;
        // Handled by 'sys_keydown'.
        return;
    } else if ((sys.ram[_ISR] & 0x01) && (sys.ram[_IER] & 0x01)) {
        idx = 0x13; // ALM
    } else if ((sys.ram[_ISR] & 0x02) && (sys.ram[_IER] & 0x02)) {
        idx = 0x12; // CT
    } else if ((sys.ram[_TISR] & 0x20) && (sys.ram[_TIER] & 0x20)) {
        idx = 0x11; // MT
    } else if ((sys.ram[_TISR] & 0x80) && (sys.ram[_TIER] & 0x80)) {
        idx = 0x10; // GTH
    } else if ((sys.ram[_TISR] & 0x40) && (sys.ram[_TIER] & 0x40)) {
        idx = 0x0f; // GTL
    }  else if ((sys.ram[_TISR] & 0x01) && (sys.ram[_TIER] & 0x01)) {
        idx = 0x03; // ST1
        sys.ram[_TISR] &= 0xfe;
        sys.ram[0x2018] += 1;
        if (sys.ram[0x2018] >= sys.ram[0x2019]) {
            sys.ram[0x201e] |= 0x01;
            sys.ram[0x2018] = 0;
        }
        return;
    } else if ((sys.ram[_TISR] & 0x02) && (sys.ram[_TIER] & 0x02)) {
        idx = 0x04; // ST2
    } else if ((sys.ram[_TISR] & 0x04) && (sys.ram[_TIER] & 0x04)) {
        idx = 0x05; // ST3
    } else if ((sys.ram[_TISR] & 0x08) && (sys.ram[_TIER] & 0x08)) {
        idx = 0x06; // ST4
    } else {
        return;
    }

    s6502_push(sys.cpu.pc >> 8);
    s6502_push(sys.cpu.pc & 0xff);
    s6502_push(sys.cpu.status);
    sys.cpu.status |= 0x04;
    sys.cpu.pc = 0x0300 + idx * 4;
}

static void sys_step()
{
    const uint32_t tstep = 400;
    uint32_t frame_cycles = 66666u;

    /* Keep the upstream 4 MHz / 60 Hz cadence without cumulative rounding. */
    step_cycle_fraction += 40u;
    if (step_cycle_fraction >= 60u) {
        step_cycle_fraction -= 60u;
        ++frame_cycles;
    }
    step_cycles += frame_cycles;
    while (step_ticked + tstep < step_cycles) {
        if (sys_halt_p()) {
            uint32_t ticks = (step_cycles - step_ticked - 1u) / tstep;
            ticks = sys_ticks_until_timer_event(ticks);
            step_ticked += ticks * tstep;
            sys_timer(ticks);
        } else {
            uint32_t p = step_ticked / tstep;
            sys_isr();
            step_ticked += s6502_exec(&sys.cpu, 0x100);
            uint32_t q = step_ticked / tstep;
            sys_timer(q - p);
        }
    }
    step_cycles -= step_ticked;
    step_ticked %= tstep;
}

#if 0
static void fallback_log(enum retro_log_level level, const char *fmt, ...)
{
    (void)level;
    va_list va;
    va_start(va, fmt);
    vfprintf(stderr, fmt, va);
    va_end(va);
}

unsigned retro_api_version(void)
{
    return RETRO_API_VERSION;
}

static void frame_cb(retro_usec_t usec)
{
    static uint32_t ms = 0;
    ms += usec / 1000;
    if (ms > 1000) {
        ms -= 1000;
        sys_rtc();
    }
}

void retro_set_environment(retro_environment_t cb)
{
    static struct retro_core_option_definition opts[] = {
        {
            .key = "gam4980_lcd_color",
            .desc = "LCD color theme",
            .values = {{"grey"}, {"green"}, {"blue"}, {"yellow"}, {"random"}, {NULL}},
            .default_value = "random",
        },
        {
            .key = "gam4980_lcd_ghosting",
            .desc = "LCD ghosting frames",
            .values = {{"0"},{"5"},{"10"},{"15"},{"20"},{"25"},{"30"},{"35"},{"40"}},
            .default_value = "15",
        },
        {
            .key = "gam4980_cpu_rate",
            .desc = "CPU clock rate",
            .values = {{"0.25"},{"0.50"},{"0.75"},{"1.00"},{"1.50"},{"2.00"},{"3.00"},{"4.00"},{"8.00"},{NULL}},
            .default_value = "1.00",
        },
        {
            .key = "gam4980_timer_rate",
            .desc = "Timer clock rate",
            .values = {{"0.25"},{"0.50"},{"0.75"},{"1.00"},{"1.50"},{"2.00"},{"3.00"},{"4.00"},{"8.00"},{NULL}},
            .default_value = "1.00",
        },
        { NULL, NULL, NULL, {{0}}, NULL },
    };

    static struct retro_log_callback log;
    static struct retro_keyboard_callback kbd = {
        .callback = keyboard_cb,
    };
    static struct retro_frame_time_callback frame = {
        .callback = frame_cb,
        .reference = 1000000 / 60,
    };
    static bool yes = true;
    environ_cb = cb;
    if (environ_cb(RETRO_ENVIRONMENT_GET_LOG_INTERFACE, &log))
        log_cb = log.log;
    environ_cb(RETRO_ENVIRONMENT_SET_FRAME_TIME_CALLBACK, &frame);
    environ_cb(RETRO_ENVIRONMENT_SET_KEYBOARD_CALLBACK, &kbd);
    environ_cb(RETRO_ENVIRONMENT_SET_SUPPORT_NO_GAME, &yes);

    unsigned opts_ver = 0;
    environ_cb(RETRO_ENVIRONMENT_GET_CORE_OPTIONS_VERSION, &opts_ver);
    if (opts_ver >= 1) {
        environ_cb(RETRO_ENVIRONMENT_SET_CORE_OPTIONS, &opts);
    }
}

void retro_set_video_refresh(retro_video_refresh_t cb)
{
    video_cb = cb;
}

void retro_set_audio_sample(retro_audio_sample_t cb)
{
    audio_cb = cb;
}

void retro_set_audio_sample_batch(retro_audio_sample_batch_t cb)
{
}

void retro_set_input_poll(retro_input_poll_t cb)
{
    input_poll_cb = cb;
}

void retro_set_input_state(retro_input_state_t cb)
{
    input_state_cb = cb;
}

void retro_get_system_info(struct retro_system_info *info)
{
    info->need_fullpath = false;
    info->valid_extensions = "gam";
    info->library_version = "0.2";
    info->library_name = "gam4980";
    info->block_extract = false;
}

void retro_get_system_av_info(struct retro_system_av_info *info)
{
    info->geometry.base_width = LCD_WIDTH;
    info->geometry.base_height = LCD_HEIGHT;
    info->geometry.max_width = LCD_WIDTH;
    info->geometry.max_height = LCD_HEIGHT;
    info->geometry.aspect_ratio = 0.0;
    info->timing.fps = 60.0;
    info->timing.sample_rate = 44100;

    static enum retro_pixel_format pixfmt = RETRO_PIXEL_FORMAT_RGB565;
    environ_cb(RETRO_ENVIRONMENT_SET_PIXEL_FORMAT, &pixfmt);
}

static bool lcd_color_ok()
{
    uint8_t bg_r = (vars.lcd_bg >> 11) & 0x1f;
    uint8_t bg_g = (vars.lcd_bg >>  6) & 0x1f;
    uint8_t bg_b = (vars.lcd_bg >>  0) & 0x1f;
    uint8_t fg_r = (vars.lcd_fg >> 11) & 0x1f;
    uint8_t fg_g = (vars.lcd_fg >>  6) & 0x1f;
    uint8_t fg_b = (vars.lcd_fg >>  0) & 0x1f;

    if (bg_r < fg_r + 18 ||
        bg_g < fg_g + 18 ||
        bg_b < fg_b + 18)
        return false;

    return true;
}

static void apply_variables()
{
    struct retro_variable var = {0};

    var.key = "gam4980_lcd_color";
    if (environ_cb(RETRO_ENVIRONMENT_GET_VARIABLE, &var)) {
        if (strcmp(var.value, "grey") == 0) {
            vars.lcd_bg = 0xd6da;
            vars.lcd_fg = 0x0000;
        } else if (strcmp(var.value, "green") == 0) {
            vars.lcd_bg = 0x96e1;
            vars.lcd_fg = 0x0882;
        } else if (strcmp(var.value, "blue") == 0) {
            vars.lcd_bg = 0x3edd;
            vars.lcd_fg = 0x09a8;
        } else if (strcmp(var.value, "yellow") == 0) {
            vars.lcd_bg = 0xf72c;
            vars.lcd_fg = 0x2920;
        } else if (strcmp(var.value, "random") == 0) {
            do {
                vars.lcd_bg = 0xdddd + (rand() % 0x2222);
                vars.lcd_fg = rand() % 0x3333;
            } while (!lcd_color_ok());
        }
    }
    var.key = "gam4980_lcd_ghosting";
    if (environ_cb(RETRO_ENVIRONMENT_GET_VARIABLE, &var))
        vars.lcd_ghosting = atoi(var.value);

    var.key = "gam4980_cpu_rate";
    if (environ_cb(RETRO_ENVIRONMENT_GET_VARIABLE, &var))
        vars.cpu_rate = atof(var.value);

    var.key = "gam4980_timer_rate";
    if (environ_cb(RETRO_ENVIRONMENT_GET_VARIABLE, &var))
        vars.timer_rate = atof(var.value);
}

void retro_init(void)
{
    char *systemdir;
    char romdir[512];
    environ_cb(RETRO_ENVIRONMENT_GET_SYSTEM_DIRECTORY, &systemdir);
    snprintf(romdir, 512, "%s/gam4980", systemdir);
    sys_init(romdir);
    apply_variables();

    // Support RetroArch cheats.
    struct retro_memory_descriptor rmdesc = {
        .flags = RETRO_MEMDESC_SYSTEM_RAM,
        .start = 0,
        .len   = sizeof(sys.ram),
        .ptr   = sys.ram,
    };
    struct retro_memory_map rmmap = {
        .descriptors = &rmdesc,
        .num_descriptors = 1,
    };
    environ_cb(RETRO_ENVIRONMENT_SET_MEMORY_MAPS, &rmmap);
}

bool retro_load_game(const struct retro_game_info *game)
{
    if (game == NULL)
        return true;
    if (game->data == NULL)
        return false;
    if (game->size > 0x1e0000) {
        // Game too large! (>1920K)
        return false;
    }
    sys_load(game->data, game->size);
    return true;
}

void retro_set_controller_port_device(unsigned port, unsigned device)
{
}

void retro_deinit(void)
{
}

void retro_reset(void)
{
}
#endif

static inline void unpack8(int y, int x, uint8_t p8)
{
    uint32_t *destination = (uint32_t *)(fb + y * LCD_STRIDE + x * 8);
    const uint32_t *high = lcd_nibble_lut[p8 >> 4];
    const uint32_t *low = lcd_nibble_lut[p8 & 0x0fu];

    destination[0] = high[0];
    destination[1] = high[1];
    destination[2] = low[0];
    destination[3] = low[1];
}

static inline int capture8(int y, int x, uint8_t p8)
{
    uint8_t *destination = lcd_frame + y * LCD_PACKED_STRIDE + x;
    int changed = !lcd_frame_valid || *destination != p8;

    *destination = p8;
    return changed;
}

#if 0
static void blend_frame(void)
{
    uint8_t bg_r = (vars.lcd_bg >> 11) & 0x1f;
    uint8_t bg_g = (vars.lcd_bg >>  6) & 0x1f;
    uint8_t bg_b = (vars.lcd_bg >>  0) & 0x1f;
    uint8_t fg_r = (vars.lcd_fg >> 11) & 0x1f;
    uint8_t fg_g = (vars.lcd_fg >>  6) & 0x1f;
    uint8_t fg_b = (vars.lcd_fg >>  0) & 0x1f;

    for (int i = 0; i < LCD_HEIGHT; i += 1) {
        for (int j = 0; j < LCD_WIDTH; j += 1) {
            int z = i * (LCD_WIDTH + 1) + j;
            float a = (float)fa[z] / vars.lcd_ghosting;
            uint8_t mix_r = 0x1f & (uint8_t)((1 - a) * bg_r + a * fg_r);
            uint8_t mix_g = 0x1f & (uint8_t)((1 - a) * bg_g + a * fg_g);
            uint8_t mix_b = 0x1f & (uint8_t)((1 - a) * bg_b + a * fg_b);
            fb[z] = mix_r << 11 | mix_g << 6 | mix_b;
        }
    }
}
#endif

void gam4980_step_frame(void)
{
    sys_step();
    if (++rtc_frames >= 60u) {
        rtc_frames = 0;
        sys_rtc();
    }
}

int gam4980_render_frame(void)
{
    int changed = 0;

    if (!lcd_dirty)
        return 0;

    // Draw the screen.
    uint8_t *v = sys.ram + 0x400;
    sys.ram[0x400] = sys.ram[0x1000];

    for (int j = 65; j >= -30; j -= 1) {
        for (int i = 1; i < 20; i += 1) {
            changed |= capture8(j >= 0 ? j : (j * -1 + 65), i, *v++);
        }
        v += 13;
    }
    v = sys.ram + 0x413;
    for (int j = 64; j >= -30; j -= 1) {
        changed |= capture8(j >= 0 ? j : (j * -1 + 65), 0, *v++);
        v += 31;
    }
    changed |= capture8(65, 0, sys.ram[0x0ff3]);
    lcd_frame_valid = 1;
    lcd_dirty = 0;
    return changed;
}

void gam4980_run_frame(void)
{
    gam4980_step_frame();
    (void)gam4980_render_frame();
    (void)gam4980_expand_frame(lcd_frame);
}

int gam4980_cpu_halted(void)
{
    return sys_halt_p() ? 1 : 0;

}

#if 0
struct __attribute__((packed)) sys_state {
    uint8_t ram[0x8000];
    s6502_t cpu;
    uint8_t bk_sel;
    uint16_t bk_tab[16];
    uint8_t flash_cmd;
    uint8_t flash_cycles;
};

size_t retro_serialize_size(void)
{
    return sizeof(struct sys_state);
}

bool retro_serialize(void *data, size_t size)
{
    struct sys_state state;
    memcpy(&state.ram, sys.ram, sizeof(sys.ram));
    state.cpu = sys.cpu;
    state.bk_sel = sys.bk_sel;
    for (int i = 0; i < 16; ++i)
        state.bk_tab[i] = sys.bk_tab[i];
    state.flash_cmd = sys.flash_cmd;
    state.flash_cycles = sys.flash_cycles;
    memcpy(data, &state, size);
    return true;
}

bool retro_unserialize(const void *data, size_t size)
{
    struct sys_state state;
    memcpy(&state, data, size);
    memcpy(sys.ram, &state.ram, sizeof(sys.ram));
    sys.cpu = state.cpu;
    sys.bk_sel = state.bk_sel;
    for (int i = 0; i < 16; ++i)
        sys.bk_tab[i] = state.bk_tab[i];
    sys.flash_cmd = state.flash_cmd;
    sys.flash_cycles = state.flash_cycles;
    for (int i = 0; i < 16; ++i)
        mem_bs(i);
    return true;
}

void retro_cheat_reset(void) {}
void retro_cheat_set(unsigned index, bool enabled, const char *code) {}

bool retro_load_game_special(unsigned game_type, const struct retro_game_info *info, size_t num_info)
{
    return false;
}

void retro_unload_game(void)
{
}

unsigned retro_get_region(void)
{
    return RETRO_REGION_NTSC;
}

void *retro_get_memory_data(unsigned id)
{
    switch (id) {
    case RETRO_MEMORY_SAVE_RAM:
        return sys.flash;
    case RETRO_MEMORY_SYSTEM_RAM:
        return sys.ram;
    default:
        return NULL;
    }
}

size_t retro_get_memory_size(unsigned id)
{
    switch (id) {
    case RETRO_MEMORY_SAVE_RAM:
        // Saved: $000000-$00bfff, $1f8000-$1fffff
        return 0x14000;
    case RETRO_MEMORY_SYSTEM_RAM:
        return sizeof(sys.ram);
    default:
        return 0;
    }
}
#endif

void gam4980_key_down(u8 key)
{
    sys_keydown(key);
}

const u8 *gam4980_packed_frame(void)
{
    return lcd_frame;
}

const u16 *gam4980_expand_frame(const u8 *packed_frame)
{
    int y;

    if (!packed_frame || !fb)
        return 0;
    for (y = 0; y < LCD_HEIGHT; ++y) {
        int x;

        for (x = 0; x < LCD_PACKED_STRIDE; ++x)
            unpack8(y, x, packed_frame[y * LCD_PACKED_STRIDE + x]);
    }
    return fb;
}

const u16 *gam4980_framebuffer(void)
{
    if (lcd_frame_valid)
        (void)gam4980_expand_frame(lcd_frame);
    return fb;
}

u8 *gam4980_save_data(void)
{
    return sys.flash;
}

int gam4980_save_dirty(void)
{
    return save_dirty;
}

void gam4980_save_mark_clean(void)
{
    save_dirty = 0;
}

int gam4980_shutdown_requested(void)
{
    return shutdown_requested;
}

u16 gam4980_shutdown_pc(void)
{
    return shutdown_pc;
}

void gam4980_deinit(void)
{
    bda_memset(&sys, 0, sizeof(sys));
    fb = 0;
    shutdown_requested = 0;
    shutdown_pc = 0;
    step_cycles = 0;
    step_ticked = 0;
    step_cycle_fraction = 0;
    rtc_frames = 0;
    bda_memset(timer_ticks, 0, sizeof(timer_ticks));
    bda_memset(lcd_frame, 0, sizeof(lcd_frame));
    lcd_frame_valid = 0;
    lcd_dirty = 0;
    save_dirty = 0;
}
