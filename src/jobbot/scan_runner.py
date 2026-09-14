"""Một lần quét — dùng chung cho cả dòng lệnh và vòng chạy nền.

Trước đây logic này nằm trong scripts/scan.py. Tách ra để scheduler gọi được
mà không phải chạy tiến trình con.
"""

from __future__ import annotations

import tomllib
from typing import Callable

from .core import db, halt, postings
from .core.journal import INFO, OK, SEARCH, log as jlog
from .core.paths import PROJECT_ROOT

STAGE = "search"      # tên khúc, dùng chung với cờ dừng và nút trên thanh
from .ingest import ashby, greenhouse, lever
from .ingest import filter as jobfilter
from .profile import store
from .profile.schema import all_questions

Log = Callable[[str], None]


def seed_boards() -> dict[str, list[str]]:
    """Board Vin tự chọn, gõ tay trong config/boards.toml."""
    path = PROJECT_ROOT / "config" / "boards.toml"
    raw = tomllib.loads(path.read_text()) if path.exists() else {}
    return {k: v.get("boards", []) for k, v in raw.items()}


def load_boards(conn) -> dict[str, list[str]]:
    """GỘP hai nguồn board: người chọn + máy học được.

    LỖI ĐÃ SỬA: trước đây file chỉ là DỰ PHÒNG khi bảng công ty rỗng. Bảng có
    53 dòng nên file không bao giờ được đọc — 5 board gõ tay (aqr, cohere,
    palantir, ramp, synthesia) chưa từng được quét lần nào. Sửa boards.toml
    xong không có gì xảy ra, mà cũng không báo gì.

    Danh sách người chọn phải LUÔN được tôn trọng: đó là chỗ duy nhất Vin nói
    được "tôi muốn theo dõi nhà này", kể cả khi nó chưa từng đăng tin nào.
    """
    from .ingest.web import companies as co
    out = {k: list(v) for k, v in seed_boards().items()}
    for ats, slugs in co.boards(conn).items():
        out.setdefault(ats, [])
        out[ats] += [s for s in slugs if s not in out[ats]]
    return out


def _nguon_hong(conn, name: str, khuc: str, exc: Exception, log: Log) -> None:
    """Ghi lại một nguồn hỏng — và ĐƯỜNG GHI NÀY KHÔNG ĐƯỢC TỰ HỎNG.

    `record_run()` viết vào đúng cái DB vừa làm `save_batch()` nổ. Nó nổ
    theo thì ngoại lệ thoát ra TỪ TRONG khối except và giết cả lượt quét —
    đúng thứ mà hàm gọi nó sinh ra để chặn. Nên cả hai lần ghi đều bọc.
    """
    cau = f"{type(exc).__name__}: {exc}"
    try:
        postings.record_run(conn, name, ok=False, error=f"{khuc}: {cau}"[:500])
    except Exception:                                 # noqa: BLE001,S110
        pass
    try:
        jlog.error(SEARCH, f"{name}: {khuc} hỏng — {cau[:60]}")
    except Exception:                                 # noqa: BLE001,S110
        pass
    log(f"  {name:26} FAILED  {khuc}: {cau[:50]}")


def _run_source(conn, name: str, fn, *args, log: Log) -> tuple[int, int]:
    """Một nguồn hỏng KHÔNG được làm hỏng cả lần quét.

    CẢ HAI KHÚC nằm trong try, và đó là điểm của hàm này. Bản cũ chỉ bọc
    khúc lấy tin: nguồn trả về đàng hoàng nhưng `save_batch()` nổ (DB bị
    khoá, một tin thiếu trường, ràng buộc UNIQUE) thì ngoại lệ bay thẳng ra
    vòng gọi và 40 nguồn sau KHÔNG chạy nữa — lại còn không có dòng
    `source_run` nào ghi rằng nguồn này đã hỏng. Một nguồn rác giết cả lượt,
    im lặng.

    `khuc` là để câu báo lỗi nói ĐÚNG chỗ hỏng. "greenhouse hỏng" thì người
    đọc đi kiểm mạng; "greenhouse: ghi vào DB hỏng" thì đi kiểm đĩa.
    """
    seen = new = 0
    khuc = "lấy tin"
    try:
        items = fn(*args)
        khuc = "ghi vào DB"
        seen, new = postings.save_batch(conn, name, items)
        postings.record_run(conn, name, ok=True, fetched=seen, new_rows=new)
        khuc = "ghi nhật ký"
        # GHI CẢ dòng "không có gì mới". Luật cũ là chỉ ghi khi có tin mới,
        # vì sợ 62 board mỗi giờ biến nhật ký thành rác — nhưng hậu quả đo
        # được ở lượt quét 19:22: 21 board chạy, nhật ký để lại đúng 3 dòng.
        # Người dùng không có cách nào biết 18 board kia đã chạy xong hay đã
        # chết giữa chừng. Im lặng không phải là gọn. Im lặng là mù.
        jlog.emit(SEARCH, f"{name}: {seen} tin về, {new} mới",
                  level=OK if new else INFO)
        log(f"  {name:26} {seen:5} tin, {new:5} mới")
    except Exception as exc:                          # noqa: BLE001
        _nguon_hong(conn, name, khuc, exc, log)
    # Trả về thứ THẬT SỰ làm được. Hỏng ở khúc nhật ký thì tin đã nằm trong
    # DB rồi, báo 0 là báo sai.
    return seen, new


