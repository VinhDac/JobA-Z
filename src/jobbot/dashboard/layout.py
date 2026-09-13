"""Khung trang: sidebar trái + thanh master + vùng widget.

CHỈ VẼ. Không luật nghiệp vụ, không đọc DB.

Bố cục kiểu app desktop, không phải trang web:
    sidebar cố định trái, chạy lên tận đỉnh cửa sổ
    thanh master trên cùng: RUN / PAUSE / trạng thái đang chạy
    nội dung là các Ô (widget) — mỗi ô tự cuộn bên trong, TRANG thì không cuộn

Vì sao ô tự cuộn chứ không phải trang cuộn: đây là app chạy 24/7, mở ra là
phải thấy ngay toàn cảnh. Trang cuộn thì nửa thông tin nằm dưới màn hình,
và cái đang chạy có thể đang nằm ở chỗ không nhìn thấy.
"""

from __future__ import annotations

from html import escape as esc

# (đường dẫn, nhãn, ký hiệu)
# Thứ tự = thứ tự công việc chạy thật, không phải thứ tự chữ cái.
# Tab có (rt) là tab CÓ THỜI GIAN CHẠY -> dùng khuôn views/runtime.py.
# Thứ tự = thứ tự công việc chạy thật, không phải thứ tự chữ cái.
# Tab có (rt) là tab CÓ THỜI GIAN CHẠY -> dùng khuôn views/runtime.py.
#
# ĐÃ BỎ: Settings (thành menu bánh răng trên thanh trên — nó không phải một
# việc, chỉ là mấy công tắc mở ra chỉnh rồi đóng), Jobs và Score. Danh sách việc sẽ nằm trong Search — "tìm" và "xem
# kết quả tìm" là một việc. Chấm điểm không phải một hệ chạy riêng, nó là
# giai đoạn cuối của cùng một lần quét.
# /jobs/<id> và /jobs/<id>/cv VẪN SỐNG — danh sách mới sẽ trỏ tới đó.
# --------------------------------------------------------------- BỘ ICON
#
# SVG NÉT, KHÔNG PHẢI KÝ TỰ UNICODE. Bản trước dùng ◈ ⌕ ▤ ▣ ◇ — và chúng
# không phải một bộ: mỗi ký tự do một nhà thiết kế font vẽ cho một mục đích
# khác, nên cỡ quang học, độ dày nét và baseline đều lệch nhau. Lúc thanh bên
# GẬP, CSS phóng chúng lên 22px và cái lệch đó thành lộ hẳn: ⌕ bé tí, ▤ là
# khối đặc, ◇ mảnh như sợi chỉ. Thêm nữa ◈ ▣ ▤ không nói được nó là cái gì —
# người dùng phải học thuộc "hình thoi kép = Home".
#
# Bộ này: một khung 24×24, một độ dày nét (1.75), đầu nét bo tròn, tô bằng
# `currentColor` nên đổi màu theo CSS chứ không phải sửa ảnh. Không file
# ngoài, không font, không CDN — đúng luật không-phụ-thuộc của app.
#
# TÊN ICON PHẢI TẢ ĐÚNG VIỆC CỦA TAB, không phải tả hình:
#     home     mái nhà      — chỗ nhìn tổng thể
#     search   kính lúp     — đi tìm việc
#     cv       tờ giấy      — mấy bản sẽ gửi đi
#     track    kẹp + dấu ✓  — theo dõi đơn đã nộp tới đâu
#     profile  người        — hồ sơ của bạn
#     setting  bánh răng    — cài đặt cả app
#     adjust   ba cần gạt   — điều chỉnh RIÊNG màn đang mở (nút ⚟)
#     to       bốn góc      — mở to một ô
#     gap      hai mũi <<   — gập thanh bên (CSS xoay 180° khi đã gập)
#
# Bánh răng dựng bằng lượng giác (6 răng) chứ không gõ tay 24 toạ độ: gõ tay
# thì lệch một số là răng méo, mà ở 16px mắt không bắt được — chỉ thấy "nhìn
# hơi bẩn" mà không biết vì sao.
ICON = {
    "home": "<path d='M3.2 10.4 12 3.2l8.8 7.2'/>"
            "<path d='M5.6 9.1V20.3h12.8V9.1'/>"
            "<path d='M9.7 20.3v-5.1h4.6v5.1'/>",
    "search": "<circle cx='10.9' cy='10.9' r='6.7'/>"
              "<path d='M20.4 20.4 15.7 15.7'/>",
    "cv": "<path d='M13.6 3.2H7.4A2.2 2.2 0 0 0 5.2 5.4v13.2a2.2 2.2 0 0 0 2.2"
          " 2.2h9.2a2.2 2.2 0 0 0 2.2-2.2V8.4z'/>"
          "<path d='M13.6 3.2v5.2h5.2'/><path d='M8.8 13.1h6.4M8.8 16.6h6.4'/>",
    "track": "<path d='M9.2 4.6H7.4a2.2 2.2 0 0 0-2.2 2.2v11.8a2.2 2.2 0 0 0 2.2"
             " 2.2h9.2a2.2 2.2 0 0 0 2.2-2.2V6.8a2.2 2.2 0 0 0-2.2-2.2h-1.8'/>"
             "<rect x='9.2' y='2.8' width='5.6' height='3.6' rx='1.2'/>"
             "<path d='M9.3 13.6l2.1 2.1 4.3-4.3'/>",
    "profile": "<circle cx='12' cy='8.1' r='3.9'/>"
               "<path d='M4.9 20.6a7.1 7.1 0 0 1 14.2 0'/>",
    "setting": "<path d='M18.03 9.32 20.84 9.83 20.84 14.17 18.03 14.68 17.34"
               " 15.88 18.3 18.57 14.54 20.74 12.69 18.56 11.31 18.56 9.46"
               " 20.74 5.7 18.57 6.66 15.88 5.97 14.68 3.16 14.17 3.16 9.83"
               " 5.97 9.32 6.66 8.12 5.7 5.43 9.46 3.26 11.31 5.44 12.69 5.44"
               " 14.54 3.26 18.3 5.43 17.34 8.12Z'/>"
               "<circle cx='12' cy='12' r='3.3'/>",
    "adjust": "<path d='M4 6.4h3.1M11.1 6.4H20'/><circle cx='9.1' cy='6.4' r='2'/>"
              "<path d='M4 12h8.9M16.9 12H20'/><circle cx='14.9' cy='12' r='2'/>"
              "<path d='M4 17.6h3.1M11.1 17.6H20'/>"
              "<circle cx='9.1' cy='17.6' r='2'/>",
    "to": "<path d='M8.8 3.6H3.6v5.2M15.2 3.6h5.2v5.2M20.4 15.2v5.2h-5.2"
          "M3.6 15.2v5.2h5.2'/>",
    "gap": "<path d='M13.4 6.2 7.6 12l5.8 5.8M19.2 6.2 13.4 12l5.8 5.8'/>",
}


