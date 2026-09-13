"""Home — chu trình dựng hồ sơ. Đây là CỬA VÀO của app.

Trước đây trang này trống trơn: người dùng mới mở app ra, đáp xuống đây đầu
tiên, và không ai nói cho họ biết phải làm gì. Bốn tab kia đều đã biết chỉ
đường ("chạy Search trước", "còn thiếu ba câu") — chỉ mỗi cửa vào là im.

Trang này KHÔNG tự nghĩ ra luật nào. Nó đọc `live.onboarding()` — cùng cái
cổng mà Search và Profile đang đọc — rồi vẽ ra đường đi: phần nào xong, phần
nào chưa, bước tiếp theo là gì, bấm vào là tới thẳng chỗ điền.

Ba câu mở cổng, 35 câu là đủ. Nên trang chia làm hai giai đoạn:

    cổng CHƯA mở  -> chỉ có một việc: điền cho xong ba câu đó. Mọi thứ khác
                     trong app đều chưa chạy được, bày thêm chỉ làm nhiễu.
    cổng ĐÃ mở    -> danh sách này thành MENU "thêm cho mạnh": mỗi phần nói
                     rõ thêm nó thì app làm tốt thêm được gì.
"""

from __future__ import annotations

from html import escape as esc

from ..layout import page

# Thêm phần này thì app làm tốt thêm được gì — nói bằng hệ quả, không bằng
# tên trường. "Thêm kỹ năng" không thuyết phục ai; "chấm điểm hết đoán mò" thì có.
LOI = {
    "muc_tieu": "Không có phần này thì app không biết tìm gì — chưa quét được.",
    "rang_buoc": "Lọc ở đây rẻ hơn nhiều so với đọc rồi mới loại.",
    # Câu hay bị hỏi nhất: "không có phần kinh nghiệm làm việc à?". Có — nó
    # đọc thẳng từ CV bạn nhập (mục EXPERIENCE), thành các khối ở tab CV. Gõ
    # lại ở đây là đẻ hai nguồn cho cùng một sự thật.
    "nang_luc": "Nguyên liệu để chấm điểm và dựng CV. Thiếu thì chấm là đoán mò.",
    "kinh_nghiem": "Chỗ nhà tuyển dụng đọc đầu tiên. Mỗi câu bạn viết ở đây là "
                   "một câu có thể lên CV.",
    "project": "Khớp thì qua được bộ lọc, bằng chứng mới đưa bạn vào nhóm được gọi.",
    "danh_tinh": "Cần lúc dựng CV và điền đơn. Chưa tới đó thì để trống cũng được.",
}


def _thanh(xong: int, tong: int) -> str:
    pc = round(xong * 100 / tong) if tong else 0
    return (f"<div class=obar><span style='width:{pc}%'></span></div>"
            f"<div class=obarnum><b>{xong}</b>/{tong} câu đã trả lời</div>")


def _the(s: dict, mo: bool) -> str:
    """Một phần hồ sơ. `mo` = cổng đã mở chưa — đổi câu chữ chứ không đổi luật."""
    if s["done"]:
        dau, lop, nut = "✓", " done", "Sửa"
    else:
        dau, lop, nut = "", "", ("Điền ngay" if s["required"] else "Thêm")

    nhan = ""
    if s["required"] and not s["done"]:
        nhan = "<span class='blkkind req'>BẮT BUỘC</span>"
    elif s["optional"]:
        nhan = "<span class=blkkind>tuỳ chọn</span>"

    # Cổng chưa mở thì chỉ phần bắt buộc được nói to; phần khác lùi lại.
    mo_nhat = " dim" if (not mo and not s["required"] and not s["done"]) else ""
    return (
        f"<a class='blk ostep{lop}{mo_nhat}' href='{esc(s['href'])}'>"
        f"<span class=blkmain>"
        f"<span class=blkhead><b>{dau} {esc(s['title'])}</b>{nhan}"
        f"<span class=ocount>{s['answered']}/{s['total']}</span></span>"
        f"<span class=osub>{esc(LOI.get(s['id'], s['why']))}</span></span>"
        f"<span class='mbtn tiny'>{nut}</span></a>")


