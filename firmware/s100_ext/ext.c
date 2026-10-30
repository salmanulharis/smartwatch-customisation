/* S100 feature extensions for the stock app V001319 (docs/ui-upgrade-plan.md §12.7).
 *
 * Three new screens in reused factory-test screen slots, plus quick-panel tiles and a tap tick:
 *   - Dock / always-on (D_CLOCK): 3 styles, opens on the charger, untouchable.
 *   - Navigation (D_NAV):    opened by a phone/PC notification "NAV|dir|dist|street|speed|eta".
 *   - Watch settings (D_WATCHSET): 12/24 h, always-on screen, tap vibration.
 * Linked into dead factory code (tools/s100_ext.py); hook trampolines are assembled there too.
 * No .data/.bss: this code has no startup, so state lives at a fixed free RAM address and is
 * initialised explicitly. Nothing here runs at boot. */
#include "stock.h"
#include "art.h"                                  /* generated: appended image addresses */

/* image addresses come from the UI pack build (-D on the command line) */
#ifndef IMG_ROW_BG
#error build with tools/s100_ext.py
#endif

#define ORANGE 0xFF5A1Eu
#define WHITE  0xF5F5F5u
#define GREY   0x8C8C8Cu
#define NAV_TIMEOUT_S 90                 /* back to the face after this long without an update */

typedef struct {
    uint32_t magic;
    uint8_t  nav_dir, ws_dirty, pad[2];
    uint16_t nav_age;
    char nav_dist[12], nav_street[40], nav_speed[16], nav_eta[24];
    /* text widgets keep a pointer to their string until the next build: strings must live here */
    char nav_num[12], nav_line[44];
    char clk_date[24], clk_time[8], clk_wx[32], clk_bat[20], clk_hh[4], clk_mm[4];
    uint8_t dock_mode, dock_auto;
    char rx[84];                                  /* last received message as ASCII */
    char aod_steps[8];
    uint8_t dimmed, last_min;
    uint8_t report[12];
    char aod_temp[8], aod_pct[8], aod_dom[4];
    char qs_bat[4], qs_day[4];
    uint8_t dim_pending, ws_page;
} state_t;
#define ST ((state_t *)0x0021B000u)      /* free static RAM between .bss end and the heap */
#define MAGIC 0x53315845u

/* 3-letter names packed in one string each (no pointer tables: code space is tight) */
static const char WEEKDAYS[] = "SunMonTueWedThuFriSat";
static const char MONTHS[] = "JanFebMarAprMayJunJulAugSepOctNovDec";
#define WEEKDAY_NOW (WEEKDAYS + 3 * (weekday_of(S_YEAR, S_MONTH, S_DAY) % 7))
#define MONTH_NOW (MONTHS + 3 * ((S_MONTH + 11) % 12))

static char *put3(char *d, const char *s) { d[0] = s[0]; d[1] = s[1]; d[2] = s[2]; d[3] = 0; return d + 3; }
static const uint32_t NAV_ARROW[8] = {IMG_NAV0, IMG_NAV1, IMG_NAV2, IMG_NAV3,
                                      IMG_NAV4, IMG_NAV5, IMG_NAV6, IMG_NAV7};

/* ------------------------------------------------------------------ small helpers */
static int slen(const char *s) { int n = 0; while (s[n]) n++; return n; }

static char *put(char *d, const char *s) { while (*s) *d++ = *s++; *d = 0; return d; }

static char *put_u(char *d, unsigned v, int min_digits) {
    char t[10]; int n = 0;
    do { t[n++] = (char)('0' + v % 10); v /= 10; } while (v);
    while (n < min_digits) t[n++] = '0';
    while (n) *d++ = t[--n];
    *d = 0;
    return d;
}

static char *put_temp(char *d, uint8_t raw) {     /* bit 7 = negative */
    if (raw & 0x80) *d++ = '-';
    d = put_u(d, raw & 0x7F, 1);
    return put(d, "\xC2\xB0");                    /* UTF-8 degree sign */
}

static widget_t *W(inst_t *in, int i) { return &in->widgets[i]; }

/* One line of font-0 text (24 px cell, ~11 px per capital); `top` = top of that 24 px cell.
 * add_text stores y + 12 and a height of box / 2, and the band renderer (0x841938) skips a widget in
 * every band that starts below y + height: with the old box of 28 (height 14) the lower part of the
 * line was dropped wherever a band boundary fell inside it. Box 56 (as stock) covers the whole cell. */
static int text(inst_t *in, int i, const char *s, int x0, int x1, int top, uint32_t rgb, int align) {
    /* widget +0x20 = "use the font tables": stock builders set it before add_text (e.g. 0x851FA8).
     * Without it Latin text goes down the CJK fixed-cell path and nothing is drawn on the watch. */
    W(in, i)->raw[0x20] = 1;
    return add_text(W(in, i), align, s, slen(s), x0, x1, top - 12, 56, 1, rgb);
}

static void stop_timer(uint32_t h) {
    if (U32(h)) { os_timer_stop(h); os_timer_delete(h); }
    U32(h) = 0;
}

/* common screen lifecycle (pattern of the stock FlashLight screen) */
static void enter(uint32_t desc, const char *name, uint32_t tick_ms) {
    screen_wake();
    screen_enter2();
    ((inst_t *)desc)->active = 1;
    gui_update(desc, 0, 0, 0, 0, 0, 0, 0);
    os_timer_create(TIMER_OFF, name, 1, (uint32_t)S_TIMEOUT * 1000u, 0, TIMER_CB);
    os_timer_create(TIMER_TICK, name, 2, tick_ms, 1, TIMER_CB);
    os_timer_create(TIMER_SLIDE, name, 3, 40, 1, TIMER_CB);
    os_timer_start(TIMER_TICK);
    os_timer_start(TIMER_OFF);
}

static void leave(uint32_t desc) {
    ((inst_t *)desc)->active = 0;
    stop_timer(TIMER_TICK);
    stop_timer(TIMER_OFF);
    stop_timer(TIMER_SLIDE);
}