def ico(ten: str) -> str:
    """Một icon. `aria-hidden` vì chữ bên cạnh (hoặc title=) đã nói rồi —
    trình đọc màn hình đọc hai lần là tệ hơn không đọc."""
    return (f"<svg class=ico viewBox='0 0 24 24' aria-hidden=true>"
            f"{ICON[ten]}</svg>")


NAV = [
    ("/",          "Home",     "home"),
    ("/search",    "Search",   "search"),    # bước 1
    ("/cv",        "CV",       "cv"),        # mọi bản sẽ gửi
    ("/track",     "Quản lí",  "track"),     # bước 5-6: nộp và theo dõi
    ("/profile",   "Profile",  "profile"),
]


# Logo app — chìa khoá. Vẽ bằng hình cơ bản chứ không phải một path dài:
# ba vòng là ba <circle> có nét mà không tô, nên lỗ giữa là lỗ thật, sau này
# đổi độ dày nét chỉ sửa MỘT số. Màu lấy từ `currentColor` nên CSS đổi màu là
# xong, không phải sửa file ảnh.
LOGO = (
    "<svg class=logo viewBox='0 0 112 38' aria-hidden=true>"
    "<g fill=none stroke=currentColor stroke-width=4.4>"
    "<circle cx=12 cy=17.4 r=7.2 /><circle cx=25 cy=9.4 r=7.2 />"
    "<circle cx=24.4 cy=26 r=7.2 /></g>"
    "<g fill=currentColor>"
    "<rect x=26 y=14.6 width=84 height=5.6 rx=2.8 />"      # thân chìa
    "<rect x=67.6 y=8 width=4.8 height=17 rx=2.4 />"       # khấc giữa
    "<rect x=78 y=20.2 width=24 height=4.8 />"             # sống răng
    "<rect x=78 y=25 width=6 height=11.6 />"
    "<rect x=87.6 y=25 width=5.4 height=11.6 />"
    "<rect x=96 y=25 width=6 height=11.6 />"
    "</g></svg>")


