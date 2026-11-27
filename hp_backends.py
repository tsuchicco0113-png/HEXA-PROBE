"""HEXA PROBE のデータ取り込み部 (画面なし)

どれも別スレッドで読み、(種類, ...) のイベントを queue に積む。画面側は events() で受け取る。
  SerialReader  USBシリアル / Grove UART       ("data", bytes, t)
  BleScanner    bluetoothctl を pty で動かす    ("dev", addr, field, value)
  NfcWorker     nfcpy の helper を別プロセスで   ("nfc", dict)
  MidiReader    ALSA rawmidi / UART 31250bps    ("msg", tuple, t)
  I2cScanner    i2cdetect を定期実行           ("scan", bus, {addr: "ok"|"UU"})
  IrReader      /dev/lirc0 (mode2)              ("frame", [µs...], t)
共通: ("error", 文) / ("status", 文)
"""
import fcntl
import glob
import json
import os
import pty
import queue
import random
import re
import select
import shutil
import struct
import subprocess
import sys
import termios
import threading
import time

DIR = os.path.dirname(os.path.abspath(__file__))
RAW_DIR = None                  # デバッグ時に画面側が入れる。入っていれば各 Worker が生データを残す


def read_text(path):
    try:
        with open(path) as f:
            return f.read().strip()
    except OSError:
        return None


class Worker:
    kind = "worker"

    def __init__(self):
        self.q = queue.Queue()
        self.stop_ev = threading.Event()
        self.th = None
        self._raw = None

    def raw(self, text):
        """デバッグ時だけ: 受け取ったものを加工前のまま raw-<種類>-日時.log へ"""
        if RAW_DIR is None:
            return
        try:
            if self._raw is None:
                os.makedirs(RAW_DIR, exist_ok=True)
                path = os.path.join(RAW_DIR, f"raw-{self.kind}-{time.strftime('%Y%m%d-%H%M%S')}.log")
                self._raw = open(path, "a", encoding="utf-8", errors="replace")
            t = time.time()
            self._raw.write(time.strftime("%H:%M:%S", time.localtime(t)) + f".{int(t * 1000) % 1000:03d} {text}\n")
            self._raw.flush()
        except OSError:
            pass

    def start(self):
        self.th = threading.Thread(target=self._run_safe, daemon=True)
        self.th.start()
        return self

    def _run_safe(self):
        try:
            self.run()
        except Exception as e:
            self.q.put(("error", str(e) or type(e).__name__))

    def run(self):
        pass

    def events(self, limit=3000):
        out = []
        while len(out) < limit:
            try:
                out.append(self.q.get_nowait())
            except queue.Empty:
                break
        return out

    def stop(self):
        self.stop_ev.set()
        try:
            self.close()
        except Exception:
            pass
        if self.th and self.th is not threading.current_thread():
            self.th.join(timeout=1.5)
        if self._raw:
            try:
                self._raw.close()
            except OSError:
                pass
            self._raw = None

    def close(self):
        pass


# ================================================================ serial
TCGETS2, TCSETS2 = 0x802C542A, 0x402C542B      # struct termios2 (44 bytes) — arm64 / x86_64 共通
BOTHER, CBAUD = 0o010000, 0o010017
T2 = "<4IB19s2I"
TIOCMBIS, TIOCMBIC = 0x5416, 0x5417
TIOCM_DTR, TIOCM_RTS = 0x002, 0x004
USB_CHIPS = {"10c4": "CP210x", "1a86": "CH340/CH9102", "0403": "FTDI", "303a": "ESP32 USB",
             "2e8a": "RP2040", "2341": "Arduino", "239a": "Adafruit", "0d28": "DAPLink", "067b": "PL2303"}


def set_raw(fd):
    a = termios.tcgetattr(fd)
    a[0] = a[1] = a[3] = 0
    a[2] = termios.CS8 | termios.CREAD | termios.CLOCAL
    a[6][termios.VMIN] = 0
    a[6][termios.VTIME] = 0
    termios.tcsetattr(fd, termios.TCSANOW, a)


def set_baud(fd, baud):
    """どんな速度でも (31250 / 74880 も) termios2 の BOTHER で設定する"""
    buf = bytearray(struct.calcsize(T2))
    try:
        fcntl.ioctl(fd, TCGETS2, buf)
        f = list(struct.unpack(T2, buf))
        f[2] = (f[2] & ~CBAUD) | BOTHER
        f[6] = f[7] = baud
        fcntl.ioctl(fd, TCSETS2, struct.pack(T2, *f))
        return
    except OSError:
        name = f"B{baud}"
        if not hasattr(termios, name):
            raise
    a = termios.tcgetattr(fd)
    a[4] = a[5] = getattr(termios, f"B{baud}")
    termios.tcsetattr(fd, termios.TCSANOW, a)


def usb_info(sysdev):
    p = os.path.realpath(sysdev)
    for _ in range(6):
        if os.path.exists(os.path.join(p, "idVendor")):
            return (read_text(os.path.join(p, "idVendor")) or "", read_text(os.path.join(p, "idProduct")) or "",
                    read_text(os.path.join(p, "product")) or "")
        p = os.path.dirname(p)
    return None


def list_serial_ports():
    """[(名前, 説明, パス)]"""
    out = []
    for dev in sorted(glob.glob("/dev/ttyUSB*") + glob.glob("/dev/ttyACM*")):
        name = os.path.basename(dev)
        sub = ""
        info = usb_info(f"/sys/class/tty/{name}/device")
        if info:
            vid, pid, prod = info
            sub = f"{prod or USB_CHIPS.get(vid, 'USB')}  {vid}:{pid}"
        out.append((name, sub, dev))
    if os.path.exists("/dev/serial0"):
        out.append(("Grove UART", "serial0 → " + os.path.basename(os.path.realpath("/dev/serial0")) +
                    "  (Grove の黄=TX 白=RX)", "/dev/serial0"))
    return out


