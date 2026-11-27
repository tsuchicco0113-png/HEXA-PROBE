#!/usr/bin/env python3
"""HEXA PROBE — CardputerZero で「なんでも覗く」ツール (v0.1)

ハニカムのホームから 6 つの覗き窓を選ぶ:
  1 SERIAL  USB シリアル / Grove UART のモニター (速度切替・HEX 表示・ESP32 リセット)
  2 BLE     周りの Bluetooth LE 機器 (電波の強さ・名前・メーカー)
  3 NFC     RC-S380 でカード/タグの中身 (種類・ID・NDEF・ダンプ)
  4 MIDI    USB MIDI / Grove UART (Unit MIDI) の MIDI メッセージ
  5 I2C     I2C バスのスキャン。B で「本体」を記録すると、挿した Unit が NEW で光る
  6 IR      赤外線リモコンの信号 (NEC / 家製協 / SONY)
どの画面でも L = ログ記録 (~/hexaprobe-logs)、ESC = 戻る

キー: 方向 = F(↑) X(↓) Z(←) C(→) / 1〜6 = 直接選ぶ / ENTER = 開く / ESC = 戻る・終了
usage:
  hexaprobe            # 通常起動 (ランチャーのアイコンと同じ)
  hexaprobe --probe    # 各機能の準備状況を表示して終了
  hexaprobe --sim OUT  # PC 用: 偽のデータで全画面を PNG に保存
"""
import argparse
import collections
import fcntl
import glob
import json
import math
import os
import select
import signal
import struct
import sys
import time

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import hp_backends as B  # noqa: E402

VERSION = "0.1.0"
LCD_W, LCD_H = 320, 170
TOP_H, BOT_H = 18, 16
BY0, BY1 = TOP_H + 2, LCD_H - BOT_H - 2          # 本文の上下
BG, FG, SUB = (14, 16, 22), (235, 238, 245), (150, 158, 175)
ACC = (176, 132, 255)                     # HEXA PROBE の強調色 (CLIP=緑 / POWER=青 / MATRIX=琥珀 / MIDI=ピンク)
ACC_DIM = (40, 30, 64)
WARN = (255, 150, 60)
REC = (255, 70, 90)
NA = (70, 76, 90)
YEL = (255, 214, 90)
CYAN = (90, 220, 240)
LOGDIR = os.path.expanduser("~/hexaprobe-logs")
CFGDIR = os.path.expanduser("~/.config/hexaprobe")

MODS = [  # key, 六角形の名前, 説明
    ("serial", "SERIAL", "USBシリアル・Grove UART"),
    ("ble", "BLE", "周りの BLE 機器を探す"),
    ("nfc", "NFC", "カード・タグの中身を読む"),
    ("midi", "MIDI", "MIDI メッセージを見る"),
    ("i2c", "I2C", "I2C バスに何がいるか探す"),
    ("ir", "IR", "赤外線リモコンの信号を読む"),
]

# ================================================================ keys (HEXA CLIP / POWER と同じ)
EVIOCGRAB = 0x40044590
EV_FMT = "llHHi"
EV_SIZE = struct.calcsize(EV_FMT)
K_ESC, K_BS, K_TAB, K_ENTER, K_SPACE = 1, 14, 15, 28, 57
K_UP, K_LEFT, K_RIGHT, K_DOWN = 103, 105, 106, 108
DIGITS = {2: "1", 3: "2", 4: "3", 5: "4", 6: "5", 7: "6", 8: "7", 9: "8", 10: "9", 11: "0"}
LETTERS = {33: "f", 45: "x", 44: "z", 46: "c", 19: "r", 16: "q", 31: "s", 38: "l", 35: "h", 48: "b",
           34: "g", 20: "t", 18: "e"}
ACTIONS = {K_UP: "UP", K_DOWN: "DOWN", K_LEFT: "LEFT", K_RIGHT: "RIGHT", K_TAB: "TAB",
           K_ENTER: "ENTER", K_ESC: "ESC", K_BS: "BS", K_SPACE: "SPACE"}
LETTER_NAV = {"f": "UP", "x": "DOWN", "z": "LEFT", "c": "RIGHT"}


class Keys:
    def __init__(self, dev):
        self.fd = os.open(dev, os.O_RDONLY | os.O_NONBLOCK)
        try:
            fcntl.ioctl(self.fd, EVIOCGRAB, 1)
        except OSError as e:
            os.close(self.fd)
            if e.errno == 16:
                raise SystemExit("キーボードが使用中です (ほかのアプリが起動中)")
            raise

    def _raw(self, timeout):
        r, _, _ = select.select([self.fd], [], [], timeout)
        if not r:
            return []
        try:
            data = os.read(self.fd, EV_SIZE * 64)
        except BlockingIOError:
            return []
        out = []
        for i in range(0, len(data) - EV_SIZE + 1, EV_SIZE):
            _, _, etype, code, value = struct.unpack(EV_FMT, data[i:i + EV_SIZE])
            if etype == 1 and value in (1, 2):            # 押した + 押しっぱなし (スクロール用)
                out.append(code)
        return out

    def poll(self, timeout=0.0):
        ev = []
        for code in self._raw(timeout):
            if code in ACTIONS:
                ev.append(("ACT", ACTIONS[code]))
            elif code in DIGITS:
                ev.append(("CHAR", DIGITS[code]))
            elif code in LETTERS:
                ch = LETTERS[code]
                ev.append(("ACT", LETTER_NAV[ch]) if ch in LETTER_NAV else ("CHAR", ch))
        return ev

    def flush(self, sec=0.4):
        end = time.time() + sec
        while time.time() < end:
            self._raw(0.05)

    def close(self):
        try:
            fcntl.ioctl(self.fd, EVIOCGRAB, 0)
        finally:
            os.close(self.fd)


def find_keyboard():
    name = None
    for line in open("/proc/bus/input/devices"):
        if line.startswith("N: Name="):
            name = line.strip().split("=", 1)[1].strip('"')
        elif line.startswith("H: Handlers=") and name and "tca8418" in name:
            for h in line.split("=", 1)[1].split():
                if h.startswith("event"):
                    return "/dev/input/" + h
    raise RuntimeError("keyboard (tca8418) not found")


# ================================================================ display
class FrameBuffer:
    def __init__(self, dev="/dev/fb0"):
        import numpy as np
        self.np = np
        base = f"/sys/class/graphics/{os.path.basename(dev)}"
        self.bpp = int(open(f"{base}/bits_per_pixel").read())
        try:
            self.stride = int(open(f"{base}/stride").read())
        except OSError:
            self.stride = LCD_W * self.bpp // 8
        self.f = open(dev, "r+b", buffering=0)

    def show(self, img):
        np = self.np
        a = np.asarray(img.convert("RGB"), dtype=np.uint16)
        if self.bpp == 16:
            buf = (((a[..., 0] >> 3) << 11) | ((a[..., 1] >> 2) << 5) | (a[..., 2] >> 3)).astype("<u2")
        else:
            buf = np.zeros((LCD_H, LCD_W, 4), np.uint8)
            buf[..., 0], buf[..., 1], buf[..., 2], buf[..., 3] = a[..., 2], a[..., 1], a[..., 0], 255
        row = LCD_W * self.bpp // 8
        raw = buf.tobytes()
        if self.stride == row:
            self.f.seek(0)
            self.f.write(raw)
        else:
            for y in range(LCD_H):
                self.f.seek(y * self.stride)
                self.f.write(raw[y * row:(y + 1) * row])

    def clear(self):
        self.show(Image.new("RGB", (LCD_W, LCD_H)))


JP_TEST = "、。あいかがきくけこさしすせそただちつてでとなにのはまみむめもやよらりるれろわをんアイエオカキクケコサシスセソタチッツテトドナニネノハバパビフブプベボマミムメモラリルレロワンー・受信送記録停止消去戻速度選本体電源設定見通信読書込可不明方式検査個台系統未有効再起動探中光挿近強弱名前空気温湿度距離圧"
_FONT_FILE = {}


def font_covers(font, text=JP_TEST):
    try:
        nd = font.getmask("\U0010FFFD")
        nd_key = (nd.size, bytes(nd))
        for ch in text:
            m = font.getmask(ch)
            if m.getbbox() is None or (m.size, bytes(m)) == nd_key:
                return False
        return True
    except Exception:
        return False