def deck(stage: str, name: str, state: str, metrics: list,
         adjust: str = "", run: str = "Chạy", run_note: str = "",
         sua: tuple = (), xoa: tuple = (), them: tuple = (),
         run_path: str = "/api/stage/start",
         stop_path: str = "/api/stage/stop") -> str:
    """Thanh của MỘT khúc: tên + trạng thái · số liệu · chạy/dừng · điều chỉnh.

    MỘT khối cho mọi chức năng. Trước đây thanh trên cùng là của cả app —
    cùng nội dung ở mọi tab — mà thứ nó điều khiển ("Chạy ngay", "Bật tự quét")
    chỉ thuộc về Search. Thanh mang danh toàn app mà làm việc của một khúc.

    `metrics` là [(số, nhãn, vai)]. Chỉ nhận số nào trả lời được câu "giờ tôi
    nên làm gì" — Home cũ chết vì đầy số đẹp mà không ai hành động theo.

    VAI quyết định MÀU, và màu ở đây mang nghĩa chứ không phải trang trí:

        act    việc phải làm      -> xanh lá (màu hành động của cả app)
        stock  kho đang giữ       -> xanh dương (tin nền, đọc để biết)
        new    vừa về, cần xem    -> cam (thời sự)
        view   số nền / bộ lọc    -> xám (đọc để biết, không phải việc)

    Và một luật đè lên tất cả: SỐ 0 THÌ KHÔNG SÁNG. "0 mới" mà vẫn rực cam là
    nói dối — thanh chỉ được sáng lên khi thật sự có chuyện.

    Nút ⚟ dùng lại tấm phủ của Cài đặt (`data-settings` nhận URL), nên không
    đẻ thêm trình nghe nào — mỗi đường mới là một nút có thể chết.

    `run` là CHỮ TRÊN NÚT, và nó đổi theo tình huống: Bắt đầu / Tiếp tục /
    Cập nhật / Đang quét…. Một nút ghi "Chạy" ở mọi hoàn cảnh là nút không
    nói gì — người mới mở app không biết chạy cái gì, người vừa bấm Dừng
    tưởng bấm vào là mất hết việc đã làm. Chữ do khúc tự tính (xem
    live.search_stage), chỗ này chỉ vẽ. `data-run` giữ lại chữ gốc để
    live.js trả về sau khi hiện "Đang quét…".
    """
    def _rong(v) -> bool:
        """Số 0 (hoặc rỗng) thì tắt màu — xem luật ở docstring."""
        try:
            return int(str(v).replace(",", "").strip() or 0) == 0
        except ValueError:
            return False

    nums = "".join(
        f"<span class='metric {esc(kind)}{' zero' if _rong(v) else ''}'>"
        f"<b>{esc(str(v))}</b>{esc(label)}</span>"
        for v, label, kind in metrics)
    knob = (f"<button class='mbtn knob' data-settings='{esc(adjust)}'"
            f" title='Điều chỉnh {esc(name)}'>{ico('adjust')}</button>"
            if adjust else "")
    # `sua` = (đường dẫn, nhãn, mô tả) — nút dẫn sang MÀN KHÁC của cùng khúc.
    # Là THẺ <a>, không phải nút mở tấm phủ: tấm phủ hợp với mấy công tắc bật
    # xong đóng lại, không hợp với chỗ ngồi soạn chữ. Màn riêng thì có địa chỉ
    # riêng, lưu lại được, Back được, và rộng bằng cả cửa sổ.
    # NÚT PHÁ — chốt HAI NHỊP (xem live.js): nhịp một đổi chữ trên nút, nhịp
    # hai mới gửi. Máy chủ còn một chốt nữa, đòi arg="xoa" — không bao giờ tin
    # mỗi phía trình duyệt.
    #
    # `xoa` = (đường POST, nhãn, nhãn khi đã nạp đạn, mô tả).
    pha = (f"<button class='mbtn kill' data-post='{esc(xoa[0])}'"
           f" data-arg='xoa' data-arm='{esc(xoa[2])}'"
           f" title='{esc(xoa[3] if len(xoa) > 3 else xoa[1])}'>"
           f"{esc(xoa[1])}</button>" if xoa else "")
    # `them` = (đường POST, nhãn, mô tả) — một VIỆC NỀN nữa của khúc này,
    # cạnh nút Chạy. Khác `xoa` ở chỗ nó không phá gì nên không cần chốt.
    nut_them = (f"<button class='mbtn' data-post='{esc(them[0])}'"
                f" title='{esc(them[2] if len(them) > 2 else them[1])}'>"
                f"{esc(them[1])}</button>" if them else "")
    khac = (f"<a class='mbtn qua' href='{esc(sua[0])}'"
            f" title='{esc(sua[2] if len(sua) > 2 else sua[1])}'>"
            f"{esc(sua[1])}</a>" if sua else "")
    # MỘT viên thuốc NẰM NGANG: được phép RỘNG, chỉ không được CAO. Tất cả
    # trong một viên — tên khúc, số liệu, nút. Đẩy số liệu ra ngoài thì thanh
    # vỡ thành ba tầng rời rạc, nhìn bẩn.
    #
    # Dòng trạng thái ("tự động: TẮT · quét lần cuối 09:42") KHÔNG ở đây: nó
    # là tin chung của cả app, chỗ của nó là thanh trạng thái dưới đáy.
    return (
        f"<div class=deckwrap><div class=deckpill>"
        f"<span class=deckpillname><span class=rdot></span>"
        f"<b class=deckname>{esc(name)}</b></span>"
        f"<span class=metrics>{nums}</span>"
        f"<span class=deckbtns>"
        f"<button class='mbtn go' data-post='{esc(run_path)}'"
        f" data-arg='{esc(stage)}' data-run='{esc(run)}'"
        f" title='{esc(run_note)}'>{esc(run)}</button>"
        f"<button class=mbtn data-post='{esc(stop_path)}'"
        f" data-arg='{esc(stage)}'>Dừng</button>"
        f"{nut_them}{khac}{pha}{knob}</span>"
        f"</div></div>")