class SerialReader(Worker):
    kind = "serial"

    def __init__(self, path, baud):
        super().__init__()
        self.path, self.baud = path, baud
        self.fd = os.open(path, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
        set_raw(self.fd)
        set_baud(self.fd, baud)

    def run(self):
        while not self.stop_ev.is_set():
            r, _, _ = select.select([self.fd], [], [], 0.2)
            if not r:
                continue
            try:
                data = os.read(self.fd, 4096)
            except BlockingIOError:
                continue
            except OSError:
                self.q.put(("error", "切断されました"))
                return
            if not data:
                time.sleep(0.05)
                continue
            self.raw(data.hex(" "))
            self.q.put(("data", data, time.time()))

    def set_baud(self, baud):
        set_baud(self.fd, baud)
        self.baud = baud

    def reset_esp32(self):
        """esptool と同じ: DTR=off, RTS=on (EN を下げる) → RTS=off"""
        fcntl.ioctl(self.fd, TIOCMBIC, struct.pack("I", TIOCM_DTR))
        fcntl.ioctl(self.fd, TIOCMBIS, struct.pack("I", TIOCM_RTS))
        time.sleep(0.12)
        fcntl.ioctl(self.fd, TIOCMBIC, struct.pack("I", TIOCM_RTS))

    def close(self):
        try:
            os.close(self.fd)
        except OSError:
            pass


# ================================================================ BLE
ANSI = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]|[\x00-\x08\x0b-\x1f\x7f]")
DEV_RE = re.compile(r"\[(NEW|CHG|DEL)\]\s+Device\s+([0-9A-Fa-f:]{17})\s*(.*)")
BLE_VENDOR = {0x004C: "Apple", 0x0006: "Microsoft", 0x0075: "Samsung", 0x00E0: "Google", 0x02E5: "Espressif",
              0x0059: "Nordic", 0x038F: "Xiaomi", 0x0157: "Huami", 0x0499: "Ruuvi", 0x0087: "Garmin",
              0x000D: "TI", 0x0131: "Cypress", 0x0171: "Amazon", 0x0310: "SGL Italia", 0x00D2: "Dialog",
              0x0822: "adafruit", 0x0BDA: "Realtek", 0x0101: "Fugoo", 0x0002: "Intel", 0x001D: "Qualcomm",
              0x0910: "M5Stack?", 0x0969: "Woan(SwitchBot)", 0x0301: "Sony?", 0x012D: "Sony"}


def vendor_name(val):
    m = re.search(r"0x([0-9a-fA-F]{1,4})", val or "")
    if not m:
        return ""
    k = int(m.group(1), 16)
    return BLE_VENDOR.get(k, f"0x{k:04X}")


def bt_state():
    """(ある, ON) — ON は rfkill でブロックされていないこと"""
    if not glob.glob("/sys/class/bluetooth/hci*"):
        return False, False
    for d in glob.glob("/sys/class/rfkill/*"):
        if read_text(d + "/type") == "bluetooth":
            return True, read_text(d + "/soft") != "1" and read_text(d + "/hard") != "1"
    return True, True


class BleScanner(Worker):
    kind = "ble"

    def run(self):
        if not shutil.which("bluetoothctl"):
            raise RuntimeError("bluetoothctl がありません (sudo apt install bluez)")
        m, s = pty.openpty()
        self.master = m
        self.proc = subprocess.Popen(["bluetoothctl"], stdin=s, stdout=s, stderr=s, close_fds=True,
                                     start_new_session=True)
        os.close(s)
        time.sleep(0.6)
        self.send("power on")
        time.sleep(0.4)
        self.send("scan on")
        self.q.put(("status", "スキャン中"))
        buf = b""
        while not self.stop_ev.is_set():
            r, _, _ = select.select([m], [], [], 0.3)
            if not r:
                if self.proc.poll() is not None:
                    raise RuntimeError("bluetoothctl が終了しました")
                continue
            try:
                buf += os.read(m, 4096)
            except OSError:
                break
            parts = re.split(rb"\r?\n|\r", buf)
            buf = parts.pop()
            for ln in parts:
                txt = ln.decode("utf-8", "replace")
                if not txt.strip():
                    continue
                self.raw(repr(txt))                       # 形式がずれた時のために、そのまま残す
                self.parse(txt)

    def send(self, cmd):
        try:
            os.write(self.master, (cmd + "\n").encode())
        except OSError:
            pass

    def parse(self, ln):
        ln = ANSI.sub("", ln).strip()
        idx = [i for i in (ln.find("[NEW]"), ln.find("[CHG]"), ln.find("[DEL]")) if i >= 0]
        if not idx:
            low = ln.lower()
            if "no default controller" in low:
                self.q.put(("error", "Bluetooth が見つかりません (HEXA POWER で BT を ON に)"))
            elif "failed to start discovery" in low or "org.bluez.error" in low:
                self.q.put(("status", ln[-60:]))
            return
        mm = DEV_RE.match(ln[min(idx):])
        if not mm:
            return
        kind, addr, rest = mm.group(1), mm.group(2).upper(), mm.group(3).strip()
        if kind == "NEW":
            name = "" if rest.replace("-", ":").upper() == addr else rest
            self.q.put(("dev", addr, "name" if name else "seen", name))
        elif kind == "DEL":
            self.q.put(("dev", addr, "del", ""))
        elif ":" in rest:
            key, val = [x.strip() for x in rest.split(":", 1)]
            key = key.replace(".", " ")                  # BlueZ 新しめ: ManufacturerData.Key
            if key == "RSSI":
                n = re.search(r"\((-?\d+)\)", val) or re.search(r"(-?\d+)", val)
                if n:
                    self.q.put(("dev", addr, "rssi", int(n.group(1))))
            elif key in ("Name", "Alias"):
                if val.replace("-", ":").upper() != addr:
                    self.q.put(("dev", addr, "name", val))
            elif key == "ManufacturerData Key":
                self.q.put(("dev", addr, "mfr", val))
            elif key == "ServiceData Key":
                self.q.put(("dev", addr, "svc", val))
            elif key == "UUIDs":
                self.q.put(("dev", addr, "uuid", val))
            elif key == "TxPower":
                self.q.put(("dev", addr, "tx", val))
            elif not key.endswith("Value"):
                self.q.put(("dev", addr, "other", f"{key}: {val}"[:60]))

    def close(self):
        self.send("scan off")
        time.sleep(0.2)
        self.send("quit")
        p = getattr(self, "proc", None)
        if p:
            try:
                p.wait(timeout=1.0)
            except subprocess.TimeoutExpired:
                p.terminate()
        try:
            os.close(self.master)
        except (OSError, AttributeError):
            pass


