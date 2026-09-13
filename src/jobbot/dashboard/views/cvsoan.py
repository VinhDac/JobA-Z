"""SOẠN KHỐI — màn con của tab CV, chỗ ngồi viết.

VÌ SAO CÓ MÀN NÀY. Soạn khối trước đây nằm trong tấm phủ bên phải: rộng 380px,
đè lên trang, đóng lại là mất. Tấm phủ hợp với mấy công tắc bật xong tắt —
không hợp với việc ngồi viết mười lăm phút. Và nó câm: gõ xong bấm Lưu, rồi
chỉ biết câu vừa viết bị luật bỏ nếu tự đi dựng lại cả loạt bản và đọc phần
"câu không lên bài".

Nên màn này khác đúng hai chỗ, và cả hai đều là lý do nó tồn tại:

    RỘNG   cả cửa sổ, khối bên trái, câu bên phải, có chỗ mà đọc
    NÓI    mỗi câu kèm luật nói gì + bao nhiêu tin đang đòi thứ nó nhắc tới

VÀ NÓ LÀ CHỖ DUY NHẤT ĐỂ VIẾT. Trước đây "viết một câu mới về X" có tấm phủ
riêng (/cv/viet): đọc yêu cầu ở một màn, gõ ở màn khác, hai đường ghi vào cùng
một `cv_text` phải trông nhau. Nhưng viết một câu mới CHÍNH LÀ sửa một khối —
cùng phép ghi, cùng chỗ ngồi. Nên `?ky=` chỉ mở thêm phần BRIEF ngay trên ô
soạn; không đẻ ra màn thứ hai.

Luật gốc không đổi: chữ ở đây là chữ NGƯỜI DÙNG gõ. Máy chấm, máy đếm, máy
không viết hộ câu nào — xem cv/build.py.

MỘT NGUỒN SỰ THẬT: ghi thẳng vào `cv_text`, không dựng bảng khối riêng.

CHỈ VẼ.
"""

from __future__ import annotations

from html import escape as esc
from urllib.parse import quote

from . import runtime

KIND_TAG = {"experience": "việc", "project": "project"}

# Phán quyết của luật -> (nhãn, lớp CSS). Ba mức, ba hành động khác nhau:
# lên CV thì thôi, xem lại là việc của người viết, luật bỏ là câu này không
# bao giờ in ra — sửa chữ hoặc để nó ở chỗ khác.
PHAN = {"keep": ("lên CV", "ok"),
        "review": ("xem lại", "warn"),
        "drop": ("luật bỏ", "bad")}


def _khoi_list(blocks: list[dict], dang: str, mang: str = "") -> str:
    """Kho khối, xếp theo VỚI TỚI BAO NHIÊU TIN. Bấm là mở bên phải.

    `mang` = phần đuôi URL phải đi theo (đích đang nhắm + nền bản nháp). Cột
    trái là chỗ trả lời "viết VÀO ĐÂU", nên bấm một khối không được vứt mất
    câu trả lời của "viết CÁI GÌ" — người dùng sẽ phải chọn lại từ đầu.
    """
    rows = ""
    for b in blocks:
        skills = "".join(f"<span class=sk>{esc(s)}</span>" for s in b["skills"][:4])
        cls = "blk"
        if b["reach"] == 0:
            cls += " dead"
        if b["title"] == dang:
            cls += " on"
        # quote(), KHÔNG esc(): đây là THAM SỐ URL. Tiêu đề "R & D" thoát HTML
        # thành "R &amp; D" — dấu & vẫn cắt tham số và trang mở ra khối rỗng.
        rows += (
            f"<a class='{cls}'"
            f" href='/cv/soan?khoi={quote(b['title'], safe='')}{mang}'>"
            f"<div class=blkmain>"
            f"<div class=blkhead><b>{esc(b['title'][:44])}</b>"
            f"<span class=blkkind>{esc(KIND_TAG.get(b['kind'], b['kind']))}</span>"
            f"</div>"
            f"<div class=blktags>{skills or '<span class=muted>không kỹ năng nào</span>'}</div>"
            f"</div>"
            f"<div class=blkreach><b>{b['reach']}</b><span>tin</span>"
            f"<i>{len(b['lines'])} câu</i></div></a>")

    if not rows:
        rows = ("<div class=empty-box>Hồ sơ chưa có khối kinh nghiệm nào. "
                "Bấm <b>+ Khối mới</b> để viết khối đầu tiên.</div>")
    return (
        f"<div class=gapnote>Xếp theo <b>số tin khối đó với tới</b>. "
        f"Khối <b>0 tin</b> đang chiếm chỗ chứ không chứng minh gì.</div>"
        f"<div class=blklist>{rows}</div>"
        f"<div class=blkfoot><a class='mbtn apply' href='/cv/soan?moi=1'>"
        f"+ Khối mới</a></div>")