static int begin_build(inst_t *in, uint32_t desc) {
    if (!in) return 0;
    in->cap = ((inst_t *)desc)->cap;
    memclr(in->widgets, (uint32_t)in->cap * sizeof(widget_t));
    if (in->current) memclr((void *)TOUCH_AREAS, 0x250);
    return 1;
}

/* msg: +0 timer id, +4 name of the screen that created the timer */
static int event_type(uint32_t desc, const uint32_t *msg) {
    const char *name = *(const char **)desc;
    if (rom_memcmp((const void *)msg[1], name, rom_strlen(name))) return 0;
    if (msg[0] == 3 && U32(TIMER_SLIDE)) { slide_step(TIMER_SLIDE); return 0; }
    return (int)msg[0];
}

static void refresh(uint32_t desc) {
    if (CUR_SCREEN == desc && ((inst_t *)desc)->active) gui_update(desc, 0, 0, 0, 0, 0, 0, 0);
}

static void touch(uint32_t desc, uint8_t *evt, int areas, uint32_t back) {
    os_timer_restart(TIMER_OFF, (uint32_t)S_TIMEOUT * 1000u);
    if (evt[0] == 7) {                              /* finger left -> right: back */
        uint32_t to = RETURN_TO ? RETURN_TO : back;
        RETURN_TO = 0;
        os_timer_restart(TIMER_SLIDE, 40);
        slide_right(desc, to, evt);
        return;
    }
    if (areas) hit_test(TOUCH_AREAS, areas, evt, 0, 0);
}

static void key(int cls, int k, uint32_t back) {   /* +0x28: cls 2 = short, 1 = long press */
    if (k != 1) return;
    if (cls == 1) { gui_switch(D_POWEROFF); return; }
    if (cls == 2) {
        uint32_t to = RETURN_TO ? RETURN_TO : back;
        RETURN_TO = 0;
        gui_switch(to);
    }
}

void ext_nop(void) {}

/* ================================================================== dock / always-on (D_CLOCK)
 * Styles (setting S_DOCK, chosen in the companion app; values > 3 read as 0):
 *   0 Dock:     bold stacked hours (white) / minutes (orange), weather, battery
 *   1 Digital:  light stacked time, battery %   (always-on display)
 *   2 Charging: battery ring, bolt, big %, time
 *   3 off:      stock charging screen on the charger
 * Opens by itself when the charger is plugged in (unless 3), or from the quick-panel tile.
 * Dock styles 0 / 2 are normal screens: tap, swipe or button -> face; on timeout they turn into the
 * always-on screen (S_AOD) or the screen goes off. Style 1 (always-on) never times out; the wake
 * settings (S_WAKE, raise) decide what returns to the face. */
#define DW 56
#define DH 84

static int dock_setting(void) { uint8_t v = S_DOCK; return v > 3 ? 0 : v; }

static int put_big(inst_t *in, int n, const char *s, int x, int y, const uint32_t *tab) {
    for (; *s; s++, x += DW) {
        int g = *s == '.' ? 10 : *s - '0';
        if (g >= 0 && g <= 10) n += add_image(W(in, n), tab[g], x, y, DW, DH);
    }
    return n;
}

static void time_strings(void) {
    unsigned h = S_HOUR;
    if (S_12H) { h %= 12; if (!h) h = 12; }
    put_u(ST->clk_hh, h, 2);
    put_u(ST->clk_mm, S_MIN, 2);
}

static int weather_icon_index(void) {                 /* name order: sun, moon, cloud, rain */
    uint8_t c = S_WX_COND;
    int night = S_HOUR < 6 || S_HOUR >= 19;
    if (c == 1) return night ? 1 : 0;
    if (c >= 4 && c <= 8) return 3;
    return 2;
}

static uint32_t weather_icon(void) { return WX_ICON[weather_icon_index()]; }

void t_aod_body(inst_t *in);
void aod_dim(int on);

static void dock_body(inst_t *in) {
    int n = 0, style = ST->dock_mode;
    char *p;
    time_strings();
    if (style == 2) {                                   /* charging face */
        int lvl = (S_BATTERY + 5) / 10, w;
        if (lvl > 10) lvl = 10;
        n += add_image(W(in, n), RING[lvl], 32, 22, 176, 176);
        n += add_image(W(in, n), IMG_BOLT, 100, 46, 40, 40);
        put_u(ST->clk_bat, S_BATTERY, 1);
        w = slen(ST->clk_bat) * DW;
        n = put_big(in, n, ST->clk_bat, 112 - w / 2, 84, DIG_BOLD_W);
        n += text(in, n, "%", 112 + w / 2 + 2, 200, 140, WHITE, 2);
        p = put(ST->clk_time, ST->clk_hh);
        p = put(p, ":");
        put(p, ST->clk_mm);
        n += text(in, n, ST->clk_time, 0, 240, 222, GREY, 1);       /* under the ring (ends at 198) */
        return;
    }
    if (style == 1) { t_aod_body(in); return; }           /* always-on display */
    /* dock */
    n = put_big(in, n, ST->clk_hh, 14, 30, DIG_BOLD_W);
    n = put_big(in, n, ST->clk_mm, 14, 126, DIG_BOLD_O);
    /* right column (x 136-226): weather and battery, each an icon over a centred value */
    n += add_image(W(in, n), weather_icon(), 161, 36, 40, 40);
    put_temp(ST->clk_wx, S_WX_NOW);
    n += text(in, n, ST->clk_wx, 136, 226, 80, WHITE, 1);
    n += add_image(W(in, n), CHARGING ? IMG_BOLT : IMG_BATTERY, 161, 128, 40, 40);
    p = put_u(ST->clk_bat, S_BATTERY, 1);
    put(p, "%");
    n += text(in, n, ST->clk_bat, 136, 226, 172, WHITE, 1);
    p = put3(ST->clk_date, WEEKDAY_NOW);
    p = put(p, " ");
    p = put_u(p, S_DAY, 1);
    p = put(p, " ");
    put3(p, MONTH_NOW);
    n += text(in, n, ST->clk_date, 0, 240, 228, GREY, 1);    /* centred: clear of the round corners */
}