# ================================================================ NFC
NFC_READERS = {("054c", "06c1"): "RC-S380", ("054c", "06c3"): "RC-S380", ("054c", "02e1"): "RC-S330",
               ("072f", "2200"): "ACR122U", ("04e6", "5591"): "SCL3711"}
_NFC_PY = []


def nfc_reader():
    for d in glob.glob("/sys/bus/usb/devices/*"):
        key = (read_text(d + "/idVendor"), read_text(d + "/idProduct"))
        if key in NFC_READERS:
            return NFC_READERS[key]
    return None


def nfc_python_guess():
    venv = os.path.expanduser("~/nfc/bin/python")
    return venv if os.path.exists(venv) else None


def nfc_python():
    """nfcpy を import できる python (HEXA SIGN の ~/nfc venv を優先)"""
    if _NFC_PY:
        return _NFC_PY[0]
    for py in (os.path.expanduser("~/nfc/bin/python"), sys.executable, "/usr/bin/python3"):
        if py and os.path.exists(py):
            try:
                if subprocess.run([py, "-c", "import nfc"], capture_output=True, timeout=30).returncode == 0:
                    _NFC_PY.append(py)
                    return py
            except (OSError, subprocess.TimeoutExpired):
                pass
    return None


class NfcWorker(Worker):
    kind = "nfc"

    def run(self):
        self.q.put(("status", "nfcpy を準備中…"))
        py = nfc_python()
        if not py:
            raise RuntimeError("nfcpy がありません (install.sh で ~/nfc に入ります)")
        self.proc = subprocess.Popen([py, "-u", os.path.join(DIR, "hp_nfc_helper.py")], stdout=subprocess.PIPE,
                                     stderr=subprocess.STDOUT, text=True, bufsize=1)
        for line in self.proc.stdout:
            if self.stop_ev.is_set():
                break
            line = line.strip()
            self.raw(line)
            try:
                ev = json.loads(line)
            except ValueError:
                if line:
                    self.q.put(("status", line[-70:]))
                continue
            self.q.put(("nfc", ev))
        if not self.stop_ev.is_set():
            self.q.put(("error", "NFC の読み取りが止まりました"))

    def close(self):
        p = getattr(self, "proc", None)
        if p and p.poll() is None:
            p.terminate()
            try:
                p.wait(timeout=1.5)
            except subprocess.TimeoutExpired:
                p.kill()


# ================================================================ MIDI
NOTE_NAMES = "C C# D D# E F F# G G# A A# B".split()
CC_NAMES = {0: "Bank", 1: "Mod", 2: "Breath", 7: "Volume", 10: "Pan", 11: "Expr", 32: "BankLSB", 64: "Sustain",
            65: "Porta", 66: "Sostenuto", 67: "Soft", 71: "Reso", 72: "Release", 73: "Attack", 74: "Cutoff",
            91: "Reverb", 93: "Chorus", 120: "SoundOff", 121: "ResetCtl", 123: "NotesOff"}
RT_NAMES = {0xF8: "Clock", 0xFA: "Start", 0xFB: "Continue", 0xFC: "Stop", 0xFE: "ActiveSense", 0xFF: "Reset",
            0xF6: "TuneReq", 0xF1: "MTC", 0xF2: "SongPos", 0xF3: "SongSel"}


def note_name(n):
    return f"{NOTE_NAMES[n % 12]}{n // 12 - 1}"


class MidiParser:
    LEN = {0x80: 2, 0x90: 2, 0xA0: 2, 0xB0: 2, 0xC0: 1, 0xD0: 1, 0xE0: 2}
    SYS = {0xF1: 1, 0xF2: 2, 0xF3: 1}

    def __init__(self):
        self.status, self.data, self.sysex = None, [], None

    def feed(self, data):
        out = []
        for b in data:
            if b >= 0xF8:                                   # リアルタイムは途中に割り込める
                out.append((b,))
                continue
            if b == 0xF0:
                self.sysex, self.status = [b], None
                continue
            if b == 0xF7:
                if self.sysex is not None:
                    out.append(tuple(self.sysex + [b]))
                    self.sysex = None
                continue
            if b >= 0x80:
                if self.sysex is not None:
                    out.append(tuple(self.sysex))
                    self.sysex = None
                self.data = []
                if b >= 0xF0 and b not in self.SYS:
                    out.append((b,))
                    self.status = None
                else:
                    self.status = b
                continue
            if self.sysex is not None:
                if len(self.sysex) < 512:
                    self.sysex.append(b)
                continue
            if self.status is None:
                continue
            self.data.append(b)
            n = self.SYS[self.status] if self.status >= 0xF0 else self.LEN[self.status & 0xF0]
            if len(self.data) >= n:
                out.append((self.status, *self.data))
                self.data = []
                if self.status >= 0xF0:
                    self.status = None
        return out


