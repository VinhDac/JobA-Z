"""Dữ liệu THẬT từ DB.

mock.py đã bị xoá hẳn — không còn số bịa nào trong app.
Đó là lý do trang không phải sửa gì khi chuyển từ giả sang thật.

Đã nối thật:  run_status · counters · jobs · job_detail · activity
Còn dùng giả: proposals · stats   (bước 5-6)
"""

from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path
from datetime import datetime, timezone

from ..core import postings


STALE_DAYS = 45          # quá ngần này thì nhiều khả năng đã tuyển xong


def _age_days(ts: int) -> int | None:
    """Tin đăng bao nhiêu ngày rồi. None = không biết ngày."""
    if not ts:
        return None
    return int((datetime.now(timezone.utc).timestamp() - ts) // 86400)


def _ago(stamp: str) -> str:
    """Nguồn trả ngày theo 2 kiểu: ISO (Greenhouse/Lever) và Unix (Arbeitnow)."""
    if not stamp:
        return ""
    try:
        then = (datetime.fromtimestamp(int(stamp), timezone.utc)
                if str(stamp).isdigit() else datetime.fromisoformat(stamp))
        if then.tzinfo is None:
            then = then.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError, OSError, OverflowError):
        return ""
    seconds = (datetime.now(timezone.utc) - then).total_seconds()
    if seconds < 90:
        return "just now"
    if seconds < 5400:
        return f"{int(seconds // 60)} min ago"
    if seconds < 172800:
        return f"{int(seconds // 3600)} hours ago"
    return f"{int(seconds // 86400)} days ago"


def dem_chip(conn: sqlite3.Connection, flt) -> dict:
    """Mỗi lựa chọn lọc ra BAO NHIÊU TIN, tính theo bộ lọc ĐANG bật.

    Vì sao cần: đo trên kho thật, chip "Gần tôi" cho ra 411 tin — đúng bằng
    "Mọi nơi". Bấm vào không đổi gì cả. "Cả nước" ra 407/411, "Chủ trực tiếp"
    ra đúng con số mặc định. Ba nút bấm vào thấy y nguyên, và người dùng thôi
    tin cả hàng nút.

    Sửa bằng cách GHI SỐ RA, không phải xoá nút: con số nói thẳng bấm vào
    được gì, và nó nói đúng theo dữ liệu HÔM NAY — hôm khác kho khác thì con
    số tự đổi, không cần ai đi sửa lại danh sách nút.

    Đếm THEO NGỮ CẢNH (chồng lên bộ lọc đang bật), vì đó mới là câu người dùng
    hỏi: "đang lọc thế này, bấm thêm cái kia thì còn mấy tin".

    Giá: 26 lượt COUNT, đo được 107ms trên kho 5.166 tin.
    """
    from .filters import BAND, CHANCE, DAYS, FOUND, LOC, SHOW, VIA, JobFilter
    nha, gan = noi_toi(conn)
    ra: dict = {}
    for khoa, bang in (("chance", CHANCE), ("band", BAND), ("loc", LOC),
                       ("found", FOUND), ("via", VIA), ("days", DAYS),
                       ("show", SHOW)):
        for val, _ in bang:
            doi = flt.pairs(**{khoa: val, "page": ""})
            moi = JobFilter.from_query({k: [v] for k, v in doi if v != ""})
            w, args = moi.where(nha=nha, near=gan)
            ra[f"{khoa}:{val}"] = int(conn.execute(
                f"SELECT COUNT(*) FROM posting{w}", args).fetchone()[0])
    return ra


def sieve(conn: sqlite3.Connection) -> dict:
    """Lưới GIỮ/BỎ — đúng ba thứ mà ingest/filter.judge() thật sự dùng.

    KHÔNG bịa thêm núm: judge() chỉ nhìn chức danh, cấp bậc, địa điểm. Thêm ô
    cho thứ code không đọc là dựng nút giả.

    Ba giá trị này nằm trong HỒ SƠ, không phải setting riêng của Search — nên
    sửa ở đây đổi cả vòng lọc, cả từ khoá gửi cho LinkedIn, lẫn phần chấm
    điểm theo chức danh.
    """
    from ..core import prefs
    from ..profile.schema import section_by_id
    from ..profile import store as pstore

    answers = pstore.load(conn)
    opts = {}
    for section in ("muc_tieu",):
        found = section_by_id(section)
        for q in (found.questions if found else []):
            if q.id in ("seniority", "markets"):
                opts[q.id] = [(o.value, o.label) for o in (q.options or [])]

    total = int(conn.execute("SELECT COUNT(*) FROM posting").fetchone()[0])
    return {
        "titles": [t.strip() for t in (answers.get("job_titles") or "").splitlines()
                   if t.strip()],
        "seniority": answers.get("seniority") or [],
        "markets": answers.get("markets") or [],
        "seniority_options": opts.get("seniority", []),
        "market_options": opts.get("markets", []),
        "missed": missed_titles(conn),
        # Công tắc nguồn — KHÔNG phải hồ sơ, nên nó không đi qua nút Áp dụng
        # và không làm phán lại 5.000 tin. Chỉ là hai cái công tắc của máy.
        "src_board": prefs.flag(conn, prefs.SRC_BOARD),
        "src_linkedin": prefs.flag(conn, prefs.SRC_LINKEDIN),
        "src_alert": prefs.flag(conn, prefs.SRC_ALERT),
        "total": total,
        # Đo thật trên 4.660 tin: 1,1 giây. Làm tròn lên để câu hứa không hụt.
        "seconds": max(1, round(total / 4000)),
    }


def noi_toi(conn: sqlite3.Connection) -> tuple[str, str]:
    """(vùng đang ở, thành phố đang ở) — ngữ cảnh cho bộ lọc nơi chốn.

    Đọc từ ô "Where you're based". Đây là chỗ `location` tác động tới việc
    XEM: nó không quyết định việc nào hợp lệ (cắt theo London là mất 71 việc
    UK ngoài London), nó cho bạn một cú bấm để xem việc nào TIỆN.
    """
    from ..ingest.filter import noi_o
    from ..profile import store
    o_dau = (store.load(conn).get("location") or "").strip()
    # "London, UK" -> "London". Lấy nguyên chuỗi đem so LIKE thì không tin
    # nào khớp, vì tin ghi "London, England, United Kingdom".
    return noi_o(o_dau) or "uk", o_dau.split(",")[0].strip()


