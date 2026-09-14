"""Search — bước 1. Ba ô, ba câu hỏi.

    VIỆC TÌM ĐƯỢC   máy kiếm được gì cho tôi     (ô đứng, to nhất)
    LƯỚI LỌC        tôi đang hỏi cái gì           (ô trái, có nút Áp dụng)
    NHẬT KÝ         nó đang làm gì                (góc dưới trái, dẹt)

Hai loại lọc KHÁC HẲN nhau, cố ý để hai chỗ:

    lưới GIỮ/BỎ   ingest/filter.judge  →  đổi là phán lại 4.660 tin (1,1 giây)
                  nằm trong ô Lưới lọc, có nút Áp dụng vì nó tốn thật

    nút XEM       filters.JobFilter    →  chỉ đổi màn hình
                  nằm ngay trên đầu danh sách, bấm là đổi luôn

Nhét chung một nút Áp dụng thì hoặc "sắp theo điểm" cũng phải chờ Áp dụng
(vô lý), hoặc đổi chức danh — thứ phán lại cả bảng — dễ như đổi cách sắp xếp.

CHỈ VẼ.
"""

from __future__ import annotations

from html import escape as esc

from ..filters import BAND, CHANCE, FOUND, LOC, SHOW, SORT, VIA
from ..layout import deck, score_bar
from . import runtime

# Badge nguồn: hai cách tìm mù ở hai chỗ khác nhau, nên nhìn dòng nào cũng
# biết ngay cách nào mang nó về. Tin cả hai cùng thấy thì hai badge.
# Huy hiệu gọi tên NGUỒN, không gọi tên cách lấy. "chrome" là công cụ mình
# dùng — người đọc không quan tâm, và nó cũng chẳng nói gì về cái tin. Cái
# tên đó là tàn dư từ hồi có HAI nguồn cùng đi qua Chrome (xem live.py).
FOUND_BY = {"linkedin": ("⌕", "linkedin", "tìm bằng từ khoá trên LinkedIn"),
            "board": ("◆", "board", "board tuyển dụng của chính công ty"),
            "alert": ("✉", "alert", "thư báo việc LinkedIn gửi vào hộp thư")}

CHANCE_TEXT = {"likely": ("đáng nộp", "ok"),
               "possible": ("có thể", ""),
               "unlikely": ("khó", "warn")}


# ---------------------------------------------------------------- danh sách

def _so(dem: dict, name: str, value: str) -> str:
    """Con số trên một nút lọc — bấm vào còn bao nhiêu tin.

    Không có số thì nút lọc là một lời mời mù: người dùng bấm để BIẾT nó lọc
    ra gì, và nếu nó lọc ra y nguyên (đo được: "Cả nước" 407 trên 411) thì họ
    vừa mất một cú bấm để học rằng nút đó vô dụng. Ghi số ra thì họ biết
    trước, và biết đúng theo dữ liệu HÔM NAY.
    """
    if not dem:
        return ""
    n = dem.get(f"{name}:{value}")
    return f"<b>{n:,}</b>" if n is not None else ""


def _chips(name: str, options, current: str, flt, dem: dict | None = None) -> str:
    """Một hàng nút XEM. Bấm là đổi ngay — không đi qua nút Áp dụng."""
    dem = dem or {}
    return "".join(
        f"<a class='vchip{' on' if value == current else ''}"
        f"{' nil' if dem.get(f'{name}:{value}') == 0 else ''}'"
        f" href='{esc(flt.url(**{name: value}))}'>{esc(label)}"
        f"{_so(dem, name, value)}</a>"
        for value, label in options)


