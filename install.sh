#!/bin/sh
# HEXA PROBE installer for CardputerZero
# 使い方: cd ~/hexaprobe && sh install.sh        (sudo は付けずに実行)
#         sh install.sh --ir                   赤外線の受信 (GPIO13) も有効にする (要再起動)
set -e
DIR=$(cd "$(dirname "$0")" && pwd)
U=$(id -un)
if [ "$U" = "root" ]; then
  echo "sudo を付けずに実行してください (sh install.sh)"; exit 1
fi
APPL=/usr/share/APPLaunch
NEED_REBOOT=0

echo "== packages"
sudo apt-get install -y python3-pil python3-numpy i2c-tools bluez >/dev/null

echo "== files"
chmod +x "$DIR/hexaprobe.py" "$DIR/hexaprobe" "$DIR/hp_nfc_helper.py"
sudo ln -sf "$DIR/hexaprobe" /usr/local/bin/hexaprobe

echo "== 日本語フォント"
if ! python3 "$DIR/hexaprobe.py" --check-font; then
  echo "   字がそろったフォントが無いので fonts-noto-cjk を入れます"
  sudo apt-get install -y fonts-noto-cjk >/dev/null
fi

echo "== permissions (画面/キー/I2C/シリアル/GPIO/NFC/BT)"
for g in video input i2c dialout gpio plugdev bluetooth; do
  if getent group "$g" >/dev/null && ! id -nG "$U" | tr ' ' '\n' | grep -qx "$g"; then
    sudo usermod -aG "$g" "$U"
    NEED_REBOOT=1
  fi
done

echo "== udev (赤外線 /dev/lirc* と NFC リーダー)"
sudo tee /etc/udev/rules.d/60-hexaprobe.rules >/dev/null <<'RULES'
# HEXA PROBE: 赤外線受信 (gpio-ir) を video グループから読めるように
KERNEL=="lirc[0-9]*", GROUP="video", MODE="0660"
# Sony RC-S380 / RC-S330 (nfcpy) — HEXA SIGN と同じ
SUBSYSTEM=="usb", ATTRS{idVendor}=="054c", ATTRS{idProduct}=="06c1", GROUP="plugdev", MODE="0664"
SUBSYSTEM=="usb", ATTRS{idVendor}=="054c", ATTRS{idProduct}=="06c3", GROUP="plugdev", MODE="0664"
SUBSYSTEM=="usb", ATTRS{idVendor}=="054c", ATTRS{idProduct}=="02e1", GROUP="plugdev", MODE="0664"
RULES
if [ ! -f /etc/modprobe.d/blacklist-port100.conf ] && ! grep -rqs "port100" /etc/modprobe.d/; then
  echo "blacklist port100" | sudo tee /etc/modprobe.d/blacklist-port100.conf >/dev/null
  NEED_REBOOT=1
fi
sudo udevadm control --reload-rules 2>/dev/null || true
sudo udevadm trigger 2>/dev/null || true

echo "== nfcpy"
if [ -x "$HOME/nfc/bin/python" ] && "$HOME/nfc/bin/python" -c "import nfc" 2>/dev/null; then
  echo "   ~/nfc の nfcpy を使います (HEXA SIGN と共用)"
elif python3 -c "import nfc" 2>/dev/null; then
  echo "   システムの nfcpy を使います"
else
  echo "   ~/nfc に nfcpy を入れます (ネットが必要。失敗しても他の機能は使えます)"
  sudo apt-get install -y python3-venv >/dev/null || true
  if python3 -m venv "$HOME/nfc" && "$HOME/nfc/bin/pip" install -q nfcpy; then
    echo "   nfcpy OK"
  else
    echo "   nfcpy を入れられませんでした (NFC 以外は使えます)"
  fi
fi

if [ "$1" = "--ir" ]; then
  echo "== 赤外線の受信 (GPIO13 / gpio-ir)"
  CFG=/boot/firmware/config.txt
  [ -f "$CFG" ] || CFG=/boot/config.txt
  if grep -qs "^dtoverlay=gpio-ir" "$CFG"; then
    echo "   すでに有効です ($CFG)"
  else
    sudo cp "$CFG" "$CFG.hexaprobe.bak"
    printf '\n# HEXA PROBE: IR receiver (G13_IR_RX)\ndtoverlay=gpio-ir,gpio_pin=13\n' | sudo tee -a "$CFG" >/dev/null
    echo "   $CFG に追加しました (元は $CFG.hexaprobe.bak)"
    NEED_REBOOT=1
  fi
fi

if [ -d "$APPL/applications" ]; then
  echo "== launcher (APPLaunch)"
  REF="$APPL/share/images/camera1.png"
  [ -f "$REF" ] || REF=64
  python3 "$DIR/make_icon.py" /tmp/hexaprobe.png "$REF"
  sudo install -m 644 /tmp/hexaprobe.png "$APPL/share/images/hexaprobe.png"
  sudo tee "$APPL/applications/hexaprobe.desktop" >/dev/null <<DESK
[Desktop Entry]
Type=Application
Name=HEXA PROBE
Comment=Serial / BLE / NFC / MIDI / I2C / IR probe
Exec=/usr/local/bin/hexaprobe
Icon=share/images/hexaprobe.png
Terminal=false
Categories=Utility;
StartupNotify=false
DESK
  NEED_REBOOT=1
fi

echo "== done"
/usr/local/bin/hexaprobe --probe || true
if [ "$NEED_REBOOT" = 1 ]; then
  echo ""
  echo "*** アイコン追加と権限の反映のため、再起動してください: sudo reboot"
fi