# Ba lượt quét, ba việc khác hẳn nhau.
DAU, TIEP, MOI = "dau", "tiep", "moi"


def _cap(answers: dict) -> tuple[list[tuple[str, str]], list[str]]:
    """(mọi cặp chức danh × nơi, cấp bậc) — dựng ĐÚNG như vòng tìm sẽ dựng.

    Phải đi qua cả trần MAX_QUERIES: `scan_mode` mà đếm 27 chức danh trong
    khi vòng tìm chỉ gõ 20 thì 7 cặp kia vĩnh viễn "chưa quét", và nút đứng
    ở "Chạy" mãi mãi.
    """
    from .ingest.web import linkedin as li
    titles = [t.strip() for t in (answers.get("job_titles") or "").splitlines()
              if t.strip()][:li.MAX_QUERIES]
    places = li.places_for(answers.get("markets") or [],
                           answers.get("location") or "")
    levels = sorted(answers.get("seniority") or ["grad", "junior"])
    return [(q, p) for q in titles for p in places], levels


def da_quet(conn) -> tuple[set[str], list[str]]:
    """Những cặp đã quét đầy, và cấp bậc lúc quét. Đọc hỏng thì coi như chưa."""
    import json as _json
    from .core import prefs
    try:
        xong = set(_json.loads(prefs.get(conn, prefs.LI_DONE) or "[]"))
        muc = list(_json.loads(prefs.get(conn, prefs.LI_LEVELS) or "[]"))
    except (ValueError, TypeError):
        return set(), []
    return xong, muc


def con_thieu(conn, answers: dict) -> tuple[list[tuple[str, str]], int]:
    """Cặp nào CHƯA quét đầy bao giờ, và tổng số cặp.

    Đây là cả luật, gói trong một hàm: thứ chưa từng hỏi thì hỏi đầy, thứ hỏi
    rồi thì chỉ hỏi tin mới. Bỏ bớt chức danh -> cặp ít đi -> không còn gì
    thiếu -> không quét lại cái gì cả. Thêm chức danh -> đúng những cặp mới
    là thiếu, và chỉ chúng được quét đầy.
    """
    cap, muc = _cap(answers)
    xong, muc_cu = da_quet(conn)
    # NỚI RỘNG cấp bậc thì f_E đổi cho mọi cặp -> coi như chưa phủ gì. THU HẸP
    # thì không: bớt một cấp bậc không đẻ ra tin nào mới.
    if not set(muc) <= set(muc_cu):
        xong = set()
    return [c for c in cap if f"{c[0]}|{c[1]}" not in xong], len(cap)