def _row(job: dict) -> str:
    marks = "".join(
        f"<i class='src {k}' title='{esc(FOUND_BY[k][2])}'>"
        f"{FOUND_BY[k][0]}<b>{FOUND_BY[k][1]}</b></i>"
        for k in job["found_by"] if k in FOUND_BY)
    if job["via_agency"]:
        marks += ("<i class='src agency' title='tin do hãng môi giới đăng'>"
                  "⚠<b>môi giới</b></i>")

    chance = ""
    if job["realism"] in CHANCE_TEXT:
        text, kind = CHANCE_TEXT[job["realism"]]
        chance = (f"<span class='chance {kind}'"
                  f" title='{esc(job['realism_why'])}'>{text}</span>")

    # Tin bị bỏ thì LÝ DO là thứ đáng đọc nhất — đó là cách duy nhất soi được
    # lưới lọc có đang quá tay không.
    why = (f"<div class=dropwhy>bỏ vì {esc(job['drop_reason'])}</div>"
           if job["state"] == "dropped" and job["drop_reason"] else "")

    merged = (f"<span class=merged>+{job['merged'] - 1} nơi</span>"
              if job["merged"] > 1 else "")
    # Tin nằm trong danh sách vì NGƯỜI bảo thế, không phải vì máy chấm đạt.
    # Phải nói ra: nếu không, một tin chức danh chẳng khớp gì nằm giữa danh
    # sách trông như bộ lọc bị hỏng.
    tay = ("<span class='chance keep' title='máy đã loại tin này,"
           " bạn giữ lại bằng tay'>bạn giữ</span>" if job.get("user_keep") else "")

    # MỘT nút, hai chiều. Bộ lọc là luật máy móc — riêng "chức danh không khớp"
    # đã loại 2.595 tin, mà luật đó chỉ là so chuỗi con với 19 chức danh khai
    # trong hồ sơ. Người liếc qua đống bị loại chắc chắn nhặt được tin thật.
    if job.get("user_keep"):
        giu = (f"<button class='mbtn tiny' data-post='/api/keep'"
               f" data-arg='{esc(job['id'])}'"
               f" title='Trả tin này về cho máy phán lại'>Bỏ giữ</button>")
    elif job["state"] == "dropped":
        giu = (f"<button class='mbtn tiny' data-post='/api/keep'"
               f" data-arg='{esc(job['id'])}'"
               f" title='Đưa tin này vào danh sách giữ và chấm điểm ngay'>"
               f"Giữ lại</button>")
    else:
        giu = ""
    money = f" · {esc(job['salary'])}" if job["salary"] != "not stated" else ""
    score = (score_bar(job["score"]) if job["score"] is not None
             else "<span class=noscore>—</span>")

    return (
        f"<a class='jrow{' dropped' if job['state'] == 'dropped' else ''}'"
        f" href='/jobs/{esc(job['id'])}'>"
        f"<div class=jscore>{score}</div>"
        f"<div class=jmain><div class=jtitle>{esc(job['title'])}</div>"
        f"<div class=jsub><b>{esc(job['company'])}</b> · {esc(job['location'])}"
        f"{money}</div>{why}</div>"
        f"<div class=jtags>{tay}{chance}{marks}{merged}"
        f"<span class=jwhen>{esc(job['posted'])}</span>"
        # KHÔNG có nút Nộp ở đây. Nộp là một QUYẾT ĐỊNH: mở Chrome, điền form,
        # ghi một dòng vào Quản lí. Quyết định đó phải đứng sau khi ĐỌC — mà
        # chỗ đọc là trang chi tiết, nơi có điểm từng yêu cầu, bằng chứng, và
        # đường sang tin gốc. Bấm nộp từ danh sách là nộp mù.
        #
        # Nút GIỮ LẠI thì ngược lại, và đó là lý do nó vẫn ở đây: sàng đống
        # 4.055 tin bị loại là việc LƯỚT, quét mắt qua hàng chục dòng một lúc.
        # Bắt mở từng trang chi tiết để nhặt một tin là giết luôn việc sàng.
        #
        # KHÔNG gắn onclick stopPropagation. Trình nghe [data-post] nằm ở
        # `document`, nên chặn lan truyền là giết sự kiện trước khi nó tới nơi
        # — nút bấm không làm gì cả, mà cũng không báo lỗi. Bản thân trình
        # nghe đã gọi preventDefault(), đủ để thẻ <a> bao ngoài không nhảy trang.
        f"{giu}"
        f"</div></a>")