def jobs(conn: sqlite3.Connection, flt) -> list[dict]:
    """Lọc theo ý người dùng, RỒI mới gộp trùng — gộp trước thì lọc sai nhóm.

    LỖI ĐÃ SỬA: gộp bằng Python SAU khi đã LIMIT theo DÒNG. Trang thì cắt theo
    dòng, còn số đếm trên đầu trang lại đếm theo NHÓM, nên hai bên không bao
    giờ khớp: trên máy thật đầu trang ghi 139 việc, đi hết các trang đếm được
    144 thẻ — 5 nhóm bị cắt đôi qua ranh giới trang và hiện thành hai thẻ.
    Gộp phải xảy ra TRONG SQL, trước khi cắt trang.
    """
    where, args = flt.where(*noi_toi(conn))
    per, offset = flt.limit()
    rows = conn.execute(
        # `ca_nhom` đếm CẢ nhóm, trên bảng CHƯA lọc. Badge "◆ api ⌕ chrome" và
        # số "+1 nơi" nói về CÁI TIN, không nói về bộ lọc đang bật — tính
        # chúng từ phần đã lọc thì bấm tag nguồn LinkedIn một cái là tin Man Group
        # rụng mất badge board và tụt từ "+1 nơi" xuống không còn gì, tức là màn
        # hình khai man về chính cái tin nó đang hiện.
        # LUẬT: bộ lọc chọn HIỆN TIN NÀO, không bao giờ đổi TIN TRÔNG RA SAO.
        #
        # Nên mọi thứ mô tả cái tin — badge nguồn, "+1 nơi", điểm, chức danh —
        # đều tính trên CẢ nhóm, trên bảng chưa lọc. Trước đây chúng tính trên
        # phần đã lọc, nên bấm tag nguồn LinkedIn một cái là tin Man Group rụng mất
        # badge api, mất "+1 nơi", và mất luôn cả điểm 100 (vì dòng LinkedIn
        # của nó chưa được đọc kỹ nên chưa có điểm). Cùng một việc, hai bộ lọc,
        # hai bộ mặt — màn hình khai man về chính cái tin nó đang hiện.
        #
        # `hop` chỉ còn một việc: nhóm nào có ÍT NHẤT MỘT dòng lọt lưới.
        "WITH ca_nhom AS ("
        "  SELECT COALESCE(group_id, CAST(id AS TEXT)) AS grp,"
        "         COUNT(*) AS n, GROUP_CONCAT(source) AS srcs"
        "    FROM posting GROUP BY 1),"
        "hop AS ("
        f"  SELECT DISTINCT COALESCE(group_id, CAST(id AS TEXT)) AS grp"
        f"    FROM posting{where})"
        "SELECT day.*, ca_nhom.n AS merged, ca_nhom.srcs AS all_sources FROM ("
        "  SELECT *,"
        # Đại diện nhóm = tin chấm cao nhất, không phải tin gặp trước.
        "         ROW_NUMBER() OVER (PARTITION BY grp"
        "                            ORDER BY score DESC NULLS LAST, id ASC) AS rn"
        "    FROM (SELECT *, COALESCE(group_id, CAST(id AS TEXT)) AS grp"
        "            FROM posting)"
        ") AS day JOIN ca_nhom USING (grp) JOIN hop USING (grp)"
        f" WHERE rn = 1 ORDER BY {flt.order()} LIMIT ? OFFSET ?",
        [*args, per, offset]).fetchall()

    out = []
    for row in rows:
        sources = list(dict.fromkeys((row["all_sources"] or "").split(",")))
        # Cách nào tìm ra tin này. Đây là badge quan trọng nhất trên mỗi dòng:
        # hai cách tìm mù ở hai chỗ khác nhau, nên nhìn danh sách là thấy ngay
        # cách nào đang mang về cái gì. Tin cả hai cùng thấy -> hai badge.
        found_by = sorted({s if s in ("linkedin", "alert") else "board"
                           for s in sources if s})
        out.append({
            "id": str(row["id"]),
            "title": row["title"], "company": row["company"],
            "location": row["location"] or "not stated",
            "salary": row["salary"] or "not stated",
            "score": row["score"],
            "confidence": row["score_conf"],
            "posted": _ago(row["posted_at"]) if row["posted_at"] else "",
            "age_days": _age_days(row["posted_ts"]),
            "sources": [s for s in sources if s],
            "found_by": found_by,
            "merged": row["merged"],
            "state": "new" if row["kept"] else "dropped",
            "user_keep": bool(row["user_keep"]),
            "via_agency": bool(row["via_agency"]),
            "realism": row["realism"], "realism_why": row["realism_why"],
            "deadline": row["deadline"],
            "drop_reason": row["drop_reason"],
            "url": row["url"],
        })
    return out


def job_counts(conn: sqlite3.Connection, flt) -> dict:
    """Số lượng cho từng lựa chọn 'Show' — người dùng thấy trước khi bấm."""
    out = {}
    noi = noi_toi(conn)          # đọc MỘT lần cho cả ba lượt đếm
    for value, _label in (("matched", ""), ("dropped", ""), ("all", "")):
        where, args = type(flt)(**{**flt.__dict__, "show": value}).where(*noi)
        out[value] = int(conn.execute(
            f"SELECT COUNT(DISTINCT COALESCE(group_id, CAST(id AS TEXT)))"
            f" FROM posting{where}", args).fetchone()[0])
    return out


def facets(conn: sqlite3.Connection) -> dict:
    """Giá trị có thật trong DB để đổ vào dropdown — không bịa lựa chọn rỗng."""
    sources = [r["s"] for r in conn.execute(
        "SELECT DISTINCT substr(source, 1, CASE WHEN instr(source,':')>0"
        " THEN instr(source,':')-1 ELSE length(source) END) AS s"
        " FROM posting ORDER BY s")]
    companies = [(r["company"], r["n"]) for r in conn.execute(
        "SELECT company, COUNT(*) n FROM posting WHERE kept=1"
        " GROUP BY company ORDER BY n DESC, LOWER(company) LIMIT 40")]
    return {"sources": sources, "companies": companies}


def job_detail(conn: sqlite3.Connection, job_id: str) -> dict | None:
    row = conn.execute("SELECT * FROM posting WHERE id = ?", (job_id,)).fetchone()
    if row is None:
        return None
    same = conn.execute(
        "SELECT source, url FROM posting WHERE group_id = ? ORDER BY id",
        (row["group_id"] or str(row["id"]),)).fetchall()
    return {
        "id": str(row["id"]), "title": row["title"], "company": row["company"],
        "location": row["location"] or "not stated",
        "salary": row["salary"] or "not stated",
        "score": row["score"], "confidence": row["score_conf"],
        "realism": row["realism"], "realism_why": row["realism_why"],
        "deadline": row["deadline"],
        "posted": _ago(row["posted_at"]) if row["posted_at"] else "",
        "sources": sorted({r["source"] for r in same}),
        "merged": len(same), "url": row["url"],
        "links": _links(same, row["url"]),
        "jd": row["description"] or "(no description from this source)",
        "requirements": _reqs(row),
        "explain": json.loads(row["score_json"]) if row["score_json"] else None,
        "score_json": row["score_json"],
        "project": None,                        # bước 4
    }


