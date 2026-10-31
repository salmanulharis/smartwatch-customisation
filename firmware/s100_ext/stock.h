/* Stock app V001319 functions and data used by the S100 feature extensions.
 * Addresses from offline reverse engineering: docs/ui-framework-notes.md, docs/ui-upgrade-plan.md.
 * Functions are called through absolute addresses (Thumb bit set). */
#ifndef S100_STOCK_H
#define S100_STOCK_H

#include <stdint.h>

#define FN(addr, ret, ...) ((ret (*)(__VA_ARGS__))((addr) | 1u))
/* Stock functions below are declared with their address ("@0x..."); tools/s100_ext.py defines them
 * as linker symbols (Thumb bit set), so calls are direct BLs instead of literal + BLX. */
#define U8(a)  (*(volatile uint8_t *)(a))
#define U16(a) (*(volatile uint16_t *)(a))
#define U32(a) (*(volatile uint32_t *)(a))

/* ---- GUI core */
typedef struct widget { uint8_t raw[0x44]; } widget_t;
typedef struct inst {                 /* runtime screen instance (UI_MenuTypeDef copy) */
    uint8_t pad0[0x24];
    widget_t *widgets;                /* +0x24 */
    uint8_t pad1[0x33 - 0x28];
    uint8_t cap;                      /* +0x33 widget capacity */
    uint8_t active;                   /* +0x34 */
    uint8_t current;                  /* +0x35 touch areas enabled */
} inst_t;

#define CUR_SCREEN   U32(0x00210760)
#define TOUCH_AREAS  0x00213CC0u      /* 37 x 16 B {s16 x,y,w,h; cb; u8 en} */
#define TOUCH_AREA(i) ((void *)(TOUCH_AREAS + 16u * (i)))
#define APP_STATE    0x0020C154u      /* +0xD54 = return-to screen */
#define RETURN_TO    U32(APP_STATE + 0xD54)
#define SETTINGS     0x0020BE84u
#define DISPLAY_ON   U8(0x0021401F)

void gui_switch(uint32_t desc);  /* @0x00844B1C */
void gui_update(uint32_t, uint32_t, uint32_t, uint32_t, uint32_t, uint32_t, uint32_t, uint32_t);  /* @0x00209642 */
int add_image(widget_t *, uint32_t img, int x, int y, int w, int h);  /* @0x008443A4 */
int add_text(widget_t *, int align, const char *s, int len, int x0, int x1, int y, int boxh, int size, uint32_t rgb);  /* @0x00845BDE */
int add_digits(widget_t *, const char *s, int n, uint32_t sprite, int x, int y, int w, int h, uint32_t table);  /* @0x00844330 */
void add_touch(void *area, int enable, int x, int y, int w, int h, void (*cb)(int));  /* @0x0084503C */
void hit_test(uint32_t areas, int count, void *evt, int r3, int zero);  /* @0x008433B6 */
void slide_right(uint32_t cur, uint32_t target, void *evt);  /* @0x00844CF6 */   /* finger L->R */
void slide_step(uint32_t timer_handle_ptr);  /* @0x00842370 */
void slide_down(uint32_t cur, uint32_t target, void *evt);  /* @0x00844DB6 */   /* 0 = template's */
void screen_off_evt(void);  /* @0x0084236C */
void screen_wake(void);  /* @0x0084648C */
void screen_enter2(void);  /* @0x008465DA */

/* ---- RTOS (ROM) */
#define TIMER_OFF    0x00214B84u      /* id 1: screen-off timer handle */
#define TIMER_TICK   0x00214B80u      /* id 2: refresh / animation */
#define TIMER_SLIDE  0x00214B88u      /* id 3: page slide */
#define TIMER_CB     0x0084149Du      /* posts {id, cur->name} to cur->+0x20 */
int os_timer_create(uint32_t handle_ptr, const char *name, uint32_t id, uint32_t ms, uint32_t reload, uint32_t cb);  /* @0x000134D2 */
int os_timer_start(uint32_t handle_ptr);  /* @0x00013518 */
int os_timer_restart(uint32_t handle_ptr, uint32_t ms);  /* @0x0001353A */
int os_timer_stop(uint32_t handle_ptr);  /* @0x00013560 */
int os_timer_delete(uint32_t handle_ptr);  /* @0x00013582 */
void memclr(void *, uint32_t);  /* @0x0003A3D4 */
uint32_t rom_strlen(const char *);  /* @0x0003A254 */
int rom_memcmp(const void *, const void *, uint32_t);  /* @0x0003A1FC */