void clock_build(inst_t *in, int arg) { (void)arg; if (begin_build(in, D_CLOCK)) dock_body(in); }
void clock_enter(int a, int b) {
    (void)a; (void)b;
    if (ST->dock_mode > 2) ST->dock_mode = 0;
    ST->last_min = 0xFF;
    enter(D_CLOCK, "dock", 1000);
    aod_dim(ST->dock_mode == 1);
    ST->dim_pending = ST->dock_mode == 1;              /* again on the first tick: see clock_event */
}
void clock_exit(void) { leave(D_CLOCK); aod_dim(0); }
void t_clock_touch(uint8_t *evt);
void t_clock_key(int cls, int k);
void t_dock_timeout(void);
void clock_touch(uint8_t *evt) { t_clock_touch(evt); }
void clock_key(int cls, int k) { t_clock_key(cls, k); }
void clock_event(const uint32_t *msg) {
    int t = event_type(D_CLOCK, msg);
    if (t == 2) {
        /* a wake-up that was still in flight when the always-on screen opened (screen_wake / LCD on
         * path) can set the normal backlight after aod_dim: set the always-on level once more */
        if (ST->dim_pending) { ST->dim_pending = 0; if (ST->dock_mode == 1) aod_dim(1); }
        if (ST->dock_mode == 1 && ST->last_min == S_MIN) return;   /* always-on: once a minute */
        ST->last_min = S_MIN;
        refresh(D_CLOCK);
    }
    else if (t == 1) t_dock_timeout();
}

/* Charger plugged / unplugged: called instead of the stock handler 0x832008 (hook at 0x83DDBC,
 * which runs only when the state changes; the new state is already in CHARGING). */
#define POWERED_ON U8(0x0020D154 + 0xDC)
void charger_change(int st) {
    uint32_t cur = CUR_SCREEN;
    if (POWERED_ON != 1) { stock_charger_ui(st); return; }       /* power-on from the charger: stock */
    if (cur == D_NAV) return;                                    /* navigating in the car: stay */
    if (CHARGING) {
        int s = dock_setting();
        if (s != 3) { ST->dock_auto = 1; ST->dock_mode = (uint8_t)s; gui_switch(D_CLOCK); return; }
        if (cur == D_CLOCK) return;
    } else if (cur == D_CLOCK && (!ST->dock_auto || (ST->dock_mode == 1 && S_AOD == 1))) {
        return;                                    /* opened by hand, or always-on: stay as it is */
    }
    stock_charger_ui(st);
}

/* ================================================================== navigation */
static void nav_body(inst_t *in) {
    int n = 0, k, digits = 0;
    char *num = ST->nav_num, *p;
    const char *unit;
    if (ST->magic != MAGIC) return;
    /* arrow 4-100, distance digits 100-184, unit 184-208, street 212-236, speed / ETA 240-264 */
    n += add_image(W(in, n), NAV_ARROW[ST->nav_dir & 7], 72, 4, 96, 96);
    for (k = 0; ST->nav_dist[k] && k < 4 &&
                ((ST->nav_dist[k] >= '0' && ST->nav_dist[k] <= '9') || ST->nav_dist[k] == '.'); k++)
        num[digits++] = ST->nav_dist[k];
    num[digits] = 0;
    unit = ST->nav_dist + k;
    while (*unit == ' ') unit++;
    if (digits) {
        n = put_big(in, n, num, (240 - digits * DW) / 2, 100, DIG_BOLD_W);
        n += text(in, n, unit, 0, 240, 184, GREY, 1);
    } else {
        n += text(in, n, ST->nav_dist, 0, 240, 140, WHITE, 1);
    }
    n += text(in, n, ST->nav_street, 12, 228, 212, WHITE, 1);
    p = put(ST->nav_line, ST->nav_speed);
    if (ST->nav_speed[0] && ST->nav_eta[0]) p = put(p, "  ");
    put(p, ST->nav_eta);
    n += text(in, n, ST->nav_line, 24, 216, 240, ORANGE, 1);
}

void nav_build(inst_t *in, int arg) { (void)arg; if (begin_build(in, D_NAV)) nav_body(in); }
void nav_enter(int a, int b) { (void)a; (void)b; enter(D_NAV, "navigation", 1000); }
void nav_exit(void) { leave(D_NAV); }
void nav_touch(uint8_t *evt) { touch(D_NAV, evt, 0, D_FACE); }
void nav_key(int cls, int k) { key(cls, k, D_FACE); }
void nav_event(const uint32_t *msg) {
    int t = event_type(D_NAV, msg);
    if (t == 1) { os_timer_restart(TIMER_OFF, 0x7FFFFFFFu); return; }
    if (t != 2) return;
    if (ST->magic == MAGIC && ++ST->nav_age > NAV_TIMEOUT_S) { ST->magic = 0; gui_switch(D_FACE); }
}

/* ASCII view of the received UTF-16BE text (non-ASCII -> '?') */
static void ascii(const uint8_t *buf, char *out, int cap) {
    int len = buf[0], i, n = 0;
    if (len > 160) len = 160;
    for (i = 0; 2 * i + 1 < len && n < cap - 1; i++)
        out[n++] = buf[1 + 2 * i] ? '?' : (char)buf[2 + 2 * i];
    out[n] = 0;
}

static int starts(const char *s, const char *tag) { while (*tag) if (*s++ != *tag++) return 0; return 1; }

/* "CFG|dock=N" (charging screen style 0-3), "CFG|aod=0/1" (always-on display), both saved;
 * "CFG|show=N" opens the dock now in style N */
void aod_toggle(void);
void t_config(const char *s);

