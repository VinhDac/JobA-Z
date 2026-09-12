"""Cài đặt — MENU, không phải một tab.

Trả về một MẢNH HTML, không phải cả trang: live.js nạp nó vào tấm phủ khi bấm
nút bánh răng. Làm thành tab thì nó chiếm một chỗ trong thanh bên ngang hàng
với Search và Projects — trong khi nó không phải một việc, nó là mấy cái công
tắc mở ra chỉnh rồi đóng lại.

Chỉ hai núm. Thước để một thứ được vào đây:

    1. có nhiều hơn một câu trả lời đúng
    2. NGƯỜI DÙNG là người nên chọn
    3. đổi nó thì máy chạy khác đi

Thiếu một trong ba thì nó là thứ khác: một câu trả lời đúng -> đó là LỖI, sửa
code; máy tự báo về mình -> đó là SỐ ĐỌC VỀ; không đổi được cố ý -> đó là
RANH GIỚI AN TOÀN. Trang cũ có 18 dòng mà chỉ 2 dòng qua được thước này.

Hai núm này đều KHÔNG đụng tới phán quyết — đổi chúng chỉ đổi cách chạy, có
tác dụng từ lần quét sau. Thứ đổi phán quyết nằm ở ô Lưới lọc bên tab Search,
và ở đó nút Áp dụng nói rõ sẽ phán lại bao nhiêu tin.

Ba TAB. Trước đây một cột dài 782px trong hộp cao 660px — phần "Làm lại từ
đầu" nằm dưới nếp gấp, phải cuộn mới thấy, mà không ai biết là có thể cuộn.
Chia tab thì mỗi tab vừa một màn, và hộp co lại đúng một hộp thoại nổi thay vì
một cột chạy gần hết chiều cao cửa sổ.

Chia theo VIỆC, không theo độ dài: thứ đổi được / thứ chỉ đọc / thứ phá huỷ.
Để việc phá huỷ chung màn với nhịp quét là sớm muộn cũng có người bấm nhầm.

CHỈ VẼ.
"""

from __future__ import annotations

from html import escape as esc

def _num(name: str, value: int, low: int, high: int, unit: str) -> str:
    return (f"<input type=number name={name} value='{value}'"
            f" min={low} max={high} step=1><span class=unit>{esc(unit)}</span>")


PACE_TEXT = [
    ("nhe", "Nhẹ nhàng", "4-7 giây mỗi tin · ít bị bóp nhất"),
    ("thuong", "Thường", "2,5-5 giây · mặc định"),
    ("nhanh", "Nhanh", "1,2-2,5 giây · gọi dày gấp đôi, dễ bị bóp hơn"),
]


def _nhip(pace: str) -> str:
    """Núm hiệu năng THẬT của vòng quét — và nó là núm ĐÁNH ĐỔI.

    Vì sao không phải "chạy mấy tab song song": N tab với nhịp P giống hệt 1
    tab với nhịp P/N — cùng số lượt gọi mỗi giây, cùng rủi ro bị bóp. Song
    song chỉ là cách viết phức tạp hơn của một con số nhỏ hơn, cộng thêm N cửa
    sổ Chrome ăn RAM và N chỗ có thể chết nửa chừng. Nên bày ra đúng cái thật
    sự đổi: nhịp.

    Nói thẳng cái ĐÁNH ĐỔI ngay trên màn hình. Một núm ghi "Nhanh" mà không
    nói nhanh bằng giá gì là núm mời người ta bấm rồi lãnh hậu quả.
    """
    nut = "".join(
        f"<label class=prow><input type=radio name=pace value='{esc(v)}'"
        f"{' checked' if v == pace else ''}>"
        f"<b>{esc(ten)}</b><span class=muted>{esc(ghi)}</span></label>"
        for v, ten, ghi in PACE_TEXT)
    return (f"<div class=sthead>Nhịp gọi LinkedIn</div>{nut}"
            "<div class=safe>Board công ty không đụng tới nhịp này — chúng là "
            "API công khai, mỗi board một lượt gọi. Nhịp chỉ áp cho LinkedIn, "
            "bên duy nhất app đang ở nhờ.</div>")