def scan_mode(conn) -> dict:
    """Lượt quét TỚI sẽ làm gì. MỘT chỗ quyết, nút Chạy chỉ đọc lại để đặt tên.

    CHỈ NÓI VỀ CHROME. Board API xong trong 22 giây và chạy mọi lượt, không có
    trạng thái gì để kể; thứ mất nửa tiếng và dở dang được là LinkedIn.

        Chạy      còn cặp chưa quét bao giờ  -> quét ĐẦY đúng mấy cặp đó
        Tiếp tục  đang dở                    -> KHÔNG tìm gì, đọc nốt chỗ dở
        Cập nhật  phủ hết rồi                -> chỉ hỏi tin đăng gần đây

    KHÔNG CHẠY ĐI CHẠY LẠI MỘT THỨ. Đơn vị là CẶP (chức danh × nơi), nên bỏ
    bớt một chức danh thì chẳng phải quét lại gì, còn thêm một chức danh thì
    chỉ mấy cặp mới được quét đầy — phần còn lại vẫn chỉ hỏi tin mới.

    Nút đoán một kiểu còn vòng quét làm một kiểu thì chữ trên nút là lời nói
    dối, và người dùng học được rằng đừng tin cái nút đó nữa.
    """
    from datetime import datetime, timezone
    from .core import prefs
    from .core.postings import HAVE_DESC
    from .ingest.web import linkedin as li
    from .profile import store

    one = lambda q, a=(): conn.execute(q, a).fetchone()[0]      # noqa: E731

    # 1. ĐANG DỞ? Xét trước mọi thứ: việc dở là việc đã trả tiền một nửa, bỏ
    #    đi rồi tìm lại từ đầu là trả hai lần.
    #
    # Đếm ĐÚNG hàng đợi mà vòng đọc kỹ sẽ chạy, nên chỉ đếm nguồn ĐANG BẬT:
    # đếm cả nguồn đã tắt thì nút mời "đọc nốt 107 tin" rồi chạy xong đọc 0.
    doc = nguon_doc(conn)
    do_dang = one("SELECT COUNT(*) FROM posting WHERE source IN"
                  f" ({','.join('?' * len(doc))})"
                  " AND length(COALESCE(description,'')) < ?"
                  " AND (kept = 1 OR user_keep = 1)",
                  (*doc, HAVE_DESC)) if doc else 0
    if do_dang:
        return {"mode": TIEP, "label": "Tiếp tục", "recent": 0, "todo": do_dang,
                "note": f"còn {do_dang:,} tin chưa đọc kỹ — đọc nốt chỗ dở,"
                        f" không tìm lại từ đầu"}

    # 2. LINKEDIN TẮT -> KHÔNG CÓ LƯỚI NÀO ĐỂ PHỦ. Lưới chức danh × nơi là
    #    của riêng nguồn linkedin; board và thư báo chạy mọi lượt và xong
    #    trong vài giây, chẳng có gì "chưa quét bao giờ" để kể. Nút mà vẫn ghi
    #    "Chạy — 80 lượt tìm chưa quét" trong khi vòng tìm không chạy thì đó
    #    là lời nói dối, và người dùng học được rằng đừng tin cái nút đó nữa.
    bat_li = prefs.flag(conn, prefs.SRC_LINKEDIN)
    if not bat_li:
        con = ", ".join(n for n in ("board", "alert")
                        if prefs.flag(conn, getattr(prefs, f"SRC_{n.upper()}")))
        return {"mode": MOI, "label": "Cập nhật", "recent": 0, "todo": 0,
                "note": ("LinkedIn đang tắt — chỉ hỏi tin mới từ " + con)
                        if con else "mọi nguồn đang tắt — chưa quét được gì"}

    # 3. CÒN CẶP NÀO CHƯA HỎI BAO GIỜ?
    thieu, tong = con_thieu(conn, store.load(conn))
    if not tong:
        # Không có cặp nào để hỏi = hồ sơ chưa khai chức danh. "Cập nhật" ở
        # đây là vô nghĩa — không có gì để cập nhật. Và run_scan cũng sẽ từ
        # chối chạy, nên nút phải nói đúng thứ sắp xảy ra.
        return {"mode": DAU, "label": "Chạy", "recent": 0, "todo": 0,
                "note": "hồ sơ chưa khai chức danh nào — chưa quét được"}
    if thieu:
        rieng = "" if len(thieu) == tong else " (phần còn lại chỉ hỏi tin mới)"
        return {"mode": DAU, "label": "Chạy", "recent": 0, "todo": len(thieu),
                "note": f"{len(thieu)}/{tong} lượt tìm chưa quét bao giờ — "
                        f"quét đầy đúng mấy lượt đó{rieng}"}

    # 4. Phủ hết rồi -> chỉ hỏi tin mới. Cửa sổ co giãn theo chính khoảng
    #    nghỉ: quét đều thì 24 giờ, nghỉ vài hôm thì nới ra 7 ngày. Một con số
    #    cứng sẽ bỏ sót đúng lúc người dùng đi vắng lâu nhất.
    row = conn.execute(
        "SELECT started_at FROM source_run WHERE source = 'linkedin' AND ok = 1"
        " ORDER BY id DESC LIMIT 1").fetchone()
    cach = 0.0
    if row and row[0]:
        try:
            cach = (datetime.now(timezone.utc)
                    - datetime.fromisoformat(row[0])).total_seconds()
        except (ValueError, TypeError):
            cach = 0.0
    if cach <= li.NGAY:
        return {"mode": MOI, "label": "Cập nhật", "recent": li.NGAY, "todo": 0,
                "note": "đã phủ hết lưới — chỉ hỏi tin đăng trong 24 giờ qua"}
    return {"mode": MOI, "label": "Cập nhật", "recent": li.TUAN, "todo": 0,
            "note": "nghỉ mấy hôm rồi — hỏi tin đăng trong 7 ngày qua"}