/* Called from the C5 notification handler hook with the received text (u8 length, UTF-16BE).
 * Returns 1 if it was one of our messages (then the notification is not stored or shown). */
int nav_check(const uint8_t *buf) {
    char *t = ST->rx, *field[5];
    int i, f = 0, used = 0, cap[5] = {2, 12, 40, 16, 24};
    char *dst = 0, dir = 'S';
    ascii(buf, t, sizeof ST->rx);
    if (starts(t, "CFG|")) { t_config(t + 4); return 1; }
    if (!starts(t, "NAV|")) return 0;
    field[0] = 0; field[1] = ST->nav_dist; field[2] = ST->nav_street;
    field[3] = ST->nav_speed; field[4] = ST->nav_eta;
    ST->magic = 0;                                     /* invalid while being rewritten */
    ST->nav_dist[0] = ST->nav_street[0] = ST->nav_speed[0] = ST->nav_eta[0] = 0;
    for (i = 4; t[i] && f < 5; i++) {
        char c = t[i];
        if (c == '|') { if (dst) *dst = 0; f++; used = 0; dst = 0; continue; }
        if (f == 0) { dir = c; continue; }
        if (!dst) dst = field[f];
        if (used < cap[f] - 1) { *dst++ = c; used++; }
    }
    if (dst) *dst = 0;
    ST->nav_dir = (uint8_t)(dir == 'L' ? 1 : dir == 'R' ? 2 : dir == 'l' ? 3 : dir == 'r' ? 4 :
                            dir == 'U' ? 5 : dir == 'A' ? 6 : dir == 'O' ? 7 : 0);
    ST->nav_age = 0;
    ST->magic = MAGIC;
    if (CUR_SCREEN == D_NAV && DISPLAY_ON == 1) refresh(D_NAV);
    else gui_switch(D_NAV);
    return 1;
}

/* watch settings: see t_ws_* below */

/* ================================================================== quick panel */
void t_set(char key, int on);
void t_report(void);
static void qp_aod(int t) { if (t) return; t_set('a', S_AOD != 1); save_settings(); t_report(); refresh(D_STATUSBAR); }
static void qp_open(uint32_t desc) { RETURN_TO = D_STATUSBAR; gui_switch(desc); }
static void qp_find(int t) { if (!t) qp_open(D_FINDPHONE); }
static void qp_watchset(int t) { if (!t) qp_open(D_WATCHSET); }
static void qp_clock(int t) { if (t) return; ST->dock_mode = 0; ST->dock_auto = 0; gui_switch(D_CLOCK); }


/* Quick panel = 3 x 3 grid of 68 px tiles (x 12 + 74 col, y 48 + 74 row; 12-16 px margins on the
 * 240 x 280 screen) under a status bar:
 *   Do not disturb | Brightness (+level) | Always-on
 *   Raise to wake  | Flashlight          | Find phone
 *   Watch settings | Desk clock          | Settings
 * The stock builder still runs (it owns the DND / brightness / raise / flashlight / settings logic and
 * their state images); afterwards only its tiles (moved into the grid, rev-10 art) and the status
 * bar's BT icon (left) and battery items (right) are kept. Everything else it drew is dropped: its
 * date (0x84383C: digits plus language-dependent month / weekday items at fixed spots that landed on
 * the first tile row) is replaced by one line in the status bar. */
enum { QI_DND, QI_DND_ON, QI_BRIGHT, QI_AOD, QI_AOD_ON, QI_RAISE, QI_RAISE_ON, QI_TORCH, QI_FIND,
       QI_WATCHSET, QI_DOCK, QI_SETTINGS };

static const struct { uint32_t img; uint8_t tile, slot; } QP_STOCK_IMG[7] = {
    {IMG888, QI_DND, 0}, {IMG889, QI_DND_ON, 0}, {IMG890, QI_BRIGHT, 1},
    {IMG891, QI_RAISE, 3}, {IMG892, QI_RAISE_ON, 3}, {IMG893, QI_TORCH, 4}, {IMG894, QI_SETTINGS, 8},
};
static const struct { uint32_t cb; uint8_t slot; } QP_STOCK_CB[5] = {   /* stock tap callbacks (Thumb) */
    {0x00858675u, 0}, {0x00858635u, 1}, {0x0085871Bu, 3}, {0x00858787u, 4}, {0x00858655u, 8},
};

#define QT 68                                     /* tile size */
static int slot_x(int s) { return 12 + 74 * (s % 3); }
static int slot_y(int s) { return 48 + 74 * (s / 3); }

static void qp_tile(inst_t *in, int wi, int tile, int slot, int area, void (*cb)(int)) {
    add_image(W(in, wi), QP_TILE[tile], slot_x(slot), slot_y(slot), QT, QT);
    if (in->current) add_touch(TOUCH_AREA(area), 1, 80 * (slot % 3), slot_y(slot) - 3, 80, 74, cb);
}

void t_qp_status(inst_t *in);

