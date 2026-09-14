"""Quản lí — bước 5 và 6. Một dòng cho một lần nộp.

    MÁY ĐIỀN -> sinh ra một dòng "đang điền"
    VIN GỬI  -> thư xác nhận về, dòng đó thành "đã nộp"
    THƯ VỀ   -> đề xuất đổi trạng thái tiếp
    BẢNG     -> mọi dòng, xem và sửa được

Thư là CẢM BIẾN, bảng là TRẠNG THÁI. Không phải hai tính năng, là một vòng.

Máy KHÔNG bấm Gửi. Nó điền phần chứng minh được rồi dừng; ba câu như
sponsorship hay ngày tốt nghiệp là việc của Vin, và cú bấm cuối cũng vậy.
Ranh giới đó nằm trong `apply/run.py` — ở đó không có lệnh bấm Gửi nào.

CHỈ VẼ.
"""

from __future__ import annotations

from html import escape as esc
from urllib.parse import quote

from ...track.board import OPEN, SILENT_AFTER, SONG_IM, STAGE_LABEL
from . import runtime

# BỐN NHÓM, xếp theo VIỆC PHẢI LÀM chứ không theo bảng chữ cái.
#
# `stage` một mình không đủ: "đã nộp" hôm qua và "đã nộp" 40 ngày trước rồi
# im bặt là hai tình trạng khác hẳn nhau, mà bảng cũ vẽ chúng giống hệt.
NHOM = (
    ("nong", "Họ đang nói chuyện với bạn",
     "việc quan trọng nhất trên màn hình này"),
    ("cho", "Còn trong cửa sổ hồi âm",
     "chưa quá {n} ngày kể từ lần chạm cuối — vẫn có thể có tin"),
    # "COI NHƯ TRƯỢT", không phải "im quá lâu". Đây là quyết định của người
    # dùng chứ không phải máy tự nghĩ ra, nên nó được nói bằng chữ của kết
    # cục — "im quá lâu" là mô tả thời tiết, "coi như trượt" là một ô đã
    # đóng. Chữ "coi như" giữ đúng sự thật: họ chưa nói gì cả.
    ("im", "Coi như trượt",
     "quá {n} ngày không một chữ — họ CHƯA nói gì, đây là bạn suy ra. "
     "Đo trên hộp thư của bạn: {tl} lần nộp có hồi âm, và quãng im lâu nhất "
     "từng có thư về là {max} ngày. Đổi mốc ở nút ⚟ trên thanh"),
    ("xong", "Đã chốt", "có kết cục rồi, để lại cho đủ bức tranh"),
)


# --------------------------------------------------------- ô tìm + lọc
#
# Cùng khuôn với "Việc tìm được" bên Search: ô tìm FORM GET, hàng chip đổi
# ngay không qua nút Áp dụng, trạng thái nằm hết trên URL nên lưu lại được và
# Back được. Học một tab là biết cả ba.

LOC = (
    ("ng", "Nguồn", (("", "tất cả"), ("board", "board"), ("linkedin", "linkedin"),
                     ("alert", "alert"), ("ngoai", "ngoài app"))),
    ("ai", "Ai nộp", (("", "tất cả"), ("mail", "tự nộp trước đây"),
                      ("apply", "nộp qua app"), ("auto", "máy nộp"),
                      ("tay", "phải tự nộp tay"))),
    ("tt", "Tình trạng", (("", "tất cả"), ("nong", "đang nói chuyện"),
                          ("cho", "còn cửa sổ"), ("im", "coi như trượt"),
                          ("xong", "đã chốt"))),
    ("cv", "Bản CV", (("", "tất cả"), ("co", "có"), ("khong", "chưa có"))),
)


def _url(loc: dict, **doi) -> str:
    d = {**loc, **doi}
    cap = "&".join(f"{k}={quote(str(v), safe='')}" for k, v in d.items() if v)
    return "/track" + ("?" + cap if cap else "")