# Nhãn cho nút Back, suy từ ĐƯỜNG đã đi. Không gõ cứng ở từng trang: một
# trang có ba lối vào thì gõ cứng là hai lối nói dối.
# Xếp từ RIÊNG tới CHUNG: "/jobs/7/cv" là BẢN CV, không phải trang tin —
# khớp "/jobs/" trước thì nút ghi "← tin này" trong khi nó về bản CV.
_TEN_DUONG = (("/cv/soan", "Soạn khối"), ("/cv", "Bản CV"),
              ("/search", "Search"), ("/track/queue", "Hàng chờ"),
              ("/track", "Quản lí"),
              ("/profile", "Hồ sơ"), ("/jobs/", "tin này"))


def duong_ve(tu: str, mac_dinh: str = "/cv") -> tuple:
    """(đường, nhãn) cho nút Back. `tu` = trang người dùng vừa rời.

    BACK PHẢI VỀ TRANG VỪA RỜI, không về một đích gõ cứng. Trang xem bản CV
    vào được từ tab CV và từ trang chi tiết tin; gõ cứng một đích thì một
    trong hai lối đi vào ngõ cụt — bấm Back xong lạc sang chỗ chưa từng đứng.

    Đường đi nằm trên URL (`?tu=`), không dựa vào lịch sử trình duyệt: mở
    thẳng một địa chỉ, hay mở tab mới, thì lịch sử trống mà nút vẫn phải đúng.

    CHỈ NHẬN ĐƯỜNG TRONG NHÀ. `tu` đi từ URL vào thẳng thuộc tính href, nên
    một giá trị như "//ke-xau" hay "https://…" biến nút Back thành cửa ra
    ngoài. Không bắt đầu bằng "/" hoặc bắt đầu bằng "//" thì vứt.
    """
    duong = (tu or "").strip()
    if not duong.startswith("/") or duong.startswith("//"):
        duong = mac_dinh
    goc = duong.split("?")[0]
    if goc.startswith("/jobs/") and goc.endswith("/cv"):
        return duong, "Bản CV"
    ten = next((t for d, t in _TEN_DUONG if goc.startswith(d)), "quay lại")
    return duong, ten