/* replaces the tail call of StatusBar's build (0x859012) */
void qp_build(inst_t *in, int arg) {
    int i, k, lvl;
    qp_stock_build(in, arg);
    if (!in) return;
    for (i = 0; i < 30; i++) {                         /* stock widgets: keep tiles + status bar only */
        uint8_t *w = in->widgets[i].raw;
        uint32_t img = *(uint32_t *)(w + 0xC);
        int16_t x = *(int16_t *)(w + 0), y = *(int16_t *)(w + 2);
        int keep = 0;
        if (!w[0x1D]) continue;
        if (w[0x1D] == 2)
            for (k = 0; k < 7; k++)
                if (img == QP_STOCK_IMG[k].img) {
                    *(uint32_t *)(w + 0xC) = QP_TILE[QP_STOCK_IMG[k].tile];
                    *(int16_t *)(w + 0) = (int16_t)slot_x(QP_STOCK_IMG[k].slot);
                    *(int16_t *)(w + 2) = (int16_t)slot_y(QP_STOCK_IMG[k].slot);
                    *(uint16_t *)(w + 8) = QT;            /* the blitter strides by the widget width */
                    *(uint16_t *)(w + 0xA) = QT;
                    w[0x1F] = 1;                          /* opaque: the tile has its own black corners */
                    keep = 1;
                }
        /* status bar: BT icon on the left, battery digits / % / icon on the right (y 20-21). The
         * battery digits (14 px frames) start further left the more digits there are (x 133 at
         * 100 %), so they are kept by frame width alone; the stock date digits use 12 px frames. */
        if (!keep && y < 36 && ((w[0x1D] == 2 && (x < 50 || x >= 140)) ||
                                (w[0x1D] == 5 && *(uint16_t *)(w + 8) != 12)))
            keep = 1;
        if (!keep) w[0x1D] = 0;
    }
    if (in->current)
        for (i = 0; i < 10; i++) {                     /* stock touch areas follow their tiles */
            int16_t *a = (int16_t *)TOUCH_AREA(i);
            uint32_t cb = *(uint32_t *)((uint8_t *)a + 8);
            for (k = 0; k < 5; k++)
                if (cb == QP_STOCK_CB[k].cb) {
                    int s = QP_STOCK_CB[k].slot;
                    a[0] = (int16_t)(80 * (s % 3)); a[1] = (int16_t)(slot_y(s) - 3); a[2] = 80; a[3] = 74;
                }
        }
    qp_tile(in, 30, S_AOD == 1 ? QI_AOD_ON : QI_AOD, 2, 10, qp_aod);
    qp_tile(in, 31, QI_FIND, 5, 11, qp_find);
    qp_tile(in, 32, QI_WATCHSET, 6, 12, qp_watchset);
    qp_tile(in, 33, QI_DOCK, 7, 13, qp_clock);
    lvl = S_BRIGHT / 25;                               /* 25/50/75/100 % -> 1..4 segments */
    if (lvl < 1) lvl = 1;
    if (lvl > 4) lvl = 4;
    add_image(W(in, 34), QP_LEVEL[lvl - 1], slot_x(1) + 12, slot_y(1) + 57, 44, 5);
    t_qp_status(in);
}

/* ================================================================== tap tick */
static const uint16_t TICK_STEPS[4] = {1, 40, 0, 0};   /* {u8 on, pad, u16 ms} x2: 40 ms on, stop */

void tap_tick(void) {
    if (S_HAPTIC_OFF || U8(MOTOR_STATE)) return;
    motor_vibrate(1, 2);                                /* keeps the stock DND / battery rules */
    if (U8(MOTOR_STATE)) {
        U32(MOTOR_STATE + 0xC) = (uint32_t)TICK_STEPS;
        motor_timer_set(40);
    }
}

/* ================================================================== always-on display (dock style 1)
 * Owner's reference (rev 14): letter-spaced weekday and grey date top left, weather top right,
 * dot-matrix time (white hours, orange minutes, grey colon), battery | steps at the bottom, all about
 * 30 px clear of the round corners. Labels and numbers are pack images (word images, sprite digits),
 * not the system font. Own backlight level (AOD_LEVEL), redrawn once a minute. With S_AOD set it
 * replaces "screen off" (timeout, wrist down), on and off the charger. */
#define AW 40
#define AH 60
#define SW 8                                           /* small sprite digit frame */
#define SH 14

static int aod_dots(inst_t *in, int n, const char *s, int x, int y, const uint32_t *tab) {
    for (; *s; s++, x += AW + 4)
        if (*s >= '0' && *s <= '9') n += add_image(W(in, n), tab[*s - '0'], x, y, AW, AH);
    return n;
}

/* backlight for the always-on screen: AOD_LEVEL 0-3 -> 15/14/13/12 driver pulses. backlight_apply
 * (0x83C2CC) sends 16 - S_BRIGHT * 13 / 100 pulses to the one-wire LED driver (more = dimmer, 15 the
 * dimmest); stock resets S_BRIGHT < 25 to 50, which tools/s100_ext.py relaxes to < 1 so the two
 * dimmest steps are reachable. The saved brightness is put back right after. */
static const uint8_t AOD_PWM[4] = {5, 20, 28, 36};
void aod_dim(int on) {
    if (on) {
        uint8_t b = S_BRIGHT;
        S_BRIGHT = AOD_PWM[AOD_LEVEL];
        backlight_apply();
        S_BRIGHT = b;
        ST->dimmed = 1;
    } else if (ST->dimmed) {
        ST->dimmed = 0;
        backlight_apply();
    }
}

/* replaces "b.w 0x8464FA" at 0x84236C: the screen-off timer path of every screen */
void aod_screen_off(void) {
    uint32_t cur = CUR_SCREEN;
    if (S_AOD == 1 && cur != D_CLOCK && cur != D_NAV && !(U16(cur + 0x30) & 0x8000) &&
        S_BATTERY > 10 && DISPLAY_ON == 1) {
        ST->dock_mode = 1;
        ST->dock_auto = 2;
        raise_reset();                                 /* a later raise is seen as a new gesture */
        gui_switch(D_CLOCK);
        return;
    }
    screen_off();
}

void aod_toggle(void) {                                /* quick panel and watch settings switch */
    S_AOD = S_AOD == 1 ? 0 : 1;
    if (S_TIMEOUT >= 15) S_TIMEOUT = 10;               /* AOD needs the normal timeout to kick in */
    os_timer_restart(TIMER_OFF, (uint32_t)S_TIMEOUT * 1000u);
}

/* ================================================================== tail region (t_*)
 * Code linked after the end of the stock app image (tools/s100_ext.py TAIL). */

/* ---- settings: one place that changes them, with the "can always wake" safeguard */
static int t_touch_on(void) { return (S_WAKE & 1) != 0; }
static int t_button_on(void) { return (S_WAKE & 2) == 0; }