def describe_midi(m):
    """(文, 種類) 種類: on / off / cc / pb / pc / sys / rt"""
    s = m[0]
    if s == 0xF0:
        body = " ".join(f"{b:02X}" for b in m[:10]) + (" …" if len(m) > 10 else "")
        return f"SysEx {len(m)}B  {body}", "sys"
    if s >= 0xF0:
        extra = " ".join(str(b) for b in m[1:])
        return f"{RT_NAMES.get(s, f'{s:02X}')} {extra}".strip(), "rt"
    hi, ch = s & 0xF0, (s & 15) + 1
    c = f"ch{ch:<2}"
    if hi == 0x90 and m[2] > 0:
        return f"{c} NoteOn   {note_name(m[1]):<4} ({m[1]:3})  vel {m[2]}", "on"
    if hi in (0x80, 0x90):
        return f"{c} NoteOff  {note_name(m[1]):<4} ({m[1]:3})  vel {m[2]}", "off"
    if hi == 0xA0:
        return f"{c} PolyAT   {note_name(m[1])}  {m[2]}", "cc"
    if hi == 0xB0:
        nm = CC_NAMES.get(m[1], "")
        return f"{c} CC {m[1]:3} {nm:<9} = {m[2]}", "cc"
    if hi == 0xC0:
        return f"{c} Program  {m[1] + 1}", "pc"
    if hi == 0xD0:
        return f"{c} ChanAT   {m[1]}", "cc"
    v = (m[1] | (m[2] << 7)) - 8192
    return f"{c} Bend     {v:+d}", "pb"


def list_midi_sources():
    out = []
    for dev in sorted(glob.glob("/dev/snd/midiC*D*")):
        mm = re.search(r"midiC(\d+)D(\d+)", dev)
        name = read_text(f"/proc/asound/card{mm.group(1)}/id") or f"card{mm.group(1)}"
        out.append((name, f"USB MIDI  {os.path.basename(dev)}", ("raw", dev)))
    if os.path.exists("/dev/serial0"):
        out.append(("Grove UART", "Unit MIDI の MIDI IN など (31250bps)", ("uart", "/dev/serial0")))
    return out


class MidiReader(Worker):
    kind = "midi"

    def __init__(self, src):
        super().__init__()
        kind, path = src
        self.parser = MidiParser()
        if kind == "uart":
            self.fd = os.open(path, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
            set_raw(self.fd)
            set_baud(self.fd, 31250)
        else:
            self.fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)

    def run(self):
        while not self.stop_ev.is_set():
            r, _, _ = select.select([self.fd], [], [], 0.2)
            if not r:
                continue
            try:
                data = os.read(self.fd, 1024)
            except BlockingIOError:
                continue
            except OSError:
                self.q.put(("error", "切断されました"))
                return
            t = time.time()
            self.raw(data.hex(" "))
            for msg in self.parser.feed(data):
                self.q.put(("msg", msg, t))

    def close(self):
        try:
            os.close(self.fd)
        except OSError:
            pass


# ================================================================ I2C
I2C_HINTS = {0x0D: "QMC5883 地磁気", 0x10: "VEML7700 光", 0x18: "LIS3DH 加速度", 0x19: "LIS3DH 加速度",
             0x1E: "HMC5883 地磁気", 0x20: "PCF8574/MCP23017 IO", 0x23: "BH1750 光",
             0x26: "Unit ?", 0x27: "PCF8574 LCD", 0x29: "VL53L0X/L1X 距離 / TCS34725 色",
             0x34: "TCA8418 キー (本体)", 0x38: "AHT20 温湿度 / FT6336 タッチ", 0x39: "APDS9960 / TSL2561",
             0x3C: "SSD1306 OLED", 0x3D: "SSD1306 OLED", 0x40: "INA219 電流 / HDC1080 / PCA9685",
             0x41: "INA219 電流", 0x42: "GPS (u-blox)", 0x44: "SHT3x/SHT4x 温湿度 (ENV)", 0x45: "SHT3x 温湿度",
             0x48: "ADS1115 ADC / TMP102", 0x49: "ADS1115 ADC", 0x4A: "ADS1115", 0x4B: "ADS1115",
             0x32: "RX8130 RTC (本体)", 0x51: "BM8563 RTC", 0x52: "VL53L4 / Nunchuk", 0x53: "ADXL345 加速度", 0x55: "BQ27220 電池 (本体)",
             0x57: "MAX30102 / EEPROM", 0x58: "SGP30 空気", 0x59: "SGP40 空気", 0x5A: "MLX90614 温度 / CCS811",
             0x5B: "CCS811", 0x5C: "AM2320 温湿度", 0x60: "Si5351 / MCP4725 DAC", 0x61: "SCD30 CO2",
             0x62: "SCD40 CO2", 0x68: "BMI270 IMU (本体) / MPU6886 / DS3231", 0x69: "BMI270 IMU",
             0x6A: "LSM6DS IMU", 0x6B: "LSM6DS IMU", 0x70: "PaHub (TCA9548A) / QMP6988 (ENV III)",
             0x76: "BMP280/BME280 気圧", 0x77: "BME680/BMP280 気圧"}


def list_i2c_buses():
    return sorted(int(p.rsplit("-", 1)[1]) for p in glob.glob("/dev/i2c-*") if p.rsplit("-", 1)[1].isdigit())


def i2c_scan(bus, raw=None):
    """i2cdetect の自動モード (アドレスに応じて quick write / read) で探す"""
    if not shutil.which("i2cdetect"):
        raise RuntimeError("i2cdetect がありません (sudo apt install i2c-tools)")
    p = subprocess.run(["i2cdetect", "-y", str(bus)], capture_output=True, text=True, timeout=10)
    if raw:
        raw(f"i2cdetect -y {bus} rc={p.returncode}\n{p.stdout}{p.stderr}")
    if p.returncode != 0:
        msg = (p.stderr or p.stdout).strip().splitlines()
        raise RuntimeError(msg[-1] if msg else f"i2cdetect が失敗 ({p.returncode})")
    res = {}
    for line in p.stdout.splitlines()[1:]:
        if ":" not in line:
            continue
        row, cells = line.split(":", 1)
        try:
            base = int(row.strip(), 16)
        except ValueError:
            continue
        for i in range(16):
            tok = cells[i * 3 + 1:i * 3 + 3].strip()
            if tok == "UU":
                res[base + i] = "UU"
            elif re.fullmatch(r"[0-9a-fA-F]{2}", tok):
                res[base + i] = "ok"
    return res


