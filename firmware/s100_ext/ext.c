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
    char nav_dist[12], nav_street[48], nav_speed[16], nav_eta[24];
    /* text widgets keep a pointer to their string until the next build: strings must live here */
    char nav_num[12], nav_line[44], nav_s1[44], nav_s2[44], nav_s3[44], nav_time[12];
    uint8_t nav_min, nav_alerted;
    char sp_time[8], sp_val[4];
    uint32_t nav_key;                             /* manoeuvre identity for the turn alert */
    /* our settings (record at flash 0x97A2D0, loaded on first use after boot: t_p) */
    struct { uint32_t magic; uint8_t wake, aod, dock, haptic_off; uint8_t rsv[8]; } p;
    char clk_date[24], clk_time[8], clk_wx[32], clk_bat[20], clk_hh[4], clk_mm[4];
    uint8_t dock_mode, dock_auto;
    char rx[84];                                  /* last received message as ASCII */
    char aod_steps[8];
    uint8_t dimmed, last_min;
    uint8_t report[12];
    char aod_temp[8], aod_pct[8], aod_dom[4];
    char qs_bat[4], qs_day[4];
    uint32_t pref_magic, pref_sum;                /* last saved user preferences (t_prefs_*) */
    uint8_t dim_pending, ws_page;
    char br_clk[8], br_left[8], br_min[4];
    uint32_t br_t0;                               /* Breathe: clock second the exercise started */
    uint8_t br_on;
} state_t;
#define ST ((state_t *)0x0021B000u)      /* free static RAM between .bss end and the heap */
#define MAGIC 0x53315845u

/* our settings, in our own record (see t_p / t_save_settings at the end) */
typedef struct { uint32_t magic; uint8_t wake, aod, dock, haptic_off; uint8_t rsv[8]; } prefs_t;
prefs_t *t_p(void);
#define S_WAKE       (t_p()->wake)        /* bit0 touch to wake ON, bit1 button to wake OFF, bits 4-5
                                             always-on backlight level 0 (dimmest) - 3, bit 6 turn alerts OFF */
#define S_AOD        (t_p()->aod)         /* 1 = always-on display instead of screen off */
#define S_DOCK       (t_p()->dock)        /* charging screen style 0-3 */
#define S_HAPTIC_OFF (t_p()->haptic_off)  /* tap vibration, 0 = on */
#define AOD_LEVEL    ((S_WAKE >> 4) & 3)

/* 3-letter names packed in one string each (no pointer tables: code space is tight) */
static const char WEEKDAYS[] = "SunMonTueWedThuFriSat";
static const char MONTHS[] = "JanFebMarAprMayJunJulAugSepOctNovDec";
#define WEEKDAY_NOW (WEEKDAYS + 3 * (weekday_of(S_YEAR, S_MONTH, S_DAY) % 7))
#define MONTH_NOW (MONTHS + 3 * ((S_MONTH + 11) % 12))

static char *put3(char *d, const char *s) { d[0] = s[0]; d[1] = s[1]; d[2] = s[2]; d[3] = 0; return d + 3; }

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
void t_charge_body(inst_t *in);
void aod_dim(int on);

static void dock_body(inst_t *in) {
    int n = 0, style = ST->dock_mode;
    char *p;
    time_strings();
    if (style == 2) { t_charge_body(in); return; }      /* charging face */
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
        return;                                                  /* "Nothing": keep the current screen */
    } else if (cur == D_CLOCK && (!ST->dock_auto || (ST->dock_mode == 1 && S_AOD == 1))) {
        return;                                    /* opened by hand, or always-on: stay as it is */
    }
    stock_charger_ui(st);
}

/* ================================================================== navigation */
void t_nav_body(inst_t *in);

void nav_build(inst_t *in, int arg) { (void)arg; if (begin_build(in, D_NAV)) t_nav_body(in); }
void nav_enter(int a, int b) { (void)a; (void)b; enter(D_NAV, "navigation", 1000); }
void nav_exit(void) { leave(D_NAV); }
void nav_touch(uint8_t *evt) { touch(D_NAV, evt, 0, D_FACE); }
void nav_key(int cls, int k) { key(cls, k, D_FACE); }
void nav_event(const uint32_t *msg) {
    int t = event_type(D_NAV, msg);
    if (t == 1) { os_timer_stop(TIMER_OFF); return; }    /* stays on while navigating */
    if (t != 2) return;
    if (ST->magic == MAGIC && ++ST->nav_age > NAV_TIMEOUT_S) { ST->magic = 0; gui_switch(D_FACE); return; }
    if (ST->nav_min != S_MIN) refresh(D_NAV);          /* the clock at the top */
}

/* ASCII view of the received UTF-16BE text. Map apps put no-break / thin spaces between number and
 * unit ("2.5<U+00A0>km") and typographic dashes, dots and quotes in street names: those become their
 * ASCII forms (t_ascii_char); anything else outside ASCII becomes '?'. */
char t_ascii_char(unsigned c);
static void ascii(const uint8_t *buf, char *out, int cap) {
    int len = buf[0], i, n = 0;
    if (len > 160) len = 160;
    for (i = 0; 2 * i + 1 < len && n < cap - 1; i++)
        out[n++] = t_ascii_char((unsigned)(buf[1 + 2 * i] << 8 | buf[2 + 2 * i]));
    out[n] = 0;
}