void t_set(char key, int on) {
    if (key == 'l') {                                  /* always-on backlight level 0-3 */
        S_WAKE = (uint8_t)((S_WAKE & ~0x30) | ((on & 3) << 4));
        if (CUR_SCREEN == D_CLOCK && ST->dock_mode == 1) aod_dim(1);   /* live while it shows */
        return;
    }
    on = on ? 1 : 0;
    if (key == 'a') {                                  /* always-on display */
        S_AOD = (uint8_t)on;
        if (S_TIMEOUT >= 15) S_TIMEOUT = 10;           /* AOD needs the normal timeout to kick in */
        os_timer_restart(TIMER_OFF, (uint32_t)S_TIMEOUT * 1000u);
    } else if (key == 't') {
        S_WAKE = (uint8_t)(on ? (S_WAKE | 1) : (S_WAKE & ~1));
    } else if (key == 'r') {                           /* stock raise to wake: keep its mirrors */
        S_RAISE = (uint8_t)on;
        S_RAISE_ALGO = (uint8_t)on;
        S_1A6 = (uint8_t)(on ? (S_1A6 | 2) : (S_1A6 & ~2));
    } else if (key == 'b') {
        S_WAKE = (uint8_t)(on ? (S_WAKE & ~2) : (S_WAKE | 2));
    } else if (key == 'h') {
        S_12H = (uint8_t)on;
    } else if (key == 'v') {
        S_HAPTIC_OFF = (uint8_t)!on;
    }
    if (!t_touch_on() && !S_RAISE && !t_button_on())   /* never lock the user out */
        S_WAKE = (uint8_t)(S_WAKE & ~2);
}

static int t_get(char key) {
    switch (key) {
    case 'a': return S_AOD == 1;
    case 't': return t_touch_on();
    case 'r': return S_RAISE != 0;
    case 'b': return t_button_on();
    case 'h': return S_12H != 0;
    case 'l': return AOD_LEVEL;
    default:  return !S_HAPTIC_OFF;
    }
}

/* settings report to the phone / PC (notify on 0x33F2, first byte 0x7E: unused by stock and app) */
void t_report(void) {
    uint8_t *r = ST->report;
    r[0] = 0x7E; r[1] = 1;
    r[2] = (uint8_t)t_get('a'); r[3] = (uint8_t)t_get('t'); r[4] = (uint8_t)t_get('r');
    r[5] = (uint8_t)t_get('b'); r[6] = (uint8_t)dock_setting(); r[7] = (uint8_t)t_get('h');
    r[8] = (uint8_t)t_get('v'); r[9] = S_BATTERY; r[10] = (uint8_t)AOD_LEVEL;
    ble_notify(r, 11);
}

/* "CFG|get", "CFG|aod=1", "CFG|tw=0", "CFG|rw=1", "CFG|bw=1", "CFG|h12=0", "CFG|vib=1",
 * "CFG|ab=N" (always-on brightness 0-3), "CFG|dock=N" (0-3), "CFG|show=N" (open the dock now,
 * style 0-2); several may be joined by '|' */
static const char *const T_TAGS[6] = {"aod=", "tw=", "rw=", "bw=", "h12=", "vib="};
static const char T_TAG_KEY[6] = {'a', 't', 'r', 'b', 'h', 'v'};

void t_config(const char *s) {
    int changed = 0, i;
    for (; *s; s++) {
        for (i = 0; i < 6; i++) {
            int n = slen(T_TAGS[i]);
            if (starts(s, T_TAGS[i]) && (s[n] == '0' || s[n] == '1')) { t_set(T_TAG_KEY[i], s[n] == '1'); changed = 1; }
        }
        if (starts(s, "ab=") && s[3] >= '0' && s[3] <= '3') { t_set('l', s[3] - '0'); changed = 1; }
        if (starts(s, "dock=") && s[5] >= '0' && s[5] <= '3') { S_DOCK = (uint8_t)(s[5] - '0'); changed = 1; }
        if (starts(s, "show=") && s[5] >= '0' && s[5] <= '2') {
            ST->dock_mode = (uint8_t)(s[5] - '0'); ST->dock_auto = 0; gui_switch(D_CLOCK);
        }
    }
    if (changed) save_settings();
    t_report();                                        /* every CFG gets the current settings back */
}

/* ---- dock / always-on behaviour */
void t_clock_touch(uint8_t *evt) {
    if (ST->dock_mode == 1) {                          /* always-on: wakes only with touch to wake */
        if (evt[0] == 2 && t_touch_on()) gui_switch(D_FACE);
        return;
    }
    os_timer_restart(TIMER_OFF, (uint32_t)S_TIMEOUT * 1000u);
    if (evt[0] == 2 || evt[0] == 7) gui_switch(D_FACE);   /* dock: a normal screen */
}

void t_clock_key(int cls, int k) {
    if (k != 1) return;
    if (cls == 1) { gui_switch(D_POWEROFF); return; }
    if (cls == 2 && !(ST->dock_mode == 1 && !t_button_on())) gui_switch(D_FACE);
}

void t_dock_timeout(void) {                            /* timer 1 on the dock screen */
    if (ST->dock_mode == 1) { os_timer_restart(TIMER_OFF, 0x7FFFFFFFu); return; }
    if (S_AOD == 1) {
        ST->dock_mode = 1;
        ST->last_min = 0xFF;
        raise_reset();
        aod_dim(1);
        os_timer_restart(TIMER_OFF, 0x7FFFFFFFu);
        refresh(D_CLOCK);
        return;
    }
    screen_off();
}

/* ---- wake hooks */
void t_button_wake(int arg) {                          /* replaces "b.w 0x843160" at 0x83D486 */
    if (arg == 0 && !t_button_on()) return;
    wake_idle(arg);
}

void t_touch_wake(void) {                              /* dark-screen touch message (0x83D4CE) */
    if (t_touch_on() && DISPLAY_ON != 1) wake_idle(0);
}