def _links(same, url_minh: str) -> list[dict]:
    """Đường tới TIN GỐC. Một việc đăng ở hai nơi thì trả về cả hai.

    Cho tới giờ `job_detail` lấy về đủ (nguồn, url) rồi VỨT phần url đi, chỉ
    giữ lại tên nguồn và con số "+1 nơi". Nên màn hình chi tiết đọc được cả
    bản mô tả mà không có lấy một đường nào để sang xem tin thật — muốn kiểm
    chứng thì phải tự đi tìm bằng tay.

    BOARD CÔNG TY ĐỨNG TRƯỚC. LinkedIn chỉ là bảng tin: nộp qua đó là qua tay
    thứ ba, còn board của chính công ty mới là chỗ đơn đi thẳng tới nơi tuyển.
    """
    thay: dict[str, dict] = {}
    for r in same:
        url = (r["source"], r["url"]) if not isinstance(r, tuple) else r
        nguon, dia_chi = url
        if not dia_chi or dia_chi in thay:
            continue
        # Thư báo dẫn tới đúng trang LinkedIn như nguồn Chrome, chỉ khác
        # đường mang nó về — nên nút mở ra vẫn ghi "LinkedIn".
        tren_li = nguon in ("linkedin", "alert")
        thay[dia_chi] = {
            "url": dia_chi,
            "kind": nguon if tren_li else "board",
            "name": "LinkedIn" if tren_li else nguon.split(":")[0],
            # Tên miền để người xem BIẾT TRƯỚC mình sắp đi đâu. Một nút ghi
            # "Mở tin gốc" mà không nói dẫn tới đâu thì phải bấm mới biết.
            "host": dia_chi.split("/")[2] if "//" in dia_chi else dia_chi[:40],
            "minh": dia_chi == url_minh,
        }
    return sorted(thay.values(), key=lambda x: x["kind"] != "board")


def _reqs(row) -> list[dict]:
    """Yêu cầu trong JD kèm bằng chứng — hình dạng đúng như views/jobs.py cần."""
    if not row["score_json"]:
        return []
    data = json.loads(row["score_json"])
    return [{"text": r["text"], "met": r["met"], "must": r["must"],
             "evidence": r["evidence"] or "—"} for r in data.get("requirements", [])]


# ---------------------------------------------------------------- settings

# CHROME_SOURCES ĐÃ BỎ. Nó từng có hai thành viên, và đó chính là lý do cái
# huy hiệu từng mang tên "chrome": hồi ấy phải gọi theo CÁCH LẤY vì có hai
# nguồn cùng đi qua Chrome. eFinancialCareers bị gỡ khỏi app từ lâu (67% tin
# của nó là môi giới), nên giờ chỉ còn đúng một nguồn — và nó có tên riêng.


def sources(conn: sqlite3.Connection) -> list[dict]:
    """Mọi nguồn, kèm loại (api hay chrome) và lần chạy gần nhất."""
    counts = {r["source"]: r["n"] for r in conn.execute(
        "SELECT source, COUNT(*) n FROM posting GROUP BY source")}
    runs = {r["source"]: r for r in postings.last_runs(conn)}

    out = []
    for name in sorted(set(counts) | set(runs)):
        family = name.split(":")[0]
        run = runs.get(name)
        out.append({
            "name": name,
            "kind": family if family in ("linkedin", "alert") else "board",
            "on": bool(run and run["ok"]),
            "last": _ago(run["at"]) if run else "never",
            "found": counts.get(name, 0),
            "note": (run["error"][:60] if run and not run["ok"] else ""),
        })
    out.sort(key=lambda s: (-s["found"], s["name"]))
    return out


def settings(conn: sqlite3.Connection) -> dict:
    """Ba núm + một dòng tình trạng. Không hơn."""
    from ..core import prefs, versions
    from ..core.derive import stale_count
    from ..core.scheduler import MAX_EVERY, MIN_EVERY, human_window

    boards = int(conn.execute(
        "SELECT COUNT(DISTINCT substr(source, instr(source,':') + 1)) FROM posting"
        " WHERE instr(source,':') > 0").fetchone()[0])
    firms = int(conn.execute("SELECT COUNT(*) FROM company").fetchone()[0])
    stale = stale_count(conn)

    from ..browser import chrome as ch
    from ..core import reset as reset_mod
    from ..profile import store as pstore
    from ..track import mail as _mail
    kho = reset_mod.inventory(conn)

    # Số THẬT cho mỗi nguồn. Giới thiệu bằng tính từ ("phổ biến", "hiện đại")
    # thì không giúp ai chọn được gì; đưa ra "lấy về bao nhiêu, giữ được bao
    # nhiêu" mới là thứ quyết định được.
    from ..scan_runner import load_boards
    boards = load_boards(conn)
    def _dem(like: str) -> tuple[int, int, int]:
        row = conn.execute(
            "SELECT COUNT(*), SUM(kept), SUM(remote) FROM posting WHERE source LIKE ?",
            (like,)).fetchone()
        return int(row[0] or 0), int(row[1] or 0), int(row[2] or 0)

    nguon = []
    for ats, note in (
        ("greenhouse", "ATS hay gặp nhất ở quỹ và công ty lớn"),
        ("lever", "hay gặp ở scale-up · có báo việc remote"),
        ("ashby", "công ty AI / startup · gần như tin nào cũng khai remote"),
    ):
        tin, giu, rem = _dem(f"{ats}:%")
        nguon.append({"id": ats, "ten": ats, "note": note,
                      "on": prefs.flag(conn, prefs.SRC_ATS[ats]),
                      "boards": len(boards.get(ats, [])),
                      "tin": tin, "giu": giu, "remote": rem})
    # Thư báo việc — cùng nhóm "nguồn nhanh" nên để chung bảng, nhưng nó
    # không phải ATS: không có board nào để đếm.
    _tin, _giu, _rem = _dem("alert")
    nguon.append({"id": "alert", "ten": "thư báo", "boards": 0,
                  "note": "LinkedIn gửi vào hộp thư · nhanh nhất, không cào ·"
                          " nguồn riêng, chạy dù LinkedIn đang tắt",
                  "on": prefs.flag(conn, prefs.SRC_ALERT),
                  "tin": _tin, "giu": _giu, "remote": _rem})
    return {
        "reset_rows": kho["total_rows"],
        "reset_files": kho["files"],
        "reset_mb": round(kho["bytes"] / 1_048_576, 1),
        "reset_backup_dir": str(reset_mod.backup_dir()),
        "every": prefs.num(conn, prefs.SCAN_EVERY, MIN_EVERY, MAX_EVERY),
        "pace": prefs.get(conn, prefs.PACE) or "thuong",
        "sources": nguon,
        "board_on": prefs.flag(conn, prefs.SRC_BOARD),
        # CHỈ địa chỉ và trạng thái. Mật khẩu không bao giờ rời config.toml.
        "mail_ready": all(_mail.account()),
        "mail_address": _mail.account()[0],
        "mail_days": prefs.num(conn, prefs.MAIL_DAYS, 1, 365),
        "mail_profile": (pstore.load(conn).get("email") or "").strip(),
        "hours": human_window(),
        "status": [
            ("Chrome", "đang mở" if ch.alive() else "tắt"),
            ("Board đang quét", f"{boards}"),
            ("Công ty đã biết", f"{firms:,}"),
            ("Tin cần phán lại", f"{stale:,}" if stale else "không"),
            ("Luật lọc", versions.FILTER_RULES),
            ("Luật chấm", versions.SCORE_RULES),
        ],
    }