# HAI NGUỒN, HAI CÁCH, HAI CÔNG TẮC. Cùng trỏ tới một trang
# `/jobs/view/<id>` của LinkedIn, nhưng đường mang cái id về khác hẳn nhau:
#
#     linkedin   gõ từ khoá vào endpoint khách — 80 lượt tìm, nửa tiếng, nằm
#                ngoài Điều khoản mục 8.2 (xem ingest/web/linkedin.py)
#     alert      đọc thư báo trong hộp thư của CHÍNH MÌNH — 6 giây, sạch
#
# Nên không gộp. Tắt `linkedin` thì `alert` vẫn đi TRỌN dây chuyền: về, lọc,
# đọc kỹ, chấm. Tắt một nguồn không được làm chết nguồn khác.
#
# CHROME LÀ CÔNG CỤ, KHÔNG PHẢI NGUỒN. Mô tả việc nằm trên trang web, nên tin
# của nguồn nào cũng phải mở trang ra mà đọc — kể cả tin do thư báo mang về,
# vì thư báo chỉ cho chức danh, công ty, nơi và id. Trước đây cả vùng Chrome
# nằm sau công tắc `linkedin`, nên tắt nó là 107 tin thư báo đứng im không ai
# chấm: một công tắc tắt luôn một nguồn khác.
DOC_KY = ("linkedin", "alert")

# Công tắc của từng nguồn cần đọc kỹ. Bảng chứ không phải if/else: thêm nguồn
# thứ tư thì thêm một dòng, không phải đi sửa bốn chỗ.
CONG_TAC = {"linkedin": "SRC_LINKEDIN", "alert": "SRC_ALERT"}


def nguon_doc(conn) -> tuple[str, ...]:
    """Nguồn nào ĐANG BẬT và cần đọc kỹ. Mỗi nguồn tự quyết phần của mình."""
    from .core import prefs
    return tuple(n for n in DOC_KY
                 if prefs.flag(conn, getattr(prefs, CONG_TAC[n])))


def _tin_do_dang(conn, nguon: tuple[str, ...] = DOC_KY) -> dict:
    """{nguồn: [tin]} — tin đáng đọc kỹ mà chưa có mô tả, dựng lại từ DB.

    Trả về THEO NGUỒN chứ không trộn một rổ: `save_batch` ghi theo cặp
    (nguồn, id), nên gộp lại rồi lưu dưới một tên là đẻ ra dòng mới thay vì
    vá mô tả vào đúng dòng cũ. Và vì hai nguồn tắt bật riêng, `nguon` phải
    lọc được — hàng đợi của nguồn đang tắt không phải việc của lượt này.
    """
    from .core.postings import HAVE_DESC
    from .ingest.base import Posting
    if not nguon:
        return {}
    rows = conn.execute(
        "SELECT r.source, r.source_id, p.title, p.company, p.location, p.url"
        "  FROM raw_posting r JOIN posting p ON p.raw_id = r.id"
        f" WHERE r.source IN ({','.join('?' * len(nguon))})"
        "   AND length(COALESCE(p.description,'')) < ?"
        "   AND (p.kept = 1 OR p.user_keep = 1)",
        (*nguon, HAVE_DESC)).fetchall()
    out: dict = {}
    for r in rows:
        out.setdefault(r["source"], []).append(
            Posting(source_id=r["source_id"], title=r["title"] or "",
                    company=r["company"] or "", location=r["location"] or "",
                    url=r["url"] or "", payload={"guest": True}))
    return out