def sheet(state: dict) -> str:
    """Chu trình dựng hồ sơ — MẢNH HTML cho tấm phủ, không phải cả trang.

    Nó không chiếm tab Home nữa: việc của nó chỉ có lúc đầu, mà tab Home là
    chỗ của bảng điều khiển pipeline. Cổng chưa mở thì tấm này tự bật lên khi
    vào app — đó là chỗ "bắt điền". Mở xong thì nó biến mất, bấm lại được từ
    tab Profile.
    """
    mo = state["gate_open"]
    ke = state["next"]

    if mo:
        gate = ("<div class='gate ok'><b>Hồ sơ đủ để chạy.</b> "
                "Sang tab Search bấm Chạy.</div>")
    else:
        thieu = " · ".join(esc(q["text"]) for q in state["gate_missing"])
        gate = (f"<div class='gate block'><b>Chưa chạy được gì.</b> "
                f"App cần đúng {len(state['gate_missing'])} câu này trước: "
                f"{thieu}</div>")

    if state["answered"] == 0:
        nut = ("<div class=octa>"
               "<a class='mbtn apply big' href='/profile/import'>"
               "Nhập CV — app điền hộ →</a>"
               + (f"<a class=oalt href='{esc(ke['href'])}'>hoặc tự gõ</a>"
                  if ke else "")
               + "</div>"
               "<p class=omeo>Máy đọc CV rồi ĐỀ XUẤT từng ô — không ô nào được "
               "ghi vào cho tới khi bạn tick duyệt. Riêng <b>quyền làm việc</b> "
               "máy cố tình không đoán: CV không nói, mà đoán sai thì hỏng cả "
               "lá đơn.</p>")
    elif ke:
        nut = (f"<a class='mbtn apply big' href='{esc(ke['href'])}'>"
               f"Tiếp tục — {esc(ke['title'])} →</a>")
    else:
        nut = ""

    return ("<div class=sheethead>Hồ sơ của bạn</div>"
            "<div class=setupbody>"
            + _thanh(state["answered"], state["total"])
            + gate + nut
            + "<div class=blklist>"
            + "".join(_the(s, mo) for s in state["sections"])
            + "</div></div>")


# ---------------------------------------------------------------- TỔNG QUAN
#
# Home KHÔNG có việc của riêng nó, và đó là cả điểm của nó: bốn tab kia mỗi
# tab nhìn một khúc, còn câu hỏi "cả quá trình này có đang chạy được không"
# thì đứng trong một khúc lẻ không trả lời nổi.
#
# VỪA ĐÚNG MỘT KHUNG MÀN HÌNH, KHÔNG CUỘN. Bản trước bày hết mọi thứ ra và
# trang dài gấp đôi cửa sổ — bày nhiều không phải là nói nhiều, nó là không
# chọn. Một trang tổng quan phải cuộn thì nó đã thôi là tổng quan.
#
# Nên mỗi ô chỉ giữ ĐÚNG MỘT câu trả lời, và phần giải thích nằm trong
# `.chitiet` — chỉ hiện khi bấm ⤢ mở to ô đó. Thuần CSS (`.wid.big .chitiet`),
# không thêm một dòng JS nào: nút ⤢ đã có sẵn trên mọi ô.

def _ct(x: str) -> str:
    """Phần CHỈ HIỆN KHI MỞ TO ô. Gọn lúc liếc, đủ lúc soi."""
    return f"<div class=chitiet>{x}</div>"