def _hut(rows: list, khoi: str = "", dang: str = "") -> str:
    """Thị trường đang thiếu gì — chọn ĐÍCH cho câu sắp viết.

    Soạn khối mà không biết thị trường hỏi gì thì chỉ là sửa chính tả. Chỉ in
    mấy dòng VIẾT ĐƯỢC: dòng gọi đích danh tên sản phẩm là việc đi học, không
    phải việc của màn này.

    Bấm một cái là Ở LẠI màn này, giữ nguyên khối đang mở, chỉ mở thêm brief.
    """
    if not rows:
        return ""
    giu = f"khoi={quote(khoi, safe='')}&" if khoi else ""
    muc = ""
    for b in rows:
        on = " on" if b["ky_nang"] == dang else ""
        muc += (f"<a class='hmini{on}'"
                f" href='/cv/soan?{giu}ky={quote(b['ky_nang'], safe='')}'>"
                f"<span class=hmname>{esc(b['ky_nang'])}</span>"
                f"<span class=hmplus>+{b['them']}<span>tin</span></span></a>")
    return (f"<div class=sntbrief>"
            f"<div class=slab>Viết thêm câu về mấy thứ này thì bao nhiêu tin "
            f"hết hụt<span>bấm một cái để xem nguyên văn dòng yêu cầu thật "
            f"của các tin đang đòi nó</span></div>"
            f"<div class=hminis>{muc}</div></div>")


def _buoc(so: int, ten: str, xong: bool, dang: bool, ruot: str) -> str:
    """MỘT BƯỚC trong màn viết. Có số, có tên, có trạng thái.

    VÌ SAO ĐÁNH SỐ. Bản trước đổ cả brief lẫn ô soạn ra một trang phẳng, và
    phản hồi đầu tiên của người dùng là "tôi không biết phải bấm cái gì, viết
    như nào, confirm cái gì". Trang có đủ mọi thứ cần thiết mà không nói thứ
    tự — mà viết một câu CV là việc ba nhịp, không phải một.
    """
    lop = "buoc" + (" xong" if xong else "") + (" dang" if dang else "")
    dau = "✓" if xong else str(so)
    return (f"<section class='{lop}'>"
            f"<div class=buochead><span class=buocso>{dau}</span>"
            f"<b>{esc(ten)}</b></div>"
            f"<div class=buocruot>{ruot}</div></section>")