void t_tp_sleep(void) {                                /* touch IC "sleep" method (+0xC of 0x20D618) */
    if (t_touch_on()) tp_config();                     /* stay able to report a touch */
    else tp_deep_sleep();
}

void t_raise_on(void) {                                /* wrist raised while the display is on */
    if (CUR_SCREEN == D_CLOCK && ST->dock_mode == 1) gui_switch(D_FACE);
}

/* ---- stock charging screen (dock off): usable while booted */
void t_charge_key(int cls, int k) {
    if (POWERED_ON != 1) { stock_charge_key(cls, k); return; }
    if (k != 1) return;
    if (cls == 2) gui_switch(D_FACE);
    else if (cls == 1) gui_switch(D_POWEROFF);
}

/* wrist lowered (replaces "bl 0x8464FA" at 0x835C6C): the always-on screen instead of off when enabled */
void t_wrist_down(void) {
    if (CUR_SCREEN == D_CLOCK) {
        if (ST->dock_mode == 1) return;                /* already always-on */
        if (S_AOD == 1) { t_dock_timeout(); return; }
    }
    aod_screen_off();
}

/* heart-rate page, swipe down (replaces "ldrb r0,[r1]; cbz r0; strb r6,[r1]" at 0x850BCC): stock only
 * cleared its second-image flag (set by a swipe up); now it also opens the quick panel, as on every
 * other side page (those get it from their navigation template; this page's code passes no target) */
void t_hr_down(uint8_t *view, uint8_t *evt) {
    *view = 0;
    os_timer_restart(TIMER_TICK, 500);                 /* as the page's own swipe cases do */
    os_timer_restart(TIMER_SLIDE, 40);
    slide_down(0x0020DBE4u, D_STATUSBAR, evt);
}

/* "Show always-on" row: switch to the always-on screen now (it stays until a wake action) */
static void t_show_aod(void) {
    ST->dock_mode = 1;
    ST->dock_auto = 2;
    raise_reset();
    gui_switch(D_CLOCK);
}

/* ---- always-on layout (see the always-on section above; coordinates measured on the reference) */
static int t_small(inst_t *in, int n, const char *s, int x, int y, const uint32_t *tab) {
    add_digits(W(in, n), s, slen(s), tab[3], x, y, SW, SH, (uint32_t)tab);   /* one widget per number */
    return n + 1;
}

void t_aod_body(inst_t *in) {
    int n = 0, lvl, x;
    uint8_t t = S_WX_NOW;
    char *p;
    n += add_image(W(in, n), AOD_DAY[weekday_of(S_YEAR, S_MONTH, S_DAY) % 7], 30, 38, 40, 14);
    n += add_image(W(in, n), AOD_MON[(S_MONTH + 11) % 12], 30, 54, 30, 14);
    put_u(ST->aod_dom, S_DAY, 1);
    n = t_small(in, n, ST->aod_dom, 63, 54, AOD_SG);
    /* weather, right-aligned to x 216 */
    p = ST->aod_temp;
    if (t & 0x80) *p++ = '-';
    put_u(p, t & 0x7F, 1);
    x = 216 - 6 - slen(ST->aod_temp) * SW;
    n += add_image(W(in, n), AOD_WX2[weather_icon_index()], x - 24, 43, 20, 16);
    n = t_small(in, n, ST->aod_temp, x, 44, AOD_SW);
    n += add_image(W(in, n), AOD_DEG, x + slen(ST->aod_temp) * SW, 44, 6, 14);
    /* time */
    n = aod_dots(in, n, ST->clk_hh, 78, 82, AOD_W);
    n += add_image(W(in, n), AOD_COLON2, 170, 111, 10, 26);
    n = aod_dots(in, n, ST->clk_mm, 78, 150, AOD_O);
    /* battery | steps */
    lvl = (S_BATTERY + 12) / 25;
    if (lvl > 4) lvl = 4;
    n += add_image(W(in, n), AOD_BAT2[lvl], 52, 232, 21, 11);
    put_u(ST->aod_pct, S_BATTERY, 1);
    n = t_small(in, n, ST->aod_pct, 79, 230, AOD_SW);
    n += add_image(W(in, n), AOD_PCT, 79 + slen(ST->aod_pct) * SW, 230, 11, 14);
    n += add_image(W(in, n), AOD_DIV2, 122, 228, 1, 18);
    n += add_image(W(in, n), AOD_STEPS2, 143, 229, 14, 16);
    put_u(ST->aod_steps, S_STEPS, 1);
    t_small(in, n, ST->aod_steps, 164, 230, AOD_SG);
}

/* ---- watch settings screen (FactoryTpTest slot): two pages, swipe up / down between them
 *   Display: Always-on, Show always-on (only while always-on is enabled), AOD brightness,
 *            12-hour time, Tap vibration
 *   Wake:    Tap to wake, Raise to wake, Press to wake                                       */
static const char T_WS_PAGE0[5] = {'a', 's', 'l', 'h', 'v'};
static const char T_WS_PAGE1[3] = {'t', 'r', 'b'};
static const char T_WS_ALL[8] = {'a', 's', 'l', 'h', 'v', 't', 'r', 'b'};
/* font 0 is ~11 px per capital / 10 per small letter; the label box is 150 px (x 20-170) */
static const char *const T_WS_LABEL[8] = {"Always-on", "Show always-on", "AOD brightness", "12-hour time",
                                          "Tap vibration", "Tap to wake", "Raise to wake", "Press to wake"};
static const char *const T_LEVEL[4] = {"Min", "Low", "Mid", "High"};

static int t_ws_rows(char *keys) {                     /* keys of the rows shown on this page */
    int i, n = 0;
    if (ST->ws_page) { for (i = 0; i < 3; i++) keys[n++] = T_WS_PAGE1[i]; return n; }
    for (i = 0; i < 5; i++)
        if (T_WS_PAGE0[i] != 's' || S_AOD == 1) keys[n++] = T_WS_PAGE0[i];
    return n;
}