def _nguon(sources: list[dict], board_on: bool) -> str:
    """Bật/tắt từng ATS. BA cái, không phải 34 cái.

    "API" ở đây là ba nhà cung cấp ATS, không phải 34 board công ty. Giới
    thiệu từng công ty thì vô nghĩa ("Jane Street — một quỹ"), còn ba ATS thì
    khác nhau thật: cách trả dữ liệu khác, loại công ty khác, tỉ lệ dùng được
    khác hẳn.

    Giới thiệu bằng SỐ THẬT của chính kho này, không bằng tính từ. "Hiện đại",
    "phổ biến" thì không ai chọn được gì; "600 tin, giữ 6" thì chọn được ngay.
    """
    hang = ""
    for n in sources:
        hang += (
            f"<label class='prow srcline{'' if n['on'] else ' off'}'>"
            f"<input type=checkbox name=ats value='{esc(n['id'])}'"
            f"{' checked' if n['on'] else ''}>"
            f"<b>{esc(n['ten'])}</b>"
            f"<span class=muted>{esc(n['note'])}</span>"
            f"<span class=srcnum>"
            + (f"{n['boards']} board · " if n["boards"] else "")
            + f"{n['tin']:,} tin về · giữ {n['giu']:,}"
            + (f" · {n['remote']:,} khai remote" if n["remote"] else "")
            + "</span></label>")
    # Công tắc TO đang tắt thì mấy công tắc nhỏ chưa có tác dụng. Không nói ra
    # thì người dùng bật/tắt ở đây rồi ngồi đợi một thứ không bao giờ tới.
    canh = ("" if board_on else
            "<div class=safe><b>Board đang TẮT</b> ở tấm Điều chỉnh · Search — "
            "mấy công tắc dưới đây chưa có tác dụng cho tới khi bật lại.</div>")
    return (
        "<form class=setform method=post action='/settings'>"
        "<input type=hidden name=phan value=nguon>"
        + canh +
        "<div class=sthead>Nguồn nhanh</div>"
        "<div class=safe>Ba nhà cung cấp ATS, cộng thư báo việc LinkedIn gửi "
        "vào hộp thư. Bỏ tick là lần quét sau không gọi tới nguồn đó nữa — "
        "tin cũ vẫn nằm nguyên trong kho.</div>"
        + hang +
        "<div class=setfoot>"
        "<button class='mbtn apply' type=submit>Lưu</button>"
        "<span class=applynote>có tác dụng từ lần quét sau · "
        "không xoá tin đã lấy về</span></div>"
        "</form>")