def _pinctrl(args):
    for base in (["pinctrl"], ["sudo", "-n", "pinctrl"]):
        try:
            p = subprocess.run(base + args, capture_output=True, text=True, timeout=5)
        except (OSError, subprocess.TimeoutExpired):
            continue
        if p.returncode == 0:
            return p.stdout
    return None


def grove_mode():
    """Grove の切替 (GPIO4): L=UART / H=I2C1。(モード, 元の設定) 読めなければ (None, None)"""
    if not shutil.which("pinctrl"):
        return None, None
    out = _pinctrl(["get", "4"])
    if not out:
        return None, None
    func = "op" if re.search(r"\bop\b", out) else "ip"
    hi = bool(re.search(r"\|\s*hi\b", out))
    return ("I2C" if hi else "UART"), (func, hi)


def set_grove_mode(mode):
    return _pinctrl(["set", "4", "op", "dh" if mode == "I2C" else "dl"]) is not None


def restore_grove(orig):
    func, hi = orig
    if func == "ip":
        _pinctrl(["set", "4", "ip"])
    else:
        _pinctrl(["set", "4", "op", "dh" if hi else "dl"])


class I2cScanner(Worker):
    kind = "i2c"

    def __init__(self, bus, interval=2.0):
        super().__init__()
        self.bus, self.interval = bus, interval
        self.auto = True
        self.kick = threading.Event()

    def run(self):
        while not self.stop_ev.is_set():
            try:
                self.q.put(("scan", self.bus, i2c_scan(self.bus, raw=self.raw), time.time()))
            except Exception as e:
                self.q.put(("error", str(e)))
            self.kick.wait(self.interval if self.auto else 3600)
            self.kick.clear()

    def rescan(self):
        self.kick.set()

    def close(self):
        self.kick.set()


# ================================================================ IR
LIRC_PULSE, LIRC_TIMEOUT, LIRC_OVERFLOW = 0x01000000, 0x03000000, 0x04000000


def ir_device():
    devs = sorted(glob.glob("/dev/lirc*"))
    return devs[0] if devs else None


class IrReader(Worker):
    kind = "ir"
    GAP = 12000                    # µs 以上の空白でフレームの区切り

    def __init__(self, dev):
        super().__init__()
        self.fd = os.open(dev, os.O_RDONLY | os.O_NONBLOCK)

    def run(self):
        frame, last = [], time.time()
        buf = b""
        while not self.stop_ev.is_set():
            r, _, _ = select.select([self.fd], [], [], 0.04)
            now = time.time()
            if not r:
                if frame and now - last > 0.08:
                    self.flush(frame)
                    frame = []
                continue
            try:
                buf += os.read(self.fd, 4096)
            except BlockingIOError:
                continue
            except OSError:
                self.q.put(("error", "受信機が読めなくなりました"))
                return
            n = len(buf) // 4
            if RAW_DIR is not None:
                self.raw(" ".join(f"{v:08X}" for (v,) in struct.iter_unpack("<I", buf[:n * 4])))
            for (v,) in struct.iter_unpack("<I", buf[:n * 4]):
                typ, val = v & 0xFF000000, v & 0x00FFFFFF
                if typ == LIRC_PULSE:
                    if len(frame) % 2 == 1:           # パルスが続いた → まとめる
                        frame[-1] += val
                    else:
                        frame.append(val)
                    last = now
                elif typ == 0:                        # space
                    if not frame:
                        continue
                    if val >= self.GAP:
                        self.flush(frame)
                        frame = []
                    elif len(frame) % 2 == 1:
                        frame.append(val)
                    else:
                        frame[-1] += val
                elif typ in (LIRC_TIMEOUT, LIRC_OVERFLOW) and frame:
                    self.flush(frame)
                    frame = []
            buf = buf[n * 4:]

    def flush(self, frame):
        if len(frame) % 2 == 0:
            frame = frame[:-1]
        if len(frame) >= 3:
            self.q.put(("frame", list(frame), time.time()))

    def close(self):
        try:
            os.close(self.fd)
        except OSError:
            pass


def _near(x, t, tol):
    return abs(x - t) <= max(t * tol, 120)


def _space_bits(d, t, zero, one):
    """[pulse, space, pulse, space, ...] を space の長さで 0/1 に"""
    bits = []
    th = (zero + one) / 2
    for i in range(0, len(d) - 1, 2):
        p, s = d[i], d[i + 1]
        if not _near(p, t, 0.5) or s > one * 1.6:
            break
        bits.append(1 if s > th else 0)
    return bits


def _lsb_bytes(bits):
    return [sum(b << i for i, b in enumerate(bits[k:k + 8])) for k in range(0, len(bits) - len(bits) % 8, 8)]


def _lsb_int(bits):
    return sum(b << i for i, b in enumerate(bits))