static void t_ws_tap(int row) {
    char keys[5];
    char k;
    if (row >= t_ws_rows(keys)) return;
    k = keys[row];
    if (k == 's') { t_show_aod(); return; }
    t_set(k, k == 'l' ? (AOD_LEVEL + 1) & 3 : !t_get(k));
    ST->ws_dirty = 1;
    t_report();
    refresh(D_WATCHSET);
}
static void t_ws0(int t) { if (!t) t_ws_tap(0); }
static void t_ws1(int t) { if (!t) t_ws_tap(1); }
static void t_ws2(int t) { if (!t) t_ws_tap(2); }
static void t_ws3(int t) { if (!t) t_ws_tap(3); }
static void t_ws4(int t) { if (!t) t_ws_tap(4); }
static void (*const T_WS_CB[5])(int) = {t_ws0, t_ws1, t_ws2, t_ws3, t_ws4};

/* title 10-34, rows of 40 px every 46 px from y 44 (last ends at 270); text centred in its row */
void t_ws_build(inst_t *in, int arg) {
    int i, j, n = 0, rows;
    char keys[5];
    (void)arg;
    if (!begin_build(in, D_WATCHSET)) return;
    rows = t_ws_rows(keys);
    n += text(in, n, ST->ws_page ? "Wake  2/2" : "Display  1/2", 0, 240, 10, GREY, 1);
    for (i = 0; i < rows; i++) {
        int y = 44 + 46 * i, v = t_get(keys[i]);
        const char *val = v ? "On" : "Off";
        uint32_t col = v ? ORANGE : GREY;
        for (j = 0; T_WS_ALL[j] != keys[i]; j++) {}
        if (keys[i] == 's') { val = ">"; col = WHITE; }
        if (keys[i] == 'l') { val = T_LEVEL[v & 3]; col = ORANGE; }
        n += add_image(W(in, n), IMG_WS_ROW, 8, y, 224, 40);
        n += text(in, n, T_WS_LABEL[j], 20, 170, y + 8, WHITE, 2);
        n += text(in, n, val, 170, 224, y + 8, col, 1);
        if (in->current) add_touch(TOUCH_AREA(i), 1, 0, y - 3, 240, 46, T_WS_CB[i]);
    }
}
void t_ws_enter(int a, int b) {
    (void)a; (void)b;
    ST->ws_dirty = 0;
    ST->ws_page = 0;
    enter(D_WATCHSET, "watchset", 3000);
}
void t_ws_exit(void) {
    leave(D_WATCHSET);
    if (ST->ws_dirty) { ST->ws_dirty = 0; save_settings(); }
}
void t_ws_touch(uint8_t *evt) {
    if (evt[0] == 8 || evt[0] == 9) {                  /* swipe up: Wake page, down: Display page */
        uint8_t page = evt[0] == 8;
        os_timer_restart(TIMER_OFF, (uint32_t)S_TIMEOUT * 1000u);
        if (ST->ws_page != page) { ST->ws_page = page; refresh(D_WATCHSET); }
        return;
    }
    touch(D_WATCHSET, evt, ST->ws_page ? 3 : 5, D_FACE);
}
void t_ws_key(int cls, int k) { key(cls, k, D_FACE); }
void t_ws_event(const uint32_t *msg) {
    if (event_type(D_WATCHSET, msg) == 1) screen_off_evt();
}

/* ---- quick-panel status bar: one centre line (y 29) and two groups on the tile grid's edges
 * (x 20 / 220): link icon + date on the left, battery digits + % + icon right-aligned on the right.
 * Date and battery use one image set (QS_*, a little smaller than the 24 px system font); the stock
 * battery digits / % are hidden and their places reused. */
static int t_free(inst_t *in) {                       /* a widget slot the keep-list emptied */
    int i;
    for (i = 0; i < 30; i++) if (!in->widgets[i].raw[0x1D]) return i;
    return 36;
}

static int t_qs_num(inst_t *in, const char *s, int x) {
    int i = t_free(in);
    add_digits(W(in, i), s, slen(s), QS_DIG[3], x, 19, 11, 20, (uint32_t)QS_DIG);
    return x + 11 * slen(s);
}

void t_qp_status(inst_t *in) {
    uint8_t *icon = 0;
    int i, x, wd = weekday_of(S_YEAR, S_MONTH, S_DAY) % 7;
    for (i = 0; i < 30; i++) {
        uint8_t *w = in->widgets[i].raw;
        int16_t x0 = *(int16_t *)(w + 0), y0 = *(int16_t *)(w + 2);
        uint16_t ww = *(uint16_t *)(w + 8), hh = *(uint16_t *)(w + 0xA);
        if ((w[0x1D] != 2 && w[0x1D] != 5) || y0 >= 36 || ww >= QT) continue;
        if (w[0x1D] == 5 || (x0 >= 50 && ww < 20)) w[0x1D] = 0;          /* stock digits and % */
        else if (x0 < 50) { *(int16_t *)(w + 0) = 20; *(int16_t *)(w + 2) = (int16_t)(29 - hh / 2); }   /* link */
        else icon = w;
    }
    x = 220;
    if (icon) { x -= *(uint16_t *)(icon + 8); *(int16_t *)(icon + 0) = (int16_t)x; *(int16_t *)(icon + 2) = 20; }
    x -= 3 + 14;                                       /* % ink is 14 of its 16 px */
    add_image(W(in, t_free(in)), QS_PCT, x, 19, 16, 20);
    put_u(ST->qs_bat, S_BATTERY, 1);
    t_qs_num(in, ST->qs_bat, x - 11 * slen(ST->qs_bat));
    /* date: link icon ends at x 44, then a 10 px gap */
    add_image(W(in, t_free(in)), QS_WD[wd], 54, 19, 44, 20);
    put_u(ST->qs_day, S_DAY, 1);
    t_qs_num(in, ST->qs_day, 54 + QS_WDW[wd] + 5);
}