def _gmail(ready: bool, address: str, days: int, ho_so: str = "") -> str:
    """Nối hộp thư + số ngày đọc lại. KHÔNG bao giờ vẽ mật khẩu ra.

    Trước đây ô này nằm trên đầu tab Quản lí — trang Vin mở hàng ngày. Nó là
    CẤU HÌNH: nối một lần rồi thôi, nên chỗ của nó là Cài đặt. Cái ở lại bên
    Quản lí là VIỆC: nút Quét thư.

    Kể cả ở đây cũng chỉ vẽ ĐỊA CHỈ và TRẠNG THÁI. Một ô password có sẵn giá
    trị là mật khẩu nằm trong HTML — đọc được bằng View Source và bị trình
    duyệt lưu vào bộ nhớ đệm. Giá trị thật nằm trong config.toml (chmod 600,
    đã gitignore).
    """
    ngay = (
        "<form class=setform method=post action='/settings'>"
        "<input type=hidden name=phan value=gmail>"
        "<div class=sthead>Đọc lại bao nhiêu ngày thư</div>"
        "<label class=srow><span>Mỗi lượt quét đọc lại</span>"
        + _num("mail_days", days, 1, 365, "ngày") + "</label>"
        "<div class=safe>Thư trả lời cho đơn nộp tháng trước vẫn cần bắt được, "
        "nên 30 ngày là mặc định. Đặt ngắn thì quét nhanh hơn nhưng dễ bỏ sót "
        "thư về muộn.</div>"
        "<div class=setfoot>"
        "<button class='mbtn apply' type=submit>Lưu</button>"
        "<span class=applynote>có tác dụng từ lần quét thư sau</span></div>"
        "</form>")

    if ready:
        # "đã lưu", KHÔNG phải "đã nối": chỗ này chỉ biết config CÓ chuỗi,
        # không biết chuỗi đó còn đăng nhập được không. App password bị thu
        # hồi bên Google thì dòng này vẫn xanh, và Vin tin là hộp thư đang
        # chạy.
        # KHÔNG có nút xoá ở đây. Nối một lần rồi thôi; đường xoá duy nhất
        # là "Làm lại từ đầu" bên tab kia. Đổi mật khẩu thì dán đè lên.
        noi = (f"<div class=safe>Hộp thư <b>{esc(address)}</b> đã lưu — sang "
               f"tab Quản lí bấm Quét thư để kiểm xem còn đăng nhập được "
               f"không.<br>Nối một lần là xong: mật khẩu chỉ mất khi bạn bấm "
               f"<b>Làm lại từ đầu</b>. Muốn đổi thì dán mật khẩu mới đè lên."
               f"</div>"
               f"<form class=boxform data-post='/api/mail/setup'>"
               f"<input name=address type=email value='{esc(address)}'"
               f" placeholder='địa chỉ hộp thư việc làm' required>"
               "<input name=password type=password autocomplete=off"
               " placeholder='dán app password mới để đổi' required>"
               "<button class='mbtn apply' type=submit>Đổi</button>"
               "<span class=formnote></span></form>")
    else:
        noi = (
            "<form class=boxform data-post='/api/mail/setup'>"
            f"<input name=address type=email value='{esc(address)}'"
            f" placeholder='địa chỉ hộp thư việc làm' required>"
            "<input name=password type=password autocomplete=off"
            " placeholder='app password 16 ký tự' required>"
            "<button class='mbtn apply' type=submit>Nối</button>"
            "<div class=boxwhy>Lấy ở <code>myaccount.google.com/apppasswords</code>"
            " (bật xác minh 2 bước trước). KHÔNG phải mật khẩu tài khoản —"
            " Gmail đã ngắt IMAP bằng mật khẩu tài khoản từ 2022. App password"
            " lưu vào <code>config/config.toml</code>, chmod 600, đã gitignore."
            "<span class=formnote></span></div></form>")

    # Nói TRƯỚC là phải khớp, đừng để bấm Nối xong mới báo hỏng. Và điền
    # sẵn địa chỉ hồ sơ: gõ tay một địa chỉ đã biết là mời gõ sai.
    khop = (f"<div class=safe>Phải đúng địa chỉ khai trong hồ sơ — "
            f"<b>{esc(ho_so)}</b>. Đó là địa chỉ in lên CV và điền vào form "
            f"nộp, tức là chỗ nhà tuyển dụng bấm Trả lời; nối hộp thư khác "
            f"thì app quét một nơi mà thư về một nơi.</div>"
            if ho_so else
            "<div class=safe>Hồ sơ chưa khai địa chỉ liên hệ — điền ở tab "
            "Profile trước, rồi nối đúng hộp thư đó.</div>")
    return (f"<div class=sthead>Hộp thư việc làm</div>"
            f"<div class=safe>Thư về là thứ tự cập nhật bảng Quản lí — trả "
            f"lời, hẹn phỏng vấn, từ chối.</div>{khop}{noi}{ngay}")


