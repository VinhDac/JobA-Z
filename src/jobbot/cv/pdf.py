"""In một bản CV ra PDF — bằng chính Chrome đã có, không thêm thư viện.

Vì sao không dùng reportlab/weasyprint: cả app là stdlib, và thêm một bộ dựng
PDF nghĩa là có HAI cách vẽ cùng một tờ CV — bản màn hình và bản giấy sẽ trôi
xa nhau, mà bản giấy mới là bản nhà tuyển dụng đọc.

Chrome in ĐÚNG trang đang hiển thị, qua `@media print` trong app.css. Một
nguồn sự thật cho cả hai.

Chạy Chrome HEADLESS ở cổng riêng: cổng 9333 là của vòng quét, đang mở cửa sổ
thật để đọc LinkedIn. Bấm nút In mà cướp mất tab của vòng quét là hỏng việc
đang chạy.
"""

from __future__ import annotations

import base64
import re
import threading
from pathlib import Path

from ..browser import cdp, chrome
from ..core.journal import CV, log as jlog

PORT = chrome.PDF_PORT   # cổng RIÊNG, profile RIÊNG — xem chrome.PROFILE

# MỘT lượt in tại một thời điểm. Cả in-một-bản lẫn in-hàng-loạt đều mở rồi TẮT
# Chrome ở cổng này; chạy chồng thì luồng xong trước tắt Chrome của luồng kia,
# và 37 bản còn lại im lặng không được in.
_ONE_AT_A_TIME = threading.Lock()

PAPER = {                                    # A4, lề 14mm — khớp @page trong CSS
    "paperWidth": 8.27, "paperHeight": 11.69,
    "marginTop": 0.55, "marginBottom": 0.55,
    "marginLeft": 0.59, "marginRight": 0.59,
    "printBackground": False,                # nền tối của app không được in ra
    "preferCSSPageSize": True,
}


def slug(text: str) -> str:
    keep = re.sub(r"[^A-Za-z0-9]+", "-", text).strip("-").lower()
    return keep[:60] or "cv"


# --- KIỂM CHẤT LƯỢNG NGAY TRƯỚC KHI IN ---------------------------------
#
# Ba lỗi dưới đây đều ĐÃ XẢY RA THẬT, và đều chỉ lộ ra khi in một tờ rồi mở
# ảnh lên nhìn — test HTML không bắt được cái nào:
#
#   rác app    thanh trạng thái in đè lên dòng cuối, mang cả đường dẫn tệp
#              trên máy ("PDF: /Users/davi/…") ra tờ giấy gửi nhà tuyển dụng;
#              tiêu đề cửa sổ in thành dòng đầu tiên
#   chữ nhợt   luật màu in liệt kê từng lớp cần tô đen, nên lớp nào quên thì
#              giữ màu giao diện TỐI — đo được .cvskill ở 192/255, tức là cả
#              mục TECHNICAL SKILLS gần như vô hình trên giấy trắng
#   lệch lề    `main` là position:fixed left:226px (chừa chỗ thanh bên); khi
#              in, Chrome đặt phần tử fixed theo hộp trang và left không ghi
#              đè được — tờ CV bị đẩy vào giữa, phí một phần tư mặt giấy
#
# Nên kiểm NGAY TRÊN TRANG SẮP IN, không kiểm trên chuỗi HTML. Không chặn in
# — vẫn ra tệp, nhưng nói thẳng tờ giấy đang hỏng chỗ nào.
SANG_NHAT = 90          # 0 = đen. Chữ nhạt hơn ngần này thì in ra đọc không rõ.

_SOI = r"""(() => {
  const den = c => { const m = c.match(/\d+/g); return m ? (+m[0] + +m[1] + +m[2]) / 3 : 255 };
  const to = document.querySelector('.cvpaper');
  if (!to) return JSON.stringify(['không tìm thấy tờ CV (.cvpaper) trên trang']);
  const loi = [];

  // 1. RÁC APP: phần tử có chữ, đang hiện, mà KHÔNG nằm trong tờ CV.
  for (const e of document.querySelectorAll('body *')) {
    if (to.contains(e) || e.contains(to)) continue;
    if (e.children.length || !e.textContent.trim()) continue;
    const r = e.getBoundingClientRect();
    if (r.width < 1 || r.height < 1) continue;
    if (getComputedStyle(e).visibility === 'hidden') continue;
    loi.push('rác app in ra: ' + (e.className || e.tagName) + ' «'
             + e.textContent.trim().slice(0, 40) + '»');
    if (loi.length > 4) break;
  }

  // 2. CHỮ NHỢT trong chính tờ CV.
  let nhat = 0, ai = '';
  for (const e of to.querySelectorAll('*')) {
    if (e.children.length || !e.textContent.trim()) continue;
    const v = den(getComputedStyle(e).color);
    if (v > nhat) { nhat = v; ai = (e.className || e.tagName) + ' «'
                                  + e.textContent.trim().slice(0, 30) + '»' }
  }
  if (nhat > SANG_NHAT) loi.push('chữ quá nhợt (' + Math.round(nhat) + '/255): ' + ai);

  // 3. LỆCH LỀ: tờ CV phải bắt đầu ở mép trái và dùng gần hết bề ngang.
  const p = to.getBoundingClientRect(), W = document.documentElement.clientWidth;
  if (p.left > 8) loi.push('tờ CV lệch vào ' + Math.round(p.left) + 'px — phí lề trái');
  if (p.width < W * 0.9) loi.push('tờ CV chỉ rộng ' + Math.round(p.width / W * 100) + '% mặt giấy');
  return JSON.stringify(loi);
})()"""