def _tim(flt) -> str:
    """Ô TÌM trong kho đã quét. Khác hẳn nút Chạy: nút Chạy đi lấy tin mới về,
    ô này lọc đống tin đã có.

    Backend nhận `q` từ đầu — lọc theo chức danh hoặc tên công ty, có ràng
    buộc tham số đàng hoàng — mà chưa bao giờ có chỗ để gõ vào. Cả một bộ lọc
    nằm đó không ai dùng được.

    FORM GET, không JavaScript: trạng thái lọc nằm hết trên URL (xem
    filters.py), nên gõ xong bấm Enter là ra một địa chỉ lưu lại được, Back
    được, gửi cho người khác được.

    Các bộ lọc đang bật đi theo dưới dạng ô ẩn. Thiếu chúng thì gõ tìm một
    phát là mọi chip đang chọn bay sạch về mặc định.
    """
    an = "".join(f"<input type=hidden name='{esc(k)}' value='{esc(v)}'>"
                 for k, v in flt.pairs(q="", page=""))
    # Nút xoá chỉ hiện khi ĐANG tìm. Hiện sẵn lúc ô trống là một nút không làm
    # gì — thứ người dùng bấm một lần rồi thôi tin vào cả hàng nút.
    xoa = (f"<a class=jfindx href='{esc(flt.url(q=''))}'"
           f" title='Bỏ tìm, xem lại tất cả'>×</a>" if flt.q else "")
    return (f"<form class=jfind method=get action='/search'>{an}"
            f"<input class=search type=search name=q value='{esc(flt.q)}'"
            f" autocomplete=off spellcheck=false"
            f" placeholder='tìm trong kho — chức danh hoặc công ty'>"
            f"{xoa}</form>")


def _thang(key: str, ten: str, options, current: str, flt,
           dem: dict | None = None) -> str:
    """THANG MỨC ĐỘ — mấy nấc liền nhau, tô đầy tới nấc đang chọn.

    Vì sao không để mấy nút rời như cũ: "Đáng nộp / Có thể / Khó" CÓ THỨ TỰ,
    mà bốn pill xám giống hệt nhau thì không nói ra được thứ tự đó — người
    dùng phải đọc hết cả bốn rồi tự suy ra. Vẽ liền thành một thanh thì nhìn
    phát biết ngay, và biết luôn chọn một nấc nghĩa là "từ đây trở lên".

    Vẫn là mấy thẻ <a>, vẫn không JavaScript: trạng thái nằm trên URL như mọi
    bộ lọc khác. Đổi CÁCH VẼ, không đổi cơ chế.
    """
    muc = [v for v, _ in options]
    tai = muc.index(current) if current in muc else 0
    nac = "".join(
        f"<a class='lvlstep{' on' if i <= tai else ''}{' now' if i == tai else ''}'"
        f" href='{esc(flt.url(**{key: value, 'raw': ''}))}'>{esc(label)}"
        f"{_so(dem or {}, key, value)}</a>"
        for i, (value, label) in enumerate(options))
    return (f"<span class=lvl><span class=lvlname>{esc(ten)}</span>"
            f"<span class=lvltrack>{nac}</span></span>")


def _noi(flt, gan: str, vung: str, dem: dict | None = None) -> str:
    """Chip NƠI CHỐN — chữ lấy từ ô "Where you're based".

    Nơi ở không quyết định việc nào HỢP LỆ: cắt theo London là mất 71 việc UK
    ngoài London (đo 12/09), mà 71 việc đó do LinkedIn mang về, board không
    phủ nổi. Nó quyết định việc nào TIỆN — nên nó là một cú bấm để XEM, không
    phải một cái kéo.

    Chưa khai nơi ở thì GIẤU chip "Gần tôi": một nút không lọc được gì là nút
    bấm vào thấy y nguyên, và người dùng thôi tin cả hàng nút.
    """
    ten = {"near": f"Near me · {gan}" if gan else "", "home": f"All of {vung}"}
    chon = [(v, ten.get(v) or nhan) for v, nhan in LOC
            if not (v == "near" and not gan)]
    return ("<span class=vlabel>Nơi</span>"
            + _chips("loc", chon, flt.loc, flt, dem))