def chrome_status() -> dict:
    from ..browser import chrome as ch
    from ..core.scheduler import HUMAN_WINDOW
    from ..ingest.web import linkedin as li
    alive = ch.alive()
    return {
        "alive": bool(alive),
        "version": (alive or {}).get("Browser", "—"),
        "profile": str(ch.profile_dir()),
        "port": ch.PORT,
        "window": f"{HUMAN_WINDOW[0]:02d}:00 – {HUMAN_WINDOW[1]:02d}:00",
        "pace": f"{li.PAUSE[0]:g}–{li.PAUSE[1]:g}s between pages on LinkedIn",
    }


def company_stats(conn: sqlite3.Connection) -> dict:
    from ..ingest.web import companies as co
    return co.stats(conn)


def last_runs(conn: sqlite3.Connection) -> list[dict]:
    return [dict(r) for r in postings.last_runs(conn)]


def health(conn: sqlite3.Connection) -> dict:
    """Sức khoẻ hệ thống — thứ người dùng phải thấy, không phải chỉ nằm trong DB.

    `stale` > 0 nghĩa là phán quyết hiện tại sinh ra từ hồ sơ hoặc luật CŨ.
    Không hiện ra thì người dùng đọc số liệu đã lỗi thời mà tưởng là mới.
    """
    from ..core import versions
    from ..core.derive import stale_count

    runs = postings.last_runs(conn)
    broken = [dict(r) for r in runs if not r["ok"]]
    flaky = [dict(r) for r in runs
             if r["ok"] and r["attempted"] and r["failed"]]
    return {
        "stale": stale_count(conn),
        "unjudged": postings.unjudged(conn),
        "filter_rules": versions.FILTER_RULES,
        "score_rules": versions.SCORE_RULES,
        "broken": broken,
        "flaky": flaky,
    }
# ---------------------------------------------------------------- projects

# ---------------------------------------------------- KHO NHỚ TẦNG CV
#
# MỘT kho, MỘT khoá, MỘT chỗ quên.
#
# Trước đây có ba cache rời — _CV_CACHE, _BLOCK_CACHE, _HUT_CACHE — cùng dựng
# trên đúng một khoá `_cv_key`, nhưng được xoá ở ba tập chỗ KHÁC NHAU: reset
# quên _HUT_CACHE, route xoay núm quên _BLOCK_CACHE, batch chỉ xoá _CV_CACHE.
# Ba thứ cùng phụ thuộc một đầu vào mà hết hạn theo ba lịch khác nhau thì sớm
# muộn màn hình trộn số cũ với số mới, và không ai lần ra được.
_NHO: dict = {}


def nho(conn: sqlite3.Connection, ten: str, tinh):
    """Nhớ `tinh()` theo khoá chung của tầng CV.

    Khoá gồm: chữ CV · luật chấm · tập tin đang giữ · mấy núm Điều chỉnh —
    xem `_cv_key`. Đổi bất kỳ thứ nào thì CẢ BA con số cùng hết hạn, vì cả ba
    đều đọc từ chúng.
    """
    from ..profile import store as pstore
    key = _cv_key(conn, pstore.load(conn).get("cv_text") or "")
    cu = _NHO.get(ten)
    if cu is not None and cu[0] == key:
        return cu[1]
    ra = tinh()
    _NHO[ten] = (key, ra)
    return ra


def quen() -> None:
    """Quên hết. MỘT chỗ gọi cho mọi thay đổi đụng tới tầng CV."""
    _NHO.clear()


def cv_hut(conn: sqlite3.Connection) -> dict:
    """Thang HỤT — viết/học thứ nào trước thì mở khoá nhiều tin nhất.

    CÓ CACHE: thang chạy tham lam qua ~47 ứng viên, đo được 0,6 giây. Tab CV
    mở nhiều lần một buổi, và kết quả chỉ đổi khi hồ sơ hoặc kho tin đổi.
    """
    from ..scoring.gap import thang
    from ..scoring.score import build_index
    from ..scoring.vocab import alias_hits
    from ..profile import store as pstore

    def _tinh():
        answers = pstore.load(conn)
        co: set = set()
        for e in build_index(answers):
            co |= set(alias_hits(e.normal))
        return thang(conn, co)
    return nho(conn, "hut", _tinh)


def cv_nut(conn: sqlite3.Connection) -> dict:
    """Hai núm của tầng CV, đã đổi sang thứ build() dùng được.

    MỘT chỗ dịch từ "tên núm" sang "giá trị". Dịch ở hai chỗ thì có ngày tấm
    Điều chỉnh hiện một đằng mà bộ dựng chạy một nẻo.

    BẢY NÚM ĐÃ BỎ — xem lời chú ở core/prefs.py. Mấy luật chúng lật giờ chạy
    cố định theo mặc định đã đo, và bản chấm điểm vẫn nói rõ câu nào bị bỏ vì
    sao. Người dùng mất bảy cái nút, không mất một thông tin nào.
    """
    from ..core import prefs
    rieng = prefs.get(conn, prefs.CV_RIENG) or "rieng"
    return {"rieng": rieng if rieng in prefs.RIENG else "rieng",
            # `tu_lo` KHÔNG có trong `ten`: nó đổi LÚC dựng, không đổi bản
            # dựng RA GÌ. Nhét vào dấu thì lật nó là mọi bản bỗng bị coi là
            # cũ, mà chúng y hệt nhau.
            "tu_lo": prefs.flag(conn, prefs.CV_TU_LO),
            "ten": {"rieng": rieng}}