def _viet(d: dict, khoi: str, nen: str, loi: str, blocks: list,
          soan: str = "", gy: str = "", tho: bool = False) -> str:
    """MÀN VIẾT MỘT CÂU — ba bước, đánh số, nhìn là biết đang ở đâu.

    Khác hẳn màn SỬA KHỐI ở dưới, và phải khác: người vào đây để viết MỘT câu
    mới, không phải để đọc lại 16 câu cũ. Đổ cả khối ra là chôn cái ô cần gõ
    xuống dưới hai màn hình.

        1  chọn một dòng họ hỏi làm điểm xuất phát
        2  chọn viết vào khối nào
        3  viết lại thành việc MÌNH làm, rồi Lưu

    Bước nào xong thì gập lại thành một dòng "đã chọn", đổi được. Bước đang
    làm thì mở và sáng. Bước chưa tới vẫn hiện — khoá nó lại chỉ làm người
    dùng hoang mang thêm chứ không dạy được gì.

    Máy vẫn KHÔNG viết câu nào. Chữ ở bước 3 là chữ NHÀ TUYỂN DỤNG nguyên văn,
    và `gap.qua_giong` chặn lúc Lưu nếu người dùng không viết lại nó.
    """
    ky = d["ky"]
    dich = quote(ky, safe="")
    giu_nen = f"&nen={quote(nen, safe='')}" if nen else ""
    giu_khoi = f"&khoi={quote(khoi, safe='')}" if khoi else ""
    o = soan if soan else nen

    def _list(rows) -> str:
        return "".join(
            f"<li><span class=wq>{esc(m['chu'])}</span>"
            f"<span class=wco>{esc(m['cong_ty'])}</span></li>" for m in rows)

    # ---- BƯỚC 1 · chọn dòng --------------------------------------------
    if nen:
        r1 = (f"<div class=dachon><span class=wq>{esc(nen)}</span>"
              f"<a class='mbtn tiny' href='/cv/soan?ky={dich}{giu_khoi}'>"
              f"Đổi dòng</a></div>")
    elif d["nen"]:
        r1 = "<div class=nenlist>"
        for m in d["nen"]:
            # Dòng chiếm TRỌN bề ngang; tên công ty và lời mời bấm xuống hàng
            # dưới. Nhét công ty vào cùng hàng thì cột của nó bị bóp còn "Bo…"
            # — mà tên công ty chính là thứ nói đây là yêu cầu THẬT.
            r1 += (f"<a class=nenone href='/cv/soan?ky={dich}{giu_khoi}"
                   f"&nen={quote(m['chu'], safe='')}'>"
                   f"<span class=wq>{esc(m['chu'])}</span>"
                   f"<span class=nenfoot>"
                   f"<span class=nengo>Dùng dòng này →</span>"
                   f"<span class=wco>{esc(m['cong_ty'])}</span></span></a>")
        r1 += "</div>"
    else:
        r1 = ("<div class=empty-box>Không tin nào đòi thứ này bằng một dòng "
              "TẢ VIỆC — mấy dòng đòi nó chỉ tả phẩm chất. Bạn vẫn viết được, "
              "cứ sang bước 2 rồi gõ câu của mình ở bước 3.</div>")

    phu = ""
    con = [m for m in d["chung"] if m not in d["nen"]][:5]
    if con:
        phu += (f"<details class=briefmore><summary>{len(con)} dòng nữa đòi "
                f"{esc(ky)} — tả phẩm chất chứ không tả việc, đọc để biết"
                f"</summary><ul class=wlist>{_list(con)}</ul></details>")
    if d["rieng"]:
        phu += (f"<details class=briefmore><summary>{len(d['rieng'])} dòng gọi "
                f"đích danh tên sản phẩm — không câu nào viết thay được"
                f"</summary><ul class=wlist>{_list(d['rieng'])}</ul></details>")

    # ---- BƯỚC 2 · chọn khối --------------------------------------------
    r2 = "<div class=khoichon>"
    for b in blocks:
        on = " on" if b["title"] == khoi else ""
        r2 += (f"<a class='khoione{on}' href='/cv/soan?ky={dich}{giu_nen}"
               f"&khoi={quote(b['title'], safe='')}'>"
               f"<b>{esc(b['title'][:34])}</b>"
               f"<span>{len(b['lines'])} câu · {b['reach']} tin</span></a>")
    r2 += (f"<a class=khoione href='/cv/soan?moi=1&ky={dich}{giu_nen}'>"
           f"<b>+ Khối mới</b><span>đặt tên ở màn sửa khối</span></a></div>")

    # ---- BƯỚC 3 · viết ---------------------------------------------------
    if not khoi:
        r3 = ("<div class=empty-box>Chọn khối ở bước 2 trước — câu viết ra "
              "phải nằm trong một khối.</div>")
    else:
        # BA TRẠNG THÁI của ô, và mỗi cái cần một lời khác nhau.
        dung_gy = bool(gy) and not tho and o == gy
        if loi:
            canh = f"<div class='sntwarn bad'>{esc(loi)}</div>"
        elif dung_gy:
            canh = ("<div class='sntwarn ok'>Đây là <b>gợi ý</b>: máy cắt phần "
                    "thừa trong dòng của họ và chia sang thì quá khứ — hình "
                    "của một câu CV. Nó <b>không biết bạn đã làm gì</b>, nên "
                    "chỗ <b>___</b> để bạn điền bằng chứng thật: bao nhiêu "
                    "cái, trên bao nhiêu dữ liệu, đổi được mấy phần.</div>")
        elif nen:
            canh = ("<div class=sntwarn>Ô dưới đang là <b>chữ của nhà tuyển "
                    "dụng</b>, chưa phải câu của bạn. Viết lại thành việc BẠN "
                    "đã làm, kèm con số thật.</div>")
        else:
            canh = ""

        # ĐỔI QUA LẠI giữa gợi ý và nguyên văn. Là LIÊN KẾT, không JavaScript:
        # trạng thái nằm trên URL nên Back được và lưu địa chỉ lại được.
        lat = ""
        if gy and nen:
            if dung_gy:
                lat = (f"<a class='mbtn tiny' href='/cv/soan?ky={dich}"
                       f"{giu_khoi}{giu_nen}&tho=1'>Dùng nguyên văn dòng của "
                       f"họ</a>")
            else:
                lat = (f"<a class='mbtn tiny apply' href='/cv/soan?ky={dich}"
                       f"{giu_khoi}{giu_nen}'>↺ Gợi ý câu CV</a>")
        elif nen:
            lat = ("<span class=muted>dòng này không rút gọn được thành hình "
                   "câu CV — dùng nó làm đề bài, viết câu của bạn</span>")

        r3 = (
            f"<form class=vietform method=post action='/cv/block'>"
            f"<input type=hidden name=them value=1>"
            f"<input type=hidden name=title value='{esc(khoi)}'>"
            f"<input type=hidden name=ky value='{esc(ky)}'>"
            + (f"<input type=hidden name=nen value='{esc(nen)}'>" if nen else "")
            + canh
            + f"<textarea class=cvdraft name=line rows=4 id=viet"
              f" placeholder='Một câu tiếng Anh, kể việc BẠN làm. Có con số "
              f"thật thì thêm vào — đó là thứ hồ sơ thiếu nhất.'>{esc(o)}"
              f"</textarea>"
            + (f"<div class=latrow>{lat}</div>" if lat else "")
            + f"<div class=vietfoot>"
              f"<button class='mbtn apply big' type=submit>Thêm câu này vào "
              f"«{esc(khoi[:26])}»</button>"
              f"<span class=applynote>ghi thẳng vào CV gốc · mấy câu đang có "
              f"trong khối giữ nguyên</span></div>"
            + "</form>")

    hd = (f"<div class=viethead><span>Viết một câu về · <b>{esc(ky)}</b></span>"
          f"<a class='mbtn tiny' href='/cv/soan{giu_khoi.replace('&', '?', 1)}'>"
          f"× bỏ đích</a></div>")
    return (f"<div class=vietbox>{hd}"
            + _buoc(1, "Chọn một dòng họ hỏi làm điểm xuất phát",
                    bool(nen), not nen, r1 + phu)
            + _buoc(2, "Viết vào khối nào", bool(khoi), bool(nen) and not khoi, r2)
            + _buoc(3, "Viết lại thành việc BẠN đã làm, rồi Lưu",
                    False, bool(khoi), r3)
            + "<div class=note>Máy KHÔNG viết câu nào. Nó biết thị trường hỏi "
              "gì, nhưng không biết bạn đã làm gì — và câu trên CV là câu bạn "
              "phải đỡ được trong phòng phỏng vấn. Để nguyên chữ của họ thì "
              "máy không cho lưu.</div></div>")