/* ---- system */
void save_settings(void);  /* @0x00830654 */
void backlight_apply(void);  /* @0x0083C2CC */
void motor_vibrate(int count, int pattern);  /* @0x0083EE8C */
void motor_timer_set(uint32_t ms);  /* @0x0083BED4 */
int weekday_of(int year, int month, int day);  /* @0x0083028E */   /* 0 = Sunday */
#define MOTOR_STATE      0x002103A0u  /* +0 active, +0xC steps pointer */

/* settings struct fields (0x0020BE84 + offset) */
#define S_12H        U8(SETTINGS + 0x66)
#define S_TIMEOUT    U16(SETTINGS + 0xFA)
#define S_YEAR       U16(0x0020BF16)
#define S_MONTH      U8(0x0020BF18)
#define S_DAY        U8(0x0020BF19)
#define S_HOUR       U8(0x0020BF1A)
#define S_MIN        U8(0x0020BF1B)
#define S_BATTERY    U8(SETTINGS + 0x109)
#define S_BRIGHT     U8(SETTINGS + 0x188)
#define S_WX_COND    U8(0x0020BFB1)
#define S_WX_NOW     U8(0x0020BFC2)
#define S_WX_MIN     U8(0x0020BFC3)
#define S_WX_MAX     U8(0x0020BFCA)
/* Our own settings (S_WAKE, S_AOD, S_DOCK, S_HAPTIC_OFF) are NOT in the stock block: its bytes
 * 0x290-0x2BF are an hourly array the stock firmware writes at 22:00 / 23:00 and clears at midnight
 * (memclr at 0x8304C6). They live in ext.c's record (t_prefs, flash 0x97A2D0); see ext.c. */
#define LEGACY_PREFS (SETTINGS + 0x2BC)    /* where releases up to r1340 kept them (migration only) */
#define S_STEPS      U32(SETTINGS + 0x14)  /* today's steps (HomeStatus builder 0x850BFA) */
#define S_RAISE      U8(SETTINGS + 0x1BA)  /* stock raise to wake (mirrors: +0x32, +0x1A6 bit 1) */
#define S_RAISE_ALGO U8(SETTINGS + 0x32)
#define S_1A6        U8(SETTINGS + 0x1A6)
#define BOOTED       U8(0x0020D154 + 0xDB)  /* 0 = powered-off charge-only state */
#define CHARGING     U8(0x00210236)
#define BT_LINK      U8(0x0020C424)

/* screen descriptors (RAM) */
#define D_FACE       0x0020E1D0u
#define D_STATUSBAR  0x0020E030u
#define D_FINDPHONE  0x0020DAECu
#define D_POWEROFF   0x0020DE54u
#define D_CLOCK      0x0020DA1Cu  /* was FactoryAgingTest */
#define D_NAV        0x0020DA54u  /* was FactoryBatteryTest */
#define D_WATCHSET   0x0020E35Cu  /* was FactoryTpTest */

/* stock functions only ext.c uses */
void stock_charger_ui(int st);  /* @0x00832008 */   /* charger plug / unplug UI */
void qp_stock_build(inst_t *in, int arg);  /* @0x008587E2 */   /* StatusBar build */
void screen_off(void);  /* @0x008464FA */
int ble_notify(uint8_t *buf, uint8_t len);  /* @0x008364A4 */   /* notify on 0x33F2 */
void wake_idle(int arg);  /* @0x00843160 */   /* wake from screen off (button path) */
void tp_config(void);  /* @0x0083F1DE */   /* touch IC reset + config, stays awake */
void tp_deep_sleep(void);  /* @0x0083F288 */   /* touch IC config + deep sleep (stock) */
void raise_reset(void);  /* @0x008716FA */   /* wrist gesture state -> idle */
void stock_charge_key(int cls, int k);  /* @0x008496A4 */   /* BatteryCharging +0x28 */
void power_off_prep(void);  /* @0x0083162C */   /* first step of power off 0x831660 */
void spo2_stock_build(inst_t *in, int arg);  /* @0x0084A9D2 */   /* BloodOxygen build (+0x1C) */
void breath_stock_build(inst_t *in, int arg);  /* @0x0084B9CA */   /* BreathTraining build (+0x1C) */
void flash_read(void *dst, uint32_t flash, uint32_t len);  /* @0x0086C0AA */
void flash_write(const void *src, uint32_t flash, uint32_t len);  /* @0x0086C54C */
int flash_erase(uint32_t flash, uint32_t cmd);  /* @0x0086C3AE */   /* cmd 0x20 = 4 KB sector */
void delay_us(uint32_t us);  /* @0x0083B474 */
#define SETTINGS_FLASH 0x0097A000u    /* save_settings: erase this sector, write the 0x2D0-byte block */

#endif