def _chrome_pass(conn, answers: dict, log: Log, deep: bool,
                 manual: bool = False) -> tuple[int, int]:
    """Việc cần tới TRANG WEB. Chạy sau nguồn API, chỉ trong cửa sổ giờ người.

    CHROME LÀ CÔNG CỤ DÙNG CHUNG. Hai việc khác nhau cùng cần nó:

        tìm       gõ từ khoá vào endpoint khách  -> của riêng nguồn linkedin
        đọc kỹ    mở /jobs/view/<id> lấy mô tả   -> của MỌI nguồn đang bật

    Nên công tắc `linkedin` chỉ tắt được việc TÌM. Tin thư báo vẫn được đọc
    kỹ, vì `alert` là nguồn khác và nó đang bật.

    Mỗi nguồn chạy độc lập: một nguồn bị chặn hay hỏng KHÔNG được làm chết
    các nguồn còn lại.
    """
    from .browser import cdp, chrome
    from .core import prefs
    from .core.scheduler import in_human_window
    from .ingest.web import linkedin as li
    from .ingest.web.base import Blocked

    # titles[:5] ĐÃ BỎ: nó cắt 7/12 chức danh của hồ sơ mà không báo gì, và nó
    # tồn tại chỉ vì vòng đọc kỹ chạy quá lâu. Sửa gốc rồi thì không cần cắt —
    # trần bây giờ nằm ở li.MAX_QUERIES và có ghi nhật ký khi chạm.
    # eFinancialCareers đã BỎ: 67% tin của nó là môi giới (LinkedIn 24%), mà
    # chỉ cho 5 tin đạt 75+ so với 20 của LinkedIn. Bẩn gấp ba, ít hơn bốn lần.
    titles = [t.strip() for t in (answers.get("job_titles") or "").splitlines() if t.strip()]
    levels = answers.get("seniority") or ["grad", "junior"]
    nhip = prefs.get(conn, prefs.PACE) or "thuong"
    bat_li = prefs.flag(conn, prefs.SRC_LINKEDIN)

    # LƯỢT NÀY LÀM GÌ — hỏi đúng chỗ đã đặt tên cho nút Chạy, nên thứ máy làm
    # và thứ nút hứa không bao giờ lệch nhau.
    kieu = scan_mode(conn)

    # DỰNG DANH SÁCH VIỆC TRƯỚC KHI MỞ CHROME. Toàn đọc DB, không tốn gì —
    # mà đổi lại: không có việc thì không mở cửa sổ nào. Trước đây Chrome mở
    # trước rồi mới biết chẳng có gì làm, và người dùng thấy một cửa sổ nhảy
    # lên rồi tắt mà không hiểu vì sao.
    viec: list[tuple[str, object]] = []
    dem: dict[str, int] = {}

    if kieu["mode"] == TIEP:
        # KHÔNG TÌM GÌ CẢ. Chỗ dở nằm sẵn trong DB rồi; chạy lại vòng tìm là
        # mở lại 2.296 tin y hệt trong 30 phút để rồi đọc nốt mấy tin đã biết
        # từ đầu là tin nào.
        #
        # MỖI NGUỒN MỘT LƯỢT LƯU. save_batch ghi theo cặp (nguồn, id): đọc
        # xong tin của thư báo rồi lưu dưới tên "linkedin" là đẻ ra một dòng
        # mới, còn dòng thư báo vẫn trống mô tả như cũ.
        do_dang = _tin_do_dang(conn, nguon_doc(conn))
        dem = {n: len(v) for n, v in do_dang.items()}

        def _doc(_ten, _items):
            def chay(tab):
                suc = li.read_deep(tab, _items, pace=nhip, ten=_ten,
                                   stop=lambda: halt.wanted(STAGE))
                return _items, suc
            return chay
        viec = [(ten, _doc(ten, items)) for ten, items in sorted(do_dang.items())]

    places = li.places_for(answers.get("markets") or [],
                           answers.get("location") or "")
    # `vua_phu` phải có mặt dù vòng tìm không chạy: vòng lưu ở dưới đọc nó để
    # biết có cặp nào vừa phủ không. Định nghĩa trong nhánh else thì bấm "Tiếp
    # tục" là NameError — bị `except Exception` bắt mất, nên mô tả đã lưu
    # xong rồi mà lượt quét vẫn bị ghi là HỎNG. Không nguồn nào báo lỗi ra.
    vua_phu: set[str] = set()
    phu, _muc_cu = da_quet(conn)
    seen: set[str] = set()
    tu_giu: set[str] = set()

    if kieu["mode"] != TIEP and bat_li and titles:
        # Đã đọc rồi thì thôi — tính trên CẢ HAI nguồn, vì cùng một id là cùng
        # một trang. Đây KHÔNG phải gộp nguồn: chỉ là không mở lại một trang
        # đã đọc. Chỉ hỏi mỗi "linkedin" thì một tin thư báo đã có mô tả vẫn
        # bị mở lại lần nữa.
        seen = postings.already_read(conn, DOC_KY)

        # Cộng thêm những tin Vin đã tự tay GIỮ LẠI: lưới sàng loại chúng, nên
        # nếu chỉ hỏi mỗi lưới thì chúng không bao giờ được đọc kỹ — giữ lại
        # một tin rồi nó đứng mãi ở "máy chưa đọc" là nút Giữ tự phản bội mình.
        tu_giu = {r[0] for r in conn.execute(
            "SELECT r.source_id FROM raw_posting r JOIN posting p ON p.raw_id = r.id"
            " WHERE r.source IN ({}) AND p.user_keep = 1".format(
                ",".join("?" * len(DOC_KY))), DOC_KY)}

        # ĐÁNG ĐỌC KỸ KHÔNG. Trả lời bằng đúng bộ lọc mà derive() sẽ dùng sau
        # đó, nên không có hai luật song song có ngày lệch nhau.
        def dang_doc(item) -> bool:
            if item.source_id in tu_giu:
                return True
            giu, _ = jobfilter.judge(item, answers)
            return giu

        # Cặp nào đã phủ thì chỉ hỏi tin mới; cặp chưa phủ thì hỏi đầy.
        # `vua_phu` là chỗ vòng tìm ghi lại những cặp nó vừa hỏi đầy trọn vẹn
        # — chỉ chúng mới được cộng vào trí nhớ. Cửa sổ cho cặp ĐÃ phủ; chưa
        # từng quét trọn lượt nào (phu rỗng) thì mọi cặp đều hỏi đầy.
        cua_so = kieu["recent"] or li.NGAY
        viec.append((li.NAME, lambda tab: li.fetch(
            tab, titles, location=places, levels=levels, pages=4, deep=deep,
            skip=frozenset(seen), worth=dang_doc, pace=nhip, recent=cua_so,
            covered=frozenset(phu), done_out=vua_phu,
            stop=lambda: halt.wanted(STAGE))))

    if not viec:
        # Nói ra vì sao trống. "Không có gì xảy ra" mà im lặng thì người dùng
        # chỉ thấy lượt quét xong nhanh lạ và không biết mình tắt mất cái gì.
        jlog.emit(SEARCH, "không có việc nào cần trang web"
                          + ("" if bat_li else " · LinkedIn đang tắt")
                          + ("" if titles else " · hồ sơ chưa khai chức danh"))
        return 0, 0

    # Cửa sổ giờ tồn tại vì lướt web lúc 3 giờ sáng MỖI ĐÊM là nhịp máy, không
    # phải nhịp người. Nhưng khi chính người dùng bấm chạy thì đó LÀ người thật.
    if not manual and not in_human_window():
        log("  chrome: ngoài cửa sổ giờ người, bỏ tới lượt sau")
        jlog.warn(SEARCH, f"ngoài cửa sổ giờ người — {len(viec)} việc chờ lượt sau")
        return 0, 0

    jlog.progress(SEARCH, "mở Chrome")
    try:
        chrome.launch(headless=False)          # headed: trang chặn headless
    except chrome.ChromeError as exc:
        jlog.error(SEARCH, f"không mở được Chrome: {exc}")
        log(f"  chrome                     FAILED  {exc}")
        return 0, 0

    # Từ đây tới hết hàm, Chrome ĐANG MỞ. Nên mọi lối ra đều phải đi qua
    # finally: đóng Chrome khi xong việc, và ĐẶC BIỆT là khi hỏng.
    #
    # Trước đây lệnh đóng nằm ở cuối hàm, ngoài mọi try. Chỉ cần một lỗi ở
    # giữa — DB bị khoá lúc đọc `already_read`, máy ngủ dậy socket chết — là
    # cửa sổ Chrome nằm lại trên màn hình cho tới khi tắt app. Mà app này
    # chạy 24/7: "tới khi tắt app" nghĩa là mãi mãi.
    try:
        # NÓI RA LƯỢT NÀY LÀM GÌ, theo từng việc một. "quét" là một chữ che
        # mất ba việc khác nhau; người dùng phải đọc được mình đang trả tiền
        # cho cái gì.
        jlog.emit(SEARCH, f"{kieu['label'].upper()} — {kieu['note']}")
        if kieu["mode"] == TIEP:
            jlog.emit(SEARCH, f"đọc nốt {sum(dem.values()):,} tin dở, bỏ qua"
                              " vòng tìm · "
                              + " · ".join(f"{n} {c}" for n, c in sorted(dem.items())))
        else:
            jlog.emit(SEARCH, f"linkedin: {len(titles)} chức danh × {len(places)} nơi"
                              f" · bỏ qua {len(seen)} tin đã đọc"
                              + (f" · {len(tu_giu)} tin bạn tự giữ" if tu_giu else ""))

        total_seen = total_new = 0
        for name, run in viec:
            tab = None
            try:
                tab = cdp.open_tab()
                items, health = run(tab)
                seen, new = postings.save_batch(conn, name, items)
                # health.ok chứ không phải True cứng: nguồn bị chặn giữa chừng vẫn
                # trả về tin (những tin đọc kịp), nhưng lần quét đó KHÔNG lành.
                postings.record_run(conn, name, ok=health.ok, fetched=seen, new_rows=new,
                                    error="" if health.ok else f"blocked: {health.summary}",
                                    attempted=health.attempted, failed=health.failed)
                # GHI NHỚ NHỮNG CẶP VỪA PHỦ. Cộng dồn chứ không ghi đè:
                # một lượt bị dừng giữa chừng vẫn phủ được mấy cặp đầu, và
                # phần đó không việc gì phải làm lại.
                #
                # Cặp nào chỉ được hỏi cửa sổ 24 giờ thì KHÔNG nằm trong đây —
                # liếc phần mới nhất không phải là đã phủ.
                if health.ok and vua_phu:
                    import json as _json
                    cu_phu, _ = da_quet(conn)
                    prefs.put(conn, prefs.LI_DONE,
                              _json.dumps(sorted(cu_phu | vua_phu)))
                    prefs.put(conn, prefs.LI_LEVELS, _json.dumps(sorted(levels)))
                    jlog.emit(SEARCH, f"đã phủ thêm {len(vua_phu - cu_phu)} lượt tìm"
                                      f" · tổng {len(cu_phu | vua_phu)}")
                bad = f"  ⚠ {health.summary}" if health.failed else ""
                (jlog.ok if health.ok else jlog.warn)(
                    SEARCH, f"{name}: {seen} tin, {new} mới"
                            + (f" · {health.summary}" if health.summary else ""))
                log(f"  {name:26} {seen:5} tin, {new:5} mới{bad}")
                total_seen += seen; total_new += new
            except Blocked as exc:
                # Trang từ chối truy cập tự động. Ghi nhận rồi thôi — không cãi lại.
                postings.record_run(conn, name, ok=False, error=f"blocked: {exc}")
                postings.log(conn, "source_blocked", f"{name}: {exc}")
                jlog.warn(SEARCH, f"{name}: BỊ CHẶN — {str(exc)[:60]}")
                log(f"  {name:26} BLOCKED {str(exc)[:44]}")
            except Exception as exc:                # noqa: BLE001
                postings.record_run(conn, name, ok=False,
                                    error=f"{type(exc).__name__}: {exc}")
                jlog.error(SEARCH, f"{name}: {type(exc).__name__} — {str(exc)[:60]}")
                log(f"  {name:26} FAILED  {type(exc).__name__}: {str(exc)[:40]}")
            finally:
                if tab is not None:
                    tab.close()

        return total_seen, total_new
    finally:
        # Mở lại tốn ~2 giây, không đáng để đánh đổi một cửa sổ nằm lì cả tiếng.
        if not chrome.shutdown():
            jlog.warn(SEARCH, "không đóng được Chrome — nó vẫn đang mở")