def _hop_loc(r: dict, loc: dict) -> bool:
    """Dòng này có lọt lưới lọc đang đặt không."""
    ng = loc.get("ng") or ""
    if ng == "ngoai" and r.get("nguon"):
        return False
    if ng and ng != "ngoai" and r.get("nguon") != ng:
        return False
    if (loc.get("ai") or "") and (r.get("origin") or "") != loc["ai"]:
        return False
    if (loc.get("tt") or "") and (r.get("song") or "") != loc["tt"]:
        return False
    cv = loc.get("cv") or ""
    if cv == "co" and not r.get("co_cv"):
        return False
    if cv == "khong" and r.get("co_cv"):
        return False
    q = (loc.get("q") or "").strip().lower()
    if q and q not in f"{r.get('company','')} {r.get('role','')}".lower():
        return False
    return True


def _thanh_loc(loc: dict, rows: list[dict]) -> str:
    """Ô tìm + bốn hàng chip. Mỗi chip kèm SỐ DÒNG nó sẽ để lại.

    Số đó là thứ biến hàng nút thành công cụ: bấm vào một chip ra 0 dòng thì
    biết trước, không phải bấm rồi mới thấy bảng trống.
    """
    an = "".join(f"<input type=hidden name='{esc(k)}' value='{esc(v)}'>"
                 for k, v in loc.items() if k != "q" and v)
    xoa = (f"<a class=jfindx href='{esc(_url(loc, q=''))}'"
           f" title='Bỏ tìm, xem lại tất cả'>×</a>" if loc.get("q") else "")
    o = (f"<form class=jfind method=get action='/track'>{an}"
         f"<input class=search type=search name=q value='{esc(loc.get('q') or '')}'"
         f" autocomplete=off spellcheck=false"
         f" placeholder='tìm trong bảng — công ty hoặc vị trí'>{xoa}</form>")
    def _nhom(ma, ten, chon) -> str:
        nut = ""
        for gia, nhan in chon:
            dem = sum(1 for r in rows if _hop_loc(r, {**loc, ma: gia}))
            on = (loc.get(ma) or "") == gia
            nut += (f"<a class='vchip{' on' if on else ''}"
                    f"{' nil' if not dem else ''}'"
                    f" href='{esc(_url(loc, **{ma: gia}))}'>{esc(nhan)}"
                    f"<b>{dem}</b></a>")
        return f"<span class=vgrp><span class=locten>{esc(ten)}</span>{nut}</span>"

    # HAI NHÓM MỘT HÀNG, đúng cách "Việc tìm được" xếp. Bốn hàng rời thì riêng
    # phần lọc đã ăn 120px, và cái bảng 37 dòng bên dưới còn đúng hai dòng.
    d = {ma: (ten, chon) for ma, ten, chon in LOC}
    hang = (f"<div class=vbar>{_nhom('ng', *d['ng'])}{_nhom('ai', *d['ai'])}</div>"
            f"<div class=vbar>{_nhom('tt', *d['tt'])}{_nhom('cv', *d['cv'])}</div>")
    return o + f"<div class=locbox>{hang}</div>"


# ------------------------------------------------------------ một dòng