def _ket_qua(k: dict) -> str:
    """TRỌNG TÂM CỦA CẢ TRANG: nộp bằng này chỗ thì mấy chỗ gọi lại.

    Một số to, không phải ba số ngang nhau. Ba số ngang nhau là ba số không
    có số nào quan trọng, và người đọc phải tự chọn hộ mình — mà chọn hộ
    người đọc chính là việc của trang tổng quan.
    """
    from . import bieudo as bd
    if not k.get("tong"):
        return ("<div class=empty-box>chưa nộp chỗ nào — chưa có gì để đánh "
                "giá. Sang <a href='/search'>Search</a> bấm Nộp trên một tin."
                "</div>")
    pc = k["pc_di"]
    # HERO và hai số phụ NẰM CÙNG HÀNG. Xếp chồng thì riêng khối số đã ăn
    # 150px, và ô này phải cuộn trên cửa sổ thấp — mà ô tổng quan phải cuộn
    # thì nó đã thôi là tổng quan.
    hero = (f"<div class=qtop><div class=hero>"
            f"<b>{'—' if pc is None else f'{pc:g}%'}</b>"
            f"<span>được gọi đi tiếp</span>"
            f"<i>{k['di_tiep']}/{k['tong']} lần nộp</i></div>"
            f"<div class=hphu>"
            f"<span><b>{k['pc_hoi']:g}%</b>có người hồi âm"
            f"<i>{k['hoi_am']}/{k['tong']}</i></span>"
            f"<span><b>{k['pc_truot']:g}%</b>trượt / coi như trượt"
            f"<i>{k['truot']}/{k['tong']}</i></span></div></div>")
    phu = ""
    thanh = bd.thanh_chia(
        [("đi tiếp", k["di_tiep"], "qdi"),
         ("họ từ chối", k["ho_noi"], "qtu"),
         (f"im quá {k['nguong_im']} ngày", k["suy"], "qim"),
         ("còn đang chờ", k["cho"], "qcho")], k["tong"])
    # CỠ MẪU nói trước mọi kết luận — nhưng nói lúc MỞ TO, vì nó là lời dặn
    # cách đọc, không phải con số.
    # CHƯA NGÃ NGŨ LẦN NÀO thì KHÔNG có tỉ lệ nào cả — `pc_di_xong` là None.
    #
    # Ca này không hiếm: người dùng ngày đầu, mọi đơn còn trong cửa sổ hồi âm.
    # Bản trước nhét thẳng vào `:g` và trang Home NỔ — đúng ngay cái ngày quan
    # trọng nhất phải chạy được.
    them = (f"<p>Tỉ lệ trên <b>đã ngã ngũ</b> (bỏ {k['cho']} lần còn đang chờ "
            f"ra): <b>{k['pc_di_xong']:g}%</b> — {k['di_tiep']}/{k['xong']}.</p>"
            if k["pc_di_xong"] is not None else
            f"<p>Cả <b>{k['cho']}</b> lần nộp đều còn trong cửa sổ hồi âm — "
            f"chưa lần nào ngã ngũ, nên chưa có tỉ lệ nào để nói.</p>"
            + (f"<p>Mới <b>{k['tong']}</b> lần nộp. Dưới 30 thì một lần được "
               f"gọi cũng làm con số nhảy vài điểm — đọc như hướng đi, đừng "
               f"đọc như kết luận.</p>" if k["tong"] < 30 else "")
            + f"<p>«Coi như trượt» là <b>phép suy</b>, không phải họ nói: quá "
              f"{k['nguong_im']} ngày im thì đóng lại. Đổi mốc ở nút ⚟ bên "
              f"<a href='/track'>Quản lí</a>.</p>")
    return hero + phu + thanh + _ct(them)


def _nang_suat(n: dict, q: dict) -> str:
    """Mỗi ngày làm được bao nhiêu, và vòng quét có chạy đều không."""
    from . import bieudo as bd
    dai = "".join(bd.dai_viec(v) for v in n["viec"].values())
    nhip = (f"<div class=nhip><b>{q['luot']}</b> lượt quét / "
            f"<b>{q['ngay']}</b> ngày"
            + (f" · <b>{q['pc_ok']}%</b> trót lọt" if q["pc_ok"] is not None else "")
            + (f" · <b class=xau>{q['hong_luot']}</b> lượt hỏng"
               if q["hong_luot"] else "")
            + (f" · <b class=xau>{len(q['cam'])}</b> nguồn câm"
               if q["cam"] else "")
            + "</div>") if q["luot"] else ""
    return dai + nhip + _ct(_thoi_quen(n))