def kiem(tab) -> list[str]:
    """Soi TRANG SẮP IN. Trả về danh sách chỗ hỏng, rỗng là sạch.

    CHÍNH CỔNG NÀY HỎNG THÌ PHẢI KÊU. Bản đầu dùng `_SOI % SANG_NHAT` để nhét
    ngưỡng vào, mà chuỗi JS có ký tự `%` thật ('% mặt giấy') — Python ném
    ValueError, `except` nuốt mất, và cổng báo "sạch" ở mọi lượt in. Một cổng
    kiểm im lặng báo sạch khi chính nó gãy thì tệ hơn là không có cổng nào.
    """
    import json
    tab.call("Emulation.setEmulatedMedia", {"media": "print"})
    js = _SOI.replace("SANG_NHAT", str(SANG_NHAT))
    try:
        return json.loads(tab.eval(js)) or []
    except Exception as exc:            # noqa: BLE001
        return [f"KHÔNG SOI ĐƯỢC tờ in ({type(exc).__name__}: {exc}) — "
                f"không ai kiểm tờ giấy này"]


def _print_one(tab, url: str, out: Path, timeout: float) -> Path:
    tab.go(url, wait_for=".cvpaper", timeout=timeout)
    for loi in kiem(tab):
        jlog.warn(CV, f"tờ CV in ra có vấn đề — {loi}")
    reply = tab.call("Page.printToPDF", PAPER, timeout=timeout)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(base64.b64decode(reply["data"]))
    return out


def render(url: str, out: Path, timeout: float = 45.0) -> Path:
    """In MỘT bản."""
    return next(iter(render_many([(url, out)], timeout=timeout)))


def render_many(jobs, timeout: float = 45.0, on_done=None):
    """In NHIỀU bản, dùng chung MỘT Chrome và MỘT tab.

    Mở/tắt Chrome chiếm gần hết thời gian một lần in. Mở lại cho từng bản thì
    41 bản mất mấy phút và bật tắt Chrome 41 lần; giữ một tab rồi điều hướng
    liên tiếp thì phần cố định trả đúng một lần.

    `jobs` = [(url, đường dẫn ra)]. `on_done(i, tổng, đường dẫn)` để báo tiến độ.
    """
    jobs = list(jobs)
    if not jobs:
        return []
    with _ONE_AT_A_TIME:
        return _render_all(jobs, timeout, on_done)


def _render_all(jobs, timeout, on_done):
    started = chrome.launch(headless=True, port=PORT)
    tab = cdp.open_tab("about:blank", port=PORT)
    made = []
    try:
        for index, (url, out) in enumerate(jobs, 1):
            try:
                made.append(_print_one(tab, url, Path(out), timeout))
            except Exception:                       # noqa: BLE001
                # Một bản hỏng KHÔNG được làm chết cả lô. Bản còn lại vẫn in.
                made.append(None)
            if on_done:
                on_done(index, len(jobs), made[-1])
    finally:
        try:
            tab.close()
        finally:
            if started is not None:
                chrome.shutdown(port=PORT)
    return [m for m in made if m]


# --- GIAO TỆP TẬN TAY ---------------------------------------------------

def tai_ve(src: Path) -> Path | None:
    """Chép bản vừa in sang ~/Downloads rồi mở Finder trỏ vào nó.

    VÌ SAO KHÔNG DÙNG LINK TẢI. Vỏ app là WKWebView (xem app.py), mà WKWebView
    KHÔNG tự tải tệp: không có WKDownloadDelegate thì `Content-Disposition:
    attachment` không xảy ra chuyện gì cả — bấm nút, im lặng, không có tệp,
    không có lỗi. Kiểm bằng cách đọc app.py: ở đó chỉ khai delegate cho hộp
    chọn tệp và cho cửa sổ mới.

    Mà đây là app CHẠY TRÊN MÁY MÌNH: tệp đã nằm sẵn trên đĩa rồi. Thứ còn
    thiếu chỉ là đưa nó ra chỗ người ta tìm được. Nên chép sang Downloads và
    mở Finder — làm được ngay, chạy đúng ở cả hai vỏ, không phải viết delegate
    PyObjC nào.

    BẢN GỐC Ở LẠI `data/cv/`: vòng nộp đơn tìm tệp đính kèm ở đó
    (live.cv_pdf_for). Chuyển hẳn đi là làm chết đường nộp.
    """
    import shutil
    import subprocess
    if not src.exists():
        return None
    dest_dir = Path.home() / "Downloads"
    if not dest_dir.is_dir():
        return None
    dest = dest_dir / src.name
    # Trùng tên thì thêm số, KHÔNG đè: bản cũ có thể đang mở, hoặc đã gửi đi
    # rồi và người ta còn cần đối chiếu.
    if dest.exists():
        for i in range(2, 100):
            thu = dest_dir / f"{src.stem}-{i}{src.suffix}"
            if not thu.exists():
                dest = thu
                break
    shutil.copy2(src, dest)
    try:
        # -R: hiện Finder và CHỌN SẴN tệp, không chỉ mở thư mục. Người dùng
        # thấy ngay tệp nào vừa ra, kéo thẳng vào ô đính kèm của đơn.
        subprocess.run(["open", "-R", str(dest)], check=False,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       timeout=10)
    except (OSError, subprocess.SubprocessError):
        pass                      # không mở được Finder thì tệp vẫn nằm đó
    return dest