def _chi_tiet(r: dict, thu: list[dict]) -> str:
    """RUỘT của một dòng — mở ra khi bấm.

    Ba thứ, và cả ba là đường ĐI TIẾP chứ không phải chữ để đọc:
        thư đã nhận     bằng chứng của mọi trạng thái trên dòng này
        bản CV đã gửi   mở đúng tờ đã đi ra ngoài
        tin gốc         JD mà app tìm được, nếu nối được
    """
    o = ""
    if thu:
        muc = "".join(
            f"<li><span class=dtkind>{esc(m['kind'])}</span>"
            f"<span class=dtsub>{esc(' '.join((m['subject'] or '').split())[:96])}</span>"
            f"<span class=dtwhen>{esc(str(m['received_at'])[:10])}</span>"
            f"<span class=dtsnip>{esc(' '.join((m['snippet'] or '').split())[:150])}</span>"
            f"</li>" for m in thu)
        o += (f"<div class=dtblock><b>{len(thu)} thư đã nhận</b>"
              f"<ul class=dtlist>{muc}</ul></div>")
    else:
        o += ("<div class=dtblock><span class=muted>chưa lá thư nào — "
              "công ty chưa hồi âm, hoặc thư nằm ngoài khoảng đang đọc"
              "</span></div>")

    # KHÔNG CÓ NÚT NÀO ĐỔI DÒNG NÀY. Ruột dòng là HỒ SƠ: thư đã nhận, tờ CV
    # đã gửi, tin gốc. Toàn đường để XEM. Việc "máy không nộp hộ được, bạn tự
    # nộp" đã sang Queue — nó là việc phải làm, mà bảng này không chứa việc.
    duong = ""
    if r.get("posting_id"):
        duong += (f"<a class='mbtn tiny' href='/jobs/{r['posting_id']}/cv?tu=/track'>"
                  f"Bản CV đã gửi</a>"
                  f"<a class='mbtn tiny' href='/jobs/{r['posting_id']}?tu=/track'>"
                  f"Tin gốc · {esc(r.get('nguon') or 'tin')}</a>")
        if r.get("url"):
            duong += (f"<a class='mbtn tiny' href='{esc(r['url'])}'"
                      f" target=_blank rel=noopener>Mở tin ngoài ↗</a>")
    else:
        # NÓI THẲNG VÌ SAO TRỐNG. "Không có gì" mà im lặng thì người dùng
        # tưởng app hỏng; nói ra thì họ biết đây là lần nộp ngoài app.
        duong += ("<span class=muted>nộp ngoài app — không có JD và không có "
                  "bản CV do máy dựng. Máy biết lần nộp này chỉ nhờ thư.</span>")
    return f"<div class=dtail>{o}<div class=dtact>{duong}</div></div>"


# CHÍN CỘT, MỖI CỘT MỘT NHÃN — bảng tính, không phải danh sách thẻ.
#
# Bản trước dồn công ty và vị trí vào một ô, và BỎ HẲN hàng tiêu đề khi đổi
# sang thẻ bấm mở được. Mất nhãn cột là mất cách đọc: người dùng phải đoán
# "20 ngày" là ngày nộp hay ngày im lặng.
#
# Vẫn là <details> để bấm mở tại chỗ — bảng <table> không mở ra được nếu
# không có JavaScript, mà mấy màn này của app không có một dòng JS nào. Hàng
# tiêu đề dùng ĐÚNG cùng một lưới cột với từng dòng, nên chúng thẳng hàng.
#
# CỘT HÀNH ĐỘNG ĐÃ BỎ, và nó là lý do bảng xộc xệch suốt: cột cuối khai
# `auto`, mà `auto` co theo NỘI DUNG. Ô tiêu đề cuối rỗng nên nó rộng 0;
# ô dữ liệu cuối có hai cái nút nên nó rộng 110 — hai cột `fr` đầu bảng
# chia phần thừa lệch nhau đúng 110px, và cả hàng trôi khỏi nhãn của nó.
# Giờ không còn track nào co theo nội dung: xem `--cot` trong app.css.
COT = ("công ty", "vị trí", "nguồn", "ai nộp", "nộp", "lần chạm cuối",
       "thư", "bản CV", "trạng thái")


def _dau_bang() -> str:
    return ("<div class=thead>" + "".join(
        f"<span>{esc(c)}</span>" for c in COT) + "</div>")


def _trang_thai(r: dict, nguong: int) -> str:
    """Huy hiệu ở cột TRẠNG THÁI — và nó phải nói CÙNG MỘT CÂU với nhóm.

    Bản trước in thẳng `stage`, nên một dòng im 21 ngày nằm dưới tiêu đề
    "Coi như trượt" mà huy hiệu của nó vẫn xanh "đã nộp". Hai câu trái nhau
    trên cùng một dòng, và mắt đọc cái huy hiệu chứ không đọc tiêu đề nhóm
    cách đó năm dòng — nên người dùng kết luận cái mốc không chạy.

    NHƯNG KHÔNG ĐƯỢC GIẢ LÀ HỌ TỪ CHỐI. "từ chối" là họ ĐÃ NÓI; đây là ta
    SUY RA. Nên chữ khác ("coi như trượt") và mặt mũi khác — viền đứt, xám,
    không tô nền như huy hiệu thật. Nhìn một cái là phân biệt được hai loại.
    """
    stage = r["stage"]
    if r.get("song") == SONG_IM:
        return (f"<span class='pill suy' title='họ chưa nói gì — quá {nguong}"
                f" ngày không một chữ nên đóng lại. Nới mốc ở nút ⚟ thì dòng"
                f" này mở lại'>coi như trượt</span>")
    return (f"<span class='pill {esc(stage)}'>"
            f"{esc(STAGE_LABEL.get(stage, stage))}</span>")