def _thoi_quen(n: dict) -> str:
    """Theo THỨ và theo THÁNG — chỉ vẽ chuỗi nào TỰ NÓ đủ dài.

    Mỗi chuỗi tự gác lấy mình. Lấy chuỗi dài nhất làm cổng chung thì biểu đồ
    "tin tìm được theo thứ" được vẽ trên 2 ngày dữ liệu, và nó sẽ nói "thứ
    sáu gấp chín lần thứ bảy" — đúng phép tính, sai hoàn toàn về nghĩa.
    """
    from . import bieudo as bd
    o = ""
    for ma, v in n["viec"].items():
        if not v["du_thu"] and not v["du_thang"]:
            continue
        o += f"<div class=tqten>{esc(v['ten'])}</div>"
        if v["du_thu"]:
            o += bd.cot_thu(n["thu"][ma], list(n["ten_thu"]), v.get("mau", ""))
        if v["du_thang"]:
            o += bd.thang_gan(n["thang"][ma], mau=v.get("mau", ""))
    chua = [v["ten"] for v in n["viec"].values()
            if not v["du_thu"] and not v["du_thang"]]
    if not o:
        return bd.chua_du(n["ngay_co"], n["can_thu"])
    if chua:
        o += (f"<div class=note>Chưa gộp được: {esc(' · '.join(chua))} — cần "
              f"đủ {n['can_thu']} ngày số liệu thì mới có nghĩa.</div>")
    return "<div class=tqhead>Theo thứ · theo tháng</div>" + o


MUC = {"chac": ("chắc", "đếm trực tiếp, không suy gì"),
       "vua": ("vừa", "đủ mẫu để tin, chưa đủ để chắc"),
       "yeu": ("yếu", "mẫu còn bé — coi là gợi ý thôi")}


def _chan_doan(ds: list) -> str:
    """Dấu hiệu đang hỏng, XẾP THEO ĐỘ CHẮC chứ không theo độ giật gân.

    Nhãn độ chắc nằm ngay trên mặt thẻ: một con số đếm trực tiếp và một suy
    đoán trên bốn mẫu mà trông giống nhau thì người dùng đi sửa nhầm chỗ — và
    đó là cách tệ nhất một trang thống kê hỏng: nó không im lặng, nó chỉ sai
    hướng.

    Lúc gọn chỉ hiện TÊN; lời giải thích và chỗ khai "đo trên bao nhiêu mẫu"
    nằm sau nút ⤢. Bốn đoạn văn xếp chồng thì không ai đọc đoạn nào.
    """
    if not ds:
        return ("<div class=empty-box>Chưa thấy dấu hiệu nào đáng lo. "
                "Chạy thêm vài vòng rồi quay lại.</div>")
    # BA CÁI ĐẦU LÚC GỌN. Danh sách đã xếp theo độ chắc, nên ba cái đầu là
    # ba cái đáng tin nhất — và bốn thẻ xếp chồng trên một ô cao 190px thì
    # không đọc được thẻ nào. Phần còn lại hiện khi bấm ⤢.
    o = ""
    for i, x in enumerate(ds):
        nhan, y = MUC.get(x["muc"], ("", ""))
        o += (f"<a class='cdrow {esc(x['muc'])}{' chitiet' if i >= 3 else ''}'"
              f" href='{esc(x['di'])}'>"
              f"<span class=cdso>{esc(x['so'])}</span>"
              f"<span class=cdmain><b>{esc(x['ten'])}</b>"
              f"<span class=chitiet>{esc(x['y'])}</span>"
              f"<i class=chitiet>đo trên {esc(x['tren'])}</i></span>"
              f"<span class=cdend><span class='cdmuc {esc(x['muc'])}'"
              f" title='{esc(y)}'>{esc(nhan)}</span>"
              f"<span class='mbtn tiny'>{esc(x['nut'])}</span></span></a>")
    con = len(ds) - 3
    them = (f"<div class=cdmore>còn <b>{con}</b> dấu hiệu nữa — bấm ⤢ để xem"
            f"</div>" if con > 0 else "")
    return f"<div class=cdlist>{o}</div>{them}"


def _pheu(d: dict, k: dict) -> str:
    """Rơi rụng từ tin lấy về tới lần được gọi — HAI đoạn, nói rõ chỗ nối."""
    from . import bieudo as bd
    noi, dang = d["noi"], d["dang"]
    chu = (f"<b>{d['cho_nop']}</b> tin đáng nộp đang nằm chờ. "
           + (f"Mới <b>{noi}</b> tin trong số đó được nộp — nên đoạn dưới gần "
              f"như KHÔNG phải kết quả của đoạn trên: phần lớn lần nộp có "
              f"trước khi app tồn tại, dựng lại từ thư."
              if noi < dang else ""))
    duoi = [("đã nộp", k["tong"], "/track"),
            ("có người hồi âm", k["hoi_am"], "/track"),
            ("được gọi đi tiếp", k["di_tiep"], "/track")]
    return (bd.pheu(d["tim"]) + "<div class=pseam>· nộp ·</div>"
            + bd.pheu(duoi) + _ct(f"<p>{chu}</p>"))