def _list(jobs: list[dict], flt, counts: dict,
          gan: str = "", vung: str = "UK", dem: dict | None = None) -> str:
    # MỘT nút thay cho hai. "Can't tell" nằm hàng cơ hội, "Not scorable" nằm
    # hàng điểm — mà đo trên kho thật thì chúng là cùng một chồng tin (185 tin
    # thiếu cả hai, 0 tin chỉ thiếu một). Cùng một nguyên nhân: vòng đọc kỹ
    # chưa mở tới tin đó nên chưa có mô tả để mà đọc.
    #
    # Bấm vào là thả hai thang về "Tất cả": hai thang đòi máy phải đọc được,
    # nút này đòi ngược lại — để cả hai cùng bật thì danh sách luôn rỗng.
    chua = (f"<a class='vchip{' on' if flt.raw else ''}'"
            f" href='{esc(flt.url(raw='' if flt.raw else '1', chance='', band=''))}'"
            f" title='Tin chưa có mô tả nên máy chưa chấm được —"
            f" chạy tiếp vòng đọc kỹ là có'>Máy chưa đọc</a>")
    # BA HÀNG, MỖI HÀNG HAI ĐẦU. Trước đây bốn hàng đều nép sát trái, mỗi hàng
    # dùng 25-50% bề ngang rồi bỏ trống hết phần phải — ô này rộng gần 2000px.
    #
    # Ghép theo NGHĨA, không phải ghép cho vừa chỗ:
    #   hàng 1  chồng nào  ←→  xếp thế nào   (hai câu hỏi bao trùm cả danh sách)
    #   hàng 2  hai thang  ←→  nút đòi điều NGƯỢC LẠI với hai thang
    #   hàng 3  tìm bằng cách nào  ←→  ai đăng tin
    hang = lambda trai, phai: (f"<div class=vbar><span class=vgrp>{trai}</span>"
                               f"<span class=vgrp>{phai}</span></div>")
    head = (_tim(flt)
            + hang(_chips("show",
                          [(v, f"{l} {counts.get(v, 0):,}") for v, l in SHOW],
                          flt.show, flt),
                   "<span class=vlabel>Xếp theo</span>"
                   + _chips("sort", SORT, flt.sort, flt))
            + hang(_thang("chance", "Cơ hội", CHANCE, flt.chance, flt, dem)
                   + _thang("band", "Điểm", BAND, flt.band, flt, dem),
                   chua)
            # NƠI ở đầu trái — đó là câu hỏi chính về một tin. Bên phải là
            # XUẤT XỨ: ai đăng (môi giới hay chủ) và mình tìm ra bằng cách
            # nào. Không đẻ thêm hàng thứ tư: một hàng có đúng một đầu thì
            # nửa màn hình lại bỏ trống, đúng thứ vừa sửa hôm qua.
            + hang(_noi(flt, gan, vung, dem),
                   _chips("via", VIA, flt.via, flt, dem)
                   + _chips("found", FOUND, flt.found, flt, dem)))
    if not jobs:
        # Nói rõ không ra CÁI GÌ, và cho đường quay lại. "không có tin nào
        # khớp" khi đang gõ dở một chữ đọc ra như kho rỗng.
        trong = (f"không có tin nào chứa “{esc(flt.q)}” — "
                 f"<a href='{esc(flt.url(q=''))}'>bỏ tìm</a>" if flt.q
                 else "không có tin nào khớp")
        return head + f"<div class=empty-box>{trong}</div>"
    return (head + "<div class=jlist>" + "".join(_row(j) for j in jobs)
            + "</div>" + _pager(flt, counts.get(flt.show, 0)))