def _cv_key(conn: sqlite3.Connection, cv_text: str) -> tuple:
    from ..core import versions
    row = conn.execute(
        "SELECT COUNT(*), COALESCE(MAX(id), 0) FROM posting"
        " WHERE kept = 1 AND realism IN ('likely','possible')").fetchone()
    return (hash(cv_text), versions.SCORE_RULES, row[0], row[1],
            tuple(sorted(cv_nut(conn)["ten"].items())))


# ---------------------------------------------------------------------- CV

# Dựng CV cho 101 tin mất 1,4 giây. Không được trả cái giá đó MỖI LẦN mở
# trang. Nhớ lại trong bộ nhớ tiến trình, và quên đi khi một trong ba thứ đầu
# vào đổi: chữ CV, luật chấm, tập tin.


def cv_versions(conn: sqlite3.Connection) -> dict:
    """Mọi bản CV hệ thống SẼ GỬI, gộp những bản giống hệt nhau làm một.

    Vì sao gộp: 101 tin đáng nộp nhưng chỉ ra 29 bản khác nhau — cấu trúc CV
    cố định (2 việc · 3 project · 2 học vấn · 1 chứng chỉ · 4 kỹ năng = 16
    câu), phần đổi chỉ là CÂU NÀO trong mỗi khối được chọn. Liệt kê 101 dòng
    là bắt Vin đọc lại cùng một bản 3-4 lần.
    """
    import json as _json
    from ..cv.build import build as build_cv
    from ..profile import store as pstore

    answers = pstore.load(conn)
    san = _NHO.get("ban")
    key = _cv_key(conn, answers.get("cv_text") or "")
    if san is not None and san[0] == key:
        return san[1]
    # BA NÚM của tấm Điều chỉnh. Đọc MỘT LẦN ở đây rồi truyền xuống: để
    # build() tự đọc DB thì nó hết thuần, và 364 lần dựng là 1.092 lượt đọc
    # prefs cho ba giá trị không đổi.
    num = cv_nut(conn)

    rows = conn.execute(
        "SELECT id, title, company, score, realism, description, score_json"
        " FROM posting WHERE kept = 1 AND realism IN ('likely','possible')"
        " ORDER BY score DESC").fetchall()

    groups: dict[tuple, dict] = {}
    for row in rows:
        explain = _json.loads(row["score_json"]) if row["score_json"] else None
        cv = build_cv(answers, explain, row["description"] or "", num)
        # Khoá gộp là ĐÚNG NHỮNG CÂU sẽ in ra. Gộp theo kỹ năng JD đòi thì hụt:
        # đo được 85 bộ kỹ năng khác nhau mà chỉ ra 29 bản.
        sig = tuple(line.text for section in cv.sections for line in section.lines)
        slot = groups.setdefault(sig, {
            "cv": cv, "jobs": [], "wanted": set(), "missing": set()})
        slot["jobs"].append({"id": row["id"], "title": row["title"],
                             "company": row["company"], "score": row["score"],
                             "realism": row["realism"]})
        slot["wanted"] |= set(cv.wanted)
        slot["missing"] |= set(cv.missing)

    # Câu nào có ở MỌI bản = phần lõi, không đổi theo JD. Phần còn lại mới là
    # thứ "may đo" thật. Đo được: 14/16 câu là lõi, chỉ 2 câu đổi — hiện con số
    # cấu trúc (2 việc, 3 project…) thì 29 dòng giống hệt nhau và vô nghĩa.
    core = set.intersection(*[set(sig) for sig in groups]) if groups else set()

    out = []
    for sig, slot in sorted(groups.items(), key=lambda kv: -len(kv[1]["jobs"])):
        cv = slot["cv"]
        # PHỦ PHẢI TÍNH TRÊN MỘT TIN, KHÔNG TRÊN CẢ NHÓM. `slot["wanted"]` là
        # HỢP của mọi tin trong nhóm: bản gộp 168 tin ra 33 kỹ năng, mà không
        # tin nào hỏi 33 thứ — nên tỉ lệ "13/33" đo KÍCH THƯỚC NHÓM chứ không
        # đo chất lượng CV, và bản gộp nhiều tin luôn trông tệ hơn bản gộp ít.
        #
        # `slot["cv"]` là bản của tin ĐIỂM CAO NHẤT trong nhóm (rows xếp theo
        # score DESC, nhóm được tạo ở lần gặp đầu). Con số của riêng nó là con
        # số thật: đúng những thứ MỘT tin hỏi, và đúng phần CV trả lời được.
        dau = max(slot["jobs"], key=lambda j: j["score"] or 0)
        out.append({
            "jobs": slot["jobs"],
            "lines": len(sig),
            "dropped": len(cv.dropped),
            "only": [line for line in sig if line not in core],
            "wanted": sorted(slot["wanted"]),
            "missing": sorted(slot["missing"]),
            "top": [j["company"] for j in slot["jobs"][:3]],
            # --- con số của TIN ĐẦU ĐÀN, để dòng nói được điều gì thật ---
            "best": dau,
            # DÙNG `asked`/`on_paper`, KHÔNG dùng `wanted`/`covered`.
            #   wanted  quét cả tin, kể cả đoạn công ty tự giới thiệu -> mẫu
            #           số phồng lên (NXP "đòi" cloud; BoA 3/4 chữ là từ đoạn
            #           giới thiệu)
            #   covered chỉ đếm kỹ năng do mấy CÂU chứng minh -> bỏ qua mục
            #           TECHNICAL SKILLS đang in trên chính tờ giấy đó
            # Đo trên 287 tin: phân số cũ 28%, phân số thật 64%.
            "hoi": len(cv.asked),           # tin đó THẬT SỰ đòi mấy thứ
            "tra_loi": len(cv.on_paper),    # TỜ GIẤY nói ra được mấy thứ
            "cam": sorted(cv.missing),      # và câm về những thứ nào
        })

    value = {"versions": out, "jobs": len(rows), "core": len(core),
             # Kỹ năng CẢ THỊ TRƯỜNG đòi mà hồ sơ không nói được câu nào. Đây
             # là danh sách đáng đọc nhất trên trang: nó nói CV thiếu gì.
             "gaps": sorted({m for v in out for m in v["missing"]})}
    _NHO["ban"] = (key, value)
    return value