static int starts(const char *s, const char *tag) { while (*tag) if (*s++ != *tag++) return 0; return 1; }

/* "CFG|dock=N" (charging screen style 0-3), "CFG|aod=0/1" (always-on display), both saved;
 * "CFG|show=N" opens the dock now in style N */
void aod_toggle(void);
void t_config(const char *s);

/* Called from the C5 notification handler hook with the received text (u8 length, UTF-16BE).
 * Returns 1 if it was one of our messages (then the notification is not stored or shown). */
uint8_t t_nav_dir(char c);
void t_nav_alert(void);
int nav_check(const uint8_t *buf) {
    char *t = ST->rx, *field[5];
    int i, f = 0, used = 0, cap[5] = {2, 12, 48, 16, 24};
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
    ST->nav_dir = t_nav_dir(dir);
    t_nav_alert();
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
void t_save(void);
static void qp_aod(int t) { if (t) return; t_set('a', S_AOD != 1); t_save(); t_report(); refresh(D_STATUSBAR); }
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

/* backlight for the always-on screen: AOD_LEVEL 0-3 (Min, Low, Mid, High) -> n = 14/13/12/11.
 * backlight_apply (0x83C2CC) computes n = 16 - S_BRIGHT * 13 / 100 and then sends 1 + n falling edges
 * to the one-wire LED driver (more = dimmer). The driver has 16 steps and wraps after the 16th edge,
 * so n = 15 is the BRIGHTEST (the old "Min" bug) and n = 14 the dimmest; s100_ext.py also caps the
 * stock clamp at 14. Stock resets S_BRIGHT < 25 to 50; relaxed to < 16 (still covers our values).
 * The saved brightness is put back right after. */
static const uint8_t AOD_PWM[4] = {20, 28, 36, 44};
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
void t_prefs_check(void);
void aod_screen_off(void) {
    uint32_t cur = CUR_SCREEN;
    t_prefs_check();
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
    if (key == 'n') {                                  /* navigation turn alerts (bit 6 = off) */
        S_WAKE = (uint8_t)(on ? (S_WAKE & ~0x40) : (S_WAKE | 0x40));
        return;
    }
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
    case 'n': return (S_WAKE & 0x40) == 0;
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
    r[11] = (uint8_t)t_get('n');
    ble_notify(r, 12);
}

/* "CFG|get", "CFG|aod=1", "CFG|tw=0", "CFG|rw=1", "CFG|bw=1", "CFG|h12=0", "CFG|vib=1",
 * "CFG|ab=N" (always-on brightness 0-3), "CFG|na=0/1" (navigation turn alerts), "CFG|dock=N" (0-3), "CFG|show=N" (open the dock now,
 * style 0-2); several may be joined by '|' */
static const char *const T_TAGS[7] = {"aod=", "tw=", "rw=", "bw=", "h12=", "vib=", "na="};
static const char T_TAG_KEY[7] = {'a', 't', 'r', 'b', 'h', 'v', 'n'};

void t_config(const char *s) {
    int changed = 0, i;
    for (; *s; s++) {
        for (i = 0; i < 7; i++) {
            int n = slen(T_TAGS[i]);
            if (starts(s, T_TAGS[i]) && (s[n] == '0' || s[n] == '1')) { t_set(T_TAG_KEY[i], s[n] == '1'); changed = 1; }
        }
        if (starts(s, "ab=") && s[3] >= '0' && s[3] <= '3') { t_set('l', s[3] - '0'); changed = 1; }
        if (starts(s, "dock=") && s[5] >= '0' && s[5] <= '3') { S_DOCK = (uint8_t)(s[5] - '0'); changed = 1; }
        if (starts(s, "show=") && s[5] >= '0' && s[5] <= '2') {
            ST->dock_mode = (uint8_t)(s[5] - '0'); ST->dock_auto = 0; gui_switch(D_CLOCK);
        }
    }
    if (changed) t_save();
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
    t_prefs_check();
    if (ST->dock_mode == 1) { os_timer_stop(TIMER_OFF); return; }   /* always-on: no timeout */
    if (S_AOD == 1) {
        ST->dock_mode = 1;
        ST->last_min = 0xFF;
        raise_reset();
        aod_dim(1);
        os_timer_stop(TIMER_OFF);
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
 *   Wake & alerts: Tap to wake, Raise to wake, Press to wake, Turn alerts (navigation)       */
static const char T_WS_PAGE0[5] = {'a', 's', 'l', 'h', 'v'};
static const char T_WS_PAGE1[4] = {'t', 'r', 'b', 'n'};
static const char T_WS_ALL[9] = {'a', 's', 'l', 'h', 'v', 't', 'r', 'b', 'n'};
/* font 0 is ~11 px per capital / 10 per small letter; the label box is 150 px (x 20-170) */
static const char *const T_WS_LABEL[9] = {"Always-on", "Show always-on", "AOD brightness", "12-hour time",
                                          "Tap vibration", "Tap to wake", "Raise to wake", "Press to wake",
                                          "Turn alerts"};
static const char *const T_LEVEL[4] = {"Min", "Low", "Mid", "High"};

static int t_ws_rows(char *keys) {                     /* keys of the rows shown on this page */
    int i, n = 0;
    if (ST->ws_page) { for (i = 0; i < 4; i++) keys[n++] = T_WS_PAGE1[i]; return n; }
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
    n += text(in, n, ST->ws_page ? "Wake & alerts  2/2" : "Display  1/2", 0, 240, 10, GREY, 1);
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
    if (ST->ws_dirty) { ST->ws_dirty = 0; t_save(); }
}
void t_ws_touch(uint8_t *evt) {
    if (evt[0] == 8 || evt[0] == 9) {                  /* swipe up: Wake page, down: Display page */
        uint8_t page = evt[0] == 8;
        os_timer_restart(TIMER_OFF, (uint32_t)S_TIMEOUT * 1000u);
        if (ST->ws_page != page) { ST->ws_page = page; refresh(D_WATCHSET); }
        return;
    }
    touch(D_WATCHSET, evt, ST->ws_page ? 4 : 5, D_FACE);
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

/* ---- user preferences survive a power-off
 * The stock firmware writes the settings block (save_settings) only after phone commands, at
 * hh:10 when hh is a multiple of 10, and from a few system paths -- not when a setting is changed on
 * the watch (menu style, brightness, raise, DND, vibration, timeout, quick-panel tiles) and not on
 * power off. So watch-side changes were lost unless a save happened to come first. The preference
 * fields below (found by driving each settings screen in the emulator) are summed; when the sum
 * differs from the last saved one, the block is saved: at every screen-off timeout and on power off.
 * Volatile fields (steps, time, battery, counters at +0x1A0) are left out, so it writes only after a
 * real change. Battery < 3 %: no flash write (brown-out risk), as stock. */
static const uint16_t T_PREFS[][2] = {   /* {offset, length} in the settings block */
    {0x32, 1}, {0x64, 3}, {0xEE, 14}, {0x11C, 1}, {0x188, 1}, {0x1A4, 3}, {0x1BA, 2}, {0x1F5, 1},
    {0x220, 1}, {0x2CC, 2},
};
#define PREF_MAGIC 0x50524546u

static uint32_t t_prefs_sum(void) {
    uint32_t h = 2166136261u, i, k;
    const uint8_t *p = &t_p()->wake;
    for (i = 0; i < sizeof T_PREFS / sizeof T_PREFS[0]; i++)
        for (k = 0; k < T_PREFS[i][1]; k++) h = (h ^ U8(SETTINGS + T_PREFS[i][0] + k)) * 16777619u;
    for (k = 0; k < 4; k++) h = (h ^ p[k]) * 16777619u;   /* our record */
    return h;
}

void t_save(void) {                                   /* save + remember what was saved */
    save_settings();
    ST->pref_sum = t_prefs_sum();
    ST->pref_magic = PREF_MAGIC;
}

void t_prefs_check(void) {
    if (S_BATTERY < 3) return;
    if (ST->pref_magic != PREF_MAGIC || ST->pref_sum != t_prefs_sum()) t_save();
}

/* power off (replaces "bl 0x83162C" at 0x831664, the first step of 0x831660) */
void t_power_off(void) {
    t_prefs_check();
    power_off_prep();
}

/* ---- navigation screen (D_NAV)
 * Arrow, big distance (unit beside it when it fits), street on up to two lines, speed / ETA on one.
 * Text is measured with the stock font-0 width table, broken at spaces / '/' / '-' and cut with "..."
 * so nothing wraps on its own into the next line (the cause of the overlapping street / ETA). */
#define FONT0_W 0x0088E38Cu                            /* advance of chars 0x20-0x7F (stock table) */
#define NAV_TEXT_W 216                                 /* street lines: x 12-228 */
/* direction letters (NAV|<dir>|...) in arrow-table order:
 * straight, left, right, slight L / R, U-turn, arrive, roundabout, sharp L / R, keep L / R, merge,
 * exit L / R, U-turn to the right (left-hand traffic) */
static const char NAV_DIRS[17] = "SLRlrUAO<>kKMeEu";

uint8_t t_nav_dir(char c) {
    int i;
    for (i = 0; i < 16; i++) if (NAV_DIRS[i] == c) return (uint8_t)i;
    return 0;
}

char t_ascii_char(unsigned c) {
    if (c >= 0x20 && c < 0x7F) return (char)c;
    if (c == 0xA0 || (c >= 0x2000 && c <= 0x200B) || c == 0x202F) return ' ';
    if ((c >= 0x2010 && c <= 0x2015) || c == 0x2212) return '-';
    if (c == 0x2018 || c == 0x2019) return 0x27;
    if (c == 0x201C || c == 0x201D) return '"';
    if (c == 0xB7 || c == 0x2022 || c == 0x2026) return '.';
    return '?';
}

static int t_cw(char c) { return (c >= 0x20 && c < 0x7F) ? U8(FONT0_W + (uint8_t)(c - 0x20)) : 12; }
static int t_tw(const char *s) { int w = 0; while (*s) w += t_cw(*s++); return w; }

static void t_copy(char *dst, const char *src, int n) {   /* n chars, trailing spaces dropped */
    while (n > 0 && src[n - 1] == ' ') n--;
    while (n-- > 0) *dst++ = *src++;
    *dst = 0;
}

/* One line of src into dst, at most `max` px wide. Breaks after the last space, '/', '-' or ','
 * that fits (else mid-word); `last`: no further line, so cut and end with "...".
 * Returns how many chars of src were used. */
static int t_fit(const char *src, char *dst, int max, int last) {
    int i, w = 0, brk = 0, dots = 3 * t_cw('.');
    for (i = 0; src[i]; i++) {
        int cw = t_cw(src[i]);
        if (w + cw > max) break;
        w += cw;
        if (src[i] == ' ' || src[i] == '/' || src[i] == '-' || src[i] == ',') brk = i + 1;
    }
    if (!src[i]) { t_copy(dst, src, i); return i; }
    if (last) {
        while (i > 0 && w + dots > max) w -= t_cw(src[--i]);
        t_copy(dst, src, i);
        put(dst + slen(dst), "...");
        return slen(src);
    }
    if (brk) i = brk;
    t_copy(dst, src, i);
    return i;
}

/* Layout (240 x 280): clock 8-32, arrow 34-130, distance 132-176 (bold 32 x 44 digits, unit beside),
 * street on up to two lines from 180, speed / ETA after it (ends <= 258). Without a distance the block
 * moves up; with the unit below the digits the street keeps one line. */
#define ND_W 32                                        /* navigation distance digits (s_navd*) */
#define ND_H 44
#define ND_ADV 28                                      /* digit step (the 32 px frames have side bearing) */
#define ND_DOT 14                                      /* '.' cell */
static int t_nd_w(const char *s) {
    int w = 0;
    for (; *s; s++) w += *s == '.' ? ND_DOT : ND_ADV;
    return w + (ND_W - ND_ADV);                        /* the last frame is drawn whole */
}
static int t_nd(inst_t *in, int n, const char *s, int x, int y) {
    for (; *s; s++) {
        if (*s == '.') { n += add_image(W(in, n), NAVD[10], x - (ND_W - ND_DOT) / 2, y, ND_W, ND_H); x += ND_DOT; }
        else { n += add_image(W(in, n), NAVD[*s - '0'], x, y, ND_W, ND_H); x += ND_ADV; }
    }
    return n;
}

void t_nav_body(inst_t *in) {
    int n = 0, k, digits = 0, two, y, wnum, wunit, beside;
    unsigned h = S_HOUR;
    char *num = ST->nav_num, *p;
    const char *unit, *rest;
    if (ST->magic != MAGIC) return;
    for (k = 0; ST->nav_dist[k] && k < 5; k++) {          /* "2.5 km", "1,2 km", "800 m" */
        char c = ST->nav_dist[k];
        if (c == ',') c = '.';
        if ((c < '0' || c > '9') && c != '.') break;
        num[digits++] = c;
    }
    num[digits] = 0;
    unit = ST->nav_dist + k;
    while (*unit == ' ') unit++;
    wunit = t_tw(unit);
    wnum = t_nd_w(num);
    beside = digits && wnum + 6 + wunit <= 228;
    /* street: up to two lines (one when the unit needs its own line) */
    rest = ST->nav_street + t_fit(ST->nav_street, ST->nav_s1, NAV_TEXT_W, digits && !beside);
    while (*rest == ' ') rest++;
    ST->nav_s2[0] = 0;
    if (*rest && !(digits && !beside)) t_fit(rest, ST->nav_s2, NAV_TEXT_W, 1);
    two = ST->nav_s2[0] != 0;
    p = put(ST->nav_line, ST->nav_speed);
    if (ST->nav_speed[0] && ST->nav_eta[0]) p = put(p, "  ");
    put(p, ST->nav_eta);
    t_fit(ST->nav_line, ST->nav_s3, 196, 1);
    /* clock */
    if (S_12H) { h %= 12; if (!h) h = 12; }
    p = put_u(ST->nav_time, h, 1);
    p = put(p, ":");
    put_u(p, S_MIN, 2);
    ST->nav_min = S_MIN;
    n += text(in, n, ST->nav_time, 0, 240, 8, WHITE, 1);
    /* arrow: centred in the space the rest leaves */
    y = digits ? 34 : (two ? 44 : 52);
    n += add_image(W(in, n), NAV_IMG[ST->nav_dir & 15], 72, y, 96, 96);
    y += 98;
    if (digits) {
        int x = (240 - wnum - (beside ? 6 + wunit : 0)) / 2;
        n = t_nd(in, n, num, x, y);
        if (beside) n += text(in, n, unit, x + wnum + 6, 240, y + ND_H - 26, GREY, 2);
        y += ND_H + 4;
        if (!beside) { n += text(in, n, unit, 0, 240, y - 2, GREY, 1); y += 24; }
    } else if (ST->nav_dist[0]) {                          /* a distance that is not a number */
        t_fit(ST->nav_dist, ST->nav_num, NAV_TEXT_W, 1);
        n += text(in, n, ST->nav_num, 12, 228, y, GREY, 1);
        y += 26;
    }
    if (ST->nav_s1[0]) { n += text(in, n, ST->nav_s1, 12, 228, y, WHITE, 1); y += 24; }
    if (two) { n += text(in, n, ST->nav_s2, 12, 228, y, WHITE, 1); y += 24; }
    if (ST->nav_s3[0]) text(in, n, ST->nav_s3, 22, 218, y + 6, ORANGE, 1);
}

/* ---- navigation turn alert: two short pulses once per manoeuvre, ~12 s before it
 * Distance in metres from the frame (km / m / mi / ft / yd), speed from "48 km/h" / "30 mph": alert
 * when the turn is within speed x 12 s (60-500 m), or 150 m without a speed. A manoeuvre = direction +
 * street; it alerts once, and again only after the distance grew well past the alert range (a
 * re-route). Not for "straight"; off with "Turn alerts" (S_WAKE bit 6). Stock vibration rules (DND,
 * battery) apply through motor_vibrate. */
static const uint16_t NAV_PULSES[8] = {1, 60, 0, 90, 1, 60, 0, 0};   /* on 60 ms, off 90, on 60, stop */

static unsigned t_num_x10(const char *s, const char **end) {    /* "2.5" -> 25 */
    unsigned v = 0, frac = 0, dec = 0;
    for (; (*s >= '0' && *s <= '9') || *s == '.' || *s == ','; s++) {
        if (*s == '.' || *s == ',') { dec = 1; continue; }
        if (!dec) v = v * 10 + (unsigned)(*s - '0');
        else if (dec == 1) { frac = (unsigned)(*s - '0'); dec = 2; }
    }
    while (*s == ' ') s++;
    *end = s;
    return v * 10 + frac;
}

static unsigned t_nav_metres(void) {                  /* 0xFFFF = unknown */
    const char *u;
    unsigned v = t_num_x10(ST->nav_dist, &u);
    if (u == ST->nav_dist) return 0xFFFF;
    if (u[0] == 'k') return v * 100;                   /* km */
    if (u[0] == 'm' && u[1] == 'i') return v * 161;    /* mi */
    if (u[0] == 'f') return v * 3 / 100;               /* ft */
    if (u[0] == 'y') return v * 9 / 100;               /* yd */
    return v / 10;                                     /* m */
}

void t_nav_alert(void) {
    const char *u;
    unsigned d = t_nav_metres(), kmh = t_num_x10(ST->nav_speed, &u) / 10, range;
    uint32_t key = 2166136261u;
    const char *s = ST->nav_street;
    if (u[0] == 'm' && u[1] == 'p') kmh = kmh * 16 / 10;   /* mph */
    key = (key ^ (uint8_t)ST->nav_dir) * 16777619u;
    for (; *s; s++) key = (key ^ (uint8_t)*s) * 16777619u;
    range = kmh > 5 ? kmh * 10 / 3 : 150;              /* km/h x 12 s = km/h x 3.33 m */
    if (range < 60) range = 60;
    if (range > 500) range = 500;
    if (key != ST->nav_key) { ST->nav_key = key; ST->nav_alerted = 0; }
    else if (ST->nav_alerted && d != 0xFFFF && d > range * 2) ST->nav_alerted = 0;   /* re-route */
    if (ST->nav_alerted || d == 0xFFFF || d > range || ST->nav_dir == 0 || (S_WAKE & 0x40)) return;
    ST->nav_alerted = 1;
    if (U8(MOTOR_STATE)) return;                       /* already vibrating (a call, an alarm) */
    motor_vibrate(1, 2);                               /* keeps the stock DND / battery rules */
    if (U8(MOTOR_STATE)) {                             /* our steps instead of the stock pattern */
        U32(MOTOR_STATE + 0xC) = (uint32_t)NAV_PULSES;
        motor_timer_set(60);
    }
}

/* ---- our settings record
 * Kept in RAM in ST->p and in flash right after the stock settings block (0x97A000 + 0x2D0): the
 * stock save erases that 4 KB sector and writes only 0x2D0 bytes, and nothing reads past them.
 * save_settings (0x830654) is replaced by t_save_settings, so every save -- ours, the phone's, the
 * stock periodic / power-off ones -- writes both. Loaded on first use after boot (nothing runs at
 * boot); before any save (the erase would lose it otherwise). No record yet (first boot after the
 * update): the old bytes 0x2BC-0x2BF are taken over when they hold valid values, else defaults
 * (touch to wake off, button on, AOD off and Min, dock "Dock", vibration and turn alerts on). */
#define PREFS_FLASH (SETTINGS_FLASH + 0x2D0)
#define PREFS_MAGIC 0x31464550u                          /* "PEF1" */

prefs_t *t_p(void) {
    prefs_t *p = (prefs_t *)&ST->p;
    if (p->magic != PREFS_MAGIC) {
        uint32_t i;
        flash_read(p, PREFS_FLASH, sizeof *p);
        if (p->magic != PREFS_MAGIC || p->aod > 1 || p->dock > 3 || p->haptic_off > 1 || (p->wake & 0x80)) {
            const uint8_t *old = (const uint8_t *)LEGACY_PREFS;
            int valid = old[1] <= 1 && old[2] <= 3 && old[3] <= 1 && !(old[0] & 0x80);
            p->wake = valid ? old[0] : 0;
            p->aod = valid ? old[1] : 0;
            p->dock = valid ? old[2] : 0;
            p->haptic_off = valid ? old[3] : 0;
            for (i = 0; i < sizeof p->rsv; i++) p->rsv[i] = 0;
        }
        p->magic = PREFS_MAGIC;
    }
    return p;
}

/* replaces save_settings (b.w at 0x830654): stock block + our record, then the stock 50 ms wait */
void t_save_settings(void) {
    prefs_t *p = t_p();                                  /* read before the erase */
    flash_erase(SETTINGS_FLASH, 0x20);
    flash_write((const void *)SETTINGS, SETTINGS_FLASH, 0x2D0);
    flash_write(p, PREFS_FLASH, sizeof *p);
    delay_us(50000);
}

/* charger state change that turns the display off (unplugged / charge complete: bl 0x8464FA at
 * 0x830FA8, outside the screen-off timer path): always-on instead, like the timeout and wrist down */
void t_charger_off(void) {
    if (S_AOD == 1 && S_BATTERY > 10 && DISPLAY_ON == 1) {
        if (CUR_SCREEN == D_CLOCK) {
            if (ST->dock_mode == 1) return;                  /* already always-on */
            t_dock_timeout();
            return;
        }
        aod_screen_off();
        return;
    }
    screen_off();
}

/* ---- charging face (dock style 2), after the owner's reference: a 196 px ring centred on the screen
 * (10 % steps), bolt, percentage in bold 32 x 44 digits with a small '%', "Charging..." / "Charged"
 * inside it; a small clock above. Refreshed by the dock's 1 s tick (clock_event). */
void t_charge_body(inst_t *in) {
    int n = 0, lvl = S_BATTERY >= 100 ? 10 : (S_BATTERY + 5) / 10, wnum, wpct = t_tw("%"), x;
    unsigned h = S_HOUR;
    char *p;
    const char *label = S_BATTERY >= 100 ? "Charged" : "Charging...";
    if (lvl > 9 && S_BATTERY < 100) lvl = 9;           /* a full ring only when charged */
    if (S_12H) { h %= 12; if (!h) h = 12; }
    p = put_u(ST->clk_time, h, 1);
    p = put(p, ":");
    put_u(p, S_MIN, 2);
    n += text(in, n, ST->clk_time, 0, 240, 8, GREY, 1);
    n += add_image(W(in, n), RING[lvl], 22, 44, 196, 196);          /* centre (120, 142) */
    n += add_image(W(in, n), IMG_BOLT, 100, 84, 40, 40);
    put_u(ST->clk_bat, S_BATTERY > 100 ? 100 : S_BATTERY, 1);
    wnum = t_nd_w(ST->clk_bat);
    x = (240 - wnum - 2 - wpct) / 2;
    n = t_nd(in, n, ST->clk_bat, x, 128);
    n += text(in, n, "%", x + wnum + 2, 240, 148, WHITE, 2);        /* small, on the digits' baseline */
    text(in, n, label, 0, 240, 176, GREY, 1);
}

/* a string of "-./0-9:" in the status-bar digit set (11 x 20 cells, one widget) */
static int t_qs_str(inst_t *in, int n, const char *s, int x, int y) {
    add_digits(W(in, n), s, slen(s), QS_DIG[3], x, y, 11, 20, (uint32_t)QS_DIG);
    return 1;
}

/* screen-header clock, right-aligned to x 226 */
static int t_hdr_clock(inst_t *in, int n, char *buf, int y) {
    unsigned h = S_HOUR;
    char *p;
    if (S_12H) { h %= 12; if (!h) h = 12; }
    p = put_u(buf, h, 1);
    p = put(p, ":");
    put_u(p, S_MIN, 2);
    return t_qs_str(in, n, buf, 226 - 11 * slen(buf), y);
}

/* ---- SpO2 screen (BloodOxygenScreenUI) after the owner's reference
 * The stock build still runs first: it owns the sensor state, the measure / cancel touch areas and the
 * animation timer. Its widgets are then replaced by: header (chevron + "SpO2" image, clock), an orange
 * card (O2 icon, BLOOD OXYGEN, halftone crescent baked in) with the reading in large black-keyed digits,
 * and a status row below it: ring + status line + 12 progress pills.
 *   measuring (the stock build added one of its ring frames): a 90-degree orange arc turns round the
 *     track (2 octant pieces, one step per 500 ms timer tick), "Measuring...", pills = real progress of
 *     the stock 60 s window (tick count 0x2142ED x timer period);
 *   idle, no reading: grey track with an orange dot, "Tap to measure", no pills lit;
 *   reading shown: full orange ring, "Tap to measure again", all pills lit.
 * Reading: the sensor result the stock screen shows (0x20D154 + 0xFE, 0 = none yet). */
#define SPO2_VALUE  U8(0x0020D154 + 0xFE)
#define ANIM_COUNT  U32(0x0020C154 + 0xD60)
#define ANIM_PERIOD U32(0x0020C154 + 0xD64)                /* stock timer period, ms (500) */
#define SPO2_TICKS  U8(0x002142ED)                         /* ticks into the measurement */
#define SPO2_FRAMES 0x0088B1C4u                            /* stock measuring ring frames (11) */
#define SPO2_CX     14                                     /* card */
#define SPO2_CY     60
#define SPO2_BASE   (SPO2_CY + 94)                         /* value baseline (glyph frames end 2 px below) */
#define SPO2_RX     20                                     /* ring */
#define SPO2_RY     206

static int t_spo2_oct(inst_t *in, int n, int k) {
    k &= 7;
    return add_image(W(in, n), SPO2_OCT[k], SPO2_RX + SPO2_OCTB[k][0], SPO2_RY + SPO2_OCTB[k][1],
                     SPO2_OCTB[k][2], SPO2_OCTB[k][3]);
}

void t_spo2_build(inst_t *in, int arg) {
    int i, k, n = 0, measuring = 0, x, lit = 0, st;
    unsigned v = SPO2_VALUE, c, per;
    const char *s;
    spo2_stock_build(in, arg);
    if (!in) return;
    for (i = 0; i < in->cap; i++) {
        const uint8_t *w = in->widgets[i].raw;
        if (w[0x1D] == 2)
            for (k = 0; k < 11; k++)
                if (*(const uint32_t *)(w + 0xC) == U32(SPO2_FRAMES + 4u * k)) measuring = 1;
    }
    memclr(in->widgets, (uint32_t)in->cap * sizeof(widget_t));
    c = ANIM_COUNT;
    /* header: chevron + "SpO2" (one image), clock right-aligned in the status-bar digits */
    n += add_image(W(in, n), SPO2_HEAD, 14, 22, 96, 28);
    n += t_hdr_clock(in, n, ST->sp_time, 26);
    /* card + reading (black-keyed glyphs on the card, baseline-aligned, proportional) */
    n += add_image(W(in, n), SPO2_CARD, SPO2_CX, SPO2_CY, 212, 128);
    x = SPO2_CX + 16;
    if (v > 0 && v <= 100) {
        put_u(ST->sp_val, v, 1);
        for (s = ST->sp_val; *s; s++) {
            n += add_image(W(in, n), SPO2_D[*s - '0'], x, SPO2_BASE + 2 - 50, SPO2_DW[*s - '0'], 50);
            x += SPO2_DW[*s - '0'] + 1;
        }
    } else {
        for (k = 0; k < 2; k++) {
            n += add_image(W(in, n), SPO2_DASH, x, SPO2_BASE + 2 - 50, SPO2_DASH_W, 50);
            x += SPO2_DASH_W + 3;
        }
    }
    n += add_image(W(in, n), SPO2_PCT, x + 3, SPO2_BASE + 2 - 26, SPO2_PCT_W, 26);
    /* status row */
    if (measuring) {
        n += add_image(W(in, n), SPO2_TRACK, SPO2_RX, SPO2_RY, 32, 32);
        n += t_spo2_oct(in, n, (int)c);
        n += t_spo2_oct(in, n, (int)c + 1);
        per = ANIM_PERIOD;
        lit = per ? (int)(SPO2_TICKS * per * 12u / 60000u) : 0;
        if (lit > 12) lit = 12;
        st = 0;
    } else if (v) {
        for (k = 0; k < 8; k++)
            n += t_spo2_oct(in, n, k);
        lit = 12;
        st = 2;
    } else {
        n += add_image(W(in, n), SPO2_TRACK, SPO2_RX, SPO2_RY, 32, 32);
        n += add_image(W(in, n), SPO2_DOT, SPO2_RX + 13, SPO2_RY, 6, 6);
        st = 1;
    }
    n += add_image(W(in, n), SPO2_ST[st], 64, 204, 160, 18);
    for (k = 0; k < 12; k++)
        n += add_image(W(in, n), k < lit ? SPO2_SEG_ON : SPO2_SEG_OFF, 64 + 13 * k, 228, 6, 12);
}

/* ---- Breathe screen (BreathTrainingScreenUI) after the owner's reference
 * The stock build still runs first (state, touch areas, the vibration at each exhale); its widgets
 * are then replaced, except on the duration / pace pickers and the summary, which stay stock.
 *   setup: header (chevron, "Breathe", clock), orange stadium with the halftone mark and a
 *     dark dot panel, Duration and Pace cards (value from the stock settings), START; the stock touch
 *     areas are moved onto the cards and the button;
 *   lead-in (stock steps 0-4, 1 s each): smallest disc, "Get ready", the five step dots;
 *   breathing: the disc follows the stock breath timer. Its phase is 22 ticks (s100_ext.py doubles the
 *     tick rate and the count, so a phase lasts as long as stock: 11 s Slow, 8.8 s Calm, 5.5 s Fast):
 *     ticks 0-17 inhale / exhale (eased over 20 frames), 18-21 hold. Label = the phase; under it the
 *     time left, from the clock (the exercise total is the stock 0x20D168: 5 s lead-in + minutes);
 *   finished (time left 0 while stock still waits for its end timer): "Well done", 0:00. */
#define BR_RUN     U8(0x0020D154 + 0x0D)               /* exercise running */
#define BR_STEP    U32(0x0020D154 + 0x10)              /* lead-in step 0-4, then 5 */
#define BR_TOTAL   U32(0x0020D154 + 0x14)              /* 5 s lead-in + duration, s */
#define BR_SUMMARY U8(0x0020D154 + 0xEE)
#define BR_IN      U8(0x0020D970)                      /* 1 inhale, 0 exhale */
#define BR_PACE    U8(0x0020D971)                      /* 1 Slow, 2 Calm, 3 Fast */
#define BR_MINUTES U8(0x0020D972)
#define BR_PICKING (U8(0x002142F0) | U8(0x002142F1))   /* duration / pace picker open */
#define S_SEC      U8(0x0020BF1C)
#define BR_HOLD    18                                  /* first hold tick of a phase */

static int t_breath_frame(inst_t *in, int n, int lv) {
    if (BR_BIG & (1u << lv))                            /* 170 x 170 slot, same centre */
        return add_image(W(in, n), BR_FRAME[lv], 35, 25, 170, 170);
    return add_image(W(in, n), BR_FRAME[lv], 60, 50, 120, 120);
}

static void t_breath_touch(void) {               /* the stock areas, found by their handlers */
    int i;
    for (i = 0; i < 15; i++) {
        int16_t *a = (int16_t *)TOUCH_AREA(i);
        uint32_t cb = *(uint32_t *)((uint8_t *)a + 8);
        if (cb == 0x0084ABC5u) { a[0] = 16; a[1] = 210; a[2] = 208; a[3] = 48; }         /* START */
        else if (cb == 0x0084AC45u) { a[0] = 12; a[1] = 156; a[2] = 108; a[3] = 52; }    /* duration */
        else if (cb == 0x0084ACB7u) { a[0] = 120; a[1] = 156; a[2] = 108; a[3] = 52; }   /* pace */
    }
}

void t_breath_build(inst_t *in, int arg) {
    int n = 0, k, x, lv, left, el, step;
    unsigned c, now, pace;
    const char *s;
    char *p;
    breath_stock_build(in, arg);
    if (!in || BR_PICKING || BR_SUMMARY) return;
    memclr(in->widgets, (uint32_t)in->cap * sizeof(widget_t));
    n += add_image(W(in, n), BR_CHEVRON, 14, 22, 11, 16);
    n += add_image(W(in, n), BR_TITLE, 30, 20, 88, 20);
    n += t_hdr_clock(in, n, ST->br_clk, 20);
    if (!BR_RUN) {
        ST->br_on = 0;
        n += add_image(W(in, n), BR_PANEL, 70, 52, 170, 170);
        n += add_image(W(in, n), BR_HERO, 18, 52, 170, 170);
        n += add_image(W(in, n), BR_CARD_L, 16, 34, 170, 170);
        n += add_image(W(in, n), BR_CARD_R, 54, 34, 170, 170);
        put_u(ST->br_min, BR_MINUTES, 1);
        for (x = 56, s = ST->br_min; *s; s++, x += 11)
            n += add_image(W(in, n), BR_DIGIT[*s - '0'], x, 166, 11, 16);
        n += add_image(W(in, n), BR_MIN, x + 3, 166, 32, 16);
        pace = BR_PACE;
        n += add_image(W(in, n), BR_PACE_IMG[pace >= 1 && pace <= 3 ? pace - 1 : 2], 164, 167, 46, 14);
        n += add_image(W(in, n), BR_START, 20, 214, 200, 60);
        t_breath_touch();
        return;
    }
    /* time left: from the clock, since the first build that saw the exercise running */
    now = S_HOUR * 3600u + S_MIN * 60u + S_SEC;
    if (!ST->br_on) { ST->br_on = 1; ST->br_t0 = now; }
    el = (int)((now + 86400u - ST->br_t0) % 86400u);
    left = (int)BR_TOTAL - el;
    if (left > (int)BR_TOTAL - 5) left = (int)BR_TOTAL - 5;
    if (left < 0) left = 0;
    p = put_u(ST->br_left, (unsigned)left / 60u, 1);
    p = put(p, ":");
    put_u(p, (unsigned)left % 60u, 2);
    step = (int)BR_STEP;
    c = ANIM_COUNT;
    if (step < 5) {                                                   /* lead-in */
        n += t_breath_frame(in, n, 0);
        n += add_image(W(in, n), BR_LBL_READY, 51, 184, 139, 24);
        for (k = 0; k < 5; k++)
            n += add_image(W(in, n), k <= step ? BR_DOT_ON : BR_DOT_OFF, 92 + 12 * k, 246, 8, 8);
    } else if (!left) {                                               /* done */
        n += t_breath_frame(in, n, 0);
        n += add_image(W(in, n), BR_LBL_DONE, 75, 151, 90, 90);
    } else {
        lv = c >= BR_HOLD ? 19 : BR_EASE[c];
        if (!BR_IN) lv = 19 - lv;
        n += t_breath_frame(in, n, lv);
        if (c >= BR_HOLD) n += add_image(W(in, n), BR_LBL_HOLD, 50, 183, 140, 26);
        else if (BR_IN) n += add_image(W(in, n), BR_LBL_IN, 81, 182, 78, 29);
        else n += add_image(W(in, n), BR_LBL_OUT, 78, 182, 85, 29);
    }
    n += t_qs_str(in, n, ST->br_left, 120 - 11 * slen(ST->br_left) / 2, 214);
}
