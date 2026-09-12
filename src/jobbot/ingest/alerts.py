"""Việc từ THƯ BÁO của LinkedIn — nguồn thứ ba, và là nguồn sạch nhất.

LinkedIn tự gửi thư báo việc vào hộp thư của Vin. Đọc hộp thư của chính mình
thì không đụng gì tới Điều khoản của ai cả — khác hẳn vòng quét Chrome, vốn
nằm ngoài mục 8.2 và app phải ghi rõ điều đó ở `ingest/web/linkedin.py`.

Ba điểm mạnh, đo trên hộp thư thật ngày 12/09:

    SẠCH   thư gửi cho mình, không cào, không giả làm trình duyệt
    NHANH  LinkedIn gửi trong vài giờ kể từ lúc tin đăng; vòng quét Chrome
           đi hết 80 lượt tìm mất nửa tiếng
    RẺ     381 thư báo, mỗi thư ~6 việc, lọc thẳng trên máy chủ IMAP —
           vài giây, không mở Chrome, không có nhịp nghỉ nào

Điểm yếu, nói luôn: thư báo KHÔNG có mô tả việc. Nó cho chức danh, công ty,
địa điểm và id — đủ để lọc, chưa đủ để chấm điểm. Mô tả vẫn phải do vòng đọc
kỹ mở từng trang mà lấy.

CẤU TRÚC THƯ. Mỗi việc là một thẻ <a> tới /jobs/view/<id>, và ngay sau nó:

    dòng 1   chức danh
    dòng 2   công ty · địa điểm
    dòng 3   nhãn ("Fast growing", "Actively recruiting") — bỏ

Một việc xuất hiện BA lần trong thư (logo, tiêu đề, nút) nhưng chỉ một lần
mang chữ. Nên gom theo id và lấy khối đầu tiên có đủ hai dòng.
"""

from __future__ import annotations

import html as _html
import re

from .base import Posting

NAME = "alert"

# Người gửi thư báo. Gõ tay vì đây là địa chỉ cố định của LinkedIn — đoán
# bằng mẫu chung ("*-noreply@") thì bắt nhầm cả thư từ chối.
SENDER = "jobalerts-noreply@linkedin.com"

# Thẻ <a> trỏ tới một tin. URL trong thư là đường theo dõi dài loằng ngoằng
# (/comm/jobs/view/...?trk=...), nên chỉ bắt lấy ID rồi dựng lại URL sạch —
# y như `linkedin._from_row` đã phải làm với href theo nước.
JOB_LINK = re.compile(r'<a\b[^>]*href="[^"]*?/jobs/view/(\d{6,})[^"]*"[^>]*>')
VIEW = "https://www.linkedin.com/jobs/view/{jid}/"

MOC = "\x01"          # ký tự không bao giờ có trong thư, dùng làm dấu cắt


def parse(html: str) -> list[Posting]:
    """Thân HTML một thư báo -> danh sách tin.

    Thay THẺ bằng XUỐNG DÒNG chứ không bằng khoảng trắng: chức danh và tên
    công ty nằm ở hai phần tử cạnh nhau, không có dấu gì ngăn giữa. Nối bằng
    khoảng trắng thì ra "Data Analyst, Business Intelligence — Entry Level
    Jobright.ai" và không có cách nào tách lại.
    """
    if not html:
        return []
    text = JOB_LINK.sub(MOC + r"\1" + MOC, html)
    text = _html.unescape(re.sub(r"<[^>]+>", "\n", text))

    phan = text.split(MOC)
    thay: dict[str, Posting] = {}
    for i in range(1, len(phan) - 1, 2):
        jid, sau = phan[i], phan[i + 1]
        if not jid.isdigit() or jid in thay:
            continue
        dong = [d.strip() for d in sau.split("\n") if d.strip()][:2]
        if len(dong) < 2 or " · " not in dong[1]:
            continue                      # khối logo/nút — không mang chữ
        cong_ty, _, noi = dong[1].partition(" · ")
        thay[jid] = Posting(
            source_id=jid, title=dong[0][:200],
            company=(cong_ty.strip() or "unknown")[:120],
            location=noi.strip()[:120],
            url=VIEW.format(jid=jid),
            payload={"alert": True})
    return list(thay.values())


def fetch(address: str, password: str, since_days: int = 30,
          limit: int = 200) -> list[Posting]:
    """Mọi việc trong thư báo `since_days` ngày gần nhất.

    Bỏ trùng theo id: cùng một việc nằm trong nhiều thư báo là chuyện thường,
    LinkedIn gửi lại cho tới khi mình bấm vào.
    """
    from ..track import mail
    thu = mail.fetch(address, password, since_days=since_days, limit=limit,
                     sender=SENDER, want_html=True)
    thay: dict[str, Posting] = {}
    for msg in thu:
        for item in parse(msg.get("html") or ""):
            # Thư MỚI ghi đè thư cũ: fetch trả về theo thứ tự hộp thư, lá sau
            # là lá mới hơn, và tin trong đó mới hơn.
            thay[item.source_id] = item
    return list(thay.values())