def onboarding(conn: sqlite3.Connection) -> dict:
    """App đang ở đâu trên đường dựng hồ sơ — MỘT chỗ tính, mọi nơi đọc.

    Trước đây mỗi tab tự đoán: Profile biết "còn thiếu 3 câu", Search không
    biết gì nên vẫn mời bấm Chạy rồi im lặng bỏ cuộc, Home thì trống trơn.
    Cùng một sự thật mà ba nơi trả lời khác nhau thì sớm muộn cũng lệch.

    Không đẻ luật mới: cổng vẫn là `store.missing_for_ingest`, "phần nào xong"
    vẫn là `store.is_section_done` — hàm này chỉ GOM lại thành một câu trả lời
    cho màn hình.
    """
    from ..profile import store
    from ..profile.schema import SECTIONS, all_questions

    answers = store.load(conn)
    hoi = all_questions()
    thieu = store.missing_for_ingest(answers)
    ke_tiep = store.first_unfinished_section(answers)

    phan = []
    da_tra_loi = tong = 0
    for s in SECTIONS:
        hien = [q for q in s.questions if not q.hidden]
        co = [q for q in hien if store.has_answer(answers, q)]
        da_tra_loi += len(co)
        tong += len(hien)
        phan.append({
            "id": s.id, "title": s.title, "why": s.why,
            "href": f"/profile/{s.id}",
            "answered": len(co), "total": len(s.questions),
            "done": store.is_section_done(answers, s),
            "optional": s.optional,
            # Phần nào chứa câu của cổng thì phần đó là BẮT BUỘC — suy ra từ
            # cổng, không gõ tay, để đổi cổng là nhãn tự đổi theo.
            "required": any(q.id in store.INGEST_GATE for q in s.questions),
        })

    return {
        "answered": da_tra_loi, "total": tong,
        "versions": len(store.history(conn)),
        "gate_open": not thieu,
        "gate_missing": [{"id": q, "text": hoi[q].text} for q in thieu if q in hoi],
        "next": ({"id": ke_tiep.id, "title": ke_tiep.title,
                  "href": f"/profile/{ke_tiep.id}"} if ke_tiep else None),
        "sections": phan,
    }


def search_stage(conn: sqlite3.Connection) -> dict:
    """Số liệu + trạng thái của khúc SEARCH.

    MỘT chỗ tính. Thanh của tab và bảng dây chuyền trên Home sau này đều đọc ở
    đây — hai chỗ tự đếm là hai con số rồi có ngày lệch nhau.
    """
    from ..core import halt
    from ..core.scheduler import current as sched_now

    one = lambda q: conn.execute(q).fetchone()[0]          # noqa: E731
    # Số của KHO, không phải số của khung nhìn. Thanh khúc trả lời "dây chuyền
    # đang có gì", còn chip trên danh sách trả lời "đang hiện gì" — trộn hai
    # thứ thì gõ tìm "quant" xong thanh báo 64 giữ mà 91 đáng nộp, trong khi
    # đáng nộp là tập con của giữ. Số vô lý ngay trên màn hình.
    kept = one("SELECT COUNT(DISTINCT COALESCE(group_id, CAST(id AS TEXT)))"
               " FROM posting WHERE kept = 1 AND via_agency = 0")
    worth = one("SELECT COUNT(*) FROM posting WHERE kept = 1"
                " AND realism IN ('likely','possible')")
    # HÀNG ĐỢI THẬT: tin đáng nộp, điểm cao, mà CHƯA NỘP. Đây là con số duy
    # nhất trên thanh trả lời được "tối nay tôi làm gì".
    #
    # Thanh cũ có bốn số mà không số nào hành động được: "363 giữ" và "364
    # đáng nộp" gần trùng nhau (hai cách đếm cùng một chồng), "0 mới" luôn là
    # 0 trừ đúng lúc vừa quét xong, "50 đang hiện" là cỡ trang.
    hang_doi = one("SELECT COUNT(*) FROM posting WHERE kept = 1"
                   " AND realism IN ('likely','possible') AND score >= 80"
                   " AND id NOT IN (SELECT posting_id FROM application)")
    da_nop = one("SELECT COUNT(*) FROM application")
    last = conn.execute(
        "SELECT at FROM audit WHERE kind = 'scan_started'"
        " ORDER BY id DESC LIMIT 1").fetchone()
    when = (last["at"] or "")[11:16] if last else ""
    # "Mới" = tin LẦN QUÉT NÀY mang về, đo bằng lúc tải raw về, không phải
    # hiệu hai lần đếm: lấy hiệu thì quét về 10 tin mới mà đồng thời 10 tin cũ
    # bị loại sẽ ra 0, và Vin không được báo gì cả.
    fresh = one(
        "SELECT COUNT(*) FROM posting p JOIN raw_posting r ON r.id = p.raw_id"
        " WHERE p.kept = 1 AND r.fetched_at >= COALESCE("
        "   (SELECT at FROM audit WHERE kind = 'scan_started'"
        "    ORDER BY id DESC LIMIT 1), '')")

    runner = sched_now()
    if halt.wanted("search"):
        state = "đang dừng…"
    elif runner.running:
        state = "đang quét"
    else:
        auto = "tự động: BẬT" if not runner.paused else "tự động: TẮT"
        state = f"{auto} · quét lần cuối {when}" if when else f"{auto} · chưa quét lần nào"

    # NÚT phải nói đúng việc nó sắp làm. "Chạy" là chữ rỗng: người mới mở app
    # lần đầu không biết chạy cái gì, còn người vừa bấm Dừng giữa chừng thì
    # đọc ra là "chạy lại từ đầu" — trong khi máy sẽ đi tiếp chỗ dở.
    #
    # Ba tình huống, đọc thẳng từ DB chứ không giữ cờ trạng thái nào: cờ thì
    # có ngày lệch với sự thật, còn đếm thì luôn đúng.
    # NÚT ĐỌC LẠI QUYẾT ĐỊNH CỦA VÒNG QUÉT, không tự đoán một quyết định
    # song song. Trước đây chỗ này có công thức riêng, và nó đếm cả tin lưới
    # sàng đã loại: nút ghi "còn 1.855 tin chưa đọc kỹ" trong khi vòng đọc kỹ
    # chỉ mở 11 tin. Bấm xong không thấy con số nhúc nhích là người dùng thôi
    # tin cái nút.
    #
    # Chữ ở đây là chữ lúc RẢNH. Lúc đang chạy thì live.js đổi thành
    # "Đang quét…" rồi khoá nút — một chỗ lo một trạng thái.
    from ..scan_runner import scan_mode
    kieu = scan_mode(conn)

    # Chữ cho chip NƠI CHỐN. Lấy từ hồ sơ, không đóng cứng: "Gần tôi · London"
    # chỉ đúng với người khai mình ở London.
    from ..ingest.filter import NOI
    nha, gan = noi_toi(conn)
    return {"kept": kept, "worth": worth, "fresh": fresh, "state": state,
            "hang_doi": hang_doi, "da_nop": da_nop,
            "run_label": kieu["label"], "run_note": kieu["note"],
            "gan": gan, "vung": NOI[nha]["ten"]}