def adjust(bat: dict | None = None) -> str:
    """Tấm ⚟ của Home — BA KHÚC của một phiên.

    Khác ⚟ bên Search và Quản lí: bên đó hỏi "quét nguồn nào", "nộp tin từ
    nguồn nào" — câu hỏi trong lòng một khúc. Ở đây câu hỏi là PHIÊN GỒM
    KHÚC NÀO, tức là ở tầng trên cả ba.

    Vì sao phải tắt được từng khúc: ba khúc có giá rất khác nhau — đọc thư
    12 giây, dựng CV 5,3 giây, còn quét LinkedIn phải mở Chrome và tốn nửa
    tiếng. Ai chỉ muốn trực hộp thư ban đêm thì tắt hai khúc kia, chứ không
    phải chọn giữa "chạy tất" và "không chạy gì".
    """
    from ...core import prefs
    d = bat or {}
    hang = ""
    for khoa, (_khuc, ten, y) in prefs.PHIEN.items():
        on = bool(d.get(khoa))
        hang += (f"<div class='swrow{'' if on else ' off'}'>"
                 f"<button class='mbtn tiny swbtn{'' if on else ' off'}'"
                 f" data-post='/api/home/num' data-arg='{esc(khoa)}:"
                 f"{'0' if on else '1'}'>{'BẬT' if on else 'TẮT'}</button>"
                 f"<b class=swten>{esc(ten)}</b>"
                 f"<span class=swnow>{'có chạy' if on else 'bỏ qua'}</span>"
                 f"<details class=swwhy><summary>vì sao</summary>"
                 f"<div class=swbody>{esc(y)}</div></details></div>")
    so_bat = sum(1 for k in prefs.PHIEN if d.get(k))
    return ("<div class=sheethead>Điều chỉnh · Phiên</div>"
            "<div class=adjbox>"
            "<div class=adjsec>Một phiên gồm khúc nào"
            "<span>chạy lần lượt, không song song</span></div>"
            + hang
            + ("<div class=note>Thứ tự cố định: <b>Search → Make CV → "
               "Manage mail</b>. Dựng CV đọc kho tin nên phải chạy sau lượt "
               "tìm; chạy trước thì nó xếp theo kho của vòng trước.</div>"
               if so_bat else
               "<div class='note xau'>Cả ba đang TẮT — phiên sẽ chạy mà không "
               "làm gì. Bật ít nhất một khúc.</div>")
            + "</div>")