def _dong(r: dict, thu: list[dict], nguong: int = SILENT_AFTER) -> str:
    """MỘT lần nộp = một hàng bảng tính, bấm vào thì mở ruột ngay dưới.

    CHỈ FACT. Không một nút nào ở đây đổi được dòng nào — mọi thứ cần bạn
    quyết hay sửa đều nằm ở Queue. Bảng mà vừa là chỗ đọc vừa là chỗ bấm thì
    không bao giờ đọc yên được: mắt đang dò một cột thì tay đã ở cạnh một cái
    nút đổi trạng thái thật.
    """
    stage = r["stage"]
    im = r.get("im_ngay")
    qua = im is not None and im >= nguong
    cham = (f"<b>{im}</b>ng" if im is not None else "—")
    if r.get("ho_tra_loi"):
        cham += "<i>có trả lời</i>"
    elif (r.get("so_thu") or 0) <= 1:
        cham += "<i>chưa một chữ</i>"
    ng = r.get("nguon") or ""
    cv = ("<a class=plink href='/jobs/%s/cv?tu=/track'>xem</a>" % r["posting_id"]
          if r.get("posting_id") else "<span class=muted>—</span>")
    return (
        f"<details class='trow {esc(stage)} s{esc(r.get('song') or '')}"
        f"{' qua' if qua else ''}'>"
        f"<summary>"
        f"<span class=c1><b>{esc(r['company'][:34])}</b></span>"
        f"<span class=c2>{esc((r.get('role') or '—')[:44])}</span>"
        f"<span class=c3>" + (f"<i class='src {esc(ng)}'>{esc(ng)}</i>" if ng
                              else "<i class='src ngoai'>ngoài app</i>") + "</span>"
        f"<span class=c4>{esc(r.get('ai_nop') or '—')}</span>"
        f"<span class=c5>{r['days']}ng</span>"
        f"<span class=c6>{cham}</span>"
        f"<span class=c7>{r.get('so_thu') or 0}</span>"
        f"<span class=c8>{cv}</span>"
        f"<span class=c9>{_trang_thai(r, nguong)}</span>"
        f"</summary>{_chi_tiet(r, thu)}</details>")


def _table(rows: list[dict], thu: dict | None = None,
           loc: dict | None = None, nguong: int = SILENT_AFTER,
           lau: int = 0) -> str:
    loc = loc or {}
    thu = thu or {}
    if not rows:
        return ("<div class=empty-box>chưa nộp chỗ nào. Sang tab Search, "
                "bấm <b>Nộp</b> trên một tin — máy mở trang nộp, điền phần "
                "chứng minh được, rồi để bạn bấm Gửi.</div>")
    loc_ui = _thanh_loc(loc, rows)
    hien = [r for r in rows if _hop_loc(r, loc)]
    if not hien:
        return (loc_ui + "<div class=empty-box>không dòng nào lọt lưới lọc "
                "đang đặt — bỏ bớt một chip ở trên.</div>")
    nhap = [r for r in hien if r["stage"] == "draft"]
    tong = [r for r in hien if r["stage"] != "draft"]
    tra_loi = [r for r in tong if r.get("ho_tra_loi")]

    body = "".join(_dong(r, thu.get(r["id"], []), nguong) for r in nhap)
    da_ve = set()
    for ma, ten, y in NHOM:
        trong = [r for r in tong if r.get("song") == ma]
        if not trong:
            continue
        da_ve.update(id(r) for r in trong)
        chu = y.format(n=nguong, tl=len(tra_loi), max=lau)
        body += (f"<div class='tgroup g{ma}'><b>{esc(ten)}</b>"
                 f"<span>{len(trong)}</span><i>{esc(chu)}</i></div>")
        body += "".join(_dong(r, thu.get(r["id"], []), nguong) for r in trong)
    # KHÔNG DÒNG NÀO ĐƯỢC BIẾN MẤT. Xếp theo nhóm nghĩa là dòng nào không rơi
    # vào nhóm nào thì không được vẽ — một lần nộp có thật lặng lẽ rời khỏi
    # màn hình, và không có gì báo.
    con = [r for r in tong if id(r) not in da_ve]
    if con:
        body += (f"<div class=tgroup><b>Chưa xếp được nhóm</b>"
                 f"<span>{len(con)}</span></div>"
                 + "".join(_dong(r, thu.get(r["id"], []), nguong) for r in con))
    return loc_ui + f"<div class=tboard>{_dau_bang()}{body}</div>"