def cv_pdf_plan(conn: sqlite3.Connection) -> list[dict]:
    """Kế hoạch in: MỘT tệp cho MỖI BẢN CV, và tin nào dùng tệp nào.

    MỘT NGUỒN đặt tên. Trước đây máy in đặt tên theo tin điểm cao nhất trong
    bản, còn nút Nộp lại tự ghép tên từ tin ĐANG BẤM — hai công thức, nên bấm
    Nộp trên tin thứ hai của cùng một bản là đi tìm tệp không tồn tại. Giờ cả
    hai đọc ở đây.
    """
    from pathlib import Path as _Path

    from ..core import db as _db
    from ..cv.pdf import slug

    root = _Path(_db.db_path()).parent / "cv"
    plan = []
    for ver in cv_versions(conn)["versions"]:
        best = max(ver["jobs"], key=lambda j: j["score"] or 0)
        # Kèm số hiệu tin. Đo được: Jane Street có HAI bản CV khác nhau cùng
        # tên "machine-learning-researcher" — hai bản ghi đè nhau, và 7 tin
        # thì có tin cầm nhầm CV của bản kia. Tên người đọc được không đủ để
        # phân biệt hai bản; số hiệu thì đủ.
        plan.append({
            "best": best,
            "file": root / (f"{slug(best['company'])}-{slug(best['title'])}"
                            f"-{best['id']}.pdf"),
            "ids": [j["id"] for j in ver["jobs"]],
        })
    return plan


def cv_pdf_for(conn: sqlite3.Connection, posting_id: int) -> Path | None:
    """Đường dẫn bản PDF của tin này. LUÔN trả đúng một tên — người gọi tự
    kiểm `.exists()` để biết đã in chưa.

    Tin không nằm nhóm nào (điểm thấp, không lọt vòng dựng CV) thì vẫn phải có
    tên, và tên đó phải theo ĐÚNG công thức của kế hoạch in. Nút "In bản này"
    trước đây tự ghép tên theo công thức cũ (thiếu số hiệu tin) nên in ra một
    tệp mà phần nộp không bao giờ đi tìm.
    """
    from pathlib import Path as _Path

    from ..core import db as _db
    from ..cv.pdf import slug

    for item in cv_pdf_plan(conn):
        if posting_id in item["ids"]:
            return item["file"]
    row = conn.execute("SELECT company, title FROM posting WHERE id = ?",
                       (posting_id,)).fetchone()
    if row is None:
        return None
    root = _Path(_db.db_path()).parent / "cv"
    return root / f"{slug(row['company'])}-{slug(row['title'])}-{posting_id}.pdf"




def cv_blocks(conn: sqlite3.Connection) -> list[dict]:
    """Khối trong CV gốc, kèm số đo NÓ ĐANG LÀM ĐƯỢC GÌ.

    Kho nguyên liệu là trần thật của cả hệ thống: 34 câu văn, mà một bản CV
    cần 18 — nên 13/18 câu giống hệt nhau ở mọi bản, và mọi thiết kế chọn lọc
    đều đụng trần đó. Muốn CV trúng hơn thì phải VIẾT THÊM, không phải chọn
    khéo hơn. Bảng này nói rõ khối nào đang gánh, khối nào chỉ chiếm chỗ.
    """
    from ..cv.blocks import parse as parse_cv, sentences as split_cv
    from ..cv.build import skills_in
    from ..profile import store as pstore

    # Có CACHE, như cv_versions. Đo được: 7,8 giây MỖI LẦN gọi, và tab CV gọi
    # nó mỗi lần mở — Vin ngồi chờ 10 giây để xem một trang không đổi gì.
    answers_now = pstore.load(conn)
    san = _NHO.get("khoi")
    key = _cv_key(conn, answers_now.get("cv_text") or "")
    if san is not None and san[0] == key:
        return san[1]
    from ..scoring.market import demand as thi_truong

    text = pstore.load(conn).get("cv_text") or ""
    demand = thi_truong(conn)
    out = []
    for block in parse_cv(text):
        if block.kind not in ("experience", "project"):
            continue
        lines = [s for s in split_cv(block)]
        skills = sorted({k for s in lines for k in skills_in(s)})
        out.append({
            "kind": block.kind,
            "title": block.title,
            "meta": block.meta,
            "lines": lines,
            "skills": skills,
            # Bao nhiêu TIN đang cần thứ khối này nói được. Khối 0 tin là khối
            # chiếm chỗ: nó lên CV vì có ô trống, không vì nó chứng minh gì.
            "reach": sum(demand.get(s, 0) for s in skills),
        })
    out.sort(key=lambda b: -b["reach"])
    _NHO["khoi"] = (key, out)
    return out


