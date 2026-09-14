#!/usr/bin/env python3
"""Đóng gói thành jobbot.app — app macOS đúng nghĩa.

    python3 scripts/make_app.py

Sau đó: kéo jobbot.app vào thư mục Applications. Bấm đúp như mọi app khác,
hiện ở Dock, ở Launchpad, cmd-tab được, có icon riêng.

Bundle chỉ là vỏ mỏng gọi run.py — code vẫn nằm trong dự án, sửa là chạy ngay,
không phải đóng gói lại.
"""

from __future__ import annotations

import plistlib
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / "jobbot.app"
BUNDLE_ID = "com.jobbot.app"


# --- ICON -----------------------------------------------------------------
#
# Khuôn giống icon app quen thuộc (GitHub Desktop, Slack…): ô bo tròn đặc →
# vòng tròn → dấu hiệu bên trong. Khuôn đó thắng vì cái vòng tròn cắt hẳn dấu
# hiệu ra khỏi nền, nên ở 32px mắt vẫn bắt được hình chứ không thấy một cục.
#
# ĐEN TRẮNG, và dấu hiệu là CHÌA KHOÁ — cùng dấu với logo trong app (ba vòng
# làm tay cầm). Icon ở Dock và logo trên thanh bên phải là MỘT cái tên; hai
# hình khác nhau thì người dùng phải học hai lần.
#
# VẼ BẰNG HÌNH, KHÔNG DÙNG KÝ TỰ. Bản trước vẽ ký tự "◆" bằng font hệ thống:
# cỡ quang học và baseline do font quyết định, nên đổi macOS là icon xê dịch,
# mà không có gì báo. Hình thì 512px hay 16px cũng ra đúng một tỉ lệ.
NEN, VONG, NET = "#0A0A0A", "#FFFFFF", "#0A0A0A"

# Đảo lại (nền trắng, vòng đen, chìa trắng) thì đổi đúng ba hằng số trên.

GOC = -38          # độ nghiêng của chìa — dùng đường chéo của vòng tròn
TI_VONG = 0.615    # đường kính vòng / cạnh ô
TI_KHOA = 0.90     # chiều dài chìa / đường kính vòng


def _mau(hexa: str):
    from AppKit import NSColor
    h = hexa.lstrip("#")
    return NSColor.colorWithSRGBRed_green_blue_alpha_(
        *[int(h[k:k + 2], 16) / 255 for k in (0, 2, 4)], 1.0)


def _khoa(L: float, mau) -> None:
    """Chìa khoá nằm ngang: từ x=0 tới x=L, trục dọc ở y=0.

    Vẽ ở tư thế NẰM NGANG rồi để người gọi xoay. Gõ cứng toạ độ đã xoay thì
    đổi góc một cái là phải tính lại cả hai chục con số bằng tay.

    Ba vòng tay cầm DÀY HƠN logo ngang trong app: ở 32px ba vòng mảnh dính
    vào nhau thành một cục đen, và cái làm nên dấu hiệu này là ba cái lỗ.
    """
    from AppKit import NSBezierPath, NSMakeRect
    mau.set()
    r, net = L * .105, L * .072
    for cx, cy in ((.115, 0), (.275, .125), (.27, -.125)):
        vong = NSBezierPath.bezierPathWithOvalInRect_(
            NSMakeRect(cx * L - r, cy * L - r, r * 2, r * 2))
        vong.setLineWidth_(net)
        vong.stroke()                      # NÉT, không tô — lỗ là lỗ thật
    h = L * .082
    NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(       # thân
        NSMakeRect(.29 * L, -h / 2, .71 * L, h), h / 2, h / 2).fill()
    NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(       # khấc
        NSMakeRect(.60 * L, -h / 2, h, L * .20), h / 2, h / 2).fill()
    for x in (.775, .885):                                         # hai răng
        NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
            NSMakeRect(x * L, -L * .225, h, L * .19), h / 2, h / 2).fill()