def _mailbox(ready: bool, address: str, days: int = 30) -> str:
    """Dòng hộp thư trên đầu bảng — CHỈ CÒN VIỆC, không còn cấu hình.

    Ô nhập địa chỉ + app password đã chuyển sang Cài đặt · Gmail. Nó là thứ
    nối một lần rồi thôi, mà trang này Vin mở hàng ngày; để một form cấu hình
    nằm trên đầu bảng việc là bắt mắt đọc lại nó mỗi ngày.

    Cái ở lại đây là VIỆC: bấm Quét thư. Chưa nối thì chỉ ra đúng chỗ nối.
    """
    if not ready:
        return ("<div class=boxrow><span class=muted>chưa nối hộp thư việc "
                "làm — thư trả lời sẽ không tự cập nhật bảng này</span>"
                "<button class='mbtn apply' data-appset='gmail'>"
                "Nối hộp thư…</button></div>")
    # "đã lưu", KHÔNG phải "đã nối": chỗ này chỉ biết config CÓ chuỗi, không
    # biết chuỗi đó còn đăng nhập được không. App password bị thu hồi bên
    # Google thì dòng này vẫn xanh, và Vin tin là hộp thư đang chạy.
    # NÚT QUÉT ĐÃ LÊN THANH KHÚC. Để lại đây nữa là hai nút cùng làm một
    # việc, và người dùng phải đoán hai nút có khác nhau không.
    return (f"<div class=boxrow><span class=boxok>hộp thư "
            f"<b>{esc(address)}</b> · đọc {days} ngày gần nhất — bấm "
            f"<b>Quét thư</b> trên thanh trên</span></div>")


def _nguong_num(dang: int, do: dict | None = None) -> str:
    """Núm MỐC IM LẶNG — quá bao nhiêu ngày thì coi như trượt.

    NĂM MỨC, không phải ô nhập số. Ô nhập là đẩy sang người dùng một câu hỏi
    họ không có dữ liệu để trả lời ("87 có hơn 86 không?"); năm mức thì mỗi
    mức có một nghĩa đọc ra được, và cái đang dùng có dấu ✓.

    CON SỐ TRONG CHÚ THÍCH LÀ SỐ ĐO, không gõ cứng: hồi âm là chuyện của
    từng hộp thư. Gõ cứng "14 ngày" thì đến hôm có lá về sau 19 ngày, app
    vẫn dạy đời bằng con số cũ.
    """
    from ...core import prefs
    d = do or {}
    tl, tong = d.get("tra_loi", 0), d.get("tong", 0)
    lau, ai, khoang = d.get("lau", 0), d.get("ai", ""), d.get("khoang") or []
    nut = ""
    for muc in prefs.IM_MUC:
        n = int(muc)
        on = n == dang
        # MỖI MỨC TỰ KHAI CÁI GIÁ CỦA NÓ, bằng số đếm được trên thư có thật:
        # đặt mốc này thì mấy lá thư đã về MUỘN HƠN THẾ — tức là mấy dòng bị
        # đóng oan. Đó là câu hỏi duy nhất cái núm này phải trả lời; "ít hay
        # nhiều ngày" thì người dùng nhìn con số cũng biết rồi.
        nham = sum(1 for k in khoang if k >= n)
        y = (f"đặt {n} ngày thì {nham} lá thư THẬT trong hộp thư của bạn đã "
             f"về sau khi dòng bị đóng" if nham else
             f"đặt {n} ngày thì không lá nào trong hộp thư của bạn bị đóng oan")
        nut += (f"<button class='mbtn tiny{' on' if on else ' off'}'"
                f" data-post='/api/track/num' data-arg='im_qua:{muc}'"
                f" title='{esc(y)}'>{'✓ ' if on else ''}{muc} ngày"
                + (f"<i class=nham>đóng oan {nham}</i>" if nham else "")
                + "</button>")
    dem = (f"đo trên hộp thư của bạn: <b>{tl}/{tong}</b> lần nộp từng có hồi "
           f"âm, và quãng im lâu nhất TỪNG CÓ THƯ VỀ là <b>{lau}</b> ngày"
           + (f" ({esc(ai)})" if ai else "")
           if tong else "chưa có lần nộp nào để đo")
    return (f"<div class=adjrow><div class=adjname><b>Coi như trượt sau</b>"
            f"<span>im bao lâu thì đóng dòng đó lại</span></div>"
            f"<div class=srcrow>{nut}</div></div>"
            f"<div class=note>{dem}. Đây là PHÉP SUY, không ghi vào bảng: "
            f"họ chưa nói gì cả. Đổi số này thì mọi dòng xếp lại ngay, và "
            f"nâng lên thì chúng quay về đúng chỗ cũ — không mất dòng nào."
            f"</div>")