def page(title: str, body: str, active: str = "",
         flow: bool = True, bar: str = "", setup: str = "") -> str:
    """flow=True  trang cuộn như cũ — dành cho trang CHƯA chuyển sang widget
    flow=False trang không cuộn, nội dung là lưới widget tự cuộn bên trong
    """
    links = ""
    for href, label, mark in NAV:
        on = " on" if href == active else ""
        # title= để lúc gập còn biết icon nào là gì
        links += (f"<a class='navlink{on}' href='{esc(href)}'"
                  f" title='{esc(label)}'>"
                  f"<i>{ico(mark)}</i><span>{esc(label)}</span></a>")

    # Cài đặt: nút, KHÔNG phải link. /settings trả về mảnh HTML cho tấm phủ.
    # `data-appset` chứ KHÔNG dùng chung `data-settings` với nút ⚟ của khúc:
    # ⚟ chỉnh thứ MÀN HÌNH NÀY làm việc trên, còn đây là cài đặt CẢ APP. Một
    # nút không thể vừa là của khúc vừa là của app — nên khác thuộc tính,
    # khác cả khung (⚟ ra tấm bên phải, Cài đặt ra hộp giữa màn).
    settings = ("<div class=navend>"
                "<button class=navlink data-appset title='Cài đặt'>"
                f"<i>{ico('setting')}</i><span>Cài đặt</span></button></div>")

    # Thanh trạng thái ĐÁY APP — tin chung, không thuộc tab nào. Không nhận
    # dữ liệu từ view: live.js đổ vào từ dòng SSE đang có sẵn, nên không phải
    # luồn tham số qua cả chục hàm render và không bao giờ cũ.
    foot = ("<footer class=statusbar>"
            "<span class=sdot></span><b data-state>đang nối…</b>"
            "<span class=smsg data-lastmsg></span></footer>")
    # Thanh trên cùng LÀ thanh của khúc đang mở, không phải thanh của app.
    # Trang chưa có khúc thì KHÔNG có thanh: trạng thái chung đã nằm ở thanh
    # đáy rồi, vẽ thêm một dòng y hệt trên đầu chỉ là nói hai lần.
    top = ((f"<header class=topbar>{bar}</header>" if bar else "")
           # Tấm phủ cho menu Cài đặt. Rỗng cho tới khi bấm bánh răng —
           # nạp nội dung lúc đó, để mọi trang khác không phải mang theo dữ
           # liệu cài đặt mà chúng không dùng.
           + "<div class=sheet hidden data-sheet><div class=sheetbox></div></div>")

    # Đọc lựa chọn gập/mở NGAY trong <head>, trước khi vẽ. Để xuống cuối trang
    # thì mỗi lần chuyển tab thanh bên bung ra rồi mới co lại — nháy một cái.
    # Đây là tuỳ chọn hiển thị của riêng máy này, không phải dữ liệu chung,
    # nên để localStorage; không cần hỏi server, cũng không cần luồn tham số
    # qua cả chục hàm render.
    early = ("<script>try{if(localStorage.jobbotNav==='1')"
             "document.documentElement.classList.add('navmin')}catch(e){}</script>")

    return (
        "<!doctype html><html lang=en><head><meta charset=utf-8>"
        "<meta name=viewport content='width=device-width,initial-scale=1'>"
        f"<title>{esc(title)} · jobbot</title>"
        "<link rel=stylesheet href='/static/app.css'>"
        f"{early}</head><body"
        # Cờ BẮT ĐIỀN: live.js thấy thuộc tính này thì bật tấm phủ chu
        # trình dựng hồ sơ ngay khi trang dựng xong. Chỉ trang Home đặt
        # cờ — đặt ở mọi trang thì nó thành pop-up đuổi theo người dùng.
        + (f" data-setup='{esc(setup)}'" if setup else "") + ">"
        # THANH TIÊU ĐỀ — dải trên cùng cửa sổ. Cửa sổ app không có khung nên
        # traffic lights của macOS nằm đè lên trang: chỗ đó phải LUÔN trống,
        # cuộn nội dung lên tới đây là mất chữ. Có thanh thật thì mọi trang tự
        # được chừa — không phải mỗi trang tự nhớ chừa bao nhiêu, mà quên một
        # trang là trang đó hỏng (đúng như trang Home vừa rồi: chừa 16px
        # trong khi cần 38px).
        f"<header class=titlebar><b>{esc(title)}</b></header>"
        f"<aside class=side>"
        f"<div class=brandrow><div class=brand>{LOGO}jobbot</div>"
        f"<button class=navtoggle data-nav title='Gập thanh bên'>"
        f"{ico('gap')}</button></div>"
        f"<nav>{links}</nav>{settings}</aside>"
        f"<main class='{'flow' if flow else ''}'>{top}"
        f"<div class=inner>{body}</div></main>"
        f"{foot}"
        "<script src='/static/live.js'></script></body></html>"
    )