def _pager(flt, total: int) -> str:
    """Không có nút sang trang thì 132 việc chỉ xem được 50 — 82 việc còn lại
    có tồn tại cũng như không."""
    # Lấy từ flt.limit() chứ KHÔNG import PER_PAGE: import theo giá trị thì
    # con số bị đóng băng lúc nạp module, test không đổi được để dựng ra
    # tình huống nhiều trang.
    per, _offset = flt.limit()
    pages = max(1, -(-total // per))
    if pages < 2:
        return ""
    prev = (f"<a class=vchip href='{esc(flt.url(page=flt.page - 1))}'>← trước</a>"
            if flt.page > 1 else "<span class='vchip off'>← trước</span>")
    nxt = (f"<a class=vchip href='{esc(flt.url(page=flt.page + 1))}'>sau →</a>"
           if flt.page < pages else "<span class='vchip off'>sau →</span>")
    return (f"<div class=pager>{prev}"
            f"<span class=muted>trang {flt.page}/{pages:,} · {total:,} việc</span>"
            f"{nxt}</div>")


# ---------------------------------------------------------------- lưới lọc

def _tags(titles: list[str]) -> str:
    """Ô thẻ: gõ chức danh rồi Enter là thêm, bấm × là bỏ.

    Mỗi thẻ mang theo một <input hidden name=job_titles>, nên form gửi lên một
    DANH SÁCH giá trị — không phải một khối chữ rồi server ngồi tách dòng.
    Khối chữ thì người dùng phải tự nhớ luật "mỗi dòng một cái", và một dòng
    trống hay một dấu phẩy thừa là ra chức danh rác.
    """
    chips = "".join(
        f"<span class=tag>{esc(t)}"
        f"<input type=hidden name=job_titles value='{esc(t)}'>"
        # type=button, nếu không bấm × là gửi luôn cả form
        f"<button type=button class=untag data-untag title='bỏ'>×</button>"
        f"</span>" for t in titles)
    return (f"<div class=tagbox data-tags>{chips}"
            "<input class=taginput type=text autocomplete=off"
            " placeholder='thêm chức danh…'></div>")


def _missed(missed: list[dict]) -> str:
    """Chức danh lưới đang bỏ sót mà trông như việc của Vin.

    Lưới là mấy chuỗi gõ tay: thiếu một chuỗi là mất cả loạt tin, và mất TRONG
    IM LẶNG. Đo ngày 10/09: `Quantitative Trader` bị bỏ chín lần, toàn ở Jane
    Street; 47 tin `machine learning` bị bỏ, mà ML là ô cầu cao nhất (56/178).

    Máy KHÔNG tự nới lưới — nới là đổi hồ sơ, và hồ sơ đổi thì cả bảng phải
    phán lại. Nó chỉ chỗ; bấm vào là thẻ rơi vào ô trên, rồi vẫn phải bấm
    Áp dụng như mọi thay đổi khác.
    """
    if not missed:
        return ""
    chips = "".join(
        f"<button type=button class=addtag data-addtag='{esc(m['title'])}'"
        f" title='{esc(', '.join(m['firms'][:3]))}'>"
        f"+ {esc(m['title'][:34])}<b>{m['n']}</b></button>" for m in missed)
    return (f"<div class=missed><div class=missedhead>"
            f"lưới đang bỏ sót — bấm để thêm</div>{chips}</div>")


def _sieve(sieve: dict) -> str:
    """Ô sửa lưới GIỮ/BỎ. FORM thật, không phải bảng đọc.

    Giá trị nằm trong HỒ SƠ — sửa ở đây là sửa hồ sơ, và nó đổi cả điểm (chức
    danh nằm trong công thức chấm). Phải ghi câu đó ra, không được im.
    """
    levels = "".join(
        f"<label class=tick><input type=checkbox name=seniority value='{esc(v)}'"
        f"{' checked' if v in sieve['seniority'] else ''}>{esc(l)}</label>"
        for v, l in sieve["seniority_options"])
    markets = "".join(
        f"<label class=tick><input type=checkbox name=markets value='{esc(v)}'"
        f"{' checked' if v in sieve['markets'] else ''}>{esc(l)}</label>"
        for v, l in sieve["market_options"])

    # CÔNG TẮC NGUỒN — nằm NGOÀI form. Chúng không phải hồ sơ: bấm là có tác
    # dụng ngay, không đi qua nút Áp dụng, và không làm phán lại 5.000 tin.
    #
    # Đặt trên cùng vì đây là công tắc thô nhất: tắt một nguồn thì mọi núm
    # bên dưới chỉ còn tác dụng với nửa còn lại.
    nguon = "".join(
        f"<button class='mbtn tiny srcbtn {esc(k)}{'' if on else ' off'}'"
        f" data-post='/api/source' data-arg='{esc(k)}'"
        f" title='{esc(mo)}'>{dau} {esc(k)} · {'bật' if on else 'tắt'}</button>"
        for k, dau, on, mo in (
            ("board", FOUND_BY["board"][0], sieve.get("src_board", True),
             "board tuyển dụng của chính công ty — thuần HTTP, ~20 giây"),
            ("linkedin", FOUND_BY["linkedin"][0], sieve.get("src_linkedin", True),
             "tìm bằng từ khoá trên LinkedIn — mở Chrome, lâu hơn nhiều. "
             "Tắt chỉ dừng việc gõ từ khoá; tin của nguồn khác vẫn được "
             "đọc kỹ và chấm điểm"),
            ("alert", FOUND_BY["alert"][0], sieve.get("src_alert", True),
             "thư báo việc LinkedIn gửi vào hộp thư — nhanh nhất, không cào. "
             "Nguồn RIÊNG: chạy trọn dây chuyền dù LinkedIn đang tắt")))

    return (
        "<label class=slab>Nguồn<span>bấm để bật/tắt · có tác dụng ngay, "
        "không cần Áp dụng</span></label>"
        f"<div class=srcrow>{nguon}</div>"
        "<form class=sieve method=post action='/api/sieve'>"
        "<label class=slab>Chức danh nhắm tới<span>gõ rồi Enter để thêm · "
        "vừa là từ khoá gửi cho LinkedIn, vừa là điều kiện giữ tin</span></label>"
        + _tags(sieve["titles"])
        + _missed(sieve.get("missed") or [])
        + "<label class=slab>Cấp bậc nhận</label>"
        f"<div class=ticks>{levels}</div>"
        "<label class=slab>Thị trường<span>quyết định LinkedIn tìm ở đâu, "
        "và tin ở đâu thì được giữ</span></label>"
        f"<div class=ticks>{markets}</div>"
        # Nút phải nói TRƯỚC hậu quả. "Lưu" trống không thì người bấm không
        # biết mình vừa làm cả bảng phán lại từ đầu.
        "<div class=stick>"
        "<button class='mbtn apply' type=submit>Áp dụng</button>"
        f"<div class=applynote>phán lại <b>{sieve['total']:,}</b> tin đã lấy về"
        f" (~{sieve['seconds']} giây) · đây là <b>hồ sơ</b> của bạn, "
        "sửa ở đây đổi cả điểm</div></div>"
        "</form>")


def adjust(sieve: dict) -> str:
    """Mảnh cho tấm phủ ⚟ — LƯỚI SÀNG.

    Vì sao lưới sàng vào đây mà BỘ LỌC thì không: lọc (hiện/cơ hội/dải/sắp
    xếp) bấm vài giây một lần khi lướt danh sách, giấu vào menu là lướt chậm
    hẳn. Lưới sàng đổi vài tháng một lần, và mỗi lần đổi là phán lại toàn bộ
    tin trong kho. Khác nhau: LỌC thứ đang nhìn ≠ ĐỔI thứ máy đi thu về.
    """
    return f"<div class=sheethead>Điều chỉnh · Search</div>{_sieve(sieve)}"


# ---------------------------------------------------------------- trang

def render(*, jobs: list[dict], flt, counts: dict, sieve: dict,
           stage: dict | None = None, dem: dict | None = None) -> str:
    info = stage or {}
    return runtime.render(
        title="Search", active="/search", stream="search",
        reload="search",
        # Thanh của KHÚC này: số liệu + nút chạy/dừng của chính nó. Hai nút
        # "Chạy ngay"/"Bật tự quét" trước đây nằm trên thanh toàn app nhưng
        # chỉ điều khiển đúng khúc này.
        bar=deck(
            "search", "Search",
            info.get("state", "chưa quét lần nào"),
            # vai -> màu: xem luật ở layout.deck()
            # "giữ" đọc từ stage chứ KHÔNG từ counts: counts đi theo ô tìm và
            # các chip, mà thanh này nói về KHO chứ không về khung nhìn. Số
            # của khung nhìn đã có rồi — đó là "đang hiện" ở cuối hàng.
            # MỖI SỐ PHẢI TRẢ LỜI "tối nay tôi làm gì". Thanh cũ có bốn số
            # mà không số nào làm được: "363 giữ" và "364 đáng nộp" là hai
            # cách đếm cùng một chồng nên gần trùng nhau, "0 mới" luôn là 0
            # trừ đúng lúc vừa quét xong, "50 đang hiện" là cỡ trang — danh
            # sách ngay dưới đã nói rồi.
            [(f"{info.get('hang_doi', 0):,}", "nên nộp", "act"),
             (f"{info.get('worth', 0):,}", "đáng nộp", "stock"),
             (f"{info.get('fresh', 0):,}", "vừa về", "new"),
             (f"{info.get('da_nop', 0):,}", "đã nộp", "view")],
            adjust="/adjust/search",
            run=info.get("run_label", "Chạy"),
            run_note=info.get("run_note", ""),
            # SỐ TIN SẮP MẤT nằm ngay trên nút đã nạp đạn. "Chắc chưa?" không
            # nói được cái giá; "Bỏ 5.166 tin?" thì nói được.
            xoa=("/api/search/xoa", "Dọn kho",
                 f"Bỏ {info.get('ca_kho', 0):,} tin?",
                 "Xoá kho tin để quét lại từ đầu. Tin đã có đơn thì GIỮ. "
                 "Hồ sơ, đơn đã nộp và lưới lọc không bị đụng.")),
        # Lưới sàng đã chuyển vào ⚟ nên cột trái hết việc. Danh sách — thứ
        # Vin thật sự đọc — lấy cả bề ngang. Nhật ký về dải dẹt dưới đáy.
        cols=1, journal="bottom",
        panels=[
            runtime.panel("Việc tìm được",
                          _list(jobs, flt, counts, dem=dem,
                                gan=info.get("gan", ""),
                                vung=info.get("vung", "UK")), span=1),
        ],
    )