def _cau(c: dict) -> str:
    """MỘT câu: ô soạn + dải chấm dưới chân nó.

    Dải chấm là thứ tấm phủ cũ không có. Nó trả lời hai câu, không hơn:
    luật có cho câu này in ra không, và thị trường có hỏi thứ nó nhắc tới
    không. Cả hai đo được; cả hai đổi ngay khi Lưu xong.
    """
    from ...cv.report import vi

    nhan, lop = PHAN.get(c["phan"], PHAN["keep"])
    sk = "".join(f"<span class=sk>{esc(t)}</span>" for t in c["tags"][:5])
    if not sk:
        sk = "<span class=muted>không nhắc kỹ năng nào có tên</span>"
    why = (f"<span class=svwhy>{esc(vi(c['vi_sao']))}</span>"
           if c["vi_sao"] else "")
    return (
        f"<div class='snt {lop}'>"
        f"<textarea class=cvdraft name=line rows=2>{esc(c['chu'])}</textarea>"
        f"<div class=sntfoot>"
        f"<span class='sv {lop}'>{nhan}</span>{why}"
        f"<span class=sntsk>{sk}</span>"
        f"<span class=sntreach><b>{c['reach']}</b> tin</span>"
        f"</div></div>")


def _form(chon: dict | None, cau: list[dict], ky: str = "",
          nen: str = "", loi: str = "", ten: str = "") -> str:
    """Ô soạn một khối. Ghi thẳng vào `cv_text`.

    `nen` rơi vào ô trống đầu tiên. `loi` là lời từ chối của lượt Lưu vừa rồi
    — hiện NGAY TRÊN ô, cạnh chữ người dùng vẫn còn nguyên, chứ không phải
    một dòng báo lỗi ở đâu đó rồi mất trắng cái vừa gõ.
    """
    # `ten` = tên khối người dùng vừa gõ nhưng CHƯA lưu. Không giữ nó thì lượt
    # Lưu bị từ chối là mất cả tên lẫn câu, và người dùng gõ lại từ đầu.
    b = chon or {"kind": "project", "title": ten, "meta": "", "lines": [],
                 "skills": [], "reach": 0}
    kinds = "".join(
        f"<option value='{k}'{' selected' if k == b['kind'] else ''}>{esc(v)}"
        f"</option>" for k, v in KIND_TAG.items())
    # Câu đã có thì kèm dải chấm; ô trống ở cuối để viết thêm — chúng chưa có
    # gì để chấm nên không có dải. Khối MỚI được nhiều ô hơn: khối đang sửa
    # thì hai ô là đủ chỗ nối thêm, còn khối mới bắt đầu từ tờ giấy trắng.
    # Ô TRỐNG ĐẦU TIÊN mang NEO `#viet`, KHÔNG mang autofocus. autofocus cuộn
    # thẳng xuống ô gõ — nghe thì tiện, nhưng nó cuộn mất phần brief ngay phía
    # trên, đúng thứ vừa đưa vào đây để người ta đọc TRƯỚC KHI viết. Neo thì
    # người dùng tự quyết: đọc xong, bấm một cái là xuống tới ô.
    goi = (f"viết một câu về {ky}…" if ky else "viết thêm một câu…")
    boxes = "".join(_cau(c) for c in cau)
    for i in range(2 if chon else 4):
        neo = " id=viet" if i == 0 else ""
        # Ô ĐẦU nhận nền. Nền là chữ của nhà tuyển dụng, nên nó phải được gắn
        # nhãn ngay tại chỗ — người dùng quay lại sau mười phút phải còn nhận
        # ra đây chưa phải câu của mình.
        if i == 0 and nen:
            xau = ("<div class='sntwarn bad'>" + esc(loi) + "</div>") if loi else (
                "<div class=sntwarn>Đây là <b>chữ của nhà tuyển dụng</b>, chưa "
                "phải câu của bạn. Viết lại thành việc BẠN đã làm — có con số "
                "thật thì thêm vào, đó là thứ hồ sơ thiếu nhất.</div>")
            boxes += (f"<div class='snt nen{' bad' if loi else ''}'{neo}>{xau}"
                      f"<textarea class=cvdraft name=line rows=3"
                      f" placeholder='{esc(goi)}'>{esc(nen)}</textarea></div>")
            continue
        boxes += (f"<div class=snt{neo}><textarea class=cvdraft name=line rows=2"
                  f" placeholder='{esc(goi)}'></textarea></div>")

    bo = sum(1 for c in cau if c["phan"] == "drop")
    xem = sum(1 for c in cau if c["phan"] == "review")
    tom = ""
    if chon:
        phan = [f"<b>{len(cau)}</b> câu"]
        if bo:
            phan.append(f"<b class=bad>{bo}</b> câu luật không cho in ra")
        if xem:
            phan.append(f"<b class=warn>{xem}</b> câu chờ bạn quyết")
        tom = (f"<div class=gapnote>Khối này với tới <b>{b['reach']}</b> tin · "
               + " · ".join(phan) + "</div>")

    return (
        "<form class=soanform method=post action='/cv/block'>"
        f"<input type=hidden name=was value='{esc(b['title'])}'>"
        + (f"<input type=hidden name=ky value='{esc(ky)}'>" if ky else "")
        # Nền đi theo form để lượt Lưu so được câu vừa gõ với chữ gốc của họ.
        + (f"<input type=hidden name=nen value='{esc(nen)}'>" if nen else "")
        +
        f"{tom}"
        "<div class=soanhead>"
        f"<label class=slab>Loại<select name=kind>{kinds}</select></label>"
        "<label class=slab>Tên khối"
        f"<input class=dfthead type=text name=title value='{esc(b['title'])}'"
        " placeholder='tên công ty, hoặc tên project' autocomplete=off>"
        "</label>"
        "<label class=slab>Ngày tháng / tổ chức<span>để trống nếu là project</span>"
        f"<input class=dfthead type=text name=meta value='{esc(b['meta'])}'"
        " placeholder='2023 — nay' autocomplete=off></label>"
        "</div>"
        "<div class=slab>Câu<span>mỗi ô một câu · ô trống thì bỏ qua · dải "
        "dưới mỗi ô là luật nói gì, tính lại sau khi Lưu</span></div>"
        f"{boxes}"
        "<div class=setfoot>"
        "<button class='mbtn apply' type=submit>Lưu vào CV gốc</button>"
        + ("<button class='mbtn kill' type=submit name=kill value=1>Xoá khối"
           "</button>" if chon else "")
        + "<span class=applynote>ghi thẳng vào hồ sơ · bấm Cập nhật trên thanh "
          "trên để dựng lại mọi bản CV từ đó</span></div>"
        + (f"<div class=forced>Khối này không tin nào với tới. Không xoá cũng "
           f"được — nhưng nó đang chiếm một chỗ trên tờ giấy mà không chứng "
           f"minh gì.</div>" if chon and b["reach"] == 0 else "")
        + "</form>")