def draw_icon(out_dir: Path) -> Path | None:
    """Vẽ icon bằng AppKit (có sẵn), xuất .icns bằng iconutil (có sẵn)."""
    try:
        from AppKit import (NSAffineTransform, NSBezierPath, NSBitmapImageRep,
                            NSImage, NSMakeRect, NSPNGFileType)
        from Foundation import NSMakeSize
    except ImportError:
        return None

    iconset = out_dir / "jobbot.iconset"
    iconset.mkdir(parents=True, exist_ok=True)

    def render(size: int) -> bytes:
        image = NSImage.alloc().initWithSize_(NSMakeSize(size, size))
        image.lockFocus()
        pad = size * .085
        _mau(NEN).set()
        NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
            NSMakeRect(pad, pad, size - 2 * pad, size - 2 * pad),
            size * .225, size * .225).fill()

        d = size * TI_VONG
        _mau(VONG).set()
        NSBezierPath.bezierPathWithOvalInRect_(
            NSMakeRect((size - d) / 2, (size - d) / 2, d, d)).fill()

        L = d * TI_KHOA
        t = NSAffineTransform.transform()
        t.translateXBy_yBy_(size / 2, size / 2)
        t.rotateByDegrees_(GOC)
        t.translateXBy_yBy_(-L / 2, 0)     # CĂN TÂM: chìa dài L, tâm ở L/2
        t.concat()
        _khoa(L, _mau(NET))
        image.unlockFocus()

        rep = NSBitmapImageRep.imageRepWithData_(image.TIFFRepresentation())
        return bytes(rep.representationUsingType_properties_(NSPNGFileType, None))

    for size in (16, 32, 128, 256, 512):
        (iconset / f"icon_{size}x{size}.png").write_bytes(render(size))
        (iconset / f"icon_{size}x{size}@2x.png").write_bytes(render(size * 2))

    icns = out_dir / "jobbot.icns"
    done = subprocess.run(["iconutil", "-c", "icns", str(iconset), "-o", str(icns)],
                          capture_output=True, text=True)
    shutil.rmtree(iconset, ignore_errors=True)
    return icns if done.returncode == 0 else None


# Vỏ của .app: một kịch bản bash mỏng, code thật nằm trong dự án nên sửa code
# là chạy ngay, không phải dựng lại bundle.
#
# HAI THỨ BIẾN MẤT ĐƯỢC sau khi dựng, và cũ thì cả hai đều chết CÂM:
#
#   1. Thư mục dự án — đổi tên hay chuyển chỗ là xong. Bản cũ `cd ... || exit 1`
#      rồi thoát lặng lẽ: bấm icon, icon nảy một cái, hết. Không thông báo,
#      không log, không cách nào đoán.
#   2. Python đã dựng bằng — bản cũ nướng cứng `sys.executable`, ở máy này là
#      /opt/anaconda3/bin/python3. Gỡ Anaconda hay nâng cấp nó là app chết,
#      trong khi máy vẫn còn Python 3.13 chỗ khác dùng được.
#
# Nên: đường dự án vẫn nướng vào (kéo .app sang /Applications thì không tự suy
# ra được), nhưng KIỂM TRA rồi mới dùng; còn Python thì đi TÌM lúc chạy, dùng
# chung đúng một bản chọn với start.command.
VO = """#!/bin/bash
# Vỏ mỏng — code thật nằm trong dự án, sửa là chạy ngay.

keu() {
  osascript -e "display alert \\"jobbot\\" message \\"$1\\"" >/dev/null 2>&1
  echo "$1" >&2
  exit 1
}

DU_AN="<DU_AN>"
[ -f "$DU_AN/run.py" ] || keu "Không thấy dự án ở:

$DU_AN

Thư mục đã bị đổi tên hoặc chuyển chỗ. Mở thư mục dự án rồi chạy lại:
  python3 scripts/make_app.py"

cd "$DU_AN" || keu "Không vào được $DU_AN"

. scripts/tim-python.sh
[ -n "$PY" ] || keu "$THIEU_PYTHON"

exec "$PY" run.py "$@"
"""


def build() -> int:
    contents = APP / "Contents"
    macos, resources = contents / "MacOS", contents / "Resources"
    if APP.exists():
        shutil.rmtree(APP)
    macos.mkdir(parents=True)
    resources.mkdir(parents=True)

    icns = draw_icon(resources)

    info = {
        "CFBundleName": "jobbot",
        "CFBundleDisplayName": "jobbot",
        "CFBundleIdentifier": BUNDLE_ID,
        "CFBundleVersion": "0.1",
        "CFBundleShortVersionString": "0.1",
        "CFBundlePackageType": "APPL",
        "CFBundleExecutable": "jobbot",
        "NSHighResolutionCapable": True,
        "LSMinimumSystemVersion": "12.0",
    }
    if icns:
        info["CFBundleIconFile"] = icns.name
    (contents / "Info.plist").write_bytes(plistlib.dumps(info))

    launcher = macos / "jobbot"
    launcher.write_text(VO.replace("<DU_AN>", str(ROOT)))
    launcher.chmod(0o755)

    subprocess.run(["touch", str(APP)], check=False)     # để Finder nhận icon mới
    print(f"\n  Đã dựng: {APP}")
    print(f"  Icon:    {'có' if icns else 'dùng icon mặc định'}")
    print("\n  Kéo jobbot.app vào /Applications rồi bấm đúp.\n")
    return 0


if __name__ == "__main__":
    sys.exit(build())
