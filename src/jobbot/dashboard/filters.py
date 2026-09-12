"""Bộ lọc do NGƯỜI DÙNG điều khiển, trạng thái nằm trong URL.

Khác với `ingest/filter.py`: cái kia chạy lúc quét, quyết định tin nào GIỮ trong DB.
Cái này chạy lúc xem, quyết định tin nào HIỆN ra — không xoá gì, đổi ý là bấm lại.

Trạng thái nằm hết trên URL (`/search?q=quant&show=dropped`) nên:
  - nút Back của trình duyệt chạy đúng
  - lưu được link về đúng bộ lọc đang xem
  - không cần JavaScript, không cần lưu session

Truy vấn LUÔN dùng tham số ràng buộc — không bao giờ nối chuỗi vào SQL.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

# BA LOẠI NÚT KHÁC NHAU, đừng vẽ giống nhau:
#
#   KHO     xem chồng nào          -> chip, loại trừ nhau
#   THANG   có THỨ TỰ              -> THANH MỨC ĐỘ, chọn sàn
#   TAG     loại, không thứ tự     -> chip
#   XẾP     không lọc gì cả        -> chip, tách hẳn ra một hàng
#
# Trước đây cả bốn loại đều là pill xám giống hệt nhau, trộn chung ba hàng:
# 20 nút, không nhìn ra nút nào liên quan nút nào. Nặng nhất là hai cái có
# thứ tự — "Worth applying / Maybe / Long shot" là một THANG, mà vẽ thành ba
# nút rời thì phải đọc hết cả ba mới đoán ra thứ tự.

SHOW = [("matched", "Giữ"), ("dropped", "Đã loại"), ("all", "Tất cả")]
# NƠI CHỐN — tính theo HỒ SƠ, không đóng cứng tên thành phố nào.
#
# "london" và "uk" từng nằm thẳng ở đây, tức là bộ lọc chỉ đúng với đúng MỘT
# người dùng. Giờ id là QUAN HỆ — gần tôi / cả nước / nơi khác — còn chữ hiện
# lên nút thì lấy từ ô "Where you're based".
#
# Đây là chỗ `location` đúng ra phải tác động: nó không quyết định việc nào
# HỢP LỆ (cắt theo London là mất 71 việc UK ngoài London, đo 12/09), nó cho
# một cú bấm để xem việc nào TIỆN.
LOC = [("", "Mọi nơi"), ("near", "Gần tôi"), ("home", "Cả nước"),
       ("remote", "Remote"), ("other", "Nơi khác")]
DAYS = [("", "Mọi lúc"), ("7", "7 ngày"), ("30", "30 ngày"), ("90", "90 ngày")]
SORT = [("score", "Khớp nhất"), ("new", "Mới nhất"), ("old", "Cũ nhất"),
        ("company", "Công ty"), ("title", "Chức danh")]

# --- THANG: giá trị là SÀN, không phải một mức riêng lẻ -------------------
# Chọn "Có thể" nghĩa là có thể TRỞ LÊN — tức là kèm cả "Đáng nộp".
#
# Trước đây là bằng-đúng: chọn "Maybe" thì giấu mất "Worth applying", đúng
# những tin tốt nhất. Không ai muốn thế. Việc thật của người dùng là gạt bớt
# phần dưới, nên sàn mới là phép đúng — và sàn thì vẽ được thành thanh.
CHANCE = [("", "Tất cả"), ("unlikely", "Khó"), ("possible", "Có thể"),
          ("likely", "Đáng nộp")]
CHANCE_RANK = {"unlikely": 1, "possible": 2, "likely": 3}
BAND = [("", "Tất cả"), ("60", "60+"), ("75", "75+")]

# --- TAG ------------------------------------------------------------------
# Dùng "all", KHÔNG dùng chuỗi rỗng: chuỗi rỗng bị coi là "chưa chọn" nên rơi
# về mặc định, và người dùng không có cách nào bảo "cho tôi xem cả hai".
VIA = [("direct", "Chủ trực tiếp"), ("all", "Cả môi giới"), ("agency", "Chỉ môi giới")]
# Tìm bằng CÁCH NÀO. Hai cách tìm mù ở hai chỗ khác nhau, và chúng cho ra hai
# loại tin khác hẳn: board công ty có mô tả đầy đủ, LinkedIn thì phải mở từng
# tin mới có. Lọc được theo cách tìm là soi được ngay cách nào đang đẻ ra rác.
FOUND = [("", "Mọi nguồn"), ("board", "board"), ("linkedin", "linkedin"),
         ("alert", "alert")]

# UK_LIKE ĐÃ BỎ. Nó là bản sao thứ BA của cùng một danh sách địa danh
# (ingest/filter.UK_WORDS, ingest/web/linkedin.MARKET_PLACE, và đây) — ba bản
# rời nhau, lệch nhau mà không ai biết. Giờ đọc chung `ingest.filter.NOI`.


PER_PAGE = 50


@dataclass
class JobFilter:
    """company/source chọn được NHIỀU (ô tích). Còn lại là dải chồng nhau
    hoặc loại trừ nhau nên chọn một (chip)."""
    q: str = ""
    show: str = "matched"
    source: list[str] = field(default_factory=list)
    company: list[str] = field(default_factory=list)
    loc: str = ""
    days: str = ""
    band: str = ""
    via: str = "direct"
    found: str = ""            # tìm bằng cách nào: api / chrome
    raw: str = ""              # "1" = CHỈ xem tin máy chưa đọc được
    chance: str = ""
    sort: str = "score"
    page: int = 1

    # --- đọc từ URL -------------------------------------------------------
    @staticmethod
    def from_query(query: dict[str, list[str]]) -> "JobFilter":
        def one(key: str, default: str = "") -> str:
            return (query.get(key, [default])[0] or default).strip()

        def many(key: str, cap: int) -> list[str]:
            seen, out = set(), []
            for value in query.get(key, []):
                value = value.strip()[:cap]
                if value and value.lower() not in seen:
                    seen.add(value.lower())
                    out.append(value)
            return out[:30]                       # chặn URL bị nhồi vô hạn

        found = JobFilter(
            q=one("q")[:120],
            show=one("show", "matched"),
            source=many("source", 60),
            company=many("company", 80),
            loc=one("loc"),
            days=one("days"),
            band=one("band"),
            via=one("via", "direct"),
            found=one("found"),
            raw="1" if one("raw") else "",
            chance=one("chance"),
            sort=one("sort", "score"),
        )
        try:
            found.page = max(1, int(one("page", "1")))
        except ValueError:
            found.page = 1
        # chỉ nhận giá trị có trong danh sách — phần còn lại vứt
        valid = lambda value, options: value if value in {v for v, _ in options} else ""
        found.show = valid(found.show, SHOW) or "matched"
        found.loc = valid(found.loc, LOC)
        found.days = valid(found.days, DAYS)
        found.band = valid(found.band, BAND)
        found.via = found.via if found.via in {v for v, _ in VIA} else "direct"
        found.found = valid(found.found, FOUND)
        found.chance = valid(found.chance, CHANCE)
        found.sort = valid(found.sort, SORT) or "score"
        return found

    # --- dựng SQL ---------------------------------------------------------
    def where(self, nha: str = "uk", near: str = "") -> tuple[str, list]:
        """`nha` = vùng người dùng đang ở, `near` = thành phố đang ở.

        Hai thứ này là NGỮ CẢNH chứ không phải lựa chọn của người dùng, nên
        chúng không nằm trên URL — chúng đến từ hồ sơ. Để mặc định thì xử như
        UK, y hệt nếp cũ.
        """
        clauses: list[str] = []
        args: list = []

        if self.show == "matched":
            clauses.append("kept = 1")
        elif self.show == "dropped":
            clauses.append("kept = 0")

        if self.q:
            clauses.append("(LOWER(title) LIKE ? OR LOWER(company) LIKE ?)")
            needle = f"%{self.q.lower()}%"
            args += [needle, needle]

        if self.source:
            clauses.append("(" + " OR ".join("source LIKE ?" for _ in self.source) + ")")
            args += [f"{s}%" for s in self.source]

        if self.company:
            marks = ",".join("?" for _ in self.company)
            clauses.append(f"LOWER(company) IN ({marks})")
            args += [c.lower() for c in self.company]

        if self.loc in ("near", "home", "other"):
            from ..ingest.filter import NOI
            vung = NOI.get(nha) or NOI["uk"]
            ca_nuoc = sorted(vung["manh"] | vung["thanh"])
            if self.loc == "near":
                # Hồ sơ chưa khai nơi ở -> "gần tôi" không có nghĩa gì. Không
                # lọc còn hơn lọc theo một chỗ bịa ra.
                if near:
                    clauses.append("LOWER(location) LIKE ?")
                    args.append(f"%{near.lower()}%")
            elif self.loc == "home":
                clauses.append("(" + " OR ".join("LOWER(location) LIKE ?"
                                                 for _ in ca_nuoc) + ")")
                args += [f"%{w}%" for w in ca_nuoc]
            else:
                clauses.append("NOT (" + " OR ".join("LOWER(location) LIKE ?"
                                                     for _ in ca_nuoc) + ")")
                args += [f"%{w}%" for w in ca_nuoc]
        elif self.loc == "remote":
            clauses.append("remote = 1")

        if self.via == "direct":
            clauses.append("via_agency = 0")
        elif self.via == "agency":
            clauses.append("via_agency = 1")
        # "all" -> không thêm điều kiện nào

        # THANG = SÀN. "Có thể" nghĩa là có thể TRỞ LÊN, kèm cả "Đáng nộp".
        # Tin máy chưa đọc được (realism rỗng hoặc 'unknown') xếp hạng 0, nên
        # chọn bất cứ mức nào khác "Tất cả" là nó tự rụng — không cần thêm
        # điều kiện nào, và đó cũng là điều người dùng chờ đợi.
        if self.chance in CHANCE_RANK:
            clauses.append(
                "CASE realism WHEN 'likely' THEN 3 WHEN 'possible' THEN 2"
                " WHEN 'unlikely' THEN 1 ELSE 0 END >= ?")
            args.append(CHANCE_RANK[self.chance])

        if self.band:
            clauses.append("score >= ?")
            args.append(int(self.band))

        if self.found == "alert":
            clauses.append("source = 'alert'")
        elif self.found == "linkedin":
            clauses.append("source = 'linkedin'")
        elif self.found == "board":
            clauses.append("source <> 'linkedin'")

        # MỘT nút thay cho hai. "Can't tell" (chưa đoán được cơ hội) và
        # "Not scorable" (chưa chấm được điểm) nằm ở hai hàng khác nhau, mà
        # đo trên kho thật thì chúng gần như cùng một chồng tin: 185 tin
        # thiếu cả hai, 0 tin chỉ thiếu cơ hội. Cùng một nguyên nhân — vòng
        # đọc kỹ chưa mở tới tin đó nên chưa có mô tả để mà đọc.
        if self.raw:
            clauses.append("(score IS NULL OR COALESCE(realism,'')"
                           " IN ('', 'unknown'))")

        if self.days:
            clauses.append("posted_ts >= ?")
            args.append(int(time.time()) - int(self.days) * 86400)

        return (" WHERE " + " AND ".join(clauses)) if clauses else "", args

    def limit(self) -> tuple[int, int]:
        return PER_PAGE, (self.page - 1) * PER_PAGE

    def order(self) -> str:
        return {"score": "CASE realism WHEN 'likely' THEN 0 WHEN 'possible' THEN 1"
                         " WHEN 'unknown' THEN 2 ELSE 3 END, score DESC NULLS LAST",
                "new": "posted_ts DESC, id DESC", "old": "posted_ts ASC, id ASC",
                "company": "LOWER(company) ASC, LOWER(title) ASC",
                "title": "LOWER(title) ASC"}[self.sort]

    # --- dựng URL ---------------------------------------------------------
    def pairs(self, **changes) -> list[tuple[str, str]]:
        """Trạng thái lọc dưới dạng cặp key/value. MỘT chỗ dựng, hai nơi dùng.

        `url()` nối chúng thành query string cho các chip; ô TÌM đổ chúng ra
        thành <input hidden> để một form GET không làm mất bộ lọc đang bật.
        Hai chỗ tự liệt kê là hai danh sách, và thêm một bộ lọc mới thì có
        ngày quên sửa một bên — lúc đó gõ tìm là mọi chip đang chọn bay sạch.
        """
        state: dict = {"q": self.q, "show": self.show, "source": list(self.source),
                       "company": list(self.company), "loc": self.loc,
                       "days": self.days, "band": self.band, "via": self.via,
                       "found": self.found, "raw": self.raw,
                       "chance": self.chance, "sort": self.sort, "page": self.page}
        # đổi bộ lọc thì về trang 1 — trừ khi chính nó đang đổi trang
        if "page" not in changes:
            state["page"] = ""
        state.update(changes)
        if str(state.get("page", "")) in ("", "1"):
            state["page"] = ""
        default = {"show": "matched", "sort": "score", "via": "direct"}

        out: list[tuple[str, str]] = []
        for key, value in state.items():
            if isinstance(value, list):
                out += [(key, v) for v in value]
            elif value and default.get(key) != value:
                out.append((key, str(value)))
        return out

    def url(self, **changes) -> str:
        from urllib.parse import urlencode
        got = self.pairs(**changes)
        # Danh sách việc nằm trong tab Search — tab Jobs đã bỏ.
        return "/search" + (f"?{urlencode(got)}" if got else "")

    def toggle(self, key: str, value: str) -> str:
        """URL sau khi bật/tắt một ô tích."""
        current = list(getattr(self, key))
        low = [c.lower() for c in current]
        if value.lower() in low:
            current.pop(low.index(value.lower()))
        else:
            current.append(value)
        return self.url(**{key: current})

    def has(self, key: str, value: str) -> bool:
        return value.lower() in [c.lower() for c in getattr(self, key)]

    def active(self) -> list[tuple[str, str]]:
        """Các bộ lọc đang bật, kèm URL để tắt từng cái."""
        out: list[tuple[str, str]] = []
        if self.q:
            out.append((f'"{self.q}"', self.url(q="")))
        if self.show != "matched":
            out.append((dict(SHOW)[self.show], self.url(show="matched")))
        for value in self.source:
            out.append((value, self.toggle("source", value)))
        for value in self.company:
            out.append((value, self.toggle("company", value)))
        if self.loc:
            out.append((dict(LOC)[self.loc], self.url(loc="")))
        if self.days:
            out.append((dict(DAYS)[self.days], self.url(days="")))
        if self.band:
            out.append((dict(BAND)[self.band], self.url(band="")))
        if self.chance:
            out.append((dict(CHANCE)[self.chance], self.url(chance="")))
        if self.via != "direct":
            out.append((dict(VIA)[self.via], self.url(via="direct")))
        if self.found:
            out.append((dict(FOUND)[self.found], self.url(found="")))
        if self.raw:
            out.append(("chưa đọc được", self.url(raw="")))
        return out