def render(*, khoi: list[dict], chon: dict | None, cau: list[dict],
           hut: list, brief: dict | None = None, ky: str = "",
           nen: str = "", soan: str = "", gy: str = "", tho: bool = False,
           loi: str = "", ten: str = "", dap: tuple = (0, 0), san: list = (),
           moi: bool = False, stage: dict | None = None) -> str:
    """Màn con Soạn khối — MỘT chỗ cho mọi phép ghi vào CV gốc.

    Ba đường vào, một màn:
        /cv/soan                 chọn khối để sửa
        /cv/soan?khoi=X          sửa khối X
        /cv/soan?ky=S            viết một câu về S — brief mở, chờ chọn khối
        /cv/soan?khoi=X&ky=S     viết vào X, brief của S mở ngay trên ô soạn

    Giữ nguyên thanh điều khiển của khúc CV có lý do: sửa khối xong thì nút
    Chạy tự đổi thành "Cập nhật — chữ trên CV đã sửa" (xem cv/batch.stage).
    Đó là lời nhắc đúng lúc đúng chỗ, không phải một dòng chữ dặn dò.

    ĐỘ PHỦ HÔM NAY đứng trên thanh, KHÔNG phải "vừa tăng mấy tin". Delta thuộc
    về nhật ký, nơi nó có dấu thời gian; in nó lên màn thì bấm F5 một cái là
    con số biến thành lời nói dối.
    """
    from ..layout import deck
    info = stage or {}
    words = sum(len(b["lines"]) for b in khoi)
    dang = chon["title"] if chon else ""

    # THỨ TỰ ĐỌC: họ hỏi gì -> mình viết gì. Brief lên trên ô soạn, luôn luôn.
    # Cột trái phải MANG THEO đích và nền: bấm một khối là trả lời "viết vào
    # đâu", không phải vứt bỏ câu trả lời của "viết cái gì".
    mang = (f"&ky={quote(ky, safe='')}" if ky else "")
    mang += (f"&nen={quote(nen, safe='')}" if nen else "")
    mang += "&tho=1" if tho else ""

    # KHỐI CHƯA TỒN TẠI VẪN PHẢI RA FORM. Gọi tên một khối chưa lưu — lượt Lưu
    # vừa bị từ chối, hoặc vừa đổi tên khối — mà màn trả về "chưa chọn khối" thì
    # chữ vừa gõ biến mất và người dùng không hiểu mình vừa mất cái gì.
    moi = moi or bool(ten and chon is None)

    # HAI VIỆC, HAI HÌNH — và đây là chỗ sửa phản hồi "không biết bấm cái gì".
    #
    #   có `ky`   VIẾT MỘT CÂU MỚI  -> ba bước đánh số, một ô, một nút
    #   không     SỬA KHỐI          -> cả khối ra, từng câu một, có dải chấm
    #
    # Trước đây cả hai dùng chung một hình: vào để viết một câu mà nhận nguyên
    # bộ soạn 16 câu, ô cần gõ bị chôn xuống dưới hai màn hình.
    ruot = _hut(hut, dang, ky)
    if brief:
        ruot += _viet(brief, dang or (ten if moi else ""), nen, loi, khoi,
                      soan, gy, tho)
        # Khối mới thì vẫn cần chỗ đặt TÊN — bước 2 không làm được việc đó.
        if moi and not dang:
            ruot += _form(None, [], ky, nen, loi, ten)
    elif chon or moi:
        ruot += _form(chon, cau, ky, nen, loi, ten)
    else:
        ruot += _san(list(san)) or _chua_chon()

    nhan = (f"viết về {ky}" if ky else
            chon["title"][:30] if chon else
            (ten[:30] or "Khối mới") if moi else "chưa chọn")
    nen, tong = dap
    do = [(f"{len(khoi)}", "khối", "stock"), (f"{words}", "câu kho", "act")]
    # Độ phủ là số DUY NHẤT nói được màn này có ích không: nó nhích lên mỗi
    # lần viết thêm một câu đúng chỗ.
    do.append((f"{nen}/{tong}" if tong else "—", "tin hồ sơ đáp trọn", "view"))
    return runtime.render(
        title="Soạn khối", active="/cv", stream="cv", journal="corner",
        bar=deck("cv", "CV · soạn khối", info.get("state", "chưa dựng bản nào"),
                 do,
                 adjust="/adjust/cv",
                 run=info.get("label", "Chạy"),
                 run_note=info.get("note", ""),
                 sua=("/cv", "← Bản CV", "Quay lại danh sách bản sẽ gửi"),
                 xoa=("/api/cv/xoa", "Xoá bản", "Xoá thật?",
                      "Vứt mọi bản CV đã dựng. Chữ trên CV gốc KHÔNG bị đụng "
                      "— bấm Chạy là dựng lại")),
        cols=2, columns="minmax(330px, 1fr) 1.7fr",
        rows_tpl="1fr 150px", journal_at=(1, 2),
        panels=[
            runtime.panel("Khối nguyên liệu", _khoi_list(khoi, dang, mang),
                          at=(1, 1)),
            runtime.panel(f"Soạn · {nhan}", ruot, rows=2, at=(2, 1)),
        ],
    )


