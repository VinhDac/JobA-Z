#!/usr/bin/env python3
"""Package it into jobbot.app — a real macOS app.

    python3 scripts/make_app.py

Then: drag jobbot.app into the Applications folder. Double-click it like any
other app; it appears in the Dock and in Launchpad, it is cmd-tabbable, and it
has its own icon.

The bundle is only a thin shell calling run.py — the code stays in the project,
so an edit runs straight away with no repackaging.
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
# The shape follows the familiar app icons (GitHub Desktop, Slack…): a solid
# rounded square -> a circle -> a mark inside it. That shape wins because the
# circle cuts the mark clean off the ground, so at 32px the eye still reads a
# shape rather than a blob.
#
# BLACK AND WHITE, and the mark is A KEY — the same mark as the logo inside the
# app (three rings for the bow). The icon in the Dock and the logo on the
# sidebar are ONE name; two different drawings make the user learn it twice.
#
# DRAWN, NEVER TYPED. An earlier version drew the character "◆" in the system
# font: its optical size and baseline are the font's to decide, so a macOS
# upgrade shifts the icon with nothing to say so. A drawing comes out in the
# same proportions at 512px and at 16px.
GROUND, RING, INK = "#0A0A0A", "#FFFFFF", "#0A0A0A"

# To invert it (white ground, black ring, white key), change exactly those three.

ANGLE = -38        # the key's tilt — it runs along the circle's diagonal
RING_RATIO = 0.615 # ring diameter / square side
KEY_RATIO = 0.90   # key length / ring diameter


def _colour(hexa: str):
    from AppKit import NSColor
    h = hexa.lstrip("#")
    return NSColor.colorWithSRGBRed_green_blue_alpha_(
        *[int(h[k:k + 2], 16) / 255 for k in (0, 2, 4)], 1.0)


def _key(L: float, colour) -> None:
    """A key lying flat: from x=0 to x=L, its long axis on y=0.

    Drawn LYING FLAT and left for the caller to rotate. Hard-code already-rotated
    coordinates and changing the angle means recomputing two dozen numbers by hand.

    The three rings of the bow are THICKER than the wide logo inside the app: at
    32px three thin rings merge into one black blob, and the three holes are what
    make this mark a mark.
    """
    from AppKit import NSBezierPath, NSMakeRect
    colour.set()
    r, stroke = L * .105, L * .072
    for cx, cy in ((.115, 0), (.275, .125), (.27, -.125)):
        ring = NSBezierPath.bezierPathWithOvalInRect_(
            NSMakeRect(cx * L - r, cy * L - r, r * 2, r * 2))
        ring.setLineWidth_(stroke)
        ring.stroke()                      # STROKED, not filled — a hole is a real hole
    h = L * .082
    NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(       # the shaft
        NSMakeRect(.29 * L, -h / 2, .71 * L, h), h / 2, h / 2).fill()
    NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(       # the notch
        NSMakeRect(.60 * L, -h / 2, h, L * .20), h / 2, h / 2).fill()
    for x in (.775, .885):                                         # the two teeth
        NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
            NSMakeRect(x * L, -L * .225, h, L * .19), h / 2, h / 2).fill()


def draw_icon(out_dir: Path) -> Path | None:
    """Draw the icon with AppKit (already there), export .icns with iconutil (already there)."""
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
        _colour(GROUND).set()
        NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
            NSMakeRect(pad, pad, size - 2 * pad, size - 2 * pad),
            size * .225, size * .225).fill()

        d = size * RING_RATIO
        _colour(RING).set()
        NSBezierPath.bezierPathWithOvalInRect_(
            NSMakeRect((size - d) / 2, (size - d) / 2, d, d)).fill()

        L = d * KEY_RATIO
        t = NSAffineTransform.transform()
        t.translateXBy_yBy_(size / 2, size / 2)
        t.rotateByDegrees_(ANGLE)
        t.translateXBy_yBy_(-L / 2, 0)     # CENTRED: the key is L long, its middle at L/2
        t.concat()
        _key(L, _colour(INK))
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


# The .app's shell: a thin bash script. The real code stays in the project, so
# an edit runs straight away with no rebuilding of the bundle.
#
# TWO THINGS CAN VANISH after the build, and the old version died SILENTLY on
# both:
#
#   1. The project folder — renamed or moved, and that is that. The old version
#      did `cd ... || exit 1` and left quietly: press the icon, it bounces once,
#      nothing. No message, no log, no way to guess.
#   2. The Python it was built with — the old version baked in `sys.executable`,
#      which on this machine is /opt/anaconda3/bin/python3. Remove Anaconda or
#      upgrade it and the app is dead, while a perfectly usable Python 3.13 sits
#      elsewhere on the same machine.
#
# So: the project path is still baked in (dragging the .app to /Applications
# leaves no way to work it out), but it is CHECKED before use; and Python is
# FOUND at run time, sharing exactly one chooser with start.command.
SHELL_SCRIPT = """#!/bin/bash
# A thin shell — the real code is in the project, so an edit runs straight away.

alert() {
  osascript -e "display alert \\"jobbot\\" message \\"$1\\"" >/dev/null 2>&1
  echo "$1" >&2
  exit 1
}

PROJECT="<PROJECT>"
[ -f "$PROJECT/run.py" ] || alert "The project is not at:

$PROJECT

The folder has been renamed or moved. Open the project folder and run again:
  python3 scripts/make_app.py"

cd "$PROJECT" || alert "Could not enter $PROJECT"

. scripts/find-python.sh
[ -n "$PY" ] || alert "$PYTHON_MISSING"

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
        "CFBundleVersion": "1.0",
        "CFBundleShortVersionString": "1.0",
        "CFBundlePackageType": "APPL",
        "CFBundleExecutable": "jobbot",
        "NSHighResolutionCapable": True,
        "LSMinimumSystemVersion": "12.0",
    }
    if icns:
        info["CFBundleIconFile"] = icns.name
    (contents / "Info.plist").write_bytes(plistlib.dumps(info))

    launcher = macos / "jobbot"
    launcher.write_text(SHELL_SCRIPT.replace("<PROJECT>", str(ROOT)))
    launcher.chmod(0o755)

    subprocess.run(["touch", str(APP)], check=False)     # so Finder picks up the new icon
    print(f"\n  Built: {APP}")
    print(f"  Icon:  {'yes' if icns else 'using the default icon'}")
    print("\n  Drag jobbot.app into /Applications, then double-click it.\n")
    return 0


if __name__ == "__main__":
    sys.exit(build())