def run_scan(log: Log | None = None, chrome_sources: bool = True,
             deep: bool = True, manual: bool = False) -> dict:
    say: Log = log or (lambda _msg: None)
    conn = db.connect()
    try:
        answers = store.load(conn)
        if not store.can_ingest(answers):
            # PHẢI nói ra. Trước đây chỗ này `return` lặng lẽ: bấm Chạy thì
            # API vẫn đáp "đang chạy…", nhật ký trống, không tin nào về, người
            # dùng ngồi chờ vô tận. Một lần từ chối mà không ai biết lý do thì
            # tệ hơn là không có nút.
            thieu = store.missing_for_ingest(answers)
            hoi = all_questions()
            ten = " · ".join(hoi[q].text for q in thieu if q in hoi)
            jlog.warn(SEARCH, f"chưa quét được — hồ sơ còn thiếu: {ten}")
            say(f"hồ sơ chưa đủ: {ten}")
            return {"ok": False, "summary": "hồ sơ chưa đủ", "missing": thieu}

        # Mốc thời gian, KHÔNG phải con số tổng: "việc mới" là việc lần quét
        # NÀY mang về, không phải hiệu của hai lần đếm. Lấy hiệu thì một lần
        # quét mang về 10 việc mới mà đồng thời 10 việc cũ bị loại sẽ ra 0,
        # và người dùng không được báo gì cả.
        started_at = postings.now()
        boards = load_boards(conn)
        postings.log(conn, "scan_started")

        # arbeitnow + remotive ĐÃ BỎ: sai thị trường. Arbeitnow là job board
        # châu Âu, Remotive là remote toàn cầu — hai nguồn tải về 1.992 tin để
        # giữ lại đúng 1. Vin ở UK, visa không xin sponsor.
        # Board công ty thì giữ: tỉ lệ thấp là vì tải cả board rồi mới lọc,
        # nhưng đó là chủ việc TRỰC TIẾP và chỉ tốn HTTP.
        todo = [(f"{key}:{board}", mod.fetch_board, (board,))
                for mod, key in ((greenhouse, "greenhouse"), (lever, "lever"),
                                 (ashby, "ashby"))
                # dict.fromkeys: hai công ty tên khác nhau có thể ra CÙNG một
                # slug ("Ocado" và "Ocado Group" -> ocadogroup) -> gọi HTTP hai
                # lần cho một board và cộng đôi vào tổng "thấy".
                for board in dict.fromkeys(boards.get(key, []))]
        # CÔNG TẮC NGUỒN. Hai cách tìm cho ra hai loại tin khác hẳn nhau, nên
        # có lúc chỉ muốn chạy một cái. Đọc ở đây chứ không ở chỗ gọi: lượt
        # quét tự động và nút Chạy tay đều phải nghe cùng một công tắc.
        from .core import prefs
        bat_board = prefs.flag(conn, prefs.SRC_BOARD)
        bat_li = prefs.flag(conn, prefs.SRC_LINKEDIN)
        if not bat_board:
            jlog.warn(SEARCH, f"board đang TẮT — bỏ qua {len(todo)} nguồn API")
            todo = []
        else:
            # Từng ATS một. Công tắc to (board) và công tắc nhỏ (từng ATS) là
            # hai tầng: tắt tầng nào cũng dừng được, và phải NÓI RA tắt cái
            # nào — bỏ qua im lặng thì quét xong ít tin hẳn mà không ai hiểu.
            tat = [k for k, key in prefs.SRC_ATS.items() if not prefs.flag(conn, key)]
            if tat:
                truoc = len(todo)
                todo = [t for t in todo if t[0].split(":")[0] not in tat]
                jlog.warn(SEARCH, f"tắt {', '.join(tat)} — bỏ qua"
                                  f" {truoc - len(todo)}/{truoc} nguồn API")
        if not bat_li:
            # TẮT LINKEDIN = TẮT VIỆC TÌM BẰNG TỪ KHOÁ. Không phải tắt Chrome:
            # Chrome còn là đường lấy MÔ TẢ cho tin của nguồn khác, và thư báo
            # là một nguồn khác với công tắc riêng.
            #
            # Gộp hai thứ đó vào một công tắc đã có giá đo được: 107 tin thư
            # báo nằm im không ai chấm, nhật ký ghi đúng "LinkedIn đang TẮT"
            # mà vẫn không ai nối được với hậu quả, vì hậu quả thuộc nguồn khác.
            jlog.warn(SEARCH, "LinkedIn đang TẮT — không gõ từ khoá lượt này"
                              + (" · thư báo vẫn chạy trọn dây chuyền"
                                 if prefs.flag(conn, prefs.SRC_ALERT) else ""))

        # THƯ BÁO VIỆC — nguồn thứ ba. Xếp cùng nhóm với board API vì nó
        # cũng rẻ và cũng không cần Chrome: 69 việc trong 6 giây, đo trên hộp
        # thư thật. Không có mô tả, nên vòng đọc kỹ vẫn phải mở từng tin —
        # nhưng nó báo nhanh hơn hẳn, và sạch về nguyên tắc.
        if prefs.flag(conn, prefs.SRC_ALERT):
            from .ingest import alerts
            from .track import mail as _mail
            dia_chi, mat_khau = _mail.account()
            if dia_chi and mat_khau:
                ngay = prefs.num(conn, prefs.MAIL_DAYS, 1, 365)
                todo.append((alerts.NAME, alerts.fetch,
                             (dia_chi, mat_khau, ngay)))
            else:
                jlog.warn(SEARCH, "thư báo việc: chưa nối hộp thư — bỏ qua")

        # `chrome_sources` là cờ của NGƯỜI GỌI (lượt cron nhẹ, test) — tắt hẳn
        # Chrome. Còn việc gì cần trang web thì _chrome_pass tự quyết theo
        # từng công tắc nguồn, nên ở đây chỉ nói "có mở Chrome hay không".
        jlog.emit(SEARCH, f"bắt đầu quét — {len(todo)} nguồn nhanh"
                          + (" + vòng Chrome" if chrome_sources else ""))

        total_seen = total_new = 0
        stopped = False
        for index, (name, fn, args) in enumerate(todo, 1):
            # Điểm ngắt: GIỮA hai nguồn, không phải giữa một giao dịch. Nửa
            # giao dịch ghi vào DB còn tệ hơn chạy nốt nguồn đang dở.
            if halt.wanted(STAGE):
                stopped = True
                break
            jlog.progress(SEARCH, f"nguồn API — {name}", index, len(todo))
            s, n = _run_source(conn, name, fn, *args, log=say)
            total_seen += s; total_new += n

        if chrome_sources and not stopped and not halt.wanted(STAGE):
            s, n = _chrome_pass(conn, answers, say, deep, manual)
            total_seen += s; total_new += n
        elif chrome_sources:
            jlog.warn(SEARCH, "bỏ qua vòng Chrome — đã xin dừng")

        if halt.wanted(STAGE):
            stopped = True

        # --- tầng suy diễn: lọc + gộp + chấm, MỘT giao dịch ---
        from .core.derive import derive
        result = derive(conn, log=say)
        kept, n_groups = result["kept"], result["groups"]
        agencies, marks = result["agencies"], {"scored": result["scored"]}

        # --- danh sách công ty tự lớn lên ---
        from .ingest.web import companies as co
        learned = co.learn_from_postings(conn)
        found = co.resolve_pending(conn, limit=12)
        if learned or found["found"]:
            say(f"  công ty: +{learned} mới, dò ra {found['found']}/{found['checked']}")

        fresh_matches = int(conn.execute(
            "SELECT COUNT(*) FROM posting p JOIN raw_posting r ON p.raw_id = r.id"
            " WHERE p.kept = 1 AND r.fetched_at >= ?", (started_at,)).fetchone()[0])

        summary = (f"thấy {total_seen} · mới {total_new} · giữ {kept} · "
                   f"{n_groups} việc duy nhất · {agencies} qua môi giới")
        postings.log(conn, "scan_finished", summary)
        jlog.done(SEARCH)
        jlog.ok(SEARCH, f"quét xong — {summary}")
        return {"ok": True, "summary": summary, "seen": total_seen, "new": total_new,
                "kept": kept, "groups": n_groups, "scored": marks["scored"],
                "new_matches": fresh_matches}
    finally:
        conn.close()