def _chua_chon() -> str:
    """Chưa chọn gì. Nói ra VIỆC, không nói "chưa có dữ liệu"."""
    return (
        "<div class=empty-box><b>Chọn một khối bên trái để sửa</b>, bấm "
        "<b>+ Khối mới</b>, hoặc bấm một thứ ở hàng trên để viết câu mới về "
        "nó.<br>Mỗi câu bạn gõ ở đây được chấm ngay: luật có cho nó in ra "
        "không, và bao nhiêu tin đang đòi thứ nó nhắc tới.</div>")


def _san(rows: list) -> str:
    """MÁY TỰ LO — bản nháp dựng sẵn cho MỌI chỗ hụt, trên một màn.

    Đây là hình duy nhất của "tự động điền" mà không nói dối. Máy làm trước
    toàn bộ phần nó làm được — tìm dòng yêu cầu tả việc, cắt phần thừa, chia
    thì quá khứ — rồi dừng đúng ở chỗ nó không biết: CON SỐ. Người dùng điền
    con số và bấm, từng câu một.

    KHÔNG tự ghi vào CV. Câu nháp nằm trong `cv_text` thì bộ chấm đếm luôn nó
    là kỹ năng đã đáp, và độ phủ nhảy lên mà không có gì thật đằng sau — app
    nói dối người dùng về chính họ. Đây là lý do duy nhất, và nó đủ.
    """
    if not rows:
        return ""
    o = ""
    for r in rows:
        cho = (f"/cv/soan?ky={quote(r['ky'], safe='')}"
               f"&nen={quote(r['nen'], safe='')}")
        o += (f"<a class=sanone href='{cho}'>"
              f"<span class=sanky>{esc(r['ky'])}<b>+{r['them']}</b>tin</span>"
              f"<span class=sannhap>{esc(r['nhap'])}</span>"
              f"<span class=sanco>{esc(r['cong_ty'])} · điền số rồi lưu →</span>"
              f"</a>")
    return (f"<div class=sanbox><div class=briefhead>Máy đã dựng sẵn "
            f"<b>{len(rows)}</b> bản nháp<span>mỗi chỗ hụt một câu, đã cắt "
            f"phần thừa và chia thì quá khứ. Chỗ <b>___</b> là bằng chứng — "
            f"thứ duy nhất máy không biết. Bấm một cái để điền rồi lưu."
            f"</span></div>{o}</div>")
