#include "gam4980_core.h"
static u8 ram[GAM4980_RAM_SIZE], flash[GAM4980_FLASH_SIZE];
static u8 rom8[GAM4980_ROM_SIZE], rome[GAM4980_ROM_SIZE];
static u16 frame[GAM4980_LCD_STRIDE * GAM4980_LCD_HEIGHT];
void *memset(void *d, int v, size_t n) { u8 *p=d; while(n--) *p++=(u8)v; return d; }
void *memcpy(void *d, const void *s, size_t n) { u8 *p=d; const u8 *q=s; while(n--) *p++=*q++; return d; }
u8 *web_rom8(void) { return rom8; }
u8 *web_rome(void) { return rome; }
int web_init(void) {
  gam4980_buffers_t buffers={ram,flash,rom8,rome,frame};
  return gam4980_init(&buffers);
}
int web_load(u32 size) { return gam4980_load_game_header(gam4980_game_storage(),size); }