def render(*, every: int, hours: tuple[int, int],
           status: list[tuple[str, str]], pace: str = "thuong",
           sources: list[dict] | None = None, board_on: bool = True,
           mail_ready: bool = False, mail_address: str = "", mail_days: int = 30,
           mail_profile: str = "",
           reset_rows: int = 0, reset_files: int = 0, reset_mb: float = 0.0,
           reset_backup_dir: str = "") -> str:
    rows = "".join(f"<div class=strow><span>{esc(k)}</span><b>{esc(v)}</b></div>"
                   for k, v in status)

    chay = (
        "<form class=setform method=post action='/settings'>"
        "<input type=hidden name=phan value=chay>"
        "<label class=srow><span>Quét lại mỗi</span>"
        + _num("every", every, 5, 1440, "phút") + "</label>"
        "<label class=srow><span>Chrome chạy từ</span>"
        + _num("from", hours[0], 0, 23, "giờ") + "</label>"
        "<label class=srow><span>… đến</span>"
        + _num("to", hours[1], 1, 24, "giờ") + "</label>"
        + _nhip(pace) +
        "<div class=setfoot>"
        "<button class='mbtn apply' type=submit>Lưu</button>"
        "<span class=applynote>có tác dụng từ lần quét sau · "
        "không đụng tới điểm hay bộ lọc</span></div>"
        "</form>")

    # Số máy tự báo về mình — KHÔNG phải cài đặt, nên tách sang tab riêng và
    # nói rõ là chỉ để xem. Ranh giới an toàn ở cùng đây vì nó cũng không đổi
    # được; chỉ giữ những câu CÓ TEST đỡ lưng (xem tests/test_browser.py) —
    # lời hứa không ai kiểm thì mục dần mà không biết.
    tinh_trang = (
        f"<div class=stlist>{rows}</div>"
        "<div class=sthead>Ranh giới — không đổi được</div>"
        "<div class=safe>Chrome chạy bằng profile riêng, không đăng nhập tài "
        "khoản nào, chỉ đọc trang tuyển dụng công khai. Cookie chỉ bấm Từ chối. "
        "Bị chặn thì dừng và ghi nhật ký, không cãi lại.</div>")

    tab = [("chay", "Chạy", chay),
           ("nguon", "Nguồn", _nguon(sources or [], board_on)),
           ("gmail", "Gmail",
            _gmail(mail_ready, mail_address or mail_profile, mail_days,
                   mail_profile)),
           ("xem", "Tình trạng", tinh_trang),
           ("lam-lai", "Làm lại",
            _lam_lai(reset_rows, reset_files, reset_mb, reset_backup_dir))]

    chips = "".join(
        f"<button class='stab{" on" if n == 0 else ""}' data-stab='{tid}'>"
        f"{esc(ten)}</button>" for n, (tid, ten, _) in enumerate(tab))
    panes = "".join(
        f"<div class='stpane{" on" if n == 0 else ""}' data-pane='{tid}'>{noi}</div>"
        for n, (tid, _, noi) in enumerate(tab))

    return (f"<div class=sheethead>Cài đặt</div>"
            f"<div class=stabs>{chips}</div>{panes}")


def _lam_lai(rows: int, files: int, mb: float, backup_dir: str) -> str:
    """Nút đưa app về trạng thái ban đầu.

    Hai chốt, cả hai đều do từng làm hỏng thật mà có:
      - phải gõ đúng chữ XOA rồi mới bấm được (server cũng kiểm lại, không
        tin mỗi phía trình duyệt);
      - nói TRƯỚC sẽ mất bao nhiêu, và nói trước sao lưu sẽ nằm ở đâu.
    """
    co = (f"{rows:,} dòng dữ liệu · {files} tệp · ~{mb} MB"
          if rows or files else "hiện đang trống")
    return (
        f"<div class=safe>Xoá sạch hồ sơ, tin đã quét, CV đã dựng, đơn đã "
        f"theo dõi, hộp thư đã nối và cả profile Chrome — đưa app về đúng lúc "
        f"mới cài. <b>Sẽ mất: {esc(co)}.</b><br>"
        f"Trước khi xoá, app tự gói tất cả vào một tệp .tar.gz ở "
        f"<code>{esc(backup_dir)}</code>. Gói hỏng thì KHÔNG xoá gì.</div>"
        "<div class=dangerrow>"
        "<input class=search id=resetword placeholder='gõ XOA để mở khoá' "
        "autocomplete=off spellcheck=false>"
        "<button class='mbtn kill' data-post='/api/reset' data-arg=''"
        " data-needword=resetword disabled>Xoá hết, làm lại</button>"
        "</div>")