def cv_soan(conn: sqlite3.Connection, title: str = "", ky: str = "",
            nen: str = "", soan: str = "", tho: bool = False) -> dict:
    """Mọi thứ màn SOẠN KHỐI cần — đo ở đây, màn hình chỉ vẽ.

    Màn soạn khác tấm phủ cũ ở đúng một chỗ, và đó là lý do nó tồn tại: nó
    chấm TỪNG CÂU ngay lúc soạn. Trước đây Vin gõ vào một ô trống rồi bấm
    Lưu, và chỉ biết câu vừa viết bị luật bỏ sau khi dựng lại cả loạt bản —
    nếu còn nhớ mà đi đọc.

        phan    luật nói gì: lên CV · xem lại · luật bỏ
        reach   bao nhiêu TIN đang đòi thứ câu đó nhắc tới

    `reach` KHÔNG phải điểm chất lượng. Câu kiến thức không nhắc tên công cụ
    nào thì reach = 0 mà vẫn là câu mạnh nhất hồ sơ. Nó trả lời đúng một câu:
    *thị trường có hỏi thứ này không* — còn câu đó đáng giữ hay không là việc
    của người viết.

    `ky` = ĐANG NHẮM kỹ năng nào. Nó mở thêm phần BRIEF: nguyên văn mấy dòng
    yêu cầu thật đang đòi thứ đó, và mấy dòng DÙNG ĐƯỢC LÀM NỀN bản nháp.

    `nen` = dòng yêu cầu người dùng đã chọn. Nó là MỐC SO SÁNH của lượt Lưu,
    và không đổi khi người dùng gõ — tách khỏi `soan` chính vì thế: trộn hai
    thứ làm một thì sửa vài chữ rồi Lưu hụt một lần là mốc trôi theo, và lần
    sau chép nguyên văn cũng lọt.

    `soan` = chữ ĐANG nằm trong ô. Mặc định là GỢI Ý (`gap.goi_y`) nếu dòng
    đó rút gọn được thành hình câu CV, không thì là nguyên văn dòng của họ.
    `tho=True` ép lấy nguyên văn — nút "dùng nguyên văn dòng của họ".

    Máy vẫn KHÔNG viết khẳng định nào: gợi ý chỉ là dòng của họ đã cắt phần
    thừa, chia sang thì quá khứ, và chừa `___` cho bằng chứng — thứ duy nhất
    người dùng mới có. `gap.con_trong` không cho lưu khi `___` còn nguyên.

    VÌ SAO BRIEF Ở ĐÂY chứ không phải một tấm phủ riêng: viết một câu mới CHÍNH
    LÀ sửa một khối — cùng một phép ghi vào `cv_text`, cùng một chỗ ngồi. Tách
    ra hai màn là bắt người dùng đọc yêu cầu ở một chỗ rồi gõ ở chỗ khác, và
    để lại hai đường ghi phải trông nhau.
    """
    from ..cv import rules
    from ..cv.build import skills_in
    from ..scoring.gap import goi_y, ho_hoi, nen_nhap
    from ..scoring.market import demand as thi_truong

    khoi = cv_blocks(conn)
    chon = next((b for b in khoi if b["title"] == title), None) if title else None
    can = nho(conn, "can", lambda: thi_truong(conn))
    cau = []
    for line in (chon or {}).get("lines", []):
        tags = sorted(skills_in(line))
        phan, vi_sao = rules.sentence_ok(line, tags)
        cau.append({"chu": line, "tags": tags, "phan": phan, "vi_sao": vi_sao,
                    "reach": sum(can.get(t, 0) for t in tags)})

    # THANG HỤT rút gọn: soạn khối mà không biết thị trường đang thiếu gì thì
    # chỉ là sửa chính tả. Chỉ lấy dòng VIẾT ĐƯỢC — dòng "phải học" không phải
    # việc làm được trong màn này.
    d_hut = cv_hut(conn)
    hut = [b for b in (d_hut.get("buoc") or [])
           if b["dong"] - b["rieng"] > 0][:6]

    # MÁY TỰ LO — dựng sẵn bản nháp cho MỌI chỗ hụt, không đợi bấm từng cái.
    #
    # Không cất xuống đĩa. Bản nháp là thứ SUY RA ĐƯỢC từ dòng yêu cầu, nên
    # cất nó đi chỉ đẻ ra một kho thứ hai phải ngồi giữ cho khớp — mà khớp với
    # chính thứ tính lại được trong một phần giây. Và cất vào `cv_text` thì
    # tệ hơn: bộ chấm sẽ đếm "data pipelines" trong câu nháp là kỹ năng đã
    # đáp, và app nói dối người dùng về chính họ.
    san = []
    if cv_nut(conn).get("tu_lo") and not ky:
        for b in hut:
            for m in nen_nhap(conn, b["ky_nang"], sau=3):
                g = goi_y(m["chu"], b["ky_nang"])
                if g:
                    san.append({"ky": b["ky_nang"], "them": b["them"],
                                "nen": m["chu"], "cong_ty": m["cong_ty"],
                                "nhap": g})
                    break

    brief = None
    if ky:
        chung, rieng = ho_hoi(conn, ky)
        # NỀN BẢN NHÁP đứng riêng khỏi `chung`: chỉ mấy dòng TẢ VIỆC mới đổi
        # sang câu CV được. "Bạn đã viết gần nhất" ĐÃ BỎ — nó gọi
        # `gan_nhat` vốn không hề dùng tới tham số kỹ năng, nên trả về đúng
        # ba câu giống hệt nhau cho mọi chỗ hụt, trong đó có cả câu luật cấm
        # lên CV. Một gợi ý không đổi theo đầu vào thì không phải gợi ý.
        brief = {"ky": ky, "chung": chung, "rieng": rieng,
                 "nen": nen_nhap(conn, ky)}
    # Ô soạn: gợi ý nếu có, không thì nguyên văn. `soan` do người dùng gõ dở
    # (lượt Lưu vừa bị chặn) thì thắng tất — không được vứt chữ của họ.
    gy = goi_y(nen, ky) if nen else ""
    return {"khoi": khoi, "chon": chon, "cau": cau, "hut": hut, "brief": brief,
            "nen": nen, "goi_y": gy, "tho": tho, "san": san,
            "soan": soan or ("" if not nen else (nen if tho or not gy else gy)),
            # Độ phủ HÔM NAY, không phải delta của lần lưu vừa rồi. Delta nằm
            # ở nhật ký, nơi nó có dấu thời gian và không hoá thành lời nói dối
            # sau một lần bấm F5.
            "dap": (d_hut.get("nen") or 0, d_hut.get("tin") or 0)}


# ------------------------------------------------------- chức danh bỏ sót

# Chữ cho biết tin này THUỘC NGÀNH của Vin, dù chức danh không khớp lưới.
NEAR_TITLE = re.compile(
    r"\b(quant\w*|machine learning|market microstructur\w*|"
    r"algorithmic trading|systematic trading|alpha research)\b", re.I)

# Chức danh cấp cao — bỏ sót chúng là ĐÚNG, không phải lỗ hổng.
ABOVE_ME = re.compile(
    r"\b(senior|lead|principal|head|director|vp|chief|staff|manager|"
    r"associate director|executive)\b", re.I)

MIN_SEEN = 2        # thấy một lần thì chưa đủ để đổi hồ sơ


def missed_titles(conn: sqlite3.Connection, limit: int = 12) -> list[dict]:
    """Chức danh bị lưới bỏ mà TRÔNG NHƯ việc của Vin.

    Lưới chức danh là mấy chuỗi gõ tay, nên thiếu một chuỗi là mất cả một loạt
    tin — và mất trong im lặng. Đo ngày 10/09: 163 tin cấp junior có chữ
    quant/machine learning bị bỏ, trong đó `Quantitative Trader` chín lần.

    Máy KHÔNG tự nới lưới. Nới lưới là đổi hồ sơ, và hồ sơ đổi thì mọi tin
    phải phán lại — đó là việc của người, không phải của vòng quét. Ở đây chỉ
    chỉ chỗ.
    """
    from ..profile import store as pstore

    have = {t.strip().lower()
            for t in (pstore.load(conn).get("job_titles") or "").splitlines()
            if t.strip()}
    seen: dict[str, dict] = {}
    for row in conn.execute(
            "SELECT title, company FROM posting WHERE kept = 0"
            " AND drop_reason LIKE 'title does not%'"):
        title = (row["title"] or "").strip()
        if not NEAR_TITLE.search(title) or ABOVE_ME.search(title):
            continue
        key = title.lower()
        if key in have:
            continue
        slot = seen.setdefault(key, {"title": title, "n": 0, "firms": []})
        slot["n"] += 1
        if row["company"] and row["company"] not in slot["firms"]:
            slot["firms"].append(row["company"])
    out = [s for s in seen.values() if s["n"] >= MIN_SEEN]
    out.sort(key=lambda s: -s["n"])
    return out[:limit]
