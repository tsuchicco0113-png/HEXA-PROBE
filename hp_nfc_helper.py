#!/usr/bin/env python3
"""HEXA PROBE の NFC 読み取り係 (nfcpy が入った python で動かす。~/nfc/bin/python など)
カードをかざすたびに 1 行の JSON を出す:
  {"ev":"ready","device":...} / {"ev":"tag",...} / {"ev":"removed"} / {"ev":"error","msg":...}
"""
import json
import os
import signal
import sys


def out(**k):
    print(json.dumps(k, ensure_ascii=False), flush=True)


def main():
    try:
        import nfc
    except ImportError as e:
        out(ev="error", msg=f"nfcpy がありません: {e}")
        return 1
    signal.signal(signal.SIGTERM, lambda *_: os._exit(0))
    try:
        clf = nfc.ContactlessFrontend("usb")
    except Exception as e:
        out(ev="error", msg=f"リーダーを開けません: {e}")
        return 1
    out(ev="ready", device=str(clf.device))

    def on_connect(tag):
        info = {"ev": "tag", "type": tag.type, "product": getattr(tag, "product", "") or "",
                "id": tag.identifier.hex().upper(), "ndef": [], "dump": []}
        if tag.type == "Type3Tag":
            try:
                info["pmm"] = tag.pmm.hex().upper()
                info["sys"] = f"{tag.sys:04X}"
            except Exception:
                pass
        try:
            nd = tag.ndef
            if nd:
                info["ndef_info"] = (f"使用 {nd.length}/{nd.capacity} バイト "
                                     + ("書込可" if nd.is_writeable else "書込不可"))
                for r in nd.records:
                    info["ndef"].append({"type": r.type, "text": str(r)[:200]})
        except Exception as e:
            info["ndef_info"] = f"NDEF 読めず: {e}"
        try:
            info["dump"] = [str(x) for x in tag.dump()][:120]
        except Exception as e:
            info["dump"] = [f"(ダンプ失敗: {e})"]
        out(**info)
        return True                         # 離すまで待つ

    try:
        while True:
            ok = clf.connect(rdwr={"on-connect": on_connect, "beep-on-connect": False})
            if not ok:
                break
            out(ev="removed")
    except Exception as e:
        out(ev="error", msg=str(e))
    finally:
        clf.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