def adjust(nop: dict | None = None, nguong: int = SILENT_AFTER,
           do: dict | None = None) -> str:
    """Tấm phủ ⚟ của khúc Quản lí — MỐC IM LẶNG, rồi BA NGUỒN.

    MỐC LÊN TRƯỚC vì nó đổi thứ người dùng NHÌN THẤY ngay trên bảng đang mở;
    ba công tắc nguồn đổi thứ xảy ra ở lượt nộp sau. Núm nào có tác dụng
    sớm hơn thì đứng trên.

    Bên Search ba công tắc cùng tên hỏi "CÓ QUÉT nguồn này không"; ở đây
    chúng hỏi "CÓ NỘP tin từ nguồn này không". Hai việc khác hẳn nhau nên
    hai bộ công tắc — gộp lại thì tắt LinkedIn để khỏi nộp là mất luôn 2.409
    tin khỏi kho, và người dùng không hiểu vì sao Search trống.
    """
    from ...core import prefs
    d = nop or {}
    hang = ""
    for khoa, (ten, y) in prefs.NOP.items():
        on = bool(d.get(khoa))
        hang += (f"<div class='swrow{'' if on else ' off'}'>"
                 f"<button class='mbtn tiny swbtn{'' if on else ' off'}'"
                 f" data-post='/api/track/num' data-arg='{esc(khoa)}:"
                 f"{'0' if on else '1'}'>{'BẬT' if on else 'TẮT'}</button>"
                 f"<b class=swten>{esc(ten)}</b>"
                 f"<span class=swnow>{'có nộp' if on else 'bỏ qua'}</span>"
                 f"<details class=swwhy><summary>vì sao</summary>"
                 f"<div class=swbody>{esc(y)}</div></details></div>")
    return ("<div class=sheethead>Điều chỉnh · Quản lí</div>"
            "<div class=adjbox>"
            "<div class=adjsec>Khi nào thì thôi chờ"
            "<span>bảng chỉ vơi đi được nếu có một mốc để đóng dòng</span>"
            "</div>"
            + _nguong_num(nguong, do)
            + "<div class=adjsec>Nộp tin từ nguồn nào"
            "<span>khác với công tắc bên Search — bên đó là CÓ QUÉT</span></div>"
            + hang
            + "<div class=note>Tắt LinkedIn <b>không</b> bỏ hết tin LinkedIn: "
              "phần lớn dẫn ra trang nộp của chính công ty và vẫn nộp được. "
              "Chỉ tin buộc nộp trong LinkedIn mới để bạn tự làm.</div></div>")