def font_candidates():
    cands = []
    for p in ["/usr/share/APPLaunch/**/*.tt[fc]", "/usr/share/APPLaunch/**/*.otf",
              "/usr/share/fonts/**/*CJK*", "/usr/share/fonts/**/*[Ii][Pp][Aa]*",
              "/usr/share/fonts/**/*[Jj][Pp]*", "/usr/share/fonts/**/*wqy*",
              "/usr/share/fonts/**/*Droid*Fallback*"]:
        cands += glob.glob(p, recursive=True)
    return sorted(set(cands))


def find_font(size, bold=False):
    f = _FONT_FILE.get(bold)
    if f:
        return ImageFont.truetype(f, size)

    def rank(f):
        n = os.path.basename(f).lower()
        if "serif" in n or "mono" in n:
            return 50
        order = (["bold", "85", "heavy", "75", "black", "medium", "65", "regular", "55", "light", "thin"]
                 if bold else ["medium", "65", "regular", "55", "bold", "75", "black", "light", "thin"])
        for i, w in enumerate(order):
            if w in n:
                return i
        return 5
    for f in sorted(font_candidates(), key=rank):
        try:
            font = ImageFont.truetype(f, size)
        except Exception:
            continue
        if font_covers(font):
            _FONT_FILE[bold] = f
            return font
    return ImageFont.load_default()


def find_mono(size):
    for p in ["/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
              "/usr/share/fonts/truetype/liberation/LiberationMono-Regular.ttf",
              *glob.glob("/usr/share/fonts/**/*Mono*.ttf", recursive=True)]:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except OSError:
                continue
    return find_font(size)


def hexpts(cx, cy, r, rot=30):
    return [(cx + r * math.cos(math.radians(60 * i + rot)),
             cy + r * math.sin(math.radians(60 * i + rot))) for i in range(6)]


def honeycomb_bg():
    img = Image.new("RGB", (LCD_W, LCD_H), BG)
    d = ImageDraw.Draw(img)
    for row in range(-1, 8):
        for col in range(-1, 12):
            d.polygon(hexpts(col * 30 + (15 if row % 2 else 0), 20 + row * 26, 17), outline=(20, 24, 34))
    return img


def glow_hex(img, cx, cy, r, col):
    g = Image.new("RGB", img.size, (0, 0, 0))
    pts = hexpts(cx, cy, r)
    ImageDraw.Draw(g).line(pts + [pts[0]], fill=col, width=6)
    g = g.filter(ImageFilter.GaussianBlur(3))
    img.paste(ImageChops.lighter(img, g))
    ImageDraw.Draw(img).line(pts + [pts[0]], fill=col, width=2)


def ago(t):
    s = time.time() - t
    return f"{s:.0f}秒前" if s < 60 else f"{s / 60:.0f}分前"