def render(state: dict, so: dict | None = None, stage: dict | None = None) -> str:
    """Tab Home — bảng tổng quan, VỪA MỘT KHUNG, tự cập nhật theo luồng.

    LUỒNG RỖNG (`stream=""`) là cố ý: live.js coi ô nhật ký không ghi luồng
    là "mọi luồng", nên bất kỳ khúc nào chạy xong cũng vẽ lại trang này. Đó
    là chỗ chữ "live" thành thật — Home không hỏi lại theo đồng hồ, nó đợi có
    chuyện thật rồi mới vẽ lại.

    BỐN Ô, hai hàng, không cuộn. Trái sang phải là đi từ KẾT LUẬN (tỉ lệ, chẩn
    đoán) sang DỮ KIỆN ĐỠ NÓ (năng suất, phễu) — người ta mở trang tổng quan
    để biết "ổn không", không phải để đọc bảng số.
    """
    from ..layout import deck
    from . import runtime
    d = so or {}
    info = stage or {}
    pheu = d.get("pheu") or {}
    k = d.get("ket_qua") or {}
    n = d.get("nang_suat") or {}
    q = d.get("nhip") or {}
    hn = d.get("hom_nay") or {}

    # THANH NÀY LÀ BẢN TIN CỦA HÔM NAY, không phải bảng tổng kết.
    #
    # Tổng kết đã nằm ở bốn ô bên dưới, và một con số như "37 đã nộp" thì hôm
    # nào nhìn cũng thế — nó không trả lời được câu duy nhất người ta hỏi một
    # trạm trực 24/7: HÔM NAY nó có làm được gì không.
    #
    # Bốn số đi theo đúng vòng đời một lần nộp: tìm được → nộp đi → họ gọi →
    # họ loại. Đọc từ trái sang phải là đọc một ngày làm việc.
    do = [(f"{hn.get('tim', 0)}", "tin tìm được", "stock"),
          (f"{hn.get('nop', 0)}", "đơn đã nộp", "act"),
          (f"{hn.get('tiep', 0)}", "được gọi tiếp", "new"),
          (f"{hn.get('truot', 0)}", "báo trượt", "view")]
    return runtime.render(
        title="Tổng quan", active="/", stream="", journal="bottom", cols=2,
        setup="" if state.get("gate_open") else "/onboarding",
        # `stage="search"` vẫn là tên khúc gửi kèm nút Dừng — cờ dừng đặt
        # theo khúc, và Search là khúc duy nhất chạy lâu đủ để cần cắt ngang.
        bar=deck("search", "Hôm nay", info.get("phien", "phiên đang TẮT"), do,
                 adjust="/adjust/home",
                 run=info.get("nhan_phien", "Start session"),
                 run_note="chạy cả dây chuyền — Search → Make CV → Manage "
                          "mail — rồi lặp lại 24/7. Chỉnh khúc nào chạy ở ⚟",
                 run_path="/api/session/start", stop_path="/api/session/stop"),
        # HAI HÀNG CO THEO RUỘT, phần thừa dồn hết cho nhật ký.
        #
        # `1fr 1fr` chia đều là sai ở cả hai đầu: cửa sổ cao thì bốn ô kia
        # thừa một khoảng trống to đùng dưới đáy mỗi ô, cửa sổ thấp thì chúng
        # phải cuộn. `auto` thì mỗi ô cao đúng bằng thứ nó chứa — không thừa,
        # không cuộn — và chỗ dôi ra rơi vào nhật ký, ô DUY NHẤT đáng được
        # cuộn: dòng nhật ký thì bao nhiêu cũng có.
        #
        # minmax(130px,1fr) để nhật ký không bị bóp thành một vạch trên màn
        # thấp; thấp hơn nữa thì cả trang cuộn, và đó là cách hỏng đúng.
        # `minmax(min-content,auto)`, KHÔNG phải `auto` trần: `auto` vẫn cho
        # phép lưới nén hàng khi cửa sổ hẹp, và vì ô giờ không còn khung cuộn
        # nên ruột TRÀN RA NGOÀI ô — xấu hơn cuộn. `min-content` là sàn cứng:
        # thiếu chỗ thì cả trang cuộn, ô vẫn nguyên vẹn.
        rows_tpl="minmax(min-content,auto) minmax(min-content,auto)"
                 " minmax(130px,1fr)",
        # `cls="vua"` = ô KHÔNG phải khung cuộn.
        #
        # Đây là chỗ sửa đúng căn nguyên chứ không phải gọt thêm vài điểm ảnh:
        # `.wbody` mặc định `overflow:auto`, mà một khung cuộn thì min-content
        # của nó bằng 0 — nên lưới được phép NÉN ô xuống bao nhiêu cũng được,
        # và ruột đành cuộn. Bỏ overflow đi thì ô đòi đúng chiều cao nó cần,
        # hàng `auto` cấp đủ, và khi cửa sổ thật sự quá thấp thì CẢ TRANG cuộn
        # — hỏng đúng cách, thay vì bốn ô cùng cuộn lén.
        panels=[
            runtime.panel("Kết quả · cả quá trình", _ket_qua(k),
                          at=(1, 1), cls="vua"),
            runtime.panel("Năng suất mỗi ngày", _nang_suat(n, q),
                          at=(2, 1), cls="vua"),
            runtime.panel("Chẩn đoán · chỗ nào đang hỏng",
                          _chan_doan(d.get("chan_doan") or []),
                          at=(1, 2), cls="vua"),
            runtime.panel("Phễu · rơi rụng ở khúc nào",
                          _pheu(pheu, k) if pheu else "",
                          at=(2, 2), cls="vua"),
        ],
    )