# ---------------------------------------------------------------- mảnh nhỏ

def h1(text: str, sub: str = "") -> str:
    return f"<h1>{esc(text)}</h1>" + (f"<p class=lead>{esc(sub)}</p>" if sub else "")


def badge(text: str, kind: str = "") -> str:
    return f"<span class='badge {kind}'>{esc(text)}</span>"


def score_bar(score: int) -> str:
    """Màu theo ngưỡng, không phải dải chuyển màu — đọc nhanh hơn."""
    kind = "hi" if score >= 75 else ("mid" if score >= 55 else "lo")
    return (f"<span class='score {kind}'><span class=track>"
            f"<span class=fill style='width:{score}%'></span></span><b>{score}</b></span>")


def stat(value: str, label: str, note: str = "", key: bool = False) -> str:
    return (f"<div class='stat{' key' if key else ''}'><b>{esc(value)}</b>"
            f"<span>{esc(label)}</span>"
            + (f"<i>{esc(note)}</i>" if note else "") + "</div>")


def card(inner: str, cls: str = "") -> str:
    return f"<div class='card {cls}'>{inner}</div>"


def empty(text: str) -> str:
    return f"<div class=empty-box>{esc(text)}</div>"


def section(title: str, inner: str, action: str = "") -> str:
    return f"<h2>{esc(title)}{action}</h2>{inner}"


# ---------------------------------------------------------------- ô (widget)

def widget(title: str, body: str, tools: str = "", span: int = 1,
           rows: int = 1, expand: bool = True, cls: str = "",
           at: tuple[int, int] | None = None) -> str:
    """Một ô trong lưới. Tự cuộn bên trong, không đẩy trang dài ra.

    span = chiếm mấy cột. expand=True thì có nút mở to ra toàn màn hình để
    xem kỹ hoặc chỉnh, bấm lại (hoặc Esc) thì thu về.
    """
    grow = (f"<button class=wexp data-expand title='Mở to (Esc để thu)'>"
            f"{ico('to')}</button>"
            if expand else "")
    # at=(cột, hàng) đặt ô vào ĐÚNG chỗ. Không có thì để trình duyệt tự xếp —
    # nhưng ô nào phải nằm cố định một cột (nhật ký ở cột cuối) thì tự xếp sẽ
    # trôi vào chỗ trống đầu tiên nó gặp.
    place = (f"grid-column:{at[0]} / span {span};grid-row:{at[1]} / span {rows}"
             if at else f"grid-column:span {span};grid-row:span {rows}")
    return (f"<section class='wid {cls}' data-widget style='{place}'>"
            f"<header class=whead><h3>{esc(title)}</h3>"
            f"<div class=wtools>{tools}{grow}</div></header>"
            f"<div class=wbody>{body}</div></section>")


def grid(*widgets: str, cols: int = 3,
         columns: str = "", rows: str = "") -> str:
    """Lưới ô. Mặc định chia đều; truyền columns/rows để chia theo ý.

    Chia đều là mặc định ĐÚNG cho phần lớn tab. Nhưng có tab mà mấy ô không
    ngang vai nhau — danh sách việc đáng chiếm gấp đôi ô lưới lọc, và dải
    nhật ký chỉ cần cao bằng ba dòng chứ không bằng một hàng đầy.
    """
    style = f"grid-template-columns:{columns or f'repeat({cols},1fr)'}"
    if rows:
        style += f";grid-template-rows:{rows}"
    return f"<div class=wgrid style='{style}'>" + "".join(widgets) + "</div>"


def journal_box(stream: str = "") -> str:
    """Khung nhật ký. live.js tự đổ dữ liệu vào — ở đây không vẽ sẵn gì cả."""
    return f"<div class=journal data-journal='{esc(stream)}'></div>"


def progress_box(stream: str = "") -> str:
    return (f"<div class=progress data-progress='{esc(stream)}'>"
            "<div class=pidle>đang nối…</div></div>")