# ================================================================ 部品
class LogBox:
    """流れるログ。back=0 で最新を表示、hold で止める (止めている間も裏では貯まる)"""

    def __init__(self, maxlen=800):
        self.lines = collections.deque(maxlen=maxlen)
        self.back = 0
        self.hold = False

    def add(self, text, col=FG, cols=51):
        parts = []
        while True:
            w, cut = 0, len(text)
            for i, ch in enumerate(text):
                w += 2 if ord(ch) > 0x2E7F else 1
                if w > cols:
                    cut = i
                    break
            parts.append(text[:cut])
            text = text[cut:]
            if not text:
                break
            text = "  " + text
        for p in parts:
            full = len(self.lines) == self.lines.maxlen
            self.lines.append((p, col))
            if (self.back or self.hold) and not full:
                self.back += 1

    def clear(self):
        self.lines.clear()
        self.back = 0

    def scroll(self, n):
        self.back = max(0, min(max(0, len(self.lines) - 1), self.back + n))

    def toggle_hold(self):
        self.hold = not self.hold
        if not self.hold:
            self.back = 0
        return self.hold

    def draw(self, app, d, x0, y0, x1, y1, lh=12):
        rows = max(1, (y1 - y0) // lh)
        end = len(self.lines) - self.back
        start = max(0, end - rows)
        lines = list(self.lines)[start:end]
        for i, (t, c) in enumerate(lines):
            app.mtext(d, (x0, y0 + i * lh), t, c)
        if self.back or self.hold:
            tag = ("止め中 " if self.hold else "") + (f"↑{self.back}" if self.back else "")
            w = app.font_t.getlength(tag) + 8
            d.rounded_rectangle((x1 - w, y0, x1, y0 + 13), 4, fill=(60, 40, 20))
            d.text((x1 - w + 4, y0), tag, fill=WARN, font=app.font_t)


class Picker:
    def __init__(self):
        self.items, self.sel = [], 0

    def set(self, items):
        self.items = items
        self.sel = min(self.sel, max(0, len(items) - 1))

    def move(self, n):
        if self.items:
            self.sel = (self.sel + n) % len(self.items)

    def cur(self):
        return self.items[self.sel] if self.items else None

    def draw(self, app, d, y0, empty):
        if not self.items:
            for i, t in enumerate(empty):
                d.text((10, y0 + 6 + i * 16), t, fill=SUB if i else FG, font=app.font_s)
            return
        rh = 30
        first = max(0, self.sel - 3)
        for i, (name, sub, _) in enumerate(self.items[first:first + 4]):
            k = first + i
            y = y0 + i * rh
            on = k == self.sel
            d.rounded_rectangle((4, y, LCD_W - 4, y + rh - 3), 5, fill=ACC_DIM if on else (18, 21, 29),
                                outline=ACC if on else (40, 46, 60), width=2 if on else 1)
            d.text((12, y + 1), name, fill=FG, font=app.font_bs)
            app.fit(d, (12, y + 14), sub, LCD_W - 24, app.font_t, SUB)


# ================================================================ 画面の基本
class View:
    key = ""
    name = ""

    def __init__(self, app):
        self.app = app
        self.rec = None

    def enter(self):
        pass

    def leave(self):
        self.stop_rec()

    def tick(self):
        return False

    def on_key(self, kind, val):
        return None

    def draw(self, img, d):
        pass

    def status(self):
        return ""

    def help(self):
        return "ESC:戻る"

    # ---- ログ記録 (L)
    def toggle_rec(self):
        if self.rec:
            self.stop_rec()
            self.app.say("記録を止めました")
            return
        os.makedirs(LOGDIR, exist_ok=True)
        path = os.path.join(LOGDIR, f"{self.key}-{time.strftime('%Y%m%d-%H%M%S')}.log")
        self.rec = open(path, "a", encoding="utf-8", errors="replace")
        self.rec.write(f"# HEXA PROBE {VERSION} {self.name} {self.status()}\n")
        self.app.say("記録中: " + path.replace(os.path.expanduser("~"), "~"), 3)

    def log(self, text):
        if self.rec:
            t = time.time()
            self.rec.write(time.strftime("%H:%M:%S", time.localtime(t)) + f".{int(t * 1000) % 1000:03d} {text}\n")
            self.rec.flush()

    def stop_rec(self):
        if self.rec:
            self.rec.close()
            self.rec = None


# ================================================================ 1 SERIAL
BAUDS = [115200, 230400, 460800, 921600, 9600, 19200, 38400, 57600, 74880, 31250]


class SerialView(View):
    key, name = "serial", "SERIAL"

    def __init__(self, app):
        super().__init__(app)
        self.pick = Picker()
        self.reader = None
        self.box = LogBox()
        self.baud = 115200
        self.hexmode = False
        self.partial = b""
        self.hexrow = b""
        self.last_rx = 0.0
        self.nbytes = 0
        self.rate = collections.deque(maxlen=50)
        self.port = None

    def enter(self):
        self.pick.set(B.list_serial_ports())

    def leave(self):
        self.close()
        super().leave()

    def open(self, item):
        name, _, path = item
        try:
            self.reader = self.app.backend("SerialReader")(path, self.baud).start()
        except OSError as e:
            self.app.say(f"開けません: {e.strerror or e}", 4)
            return
        self.port = name
        self.box.clear()
        self.nbytes = 0
        self.partial = self.hexrow = b""
        self.box.add(f"--- {name} {self.baud}bps ---", ACC)
        self.log(f"open {name} {path} {self.baud}")

    def close(self):
        if self.reader:
            self.reader.stop()
            self.reader = None
            self.log("close")

    def feed(self, data, now):
        self.nbytes += len(data)
        self.rate.append((now, len(data)))
        self.last_rx = now
        if self.hexmode:
            self.hexrow += data
            while len(self.hexrow) >= 8:
                self.emit_hex(self.hexrow[:8])
                self.hexrow = self.hexrow[8:]
            return
        self.partial += data
        while b"\n" in self.partial:
            line, self.partial = self.partial.split(b"\n", 1)
            self.emit_text(line)
        if len(self.partial) > 400:
            self.emit_text(self.partial)
            self.partial = b""

    def emit_text(self, raw):
        t = raw.decode("utf-8", "replace").replace("\r", "")
        t = "".join(ch if ch.isprintable() else "." for ch in t)
        low = t.lower()
        col = REC if ("error" in low or "fail" in low or "panic" in low or "guru" in low) else \
            WARN if "warn" in low else FG
        self.box.add(t, col)
        self.log(t)

    def emit_hex(self, raw):
        hx = " ".join(f"{b:02X}" for b in raw)
        asc = "".join(chr(b) if 32 <= b < 127 else "." for b in raw)
        self.box.add(f"{hx:<24}  {asc}", CYAN)
        self.log(hx)

    def tick(self):
        if not self.reader:
            return False
        dirty = False
        for ev in self.reader.events():
            if ev[0] == "data":
                self.feed(ev[1], time.time())
                dirty = True
            elif ev[0] == "error":
                self.box.add("--- " + ev[1] + " ---", REC)
                self.app.say(ev[1], 3)
                self.close()
                return True
        if time.time() - self.last_rx > 0.35:           # 改行の来ない行も出す
            if self.partial:
                self.emit_text(self.partial)
                self.partial = b""
                dirty = True
            if self.hexrow:
                self.emit_hex(self.hexrow)
                self.hexrow = b""
                dirty = True
        return dirty

    def bps(self):
        now = time.time()
        n = sum(b for t, b in self.rate if now - t < 2)
        return n / 2

    def status(self):
        if not self.port:
            return "ポートを選ぶ"
        r = self.bps()
        rt = f"{r / 1000:.1f}kB/s" if r >= 1000 else f"{r:.0f}B/s"
        return f"{self.port} {self.baud} {'HEX' if self.hexmode else 'TXT'} {rt}"

    def help(self):
        if not self.port:
            return "↑↓:選ぶ ENTER:開く R:探し直す ESC:戻る"
        return "B:速度 H:HEX R:ESP32リセット SPC:止める ↑↓:遡る BS:消去 L:記録"

    def on_key(self, kind, val):
        if not self.port:
            if val == "ESC":
                return "back"
            if val in ("UP", "LEFT"):
                self.pick.move(-1)
            elif val in ("DOWN", "RIGHT", "TAB"):
                self.pick.move(1)
            elif val == "r":
                self.enter()
                self.app.say(f"{len(self.pick.items)}個見つかりました")
            elif val == "ENTER" and self.pick.cur():
                self.open(self.pick.cur())
            return None
        if val == "ESC":
            self.close()
            self.port = None
            self.enter()
        elif val == "b":
            self.baud = BAUDS[(BAUDS.index(self.baud) + 1) % len(BAUDS)] if self.baud in BAUDS else BAUDS[0]
            try:
                if self.reader:
                    self.reader.set_baud(self.baud)
                self.box.add(f"--- {self.baud}bps ---", ACC)
                self.log(f"baud {self.baud}")
            except OSError as e:
                self.app.say(f"速度を変えられません: {e}", 3)
        elif val == "h":
            self.hexmode = not self.hexmode
            self.partial = self.hexrow = b""
            self.box.add(f"--- {'HEX' if self.hexmode else 'テキスト'} 表示 ---", ACC)
        elif val == "r" and self.reader:
            try:
                self.reader.reset_esp32()
                self.box.add("--- リセット (RTS) ---", ACC)
                self.log("reset")
            except OSError as e:
                self.app.say(f"リセットできません: {e}", 3)
        elif val == "SPACE":
            self.app.say("止めました (SPACE で再開)" if self.box.toggle_hold() else "再開")
        elif val == "UP":
            self.box.scroll(3)
        elif val == "DOWN":
            self.box.scroll(-3)
        elif val == "BS":
            self.box.clear()
        elif val == "l":
            self.toggle_rec()
        return None

    def draw(self, img, d):
        if not self.port:
            d.text((6, BY0), "どのポートを見る?", fill=SUB, font=self.app.font_t)
            self.pick.draw(self.app, d, BY0 + 14, ["シリアルポートが見つかりません",
                                                   "USB シリアル (ESP32 など) を挿して R",
                                                   "Grove UART は /dev/serial0 として出ます"])
            return
        self.box.draw(self.app, d, 4, BY0, LCD_W - 4, BY1)


# ================================================================ 2 BLE
class BleView(View):
    key, name = "ble", "BLE"

    def __init__(self, app):
        super().__init__(app)
        self.worker = None
        self.devs = {}
        self.order = []
        self.sel = 0
        self.detail = None
        self.state = ""

    def enter(self):
        has, on = B.bt_state() if not self.app.sim else (True, True)
        if not has or not on:
            self.state = "Bluetooth が OFF です (HEXA POWER の 1 で ON に)" if has else "Bluetooth が見つかりません"
            return
        self.worker = self.app.backend("BleScanner")().start()
        self.state = "準備中…"

    def leave(self):
        if self.worker:
            self.worker.stop()
            self.worker = None
        super().leave()

    def tick(self):
        if not self.worker:
            return False
        dirty = False
        for ev in self.worker.events():
            dirty = True
            if ev[0] == "status":
                self.state = ev[1]
            elif ev[0] == "error":
                self.state = ev[1]
                self.app.say(ev[1], 4)
            elif ev[0] == "dev":
                _, addr, field, val = ev
                dv = self.devs.get(addr)
                if dv is None:
                    if field == "del":
                        continue
                    dv = self.devs[addr] = {"addr": addr, "name": "", "rssi": None, "mfr": "", "svc": "",
                                            "uuid": [], "tx": "", "other": [], "first": time.time()}
                    self.log(f"NEW {addr} {val}")
                dv["last"] = time.time()
                if field == "name" and val and val != dv["name"]:
                    if dv["name"]:
                        self.log(f"NAME {addr} {val}")
                    dv["name"] = val
                elif field == "rssi":
                    dv["rssi"] = val
                elif field in ("mfr", "svc", "tx"):
                    dv[field] = val
                elif field == "uuid" and val not in dv["uuid"]:
                    dv["uuid"].append(val)
                elif field == "other" and val not in dv["other"]:
                    dv["other"] = (dv["other"] + [val])[-6:]
        if dirty and not getattr(self, "hold", False):
            self.resort()
        sec = int(time.time())                       # 「◯秒前」と古い機器の色を毎秒更新
        if sec != getattr(self, "_sec", 0):
            self._sec = sec
            dirty = True
        return dirty

    def resort(self):
        cur = self.order[self.sel] if self.order and self.sel < len(self.order) else None
        self.order = sorted(self.devs, key=lambda a: -(self.devs[a]["rssi"] if self.devs[a]["rssi"] is not None
                                                       else -999))
        if cur in self.order:
            self.sel = self.order.index(cur)

    def status(self):
        return f"{len(self.devs)}台  {self.state}"

    def help(self):
        if self.detail:
            return "ESC:一覧へ  L:記録"
        return "↑↓:選ぶ ENTER:詳しく SPC:並び固定 BS:消去 L:記録 ESC:戻る"

    def on_key(self, kind, val):
        if self.detail:
            if val in ("ESC", "ENTER"):
                self.detail = None
            elif val == "l":
                self.toggle_rec()
            return None
        if val == "ESC":
            return "back"
        if val == "UP" and self.order:
            self.sel = (self.sel - 1) % len(self.order)
        elif val == "DOWN" and self.order:
            self.sel = (self.sel + 1) % len(self.order)
        elif val == "ENTER" and self.order:
            self.detail = self.order[self.sel]
        elif val == "SPACE":
            self.hold = not getattr(self, "hold", False)
            self.app.say("並びを固定しました" if self.hold else "電波の強い順に並べます")
        elif val == "BS":
            self.devs.clear()
            self.order = []
            self.sel = 0
        elif val == "l":
            self.toggle_rec()
        return None

    def draw(self, img, d):
        app = self.app
        if not self.worker and not self.devs:
            d.text((10, BY0 + 20), self.state, fill=WARN, font=app.font_s)
            return
        if self.detail:
            return self.draw_detail(d, self.devs.get(self.detail))
        if not self.order:
            d.text((10, BY0 + 20), "探しています…", fill=SUB, font=app.font_s)
            return
        rh = 14
        rows = (BY1 - BY0) // rh
        first = max(0, min(self.sel - rows // 2, len(self.order) - rows))
        now = time.time()
        for i, addr in enumerate(self.order[first:first + rows]):
            k = first + i
            dv = self.devs[addr]
            y = BY0 + i * rh
            old = now - dv.get("last", now) > 20
            if k == self.sel:
                d.rectangle((2, y - 1, LCD_W - 3, y + rh - 2), fill=ACC_DIM)
            r = dv["rssi"]
            col = NA if old else FG
            app.mtext(d, (4, y), f"{r:4d}" if r is not None else "   ?", ACC if r and r > -60 else col)
            lv = 0 if r is None else 4 if r > -55 else 3 if r > -67 else 2 if r > -80 else 1
            for j in range(4):
                h = 3 + j * 2
                d.rectangle((32 + j * 4, y + 10 - h, 34 + j * 4, y + 10),
                            fill=(ACC if j < lv else (40, 44, 56)) if not old else (40, 44, 56))
            name = dv["name"] or "(名前なし)"
            app.fit(d, (52, y - 1), name, 128, app.font_t, col if dv["name"] else SUB)
            app.fit(d, (184, y - 1), B.vendor_name(dv["mfr"]), 62, app.font_t, YEL if not old else NA)
            app.mtext(d, (250, y), addr[-8:], SUB if not old else NA)

    def draw_detail(self, d, dv):
        app = self.app
        if not dv:
            return
        d.text((6, BY0), dv["name"] or "(名前なし)", fill=ACC, font=app.font_bs)
        lines = [f"アドレス  {dv['addr']}",
                 f"電波      {dv['rssi']} dBm" + (f"   TxPower {dv['tx']}" if dv["tx"] else ""),
                 f"メーカー  {B.vendor_name(dv['mfr']) or '-'}  {dv['mfr']}",
                 f"見つけた  {ago(dv['first'])}   最後 {ago(dv.get('last', time.time()))}"]
        if dv["svc"]:
            lines.append(f"ServiceData {dv['svc']}")
        lines += [f"UUID {u}" for u in dv["uuid"][:3]]
        lines += dv["other"][:3]
        for i, t in enumerate(lines[:9]):
            app.fit(d, (6, BY0 + 18 + i * 12), t, LCD_W - 12, app.font_t, FG if i < 4 else SUB)


# ================================================================ 3 NFC
class NfcView(View):
    key, name = "nfc", "NFC"

    def __init__(self, app):
        super().__init__(app)
        self.worker = None
        self.hist = []
        self.sel = 0
        self.detail = None
        self.state = ""
        self.present = False

    def enter(self):
        rd = B.nfc_reader() if not self.app.sim else "RC-S380"
        if not rd:
            self.state = "リーダーがありません (RC-S380 を挿してね)"
            return
        self.worker = self.app.backend("NfcWorker")().start()
        self.state = f"{rd} を準備中…"

    def leave(self):
        if self.worker:
            self.worker.stop()
            self.worker = None
        super().leave()

    def tick(self):
        if not self.worker:
            return False
        dirty = False
        for ev in self.worker.events():
            dirty = True
            if ev[0] == "status":
                self.state = ev[1]
            elif ev[0] == "error":
                self.state = ev[1]
                self.app.say(ev[1], 4)
            elif ev[0] == "nfc":
                e = ev[1]
                if e.get("ev") == "ready":
                    self.state = "カードをかざしてね"
                elif e.get("ev") == "tag":
                    e["t"] = time.time()
                    self.hist.insert(0, e)
                    self.hist = self.hist[:50]
                    self.sel = 0
                    self.present = True
                    self.state = "読みました (離すと次へ)"
                    self.log(json.dumps({k: v for k, v in e.items() if k != "ev"}, ensure_ascii=False))
                elif e.get("ev") == "removed":
                    self.present = False
                    self.state = "カードをかざしてね"
                elif e.get("ev") == "error":
                    self.state = e.get("msg", "エラー")
                    self.app.say(self.state, 4)
        return dirty

    def status(self):
        return f"{len(self.hist)}枚  {'●' if self.present else ''}"

    def help(self):
        if self.detail is not None:
            return "↑↓:スクロール ESC:一覧へ L:記録"
        return "↑↓:選ぶ ENTER:中身 BS:消去 L:記録 ESC:戻る"

    def detail_lines(self, e):
        ls = [(f"種類   {e.get('type', '')}  {e.get('product', '')}", FG), (f"ID     {e.get('id', '')}", ACC)]
        if e.get("pmm"):
            ls.append((f"PMm    {e['pmm']}   System {e.get('sys', '')}", FG))
        if e.get("ndef_info"):
            ls.append((f"NDEF   {e['ndef_info']}", YEL))
        for r in e.get("ndef", []):
            ls.append((f"  {r.get('type', '')}", YEL))
            ls.append((f"  {r.get('text', '')}", FG))
        if e.get("dump"):
            ls.append(("--- ダンプ ---", SUB))
            ls += [(x, CYAN) for x in e["dump"]]
        return ls

    def on_key(self, kind, val):
        if self.detail is not None:
            if val in ("ESC", "ENTER"):
                self.detail = None
            elif val == "UP":
                self.detail.scroll(3)
            elif val == "DOWN":
                self.detail.scroll(-3)
            elif val == "l":
                self.toggle_rec()
            return None
        if val == "ESC":
            return "back"
        if val == "UP" and self.hist:
            self.sel = (self.sel - 1) % len(self.hist)
        elif val == "DOWN" and self.hist:
            self.sel = (self.sel + 1) % len(self.hist)
        elif val == "ENTER" and self.hist:
            box = LogBox()
            for t, c in self.detail_lines(self.hist[self.sel]):
                box.add(t, c)
            box.back = max(0, len(box.lines) - 10)            # 先頭から見せる
            self.detail = box
        elif val == "BS":
            self.hist, self.sel = [], 0
        elif val == "l":
            self.toggle_rec()
        return None

    def draw(self, img, d):
        app = self.app
        if self.detail is not None:
            self.detail.draw(app, d, 4, BY0, LCD_W - 4, BY1)
            return
        # 上: いちばん新しいカード
        d.rounded_rectangle((4, BY0, LCD_W - 4, BY0 + 50), 6, fill=(22, 18, 34) if self.present else (18, 21, 29),
                            outline=ACC if self.present else (40, 46, 60), width=2 if self.present else 1)
        if self.hist:
            e = self.hist[0]
            app.fit(d, (12, BY0 + 3), f"{e.get('product') or e.get('type')}", LCD_W - 30, app.font_bs, FG)
            app.mtext(d, (12, BY0 + 19), e.get("id", ""), ACC, big=True)
            nd = e.get("ndef") or []
            sub = nd[0]["text"] if nd else e.get("type", "")
            app.fit(d, (12, BY0 + 35), sub, LCD_W - 30, app.font_t, YEL if nd else SUB)
        else:
            d.text((12, BY0 + 8), self.state, fill=FG if self.worker else WARN, font=app.font_s)
            d.text((12, BY0 + 28), "Suica・NTAG・Mifare・電子ペーパーの札など", fill=SUB, font=app.font_t)
        d.text((8, BY0 + 53), self.state if self.hist else "", fill=SUB, font=app.font_t)
        y0 = BY0 + 67
        rh = 13
        rows = (BY1 - y0) // rh
        first = max(0, self.sel - rows + 1)
        for i, e in enumerate(self.hist[first:first + rows]):
            k = first + i
            y = y0 + i * rh
            if k == self.sel:
                d.rectangle((2, y - 1, LCD_W - 3, y + rh - 2), fill=ACC_DIM)
            app.mtext(d, (6, y), time.strftime("%H:%M:%S", time.localtime(e["t"])), SUB)
            app.fit(d, (64, y - 1), e.get("product") or e.get("type", ""), 130, app.font_t, FG)
            app.mtext(d, (200, y), e.get("id", "")[:18], CYAN)


# ================================================================ 4 MIDI
class MidiView(View):
    key, name = "midi", "MIDI"
    KIND_COL = {"on": ACC, "off": SUB, "cc": YEL, "pb": CYAN, "pc": (120, 230, 150), "sys": WARN, "rt": SUB}

    def __init__(self, app):
        super().__init__(app)
        self.pick = Picker()
        self.reader = None
        self.src = None
        self.box = LogBox()
        self.held = set()
        self.clock = collections.deque(maxlen=48)
        self.n_clock = self.n_as = self.n_msg = 0
        self.show_rt = False

    def enter(self):
        self.pick.set(B.list_midi_sources())

    def leave(self):
        self.close()
        super().leave()

    def open(self, item):
        try:
            self.reader = self.app.backend("MidiReader")(item[2]).start()
        except OSError as e:
            self.app.say(f"開けません: {e.strerror or e}", 4)
            return
        self.src = item[0]
        self.box.clear()
        self.held.clear()
        self.box.add(f"--- {item[0]}  {item[1]} ---", ACC)
        self.log(f"open {item[0]} {item[2]}")

    def close(self):
        if self.reader:
            self.reader.stop()
            self.reader = None

    def tick(self):
        if not self.reader:
            return False
        dirty = False
        for ev in self.reader.events():
            if ev[0] == "error":
                self.box.add("--- " + ev[1] + " ---", REC)
                self.close()
                return True
            if ev[0] != "msg":
                continue
            m = ev[1]
            s = m[0]
            if s == 0xF8:
                self.n_clock += 1
                self.clock.append(time.time())
                if not self.show_rt:
                    continue
            if s == 0xFE:
                self.n_as += 1
                if not self.show_rt:
                    continue
            self.n_msg += 1
            hi = s & 0xF0
            if hi == 0x90 and len(m) > 2 and m[2] > 0:
                self.held.add(m[1])
            elif hi in (0x80, 0x90) and len(m) > 1:
                self.held.discard(m[1])
            elif hi == 0xB0 and len(m) > 1 and m[1] in (120, 123):
                self.held.clear()
            text, kind = B.describe_midi(m)
            self.box.add(text, self.KIND_COL.get(kind, FG))
            self.log(" ".join(f"{b:02X}" for b in m) + "  " + text)
            dirty = True
        return dirty

    def bpm(self):
        c = [t for t in self.clock if time.time() - t < 2]
        if len(c) < 6:
            return None
        return 60 / ((c[-1] - c[0]) / (len(c) - 1) * 24)

    def status(self):
        if not self.src:
            return "入力を選ぶ"
        b = self.bpm()
        return f"{self.src}  {self.n_msg}個" + (f"  ♩{b:.1f}" if b else "")

    def help(self):
        if not self.src:
            return "↑↓:選ぶ ENTER:開く R:探し直す ESC:戻る"
        return "T:Clock表示 SPC:止める ↑↓:遡る BS:消去 L:記録 ESC:戻る"

    def on_key(self, kind, val):
        if not self.src:
            if val == "ESC":
                return "back"
            if val in ("UP", "LEFT"):
                self.pick.move(-1)
            elif val in ("DOWN", "RIGHT", "TAB"):
                self.pick.move(1)
            elif val == "r":
                self.enter()
            elif val == "ENTER" and self.pick.cur():
                self.open(self.pick.cur())
            return None
        if val == "ESC":
            self.close()
            self.src = None
            self.enter()
        elif val == "t":
            self.show_rt = not self.show_rt
            self.app.say("Clock / ActiveSense も出します" if self.show_rt else "Clock は数えるだけにします")
        elif val == "SPACE":
            self.app.say("止めました (SPACE で再開)" if self.box.toggle_hold() else "再開")
        elif val == "UP":
            self.box.scroll(3)
        elif val == "DOWN":
            self.box.scroll(-3)
        elif val == "BS":
            self.box.clear()
            self.held.clear()
        elif val == "l":
            self.toggle_rec()
        return None

    def draw(self, img, d):
        app = self.app
        if not self.src:
            d.text((6, BY0), "どの入力を見る?", fill=SUB, font=app.font_t)
            self.pick.draw(app, d, BY0 + 14, ["MIDI の入力が見つかりません", "USB MIDI 機器を挿して R"])
            return
        # 88鍵 (A0〜C8) の帯。鳴っている音が光る
        x0, y0, w = 4, BY0, LCD_W - 8
        white = [n for n in range(21, 109) if n % 12 not in (1, 3, 6, 8, 10)]
        kw = w / len(white)
        for i, n in enumerate(white):
            x = x0 + i * kw
            d.rectangle((x, y0, x + kw - 1, y0 + 16), fill=ACC if n in self.held else (200, 204, 214))
        for i, n in enumerate(white):
            if (n + 1) % 12 in (1, 3, 6, 8, 10) and n + 1 < 109:
                x = x0 + (i + 1) * kw - kw * 0.3
                d.rectangle((x, y0, x + kw * 0.6, y0 + 9), fill=ACC if n + 1 in self.held else (30, 32, 40))
        held = " ".join(B.note_name(n) for n in sorted(self.held)[:8])
        d.text((6, y0 + 18), f"鳴っている音: {held or '-'}", fill=FG if held else SUB, font=app.font_t)
        rt = f"Clock {self.n_clock}  AS {self.n_as}"
        d.text((LCD_W - 6 - app.font_t.getlength(rt), y0 + 18), rt, fill=SUB, font=app.font_t)
        self.box.draw(app, d, 4, y0 + 32, LCD_W - 4, BY1)


# ================================================================ 5 I2C
class I2cView(View):
    key, name = "i2c", "I2C"

    def __init__(self, app):
        super().__init__(app)
        self.buses = []
        self.bus = None
        self.worker = None
        self.found = {}
        self.base = None
        self.cur = 0x44
        self.err = ""
        self.scans = 0
        self.grove = None
        self.grove_orig = None
        self.grove_changed = False

    def enter(self):
        self.buses = B.list_i2c_buses() if not self.app.sim else [1]
        if not self.buses:
            self.err = "I2C バスがありません (raspi-config で I2C を有効に)"
            return
        self.bus = 1 if 1 in self.buses else self.buses[0]
        if not self.app.sim:
            self.grove, self.grove_orig = B.grove_mode()
        else:
            self.grove = "I2C"
        self.start()

    def start(self):
        if self.worker:
            self.worker.stop()
        self.found, self.scans, self.err = {}, 0, ""
        self.base = self.load_base()
        self.worker = self.app.backend("I2cScanner")(self.bus).start()

    def leave(self):
        if self.worker:
            self.worker.stop()
            self.worker = None
        if self.grove_changed and self.grove_orig:
            B.restore_grove(self.grove_orig)               # Grove を元 (UART など) に戻す
            self.grove_changed = False
        super().leave()

    def base_path(self):
        return os.path.join(CFGDIR, f"i2c-base-{self.bus}.json")

    def load_base(self):
        if self.app.sim:
            return {0x34, 0x55, 0x10, 0x51, 0x68, 0x43}
        try:
            return set(json.load(open(self.base_path())))
        except (OSError, ValueError):
            return None

    def tick(self):
        if not self.worker:
            return False
        dirty = False
        for ev in self.worker.events():
            dirty = True
            if ev[0] == "error":
                self.err = ev[1]
            elif ev[0] == "scan" and ev[1] == self.bus:
                new = ev[2]
                if self.scans:
                    for a in sorted(set(new) - set(self.found)):
                        self.log(f"+0x{a:02X}  {B.I2C_HINTS.get(a, '')}")
                        if self.base is not None and a not in self.base:
                            self.app.say(f"0x{a:02X} が見つかりました  {B.I2C_HINTS.get(a, '')}", 3)
                            self.cur = a
                    for a in sorted(set(self.found) - set(new)):
                        self.log(f"-0x{a:02X}")
                else:
                    self.log("scan i2c-%d: %s" % (self.bus, " ".join(f"{a:02X}" for a in sorted(new))))
                self.found = new
                self.scans += 1
                self.err = ""
        return dirty

    def status(self):
        auto = "自動" if (self.worker and self.worker.auto) else "手動"
        return f"i2c-{self.bus}  {len(self.found)}個  {auto}" if self.bus is not None else ""

    def help(self):
        return "方向:選ぶ B:本体を記録 G:Grove切替 TAB:バス SPC:自動 R:再 L:記録"

    def on_key(self, kind, val):
        if val == "ESC":
            return "back"
        if not self.worker:
            return None
        if val == "LEFT":
            self.cur = max(0x08, self.cur - 1)
        elif val == "RIGHT":
            self.cur = min(0x77, self.cur + 1)
        elif val == "UP":
            self.cur = self.cur - 16 if self.cur - 16 >= 0x08 else self.cur
        elif val == "DOWN":
            self.cur = self.cur + 16 if self.cur + 16 <= 0x77 else self.cur
        elif val == "b":
            self.base = set(self.found)
            if not self.app.sim:
                os.makedirs(CFGDIR, exist_ok=True)
                json.dump(sorted(self.base), open(self.base_path(), "w"))
            self.app.say(f"今の {len(self.base)}個を「本体」として記録。挿した物が NEW で光ります", 4)
        elif val == "g":
            self.toggle_grove()
        elif val == "TAB" and len(self.buses) > 1:
            self.bus = self.buses[(self.buses.index(self.bus) + 1) % len(self.buses)]
            self.start()
        elif val == "SPACE":
            self.worker.auto = not self.worker.auto
            self.worker.rescan()
            self.app.say("2秒ごとに探します" if self.worker.auto else "R を押した時だけ探します")
        elif val == "r":
            self.worker.rescan()
        elif val == "l":
            self.toggle_rec()
        return None

    def toggle_grove(self):
        if self.grove is None:
            self.app.say("Grove の切替が読めません (pinctrl)", 3)
            return
        to = "UART" if self.grove == "I2C" else "I2C"
        if self.app.sim or B.set_grove_mode(to):
            self.grove = to
            self.grove_changed = True
            self.worker.rescan()
            self.app.say(f"Grove を {to} にしました (抜けると元に戻します)", 3)
        else:
            self.app.say("切り替えられません (gpio グループ / pinctrl)", 3)

    def draw(self, img, d):
        app = self.app
        if self.bus is None:
            d.text((10, BY0 + 20), self.err, fill=WARN, font=app.font_s)
            return
        cw, ch, x0, y0 = 18, 11, 22, BY0 + 11
        for c in range(16):
            app.mtext(d, (x0 + c * cw + 5, BY0), f"{c:X}", SUB)
        for r in range(8):
            app.mtext(d, (2, y0 + r * ch), f"{r:X}0", SUB)
            for c in range(16):
                a = r * 16 + c
                x, y = x0 + c * cw, y0 + r * ch
                if a < 0x08 or a > 0x77:
                    continue
                st = self.found.get(a)
                new = st and self.base is not None and a not in self.base
                gone = not st and self.base is not None and a in self.base and self.scans
                if new:
                    d.rectangle((x, y, x + cw - 2, y + ch - 1), fill=ACC)
                    tc = (10, 10, 20)
                elif st == "UU":
                    d.rectangle((x, y, x + cw - 2, y + ch - 1), fill=(40, 50, 70))
                    tc = (160, 180, 210)
                elif st:
                    d.rectangle((x, y, x + cw - 2, y + ch - 1), fill=(60, 64, 80))
                    tc = FG
                else:
                    tc = WARN if gone else (52, 56, 70)
                txt = ("UU" if st == "UU" else f"{a:02X}") if st else ("--" if gone else "·")
                app.mtext(d, (x + 2 if st or gone else x + 6, y - 1), txt, tc)
                if a == self.cur:
                    d.rectangle((x - 1, y - 1, x + cw - 1, y + ch), outline=YEL)
        a = self.cur
        st = self.found.get(a)
        word = ("NEW " if st and self.base is not None and a not in self.base else "") + \
               ({"ok": "応答あり", "UU": "ドライバ使用中"}.get(st, "応答なし"))
        hint = B.I2C_HINTS.get(a, "")
        yy = y0 + 8 * ch + 2
        app.fit(d, (4, yy), f"0x{a:02X} {word}" + (f"  候補: {hint}" if hint else ""), LCD_W - 8, app.font_t,
                ACC if st else SUB)
        if self.err:
            app.fit(d, (4, yy + 12), self.err, LCD_W - 8, app.font_t, WARN)
        else:
            nb = "未記録 (B で記録)" if self.base is None else f"本体 {len(self.base)}"
            g = f"Grove: {self.grove or '?'}" + (" (G で I2C)" if self.grove == "UART" else "")
            app.fit(d, (4, yy + 12), f"{nb}  今 {len(self.found)}  {g}  電源: 設定>ExtPort", LCD_W - 8,
                    app.font_t, SUB)


# ================================================================ 6 IR
class IrView(View):
    key, name = "ir", "IR"

    def __init__(self, app):
        super().__init__(app)
        self.worker = None
        self.hist = []
        self.sel = 0
        self.detail = None
        self.dev = None

    def enter(self):
        self.dev = B.ir_device() if not self.app.sim else "/dev/lirc0"
        if not self.dev:
            return
        try:
            self.worker = self.app.backend("IrReader")(self.dev).start()
        except OSError as e:
            self.app.say(f"開けません: {e.strerror or e}", 4)

    def leave(self):
        if self.worker:
            self.worker.stop()
            self.worker = None
        super().leave()

    def tick(self):
        if not self.worker:
            return False
        dirty = False
        for ev in self.worker.events():
            dirty = True
            if ev[0] == "error":
                self.app.say(ev[1], 4)
                continue
            if ev[0] != "frame":
                continue
            durs, now = ev[1], time.time()
            proto, text, key = B.decode_ir(durs)
            top = self.hist[0] if self.hist else None
            if top and now - top["t"] < 0.6 and (key == top["key"] or
                                                 (text == "リピート" and proto == top["proto"])):
                top["n"] += 1
                top["t"] = now
                continue
            self.hist.insert(0, {"t": now, "t0": now, "proto": proto, "text": text, "key": key, "n": 1,
                                 "durs": durs})
            self.hist = self.hist[:60]
            self.sel = 0
            self.log(f"{proto}  {text}  raw {' '.join(map(str, durs))}")
        return dirty

    def status(self):
        return f"{len(self.hist)}件" if self.dev else "受信機なし"

    def help(self):
        if self.detail is not None:
            return "↑↓:スクロール ESC:一覧へ L:記録"
        return "↑↓:選ぶ ENTER:生データ BS:消去 L:記録 ESC:戻る"

    def on_key(self, kind, val):
        if self.detail is not None:
            if val in ("ESC", "ENTER"):
                self.detail = None
            elif val == "UP":
                self.detail.scroll(3)
            elif val == "DOWN":
                self.detail.scroll(-3)
            elif val == "l":
                self.toggle_rec()
            return None
        if val == "ESC":
            return "back"
        if val == "UP" and self.hist:
            self.sel = (self.sel - 1) % len(self.hist)
        elif val == "DOWN" and self.hist:
            self.sel = (self.sel + 1) % len(self.hist)
        elif val == "ENTER" and self.hist:
            e = self.hist[self.sel]
            box = LogBox()
            box.add(f"{e['proto']}  {e['text']}", ACC)
            box.add(f"区間 {len(e['durs'])}  合計 {sum(e['durs']) / 1000:.1f}ms  ×{e['n']}", SUB)
            row = []
            for i, v in enumerate(e["durs"]):
                row.append(("P" if i % 2 == 0 else "S") + str(v))
                if len(row) == 6:
                    box.add(" ".join(row), CYAN if i % 2 else FG)
                    row = []
            if row:
                box.add(" ".join(row), CYAN)
            box.back = max(0, len(box.lines) - 10)
            self.detail = box
        elif val == "BS":
            self.hist, self.sel = [], 0
        elif val == "l":
            self.toggle_rec()
        return None

    def draw(self, img, d):
        app = self.app
        if not self.dev:
            for i, t in enumerate(["赤外線の受信機がまだ有効になっていません", "",
                                   "1. sh install.sh --ir   (GPIO13 の受信を有効化)",
                                   "2. sudo reboot", "3. もう一度ここを開く"]):
                d.text((8, BY0 + 6 + i * 16), t, fill=WARN if i == 0 else FG, font=app.font_s if i == 0 else app.font_t)
            return
        if self.detail is not None:
            self.detail.draw(app, d, 4, BY0, LCD_W - 4, BY1)
            return
        d.rounded_rectangle((4, BY0, LCD_W - 4, BY0 + 38), 6, fill=(18, 21, 29), outline=(40, 46, 60))
        if self.hist:
            e = self.hist[0]
            lit = time.time() - e["t"] < 0.4
            d.text((12, BY0 + 2), e["proto"], fill=ACC if lit else FG, font=app.font_bs)
            if e["n"] > 1:
                d.text((LCD_W - 50, BY0 + 2), f"×{e['n']}", fill=YEL, font=app.font_bs)
            app.fit(d, (12, BY0 + 19), e["text"], LCD_W - 30, app.font_s, ACC)
        else:
            d.text((12, BY0 + 4), "リモコンを向けてボタンを押してね", fill=FG, font=app.font_s)
            d.text((12, BY0 + 21), f"受信: {self.dev}", fill=SUB, font=app.font_t)
        y0 = BY0 + 43
        rh = 13
        rows = (BY1 - y0) // rh
        first = max(0, self.sel - rows + 1)
        for i, e in enumerate(self.hist[first:first + rows]):
            k = first + i
            y = y0 + i * rh
            if k == self.sel:
                d.rectangle((2, y - 1, LCD_W - 3, y + rh - 2), fill=ACC_DIM)
            app.mtext(d, (6, y), time.strftime("%H:%M:%S", time.localtime(e["t0"])), SUB)
            d.text((64, y - 1), e["proto"], fill=FG, font=app.font_t)
            app.fit(d, (112, y - 1), e["text"] + (f"  ×{e['n']}" if e["n"] > 1 else ""), LCD_W - 118,
                    app.font_t, CYAN)


VIEWS = {"serial": SerialView, "ble": BleView, "nfc": NfcView, "midi": MidiView, "i2c": I2cView, "ir": IrView}


# ================================================================ app
class App:
    HEX_R = 25
    POS = [(27, 48), (74, 48), (121, 48), (50, 86), (97, 86), (144, 86)]

    def __init__(self, fb, keys, sim=False, backends=None):
        self.fb, self.keys, self.sim = fb, keys, sim
        self.backends = backends or {}
        self.font = find_font(14)
        self.font_s = find_font(12)
        self.font_t = find_font(10)
        self.font_bs = find_font(11, bold=True)
        self.font_big = find_font(16, bold=True)
        self.font_hex = find_font(11, bold=True)
        self.mono = find_mono(10)
        self.mono_big = find_mono(13)
        self.honey = honeycomb_bg()
        self.sel = 0
        self.view = None
        self.toast = ("", 0.0)
        self.det = {}
        self.next_det = 0.0
        self._home = None
        self._home_key = None

    def backend(self, name):
        return self.backends.get(name) or getattr(B, name)

    def say(self, msg, sec=2.5):
        self.toast = (msg, time.time() + sec)

    # ---- 文字
    def mtext(self, d, xy, text, col, big=False):
        """データ用: ASCII は等幅、日本語が混ざる行は日本語フォント"""
        if any(ord(ch) > 126 for ch in text):
            d.text((xy[0], xy[1] - 1), text, fill=col, font=self.font_t)
        else:
            d.text(xy, text, fill=col, font=self.mono_big if big else self.mono)

    def fit(self, d, xy, text, w, font, col):
        text = str(text)
        if font.getlength(text) > w:
            while text and font.getlength(text + "…") > w:
                text = text[:-1]
            text += "…"
        d.text(xy, text, fill=col, font=font)

    # ---- ホーム
    def detect(self):
        if time.time() < self.next_det:
            return False
        self.next_det = time.time() + 3
        new = self.backends["detect_all"]() if "detect_all" in self.backends else B.detect_all()
        changed = new != self.det
        self.det = new
        return changed

    def draw_home(self):
        key = (self.sel, json.dumps(self.det, ensure_ascii=False, sort_keys=True))
        if self._home_key == key:
            return self._home.copy()
        img = self.honey.copy()
        d = ImageDraw.Draw(img)
        for i, (k, name, _) in enumerate(MODS):
            cx, cy = self.POS[i]
            r = self.HEX_R
            on = i == self.sel
            pts = hexpts(cx, cy, r)
            d.polygon(pts, fill=(30, 22, 46) if on else (18, 21, 29))
            if on:
                glow_hex(img, cx, cy, r, ACC)
                d = ImageDraw.Draw(img)
            else:
                d.polygon(pts, outline=(44, 50, 64), width=2)
            lab, ok, _ = self.det.get(k, ("…", False, []))
            f = self.font_hex
            d.text((cx - f.getlength(name) / 2, cy - 15), name, fill=FG if on else SUB, font=f)
            ft = self.font_t
            lab = lab if ft.getlength(lab) < 2 * r - 6 else lab[:5]
            d.text((cx - ft.getlength(lab) / 2, cy + 1), lab, fill=ACC if ok else NA, font=ft)
        # 右: 選んだ機能の説明と準備状況
        k, name, desc = MODS[self.sel]
        x0 = 176
        d.rounded_rectangle((x0 - 6, TOP_H + 3, LCD_W - 3, LCD_H - BOT_H - 3), 6, fill=(16, 19, 27),
                            outline=(34, 40, 52))
        d.text((x0, TOP_H + 5), f"{self.sel + 1} {name}", fill=ACC, font=self.font_big)
        self.fit(d, (x0, TOP_H + 26), desc, LCD_W - x0 - 8, self.font_t, FG)
        _, ok, lines = self.det.get(k, ("", False, []))
        for i, t in enumerate(lines[:5]):
            self.fit(d, (x0, TOP_H + 44 + i * 14), t, LCD_W - x0 - 8, self.font_t, SUB if ok else WARN)
        # 下: ロゴ的な一言
        d.text((6, 118), "なんでも覗く", fill=FG, font=self.font_bs)
        d.text((6, 133), f"ログ: ~/hexaprobe-logs   v{VERSION}", fill=(90, 98, 115), font=self.font_t)
        self._home, self._home_key = img, key
        return img.copy()

    def move(self, act):
        row, col = divmod(self.sel, 3)
        if act == "LEFT":
            col = (col - 1) % 3
        elif act == "RIGHT":
            col = (col + 1) % 3
        elif act in ("UP", "DOWN"):
            row = 1 - row
        elif act == "TAB":
            self.sel = (self.sel + 1) % 6
            return
        self.sel = row * 3 + col

    # ---- 画面全体
    def frame(self):
        if self.view is None:
            img = self.draw_home()
        else:
            img = Image.new("RGB", (LCD_W, LCD_H), BG)
            self.view.draw(img, ImageDraw.Draw(img))
        return self.chrome(img)

    def chrome(self, img):
        d = ImageDraw.Draw(img)
        d.rectangle((0, 0, LCD_W, TOP_H - 1), fill=(0, 0, 0))
        title = "HEXA PROBE" if self.view is None else f"PROBE › {self.view.name}"
        d.text((5, 1), title, fill=ACC, font=self.font_bs)
        x = 5 + self.font_bs.getlength(title) + 8
        if self.view is not None and self.view.rec:
            d.ellipse((x, 5, x + 7, 12), fill=REC)
            d.text((x + 10, 3), "REC", fill=REC, font=self.font_t)
            x += 36
        st = self.view.status() if self.view else "ENTER で開く"
        self.fit(d, (max(x, LCD_W - 4 - self.font_t.getlength(st)), 3), st, LCD_W - 4 - x, self.font_t, SUB)
        d.rectangle((0, LCD_H - BOT_H, LCD_W, LCD_H), fill=(0, 0, 0))
        hp = self.view.help() if self.view else "FXZC:選ぶ 1-6:直接 ENTER:開く ESC:終了"
        self.fit(d, (4, LCD_H - BOT_H + 2), hp, LCD_W - 8, self.font_t, (210, 210, 210))
        msg, until = self.toast
        if msg and time.time() < until:
            f = self.font_t
            w = min(int(f.getlength(msg)) + 16, LCD_W - 8)
            yy = LCD_H - BOT_H - 20
            d.rounded_rectangle(((LCD_W - w) // 2, yy, (LCD_W + w) // 2, yy + 17), 7, fill=(44, 28, 80),
                                outline=ACC)
            self.fit(d, ((LCD_W - w) // 2 + 8, yy + 2), msg, w - 14, f, (255, 255, 255))
        return img

    def confirm_quit(self, base):
        img = Image.blend(base, Image.new("RGB", base.size), 0.65)
        d = ImageDraw.Draw(img)
        x0, y0, x1, y1 = 40, 42, LCD_W - 40, LCD_H - 38
        d.rounded_rectangle((x0, y0, x1, y1), 8, fill=(26, 30, 38), outline=ACC, width=2)
        for i, (txt, font, col) in enumerate([("HEXA PROBE を終了しますか?", self.font, FG),
                                              ("ログは ~/hexaprobe-logs に残ります", self.font_t, SUB),
                                              ("ENTER: 終了    ESC: 戻る", self.font_s, ACC)]):
            d.text(((LCD_W - font.getlength(txt)) / 2, y0 + 12 + i * 22), txt, fill=col, font=font)
        self.fb.show(img)
        self.keys.flush(0.2)
        while True:
            for kind, val in self.keys.poll(0.5):
                self.keys.flush(0.1)
                return kind == "ACT" and val == "ENTER"

    def open_view(self, i):
        self.sel = i
        self.view = VIEWS[MODS[i][0]](self)
        try:
            self.view.enter()
        except Exception as e:
            self.say(f"開けません: {e}", 4)

    def close_view(self):
        try:
            self.view.leave()
        except Exception as e:
            print("leave failed:", e, flush=True)
        self.view = None
        self.next_det = 0

    def run(self):
        self.keys.flush(0.4)
        dirty, last_draw = True, 0.0
        try:
            while True:
                if self.view is None:
                    dirty |= self.detect()
                else:
                    try:
                        dirty |= bool(self.view.tick())
                    except Exception as e:
                        import traceback
                        traceback.print_exc()
                        self.say(f"エラー: {e}", 4)
                now = time.time()
                toast_on = self.toast[1] > now - 0.5
                if (dirty or toast_on) and now - last_draw > 0.12:
                    self.fb.show(self.frame())
                    last_draw, dirty = now, False
                for kind, val in self.keys.poll(0.05):
                    dirty = True
                    if self.view is not None:
                        if self.view.on_key(kind, val) == "back":
                            self.close_view()
                        continue
                    if val == "ESC":
                        if self.confirm_quit(self.frame()):
                            return "ESC"
                    elif val == "ENTER":
                        self.open_view(self.sel)
                    elif kind == "ACT":
                        self.move(val)
                    elif kind == "CHAR" and val in "123456":
                        self.sel = int(val) - 1
                        self.open_view(self.sel)
                    elif kind == "CHAR" and val == "q":
                        return "q"
        finally:
            if self.view is not None:
                self.close_view()


# ================================================================ launcher (HEXA CLIP / POWER と同じ)
def launcher_pids():
    pids = []
    for d in os.listdir("/proc"):
        if not d.isdigit():
            continue
        try:
            cmd = open(f"/proc/{d}/cmdline", "rb").read()
        except OSError:
            continue
        if b"M5CardputerZero-APPLaunch" in cmd:
            pids.append(int(d))
    return pids


def signal_launcher(sig):
    for pid in launcher_pids():
        try:
            os.kill(pid, sig)
        except ProcessLookupError:
            pass


# ================================================================ PC 用シミュレーション
class SimFB:
    def __init__(self, outdir):
        self.outdir, self.img = outdir, None
        os.makedirs(outdir, exist_ok=True)

    def show(self, img):
        self.img = img.copy()

    def snap(self, name):
        self.img.resize((LCD_W * 2, LCD_H * 2), Image.NEAREST).save(os.path.join(self.outdir, name))

    def clear(self):
        pass


class SimKeys:
    """台本どおりにキーを押す: [(待つ秒, ('ACT','ENTER')) or (待つ秒, ('SNAP','name.png'))]"""

    def __init__(self, script, fb, app_ref):
        self.script, self.fb, self.t, self.app_ref = list(script), fb, time.time(), app_ref

    def poll(self, timeout=0.0):
        time.sleep(min(timeout, 0.05))
        out = []
        while self.script and time.time() - self.t >= self.script[0][0]:
            _, ev = self.script.pop(0)
            self.t = time.time()
            if ev[0] == "SNAP":
                app = self.app_ref[0]
                self.fb.show(app.frame())             # 最新の状態で撮る
                self.fb.snap(ev[1])
            else:
                out.append(ev)
                break
        if not self.script and not out:
            out.append(("CHAR", "q"))
        return out

    def flush(self, sec=0):
        pass


def sim_detect():
    return {"serial": ("2個", True, ["ttyUSB0  CP2102N USB to UART  10c4:ea60",
                                     "Grove UART  serial0 → ttyS0"]),
            "ble": ("OK", True, ["ENTER でスキャン開始", "電波の強い順に並びます"]),
            "nfc": ("RC-S380", True, ["リーダー: RC-S380", "nfcpy: ~/nfc"]),
            "midi": ("2系統", True, ["UMONE  USB MIDI  midiC1D0", "Grove UART  Unit MIDI (31250bps)"]),
            "i2c": ("bus1", True, ["バス: i2c-1", "Grove: UART  (画面の G で I2C に)", "Grove の電源は 設定 > ExtPort"]),
            "ir": ("未設定", False, ["受信機がまだ有効になっていません", "sh install.sh --ir → 再起動"])}


def run_sim(outdir):
    B.list_serial_ports = lambda: [("ttyUSB0", "CP2102N USB to UART  10c4:ea60", "/dev/ttyUSB0"),
                                   ("Grove UART", "serial0 → ttyS0  (Grove の黄=TX 白=RX)", "/dev/serial0")]
    B.list_midi_sources = lambda: [("UMONE", "USB MIDI  midiC1D0", ("raw", "/dev/snd/midiC1D0")),
                                   ("Grove UART", "Unit MIDI の MIDI IN など (31250bps)", ("uart", "/dev/serial0"))]
    backends = {"SerialReader": B.FakeSerial, "BleScanner": B.FakeBle, "NfcWorker": B.FakeNfc,
                "MidiReader": B.FakeMidi, "I2cScanner": B.FakeI2c, "IrReader": B.FakeIr, "detect_all": sim_detect}
    fb = SimFB(outdir)
    A, C, S = (lambda v: ("ACT", v)), (lambda v: ("CHAR", v)), (lambda n: ("SNAP", n))
    script = [(0.6, S("01_home.png")), (0.1, A("RIGHT")), (0.3, S("02_home_ble.png")),
              # SERIAL
              (0.1, C("1")), (0.3, S("03_serial_pick.png")), (0.1, A("ENTER")), (2.6, S("04_serial.png")),
              (0.1, C("h")), (0.6, S("05_serial_hex.png")), (0.1, A("ESC")), (0.1, A("ESC")),
              # BLE
              (0.2, C("2")), (2.0, S("06_ble.png")), (0.1, A("ENTER")), (0.3, S("07_ble_detail.png")),
              (0.1, A("ESC")), (0.1, A("ESC")),
              # NFC
              (0.2, C("3")), (1.0, S("08_nfc.png")), (1.4, S("09_nfc2.png")), (0.1, A("DOWN")), (0.1, A("ENTER")),
              (0.3, S("10_nfc_detail.png")), (0.1, A("ESC")), (0.1, A("ESC")),
              # MIDI
              (0.2, C("4")), (0.2, A("ENTER")), (0.95, S("11_midi.png")), (1.0, S("12_midi_end.png")),
              (0.1, A("ESC")), (0.1, A("ESC")),
              # I2C
              (0.2, C("5")), (0.6, S("13_i2c.png")), (1.2, S("14_i2c_new.png")), (0.1, A("ESC")),
              # IR
              (0.2, C("6")), (2.0, S("15_ir.png")), (0.1, A("DOWN")), (0.1, A("DOWN")), (0.1, A("ENTER")),
              (0.3, S("16_ir_raw.png")), (0.1, A("ESC")), (0.1, A("ESC")), (0.5, S("17_home_ir.png"))]
    ref = [None]
    keys = SimKeys(script, fb, ref)
    app = App(fb, keys, sim=True, backends=backends)
    ref[0] = app
    app.run()
    print("sim done:", outdir)


# ================================================================ main
def probe():
    print(f"HEXA PROBE {VERSION}")
    for k, (lab, ok, lines) in B.detect_all().items():
        print(f"[{'OK' if ok else '--'}] {k:6} {lab}")
        for ln in lines:
            print("         " + ln)
    print("nfcpy:", B.nfc_python() or "なし")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--probe", action="store_true")
    ap.add_argument("--sim", metavar="OUTDIR")
    ap.add_argument("--no-pause", action="store_true", help="ランチャーを一時停止しない")
    ap.add_argument("--check-font", action="store_true")
    a = ap.parse_args()
    if a.check_font:
        find_font(12)
        print("font:", _FONT_FILE.get(False) or "見つかりません")
        raise SystemExit(0 if _FONT_FILE.get(False) else 1)
    if a.probe:
        return probe()
    if a.sim:
        return run_sim(a.sim)
    fb = FrameBuffer()
    keys = Keys(find_keyboard())
    paused = False
    if not a.no_pause and launcher_pids():
        signal_launcher(signal.SIGSTOP)
        paused = True
        for sg in (signal.SIGTERM, signal.SIGHUP):
            signal.signal(sg, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
    reason = "unknown"
    try:
        print(f"HEXA PROBE {VERSION}", flush=True)
        reason = App(fb, keys).run()
    except KeyboardInterrupt:
        reason = "Ctrl+C"
    except Exception:
        import traceback
        traceback.print_exc()
        reason = "error"
    finally:
        print("exit:", reason, flush=True)
        keys.close()
        fb.clear()
        if paused:
            signal_launcher(signal.SIGCONT)


if __name__ == "__main__":
    main()