def render(*, rows: list[dict], asks: list[dict] | None = None,
           counts: dict | None = None,
           mu: list[dict] | None = None, stage: dict | None = None,
           thu: dict | None = None, loc: dict | None = None,
           mail_ready: bool = False, mail_address: str = "",
           mail_days: int = 30) -> str:
    from ..layout import deck
    info = stage or {}
    scan = _mailbox(mail_ready, mail_address, mail_days)
    # DÒNG `note` CŨ ĐÃ BỎ. Nó in "37 lần nộp · 35 đang chờ · 35 im lặng"
    # — "đang chờ" và "im lặng" gần bằng nhau vì phần lớn cái đang chờ CHÍNH
    # LÀ cái đã im. Hai cách đếm cùng một chồng, và không con nào nói phải
    # làm gì. Thay bằng `_tom`, bốn số mỗi số một việc.
    return runtime.render(
        title="Quản lí", active="/track", stream="search", journal="bottom",
        # VẼ LẠI khi khúc QUẢN LÍ chạy xong, không phải khi vòng quét xong.
        # Bảng này dựng từ đơn + thư, mà vòng quét chỉ đẻ ra tin — quét xong
        # mà nhảy trang thì nó đóng sập mọi dòng đang mở dở, đúng lúc người
        # dùng đang đọc một lá thư. Ô nhật ký vẫn xem luồng `search` vì đó
        # là khúc chạy lâu, đáng nhìn nhất; hai việc khác nhau.
        reload="track",
        cols=1,
        bar=deck("track", "Quản lí", info.get("state", "chưa nộp chỗ nào"),
                 # TRƯỢT và IM LẶNG là HAI số, không gộp: trượt là họ ĐÃ
                 # NÓI, im lặng là họ CHƯA NÓI GÌ — gộp lại là mất phân biệt
                 # duy nhất giữa "đã chết" và "chưa biết".
                 [(f"{info.get('da_nop', 0)}", "đã nộp", "stock"),
                  (f"{info.get('di_tiep', 0)}", "đi tiếp", "act"),
                  (f"{info.get('truot', 0)}", "trượt", "view"),
                  (f"{info.get('cho_ban', 0)}", "chờ bạn", "new")],
                 adjust="/adjust/track",
                 # NÚT QUEUE — cửa sang màn HÀNG CHỜ. Con số trên nút chính
                 # là số "chờ bạn" bên trái: chỗ duy nhất giải quyết được nó.
                 # Thiếu số thì nút câm, và người dùng không có lý do bấm.
                 sua=("/track/queue",
                      f"Queue {info.get('cho_ban', 0)}" if info.get("cho_ban")
                      else "Queue",
                      "Thư máy không tự chốt được — sang đó quyết một lượt"),
                 run="Quét thư", run_note="đọc hộp thư rồi cập nhật bảng",
                 # NÚT NỘP — mở trang nộp cho tin đáng nộp kế tiếp chưa nộp.
                 # Nó là cây cầu sang tab Search: bảng này nói "còn bao nhiêu
                 # chỗ đáng nộp", nút này đi nộp luôn chỗ đầu tiên.
                 them=("/api/track/nop-tiep", "Nộp",
                       f"{info.get('hang_doi', 0)} tin đáng nộp chưa nộp — "
                       f"mở trang nộp cho tin điểm cao nhất"),
                 xoa=("/api/track/xoa", "Xoá bảng", "Xoá thật?",
                      "Bỏ mọi lần nộp DỰNG TỪ THƯ. Đơn bạn tự nộp qua app và "
                      "thư đã đọc thì giữ nguyên")),
        panels=[runtime.panel(
            "Đã nộp",
            # THỨ TỰ ĐÚNG NHƯ "VIỆC TÌM ĐƯỢC": ô tìm -> hàng tag -> bảng.
            #
            # Bản trước nhét 16 thẻ thư vào giữa, nên ô tìm nằm dưới hơn một
            # màn hình — người dùng phải cuộn qua cả đống thư mới thấy thứ
            # dùng để lọc bảng. Thư cần quyết là VIỆC KHÁC, nên nó ra ô riêng.
            f"<div class=tracktop>{scan}</div>"
            + _table(rows, thu, loc, info.get("nguong") or SILENT_AFTER,
                     (info.get("do") or {}).get("lau", 0)),
            # MỘT Ô, ăn trọn chiều cao. Thư cần quyết đã sang /track/queue —
            # tab này chỉ còn thứ đã chốt, nên nó sạch và nó là cái bảng.
            span=1, rows=1)],
    )