def decode_ir(d):
    """(方式, 内容, 同じ信号か判定する鍵 or None)"""
    n = len(d)
    if n < 3:
        return "ノイズ", f"{n}区間", None
    p0, s0 = d[0], d[1]
    if _near(p0, 9000, 0.2):
        if _near(s0, 2250, 0.25) and n <= 5:
            return "NEC", "リピート", ("NEC", "rep")
        if _near(s0, 4500, 0.25):
            bits = _space_bits(d[2:], 560, 560, 1690)
            if len(bits) >= 32:
                a, na, c, nc = _lsb_bytes(bits[:32])
                addr = f"{a:02X}" if a ^ na == 0xFF else f"{a | (na << 8):04X}"
                ok = (c ^ nc) == 0xFF
                return "NEC", f"addr {addr}  cmd {c:02X}" + ("" if ok else "  (検査NG)"), ("NEC", addr, c)
    if _near(p0, 2400, 0.25) and _near(s0, 600, 0.4):
        bits = [1 if d[i] > 900 else 0 for i in range(2, n, 2)]
        if len(bits) in (12, 15, 20):
            cmd, addr = _lsb_int(bits[:7]), _lsb_int(bits[7:])
            return f"SONY{len(bits)}", f"addr {addr:X}  cmd {cmd:02X}", ("SONY", len(bits), addr, cmd)
    if 2400 <= p0 <= 5200 and _near(s0, p0 / 2, 0.3):
        t = p0 / 8
        bits = _space_bits(d[2:], t, t, 3 * t)
        if len(bits) >= 16:
            by = _lsb_bytes(bits)
            txt = " ".join(f"{b:02X}" for b in by[:9]) + (" …" if len(by) > 9 else "")
            return "家製協", f"{txt}  ({len(bits)}bit)", ("AEHA", tuple(by))
    if 2400 <= p0 <= 5200 and _near(s0, p0, 0.3) and n <= 5:
        return "家製協", "リピート", ("AEHA", "rep")
    return "不明", f"パルス{(n + 1) // 2}個  先頭 {p0}/{s0}µs", ("RAW", n // 4, p0 // 500, s0 // 500)


# ================================================================ TEST (導通チェック: G22 ⇔ GND)
TEST_GPIO = 22             # 14P の正面側の列 5番目 (G22)。ﾃｽﾄ線は 1kΩ を通してから出す


def _gpiod():
    try:
        import gpiod
        if hasattr(gpiod, "request_lines"):        # libgpiod v2 の python
            return gpiod
    except ImportError:
        pass
    return None


def _find_gpio_chip(gpiod, gpio):
    """GPIO22 がどの gpiochip の何番か (名前 "GPIO22" で探す。無ければ bcm の chip の 22 番)"""
    fallback = None
    for path in sorted(glob.glob("/dev/gpiochip*")):
        try:
            with gpiod.Chip(path) as ch:
                try:
                    return path, ch.line_offset_from_id(f"GPIO{gpio}")
                except (OSError, ValueError):
                    pass
                lab = ch.get_info().label
                if fallback is None and ("bcm2835" in lab or "bcm2711" in lab or "rp1" in lab):
                    fallback = (path, gpio)
        except OSError:
            continue
    return fallback


def test_backend():
    """('gpiod', 説明) / ('pinctrl', 説明) / (None, 理由)"""
    g = _gpiod()
    if g:
        try:
            found = _find_gpio_chip(g, TEST_GPIO)
        except Exception:
            found = None
        if found:
            return "gpiod", f"{found[0]} line {found[1]}"
    if shutil.which("pinctrl") and _pinctrl(["get", str(TEST_GPIO)]):
        return "pinctrl", "pinctrl (20回/秒で読む)"
    return None, "GPIO が読めません (python3-libgpiod か pinctrl、gpio グループ)"


class ContinuityReader(Worker):
    """G22 を内部プルアップの入力にして、GND とつながった (LOW) / 離れた (HIGH) を時刻付きで出す
    ("level", つながった?, 時刻ns)。gpiod ならエッジを ns 単位で取れる (瞬断の長さが測れる)"""
    kind = "test"

    def __init__(self):
        super().__init__()
        self.mode, self.info = test_backend()
        if not self.mode:
            raise RuntimeError(self.info)
        self.req = None

    def run(self):
        if self.mode == "gpiod":
            return self.run_gpiod()
        return self.run_pinctrl()

    def run_gpiod(self):
        import gpiod
        from gpiod.line import Bias, Direction, Edge, Value
        path, off = _find_gpio_chip(gpiod, TEST_GPIO)
        self.req = gpiod.request_lines(path, consumer="hexaprobe-test", config={
            off: gpiod.LineSettings(direction=Direction.INPUT, bias=Bias.PULL_UP, edge_detection=Edge.BOTH)})
        time.sleep(0.01)                          # プルアップが効くまで
        v = self.req.get_value(off)
        self.q.put(("level", v == Value.INACTIVE, time.monotonic_ns()))
        self.raw(f"start {path} line {off} value={v}")
        while not self.stop_ev.is_set():
            if not self.req.wait_edge_events(0.2):
                continue
            for ev in self.req.read_edge_events():
                conn = ev.event_type == ev.Type.FALLING_EDGE
                self.raw(f"{ev.timestamp_ns} {'FALL' if conn else 'RISE'}")
                self.q.put(("level", conn, ev.timestamp_ns))

    def run_pinctrl(self):
        _pinctrl(["set", str(TEST_GPIO), "ip", "pu"])
        last = None
        while not self.stop_ev.is_set():
            out = _pinctrl(["get", str(TEST_GPIO)]) or ""
            conn = bool(re.search(r"\|\s*lo\b", out))
            if conn != last:
                self.raw(out.strip())
                self.q.put(("level", conn, time.monotonic_ns()))
                last = conn
            self.stop_ev.wait(0.05)

    def close(self):
        if self.req is not None:
            try:
                self.req.release()
            except Exception:
                pass
            self.req = None
        elif self.mode == "pinctrl":
            _pinctrl(["set", str(TEST_GPIO), "ip", "pn"])


class Beeper:
    """本体スピーカーで鳴らし続けるための aplay。on の間だけ音、off は無音を流す (遅れ 30ms ほど)"""
    RATE, CHUNK = 16000, 160                  # 10ms ずつ

    def __init__(self, freq=2400, vol=0.35):
        import math as _m
        self.on = False
        self.until = 0.0                          # 瞬断でも聞こえるよう最低限鳴らす時刻
        self.proc = None
        self.err = None
        self.muted = False
        n = self.RATE // freq * 20                # 周期の整数倍で切れ目のない波形
        self.tone = b"".join(struct.pack("<h", int(32767 * vol * _m.sin(2 * _m.pi * freq * i / self.RATE)))
                             for i in range(n))
        self.silence = b"\x00\x00" * self.CHUNK
        if not shutil.which("aplay"):
            self.err = "aplay がありません (alsa-utils)"
            return
        try:
            self.proc = subprocess.Popen(["aplay", "-q", "-t", "raw", "-f", "S16_LE", "-r", str(self.RATE), "-c", "1",
                                          "-B", "40000"], stdin=subprocess.PIPE, stderr=subprocess.DEVNULL)
        except OSError as e:
            self.err = str(e)
            return
        self.stop_ev = threading.Event()
        self.th = threading.Thread(target=self._run, daemon=True)
        self.th.start()

    def _run(self):
        pos = 0
        next_t = time.monotonic()
        while not self.stop_ev.is_set():
            sound = (self.on or time.monotonic() < self.until) and not self.muted
            if sound:
                b = (self.tone * 3)[pos:pos + self.CHUNK * 2]
                pos = (pos + self.CHUNK * 2) % len(self.tone)
            else:
                b = self.silence
            try:
                self.proc.stdin.write(b)
                self.proc.stdin.flush()
            except (BrokenPipeError, OSError):
                self.err = "音が出せません (aplay が終了)"
                return
            next_t += self.CHUNK / self.RATE
            d = next_t - time.monotonic()
            if d > 0:
                time.sleep(d)
            else:
                next_t = time.monotonic()

    def set(self, on, min_sec=0.0):
        self.on = on
        if min_sec:
            self.until = max(self.until, time.monotonic() + min_sec)

    def close(self):
        if self.proc:
            self.stop_ev.set()
            try:
                self.proc.stdin.close()
            except OSError:
                pass
            self.proc.terminate()
            self.proc = None


# ================================================================ 準備状況 (ホーム画面用)
def detect_all():
    """{key: (六角形の下の文字, OK?, [説明の行])}"""
    r = {}
    ports = list_serial_ports()
    r["serial"] = (f"{len(ports)}個" if ports else "なし", bool(ports),
                   [f"{n}  {s}" for n, s, _ in ports][:4] or ["USB シリアルを挿してね"])
    has, on = bt_state()
    if not has:
        r["ble"] = ("なし", False, ["Bluetooth が見つかりません"])
    elif not on:
        r["ble"] = ("OFF", False, ["BT が OFF (HEXA POWER の 1 で ON に)"])
    else:
        r["ble"] = ("OK", True, ["ENTER でスキャン開始", "電波の強い順に並びます"])
    rd = nfc_reader()
    py = nfc_python_guess()
    r["nfc"] = ("OK" if rd else "なし", bool(rd), [f"リーダー: {rd or 'なし (RC-S380 を挿す)'}",
                                         f"nfcpy: {'~/nfc' if py else 'python3 (未確認)'}"])
    src = list_midi_sources()
    r["midi"] = (f"{len(src)}系統" if src else "なし", bool(src), [f"{n}  {s}" for n, s, _ in src][:4] or ["なし"])
    buses = list_i2c_buses()
    gm, _ = grove_mode()
    r["i2c"] = (f"bus{','.join(map(str, buses))}" if buses else "なし", bool(buses),
                [f"バス: {', '.join(f'i2c-{b}' for b in buses) or 'なし'}",
                 f"Grove: {gm or '?'}" + ("  (画面の G で I2C に)" if gm == "UART" else ""),
                 "Grove の電源は 設定 > ExtPort"])
    dev = ir_device()
    r["ir"] = ("OK" if dev else "未設定", bool(dev),
               [f"受信: {dev}  (GPIO13)"] if dev else ["受信機がまだ有効になっていません",
                                                     "sh install.sh --ir → 再起動"])
    mode, info = test_backend()
    r["test"] = ("G22" if mode else "なし", bool(mode),
                 ([f"読み方: {info}"] if mode else [info]) +
                 ["ﾃｽﾄ線: G22 →1kΩ→ / GND", "電源を切った回路だけ!"])
    return r


# ================================================================ PC 用の偽データ
class FakeWorker(Worker):
    script = []                     # [(秒, event)]

    def run(self):
        t0 = time.time()
        for dt, ev in self.script:
            while time.time() - t0 < dt:
                if self.stop_ev.wait(0.02):
                    return
            self.q.put(ev)


class FakeSerial(FakeWorker):
    def __init__(self, path, baud):
        super().__init__()
        self.path, self.baud = path, baud
        boot = (b"ets Jul 29 2019 12:21:46\r\n\r\nrst:0x1 (POWERON_RESET),boot:0x13 (SPI_FAST_FLASH_BOOT)\r\n"
                b"configsip: 0, SPIWP:0xee\r\nclk_drv:0x00,q_drv:0x00,d_drv:0x00,cs0_drv:0x00\r\n"
                b"mode:DIO, clock div:1\r\nload:0x3fff0030,len:1184\r\nentry 0x400805e4\r\n"
                b"[TOMOSHIBI] boot v1.4\r\n[TOMOSHIBI] LED 24 px, brightness 80\r\n[WiFi] connecting...\r\n"
                b"[WiFi] connected 192.168.4.2\r\n")
        self.script = [(0.1 + i * 0.02, ("data", boot[i * 40:(i + 1) * 40], 0)) for i in range(len(boot) // 40 + 1)]
        self.script += [(1.0 + i * 0.25, ("data", f"[LED] mode=rainbow t={i * 250}ms\r\n".encode(), 0))
                        for i in range(30)]

    def set_baud(self, b):
        self.baud = b

    def reset_esp32(self):
        pass


class FakeBle(FakeWorker):
    def __init__(self):
        super().__init__()
        devs = [("D4:F5:13:AA:01:22", "HEXA-TOMOSHIBI", -48, "0x02e5"), ("7C:9E:BD:11:22:33", "", -71, "0x004c"),
                ("E1:22:33:44:55:66", "SwitchBot", -64, "0x0969"), ("C8:2B:96:00:11:AA", "M5Stack-Dial", -55, "0x02e5"),
                ("44:55:66:77:88:99", "", -88, "0x0006"), ("5A:11:22:33:44:01", "Galaxy Buds", -77, "0x0075"),
                ("00:1A:7D:DA:71:13", "LE-Bose", -82, ""), ("F0:F5:BD:01:02:03", "ESP32_BLE_MIDI", -59, "0x02e5")]
        sc = [(0.05, ("status", "スキャン中"))]
        for i, (a, n, r, m) in enumerate(devs):
            t = 0.1 + i * 0.15
            sc.append((t, ("dev", a, "name" if n else "seen", n)))
            sc.append((t + 0.01, ("dev", a, "rssi", r)))
            if m:
                sc.append((t + 0.02, ("dev", a, "mfr", m)))
        sc.append((1.6, ("dev", devs[0][0], "uuid", "0000ffe0-0000-1000-8000-00805f9b34fb")))
        sc.append((1.6, ("dev", devs[0][0], "tx", "9")))
        self.script = sc


class FakeNfc(FakeWorker):
    def __init__(self):
        super().__init__()
        self.script = [
            (0.1, ("nfc", {"ev": "ready", "device": "SONY RC-S380/P on usb:001:004"})),
            (0.6, ("nfc", {"ev": "tag", "type": "Type2Tag", "product": "NXP NTAG215", "id": "04A1B2C3D4E580",
                           "ndef": [{"type": "urn:nfc:wkt:U", "text": "https://booth.pm/"}],
                           "ndef_info": "使用 26/496 バイト 書込可",
                           "dump": ["000: 04 a1 b2 9f (UID0-UID2, BCC0)", "001: c3 d4 e5 80 (UID3-UID6)",
                                    "002: 82 48 00 00 (BCC1, INT, LOCK0-LOCK1)", "003: e1 10 3e 00 (OTP0-OTP3)",
                                    "004: 03 15 d1 01 |....|", "005: 11 55 04 62 |.U.b|"]})),
            (1.4, ("nfc", {"ev": "removed"})),
            (1.8, ("nfc", {"ev": "tag", "type": "Type3Tag", "product": "FeliCa Standard (RC-SA00/1)",
                           "id": "012E4CD1A2B3C4D5", "pmm": "100B4B428485D0FF", "sys": "0003",
                           "ndef": [], "dump": ["System 0003", "Area 0000--FFFE", "Service 090F 読み取り可 (履歴)"]})),
        ]


class FakeMidi(FakeWorker):
    def __init__(self, src):
        super().__init__()
        p = MidiParser()
        sc, t = [], 0.1
        for _ in range(20):
            sc.append((t, ("msg", (0xF8,), 0)))
            t += 0.02
        seq = [(0x90, 60, 100), (0x90, 64, 90), (0x90, 67, 92), (0xB0, 64, 127), (0x80, 60, 0), (0xE0, 0, 72),
               (0xB0, 74, 88), (0xC0, 5), (0x90, 72, 110), (0xF0, 0x7E, 0x7F, 0x06, 0x01, 0xF7)]
        for m in seq:
            for msg in p.feed(bytes(m)):
                sc.append((t, ("msg", msg, 0)))
            for _ in range(3):
                sc.append((t, ("msg", (0xF8,), 0)))
                t += 0.02
            t += 0.05
        self.script = sc


class FakeI2c(FakeWorker):
    def __init__(self, bus, interval=2.0):
        super().__init__()
        self.bus, self.auto = bus, True
        base = {0x34: "UU", 0x55: "UU", 0x10: "ok", 0x51: "ok", 0x68: "ok", 0x43: "ok"}
        more = {**base, 0x44: "ok", 0x70: "ok"}
        self.script = [(0.1, ("scan", bus, base, 0)), (1.2, ("scan", bus, more, 0))]

    def rescan(self):
        pass


class FakeTest(FakeWorker):
    mode, info = "gpiod", "sim"

    def __init__(self):
        super().__init__()
        ns = lambda t: int(t * 1e9)              # noqa: E731
        sc = [(0.05, ("level", False, ns(0.05)))]
        t = 0.3
        for conn, dt in [(True, 0.6), (False, 0.4), (True, 0.9), (False, 0.003), (True, 0.5), (False, 0.012),
                         (True, 0.3), (False, 0.5)]:
            sc.append((t, ("level", conn, ns(t))))
            t += dt
        self.script = sc


class FakeIr(FakeWorker):
    def __init__(self, dev):
        super().__init__()

        def nec(addr, cmd):
            d = [9000, 4500]
            for byte in (addr, addr ^ 0xFF, cmd, cmd ^ 0xFF):
                for i in range(8):
                    d += [560 + random.randint(-40, 40), 1690 if byte >> i & 1 else 560]
            return d + [560]

        def aeha(data):
            t = 425
            d = [8 * t, 4 * t]
            for byte in data:
                for i in range(8):
                    d += [t, 3 * t if byte >> i & 1 else t]
            return d + [t]
        self.script = [(0.2, ("frame", nec(0x00, 0x45), 0)), (0.35, ("frame", [9000, 2250, 560], 0)),
                       (0.45, ("frame", [9000, 2250, 560], 0)),
                       (0.8, ("frame", aeha([0x02, 0x20, 0xE0, 0x04, 0x00, 0x00, 0x00, 0x06]), 0)),
                       (1.2, ("frame", nec(0x40, 0x12), 0)), (1.5, ("frame", [3200, 800, 600, 900, 600], 0))]
