"""Test tab Home — tổng quan.  python3 tests/test_home.py

Trọng tâm KHÔNG phải "có vẽ ra hình không". Nó là: hình có NÓI THẬT không.

Một trang thống kê hỏng thì không im lặng, nó chỉ sai hướng — và người dùng
đi sửa nhầm chỗ mà không biết. Nên phần lớn bài ở đây canh đúng ba thứ:

    · ngày app CHƯA CHẠY phải khác ngày LÀM ĐƯỢC 0
    · mọi tỉ lệ phải kèm mẫu số và cỡ mẫu
    · chưa đủ dữ liệu thì NÓI RA, không vẽ một cái lưới trống
"""

import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

GOC = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(GOC / "src"))

# CHẠY LẺ CŨNG PHẢI ĐÚNG.
#
# run_all.py dựng một gốc dự án giả + khoá mạng cho mọi bài. Nhưng chạy lẻ
# một file (python3 tests/test_web.py) thì không có chốt đó, và mấy bài
# khẳng định "chưa nối bot" sẽ đỏ — đỏ vì máy này có cấu hình, không vì code
# sai. Tệ hơn: chạy lẻ có thể gửi tin thật về điện thoại người dùng.
#
# Đặt NGAY ĐÂY, trước mọi import jobbot, để không có lối vòng.
import os as _os, tempfile as _tf, pathlib as _pl
_os.environ.setdefault("JOBBOT_OFFLINE", "1")
if "JOBBOT_ROOT" not in _os.environ:
    _gia = _tf.mkdtemp(prefix="jobbot-test-")
    _pl.Path(_gia, "config").mkdir(parents=True, exist_ok=True)
    _os.environ["JOBBOT_ROOT"] = _gia

from jobbot.core import db
from jobbot.dashboard import tongquan as T
from jobbot.dashboard.views import bieudo as bd
from jobbot.dashboard.views import home
from jobbot.track import board

ok = fail = 0
def check(name, cond):
    global ok, fail
    if cond: ok += 1; print(f"  ok   {name}")
    else:    fail += 1; print(f"  FAIL {name}")


def truoc(n):
    return (datetime.now(timezone.utc) - timedelta(days=n)).isoformat()


def kho():
    """Kho thử: 1 đi tiếp · 1 họ từ chối · 1 im quá mốc · 1 còn trong cửa sổ."""
    c = db.connect(":memory:")
    board.add(c, "Kappa Lab", "Quant", applied_at=truoc(9),
              stage=board.INTERVIEW)
    board.add(c, "Maven", "Quant", applied_at=truoc(30), stage=board.REJECTED)
    board.add(c, "Im Lâu", "Quant", applied_at=truoc(40))
    board.add(c, "Vừa Nộp", "Quant", applied_at=truoc(3))
    return c


print("\n[PHỄU — hai đoạn, và chỗ nối phải nói thật]")
c = kho()
p = T.pheu(c)
check("bốn bước của đoạn TÌM", len(p["tim"]) == 4)
check("mỗi bước dẫn về tab của nó", all(b[2].startswith("/") for b in p["tim"]))
check("kho rỗng thì mọi bước bằng 0", all(b[1] == 0 for b in p["tim"]))
# Ngưỡng "đáng nộp" phải TRÙNG với nút Nộp bên Quản lí. Hai chỗ hai ngưỡng là
# có ngày Home bảo còn 130 tin đáng nộp mà bấm Nộp thì nó nói hết.
_nop = (GOC / "src/jobbot/dashboard/live.py").read_text(encoding="utf-8")
check("cùng một ngưỡng điểm với nút Nộp bên Quản lí",
      f"score >= {T.DIEM_DANG_NOP}" in _nop)

print("\n[KẾT QUẢ — mọi tỉ lệ phải kèm MẪU SỐ]")
k = T.ket_qua(c)
check("đếm đúng 4 lần nộp", k["tong"] == 4)
check("đi tiếp = phỏng vấn + nhận việc", k["di_tiep"] == 1)
# TRƯỢT gộp hai thứ, nhưng vẫn giữ riêng từng cái: "họ đã nói" và "ta suy ra"
# là hai sự thật khác nhau, gộp mà không tách được là mất phân biệt đó.
check("trượt = họ từ chối + coi như trượt", k["truot"] == 2)
check("và vẫn tách được từng loại", k["ho_noi"] == 1 and k["suy"] == 1)
check("còn lại là CHƯA BIẾT, không nhét vào trượt", k["cho"] == 1)
check("tỉ lệ trên TỔNG", k["pc_di"] == 25.0)
check("và tỉ lệ trên ĐÃ NGÃ NGŨ khác nó", k["pc_di_xong"] == round(100 / 3, 1))
check("kèm mốc im lặng đang đặt để giải thích con số",
      k["nguong_im"] == board.nguong(c))
_rong = T.ket_qua(db.connect(":memory:"))
check("chưa nộp gì thì tỉ lệ là None, KHÔNG phải 0%", _rong["pc_di"] is None)
check("và 0% không bao giờ bị in ra thay cho «chưa có số»",
      "0%" not in home._ket_qua(_rong))

_css = (GOC / "src/jobbot/dashboard/web/app.css").read_text(encoding="utf-8")
print("\n[NĂNG SUẤT — mỗi chuỗi TỰ GÁC lấy mình]")
# Đây là lỗi đã xảy ra thật: lấy chuỗi DÀI NHẤT làm cổng chung, nên biểu đồ
# "tin tìm được theo thứ" được vẽ trên 2 ngày dữ liệu và nói "thứ sáu gấp chín
# lần thứ bảy" — đúng phép tính, sai hoàn toàn về nghĩa.
c2 = db.connect(":memory:")
for i in range(60):                       # thư từ chối: 60 ngày, thừa sức gộp
    c2.execute("INSERT INTO message (msg_id, from_addr, subject, received_at,"
               " snippet, kind) VALUES (?,?,?,?,?,?)",
               (f"m{i}", "a@b.c", "s", truoc(i), "", "rejected"))
board.add(c2, "X", "R", applied_at=truoc(1))   # nộp: đúng 1 ngày
c2.commit()
n = T.nang_suat(c2)
check("chuỗi báo trượt đủ dài -> cho gộp theo thứ", n["viec"]["truot"]["du_thu"])
check("chuỗi nộp mới 1 ngày -> KHÔNG cho gộp theo thứ",
      not n["viec"]["nop"]["du_thu"])
check("cổng là của TỪNG chuỗi, không phải một số chung",
      n["viec"]["truot"]["du_thu"] != n["viec"]["nop"]["du_thu"])

print("\n[BỐN DẢI = ĐÚNG BỐN SỐ TRÊN THANH MASTER]")
# Thanh trên nói "hôm nay được bao nhiêu", dải dưới nói "mấy hôm trước thì
# sao". Cùng một câu hỏi, hai độ dài — nên phải cùng một bộ số, không phải
# hai bộ khác nhau đặt cạnh nhau.
_hn = T.hom_nay(c2)
check("bốn dải", len(n["viec"]) == 4)
check("và trùng đúng bốn khoá của thanh «hôm nay»",
      set(n["viec"]) == set(_hn) - {"ngay"})
check("«thư về» đã bỏ — 95% là nhiễu", "thu" not in n["viec"])
# MÀU MANG NGHĨA. Cột cao của thư TỪ CHỐI mà tô xanh thì đọc thành "hôm nay
# được việc", tức là ngược hẳn sự thật.
check("báo trượt tô màu XẤU", n["viec"]["truot"]["mau"] == "xau")
check("được gọi tiếp tô màu TỐT", n["viec"]["tiep"]["mau"] == "tot")
check("và CSS thật sự tô chúng khác nhau",
      ".spark.xau rect{fill:var(--bad)" in _css and ".spark.tot rect{" in _css)
# Hai dải kết cục dựng từ THƯ, nên "app chạy từ bao giờ" là của HỘP THƯ, không
# phải của lá thư từ chối đầu tiên. Không có luật này thì mọi ngày trước lời
# mời đầu tiên bị ghi là "app chưa chạy" — trong khi hộp thư chạy suốt, và
# một ngày KHÔNG AI GỌI là số 0 có thật.
check("ngày chưa ai gọi là số 0 THẬT, không phải «app chưa chạy»",
      n["viec"]["tiep"]["truoc"] == 0)
check("mốc bắt đầu của nó là mốc HỘP THƯ",
      n["viec"]["tiep"]["tu"] == n["viec"]["truot"]["tu"])
check("ngưỡng đủ-để-gộp có nói ra thành số", n["can_thu"] == T.DU_NGAY)
# Chuỗi trả về THƯA: ngày không có gì thì KHÔNG có khoá. Điền 0 cho đủ là
# trộn "làm được 0" với "app chưa chạy" ngay từ tầng số liệu.
_ch = T._chuoi(c2, "application", "applied_at", 30)
check("chuỗi ngày trả về THƯA, không điền 0 cho đủ", len(_ch) == 1)
check("và nói rõ mấy ngày trong cửa sổ app chưa chạy",
      n["viec"]["nop"]["truoc"] > 0)

print("\n[BIỂU ĐỒ — «làm được 0» KHÁC «app chưa chạy»]")
h = bd.cot_ngay([("2026-09-01", 5), ("2026-09-02", 0)], 5, truoc=3)
check("ngày app chưa chạy có lớp riêng", h.count("class=ngoai") == 3)
check("ngày làm được 0 có lớp KHÁC", "class=khong" in h)
check("hai lớp đó không trùng tên", "class=ngoai" in h and "khong" in h)
check("và CSS thật sự tô chúng khác nhau",
      ".spark rect.ngoai{" in _css and ".spark rect.khong{" in _css)
check("cột nào cũng có nhãn chữ để rê chuột", h.count("<title>") == 5)
check("chuỗi rỗng thì không vẽ khung trống", bd.cot_ngay([], 0) == "")
# Chưa đủ dữ liệu thì NÓI RA. Một biểu đồ trống trông y hệt một biểu đồ
# "năng suất bằng 0", và người dùng sẽ tin cái thứ hai.
_cd = bd.chua_du(2, 21)
check("chưa đủ thì nói thẳng", "Chưa đủ để nói" in _cd)
check("và nói rõ đang có mấy, cần mấy", ">2<" in _cd and ">21<" in _cd)
check("tỉ lệ luôn đi kèm mẫu số",
      "1/37" in bd.ti_le(2.7, "1/37 lần nộp", "đi tiếp"))
check("chưa có số thì in «—», không in 0%", "—" in bd.ti_le(None, "x", "y"))
check("khúc bằng 0 thì KHÔNG vẽ, cũng không chú thích",
      "qtu" not in bd.thanh_chia([("a", 3, "qdi"), ("b", 0, "qtu")], 3))

print("\n[CHẨN ĐOÁN — nói rõ CHẮC tới đâu]")
ds = T.chan_doan(c)
check("mỗi dấu hiệu khai độ chắc", all(x["muc"] in T.MUC_HET for x in ds))
check("mỗi dấu hiệu khai đo trên bao nhiêu mẫu",
      all(x.get("tren") for x in ds))
check("và dẫn đi đâu để sửa",
      all(x.get("di", "").startswith("/") and x.get("nut") for x in ds))

print("\n[TRANG HOME — vừa MỘT khung, không ô nào cuộn]")
d = T.tat_ca(c)
_h = home.render({"gate_open": True}, so=d,
                 stage={"state": "x", "cho_ban": 3, "label": "Quét việc"})
check("có thanh khúc như mọi tab", "class=deckpill" in _h)
check("có nhật ký", "data-journal" in _h)
for _o in ("Kết quả", "Năng suất", "Chẩn đoán", "Phễu"):
    check(f"có ô «{_o}»", _o in _h)
# HAI CÂU HỎI KHÁC NHAU, và bài test cũ gộp chúng làm một y như code:
#   data-journal  = ô nhật ký HIỆN dòng của luồng nào ("" = mọi luồng)
#   data-reload   = khúc nào chạy xong thì VẼ LẠI trang ("*" = mọi khúc)
# Bài cũ khẳng định `"mine && m.stream === mine" in _js` rồi gọi đó là "hiểu
# luồng rỗng là mọi luồng" — trong khi JavaScript đọc chuỗi rỗng là SAI, nên
# nhánh đó không bao giờ chạy và Home KHÔNG BAO GIỜ tự vẽ lại. Bài test canh
# đúng dòng chữ gây ra lỗi, và gật đầu với nó.
check("nhật ký nghe MỌI luồng", "data-journal=''" in _h)
check("và trang tự vẽ lại khi BẤT KỲ khúc nào xong", "data-reload='*'" in _h)
_js = (GOC / "src/jobbot/dashboard/web/live.js").read_text(encoding="utf-8")
check("live.js đọc cờ của trang, không suy từ ô nhật ký",
      "dataset.reload" in _js and "mine && m.stream === mine" not in _js)
check("và «*» thật sự nghĩa là mọi khúc", "=== '*'" in _js)
# Ô Home KHÔNG được là khung cuộn: `.wbody{overflow:auto}` làm min-content của
# ô bằng 0, nên lưới nén ô xuống bao nhiêu cũng được và ruột đành cuộn.
check("bốn ô khai là ô VỪA RUỘT, không phải khung cuộn", _h.count("wid vua") == 4)
check("và CSS bỏ khung cuộn cho chúng", ".wid.vua > .wbody{overflow:visible" in _css)
check("hàng nội dung có sàn min-content, không bị nén",
      "minmax(min-content,auto)" in _h)
check("nhật ký là ô DUY NHẤT ăn phần dôi ra", "minmax(130px,1fr)" in _h)

print("\n[GỌN LÚC LIẾC, ĐỦ LÚC SOI]")
check("chi tiết giấu sau nút ⤢", "class=chitiet" in _h)
check("và ô nào cũng có nút ⤢ để mở", _h.count("data-expand") >= 4)
# ĐỘ ĐẶC HIỆU PHẢI THẮNG: `.chitiet{display:none}` và `.cdrow{display:flex}`
# cùng 0,1,0 — cái nào khai sau thì thắng, và `.cdrow` nằm dưới ~200 dòng.
# Hậu quả: thẻ gắn .chitiet vẫn hiện, hỏng CÂM.
check("lớp ẩn không thua cascade của .cdrow", ".cdrow.chitiet{display:none}" in _css)
check("mở to thì nó hiện lại", ".wid.big .cdrow.chitiet{display:flex}" in _css)
_nhieu = [dict(muc="chac", ma=f"m{i}", so=f"{i}", ten=f"dấu {i}", y="y",
               tren="t", di="/cv", nut="Xem") for i in range(5)]
_cd5 = home._chan_doan(_nhieu)
check("lúc gọn chỉ bày 3 dấu hiệu", _cd5.count("cdrow chac'") == 3)
check("2 cái còn lại gắn lớp ẩn", _cd5.count("chac chitiet") == 2)
# Cắt mà không báo thì người dùng tin là hết.
check("và NÓI RÕ còn mấy cái nữa", "còn <b>2</b> dấu hiệu nữa" in _cd5)
check("đúng 3 cái thì không bịa ra dòng «còn 0»",
      "dấu hiệu nữa" not in home._chan_doan(_nhieu[:3]))

print("\n[THANH MASTER = BẢN TIN CỦA HÔM NAY]")
from jobbot.core import prefs
c3 = db.connect(":memory:")
board.add(c3, "Hôm Nay", "R", applied_at=truoc(0))
board.add(c3, "Hôm Qua", "R", applied_at=truoc(1))
for i, (k, d) in enumerate((("interview", 0), ("rejected", 0), ("rejected", 5))):
    c3.execute("INSERT INTO message (msg_id, from_addr, subject, received_at,"
               " snippet, kind) VALUES (?,?,?,?,?,?)",
               (f"h{i}", "a@b.c", "s", truoc(d), "", k))
c3.commit()
hn = T.hom_nay(c3)
check("đếm đơn nộp HÔM NAY, không phải tổng", hn["nop"] == 1)
check("đếm lời mời HÔM NAY", hn["tiep"] == 1)
check("đếm báo trượt HÔM NAY, bỏ lá 5 ngày trước", hn["truot"] == 1)
_trang = home.render({"gate_open": True}, so=T.tat_ca(c3),
                     stage={"phien": "phiên đang TẮT",
                            "nhan_phien": "Start session"})
# CHỈ CẮT RA CÁI THANH. Dò cả trang thì "đã nộp" ở ô Phễu cũng dính, và bài
# test đỏ vì một lý do chẳng liên quan gì tới thứ nó mang tên.
_bar = _trang[_trang.index("<div class=deckpill>"):]
_bar = _bar[:_bar.index("</div></div>")]
for _n in ("tin tìm được", "đơn đã nộp", "được gọi tiếp", "báo trượt"):
    check(f"thanh có số «{_n}»", f">{_n}<" in _bar)
# Tổng kết đã nằm ở bốn ô bên dưới. Để chúng trên thanh nữa thì thanh nói một
# thứ hôm nào nhìn cũng thế, và nó thôi trả lời được câu «hôm nay có gì mới».
# Nhãn CŨ là "<b>37</b>đã nộp"; nhãn MỚI là "đơn đã nộp" (hôm nay). Dò
# "đã nộp<" thì bắt cả hai — phải neo vào `</b>` mới tách được.
for _cu in ("đáng nộp chưa nộp", "</b>đã nộp<", "chờ bạn quyết", "Kho việc"):
    check(f"thanh KHÔNG còn «{_cu}»", _cu not in _bar)
check("nút đổi tên thành Start session", ">Start session<" in _bar)
check("và bấm vào là chạy PHIÊN, không phải một khúc",
      "data-post='/api/session/start'" in _bar)
check("nút Dừng cũng tắt cả phiên", "data-post='/api/session/stop'" in _bar)
check("có nút ⚟ của phiên", "data-settings='/adjust/home'" in _bar)

print("\n[PHIÊN — một vòng, ba khúc, chạy tuần tự]")
from jobbot import phien
check("ba khúc, đúng thứ tự dây chuyền",
      phien.dang_bat(c3) == ["search", "cv", "track"])
prefs.set_flag(c3, prefs.PHIEN_CV, False)
check("tắt một khúc thì phiên bỏ đúng khúc đó",
      phien.dang_bat(c3) == ["search", "track"])
# Thứ tự lấy từ prefs.PHIEN, không gõ lại trong phien.py — gõ lại là hai
# nguồn cho một sự thật, và có ngày tấm ⚟ xếp một đằng, phiên chạy một nẻo.
check("thứ tự chạy lấy từ CÙNG bảng với tấm ⚟",
      [v[0] for v in prefs.PHIEN.values()] == ["search", "cv", "track"])
for k in prefs.PHIEN:
    prefs.set_flag(c3, k, False)
_ra = phien.chay(c3)
check("tắt cả ba thì phiên NÓI RA, không im lặng chạy không", _ra["tat"])
check("và không khúc nào chạy", _ra["xong"] == [])
_adj = home.adjust({k: False for k in prefs.PHIEN})
check("tấm ⚟ cảnh báo khi cả ba đang tắt", "Cả ba đang TẮT" in _adj)
check("và bày đủ ba công tắc", _adj.count("/api/home/num") == 3)
for _t in ("Search", "Make CV", "Manage mail"):
    check(f"có công tắc «{_t}»", f">{_t}<" in _adj)
_adj_on = home.adjust({k: True for k in prefs.PHIEN})
check("đang bật thì nút sáng, không chỉ khác chữ", "swbtn'" in _adj_on)
check("nói rõ thứ tự cố định và VÌ SAO", "Dựng CV đọc kho tin" in _adj_on)
c3.close()

print("\n[BÁO VỀ ĐIỆN THOẠI — báo ÍT thôi, và không báo lại cái cũ]")
from jobbot import bao as _bao
from jobbot.core import tele as _tele, prefs as _pf2
c4 = db.connect(":memory:")
_ap = board.add(c4, "Kappa Lab", "Quant", applied_at=truoc(9))
for i, k in enumerate(("interview", "rejected", "other")):
    c4.execute("INSERT INTO message (msg_id, from_addr, subject, received_at,"
               " snippet, kind, application_id) VALUES (?,?,?,?,?,?,?)",
               (f"b{i}", "a@b.c", f"thư {k}", truoc(0), "", k, _ap))
c4.commit()
# CHỈ THƯ ĐI TIẾP mới được nhắn. Nhắn cả thư từ chối và thư quảng cáo thì
# người dùng tắt thông báo sau đúng hai ngày, và mất luôn cái đáng giá.
_moi = _bao._thu_moi(c4)
check("chỉ lấy thư ĐI TIẾP để nhắn", [m["kind"] for m in _moi] == ["interview"])
check("và kèm tên công ty, không phải mỗi tiêu đề",
      _moi[0]["cong_ty"] == "Kappa Lab")
# MỐC ĐÃ BÁO: không có nó thì mỗi lượt quét lại nhắn đúng lá cũ.
_pf2.put(c4, _pf2.BAO_MOC, str(_moi[0]["id"]))
check("đã nhắn rồi thì KHÔNG nhắn lại", _bao._thu_moi(c4) == [])
# Chưa nối bot thì không hàm nào được gửi đi đâu cả.
check("chưa nối bot -> không báo gì", _bao.di_tiep(c4) == 0)
check("và cũng không báo phiên hỏng", not _bao.phien_hong(c4, ["search"]))
check("dù có bật công tắc",
      _pf2.flag(c4, _pf2.BAO_TIEP) and not _bao.bat(c4, _pf2.BAO_TIEP))
# Bản tin cuối ngày gửi ĐÚNG MỘT LẦN: vòng nền chạy mỗi 30 giây, không có
# mốc ngày thì qua giờ hẹn nó nhắn liên tục tới nửa đêm.
check("bản tin ngày có mốc chống nhắn lặp",
      _pf2.BAO_NGAY_CUOI in _pf2.DEFAULTS)
# Bốn loại, không hơn — mỗi loại phải trả lời được "biết rồi thì làm gì khác".
check("đúng bốn loại báo", len(_pf2.BAO) == 4)
check("mỗi loại có tên và lý do cho người dùng đọc",
      all(len(v) == 2 and v[0] and v[1] for v in _pf2.BAO.values()))
check("mặc định chỉ bật hai loại ĐÁNG NHẤT",
      [k for k in _pf2.BAO if _pf2.DEFAULTS[k] == "1"]
      == [_pf2.BAO_TIEP, _pf2.BAO_HONG])

print("\n[LỆNH TỪ XA — chốt quyền TRƯỚC, rồi mới đọc nội dung]")
check("lệnh không rõ thì chỉ đường, không im",
      "giupdo" in _bao.tra_loi(c4, "xyz", ""))
check("/giupdo nói rõ KHÔNG có lệnh nộp đơn",
      "không có lệnh nộp đơn" in _bao.GIUP.lower())
check("/nhan thiếu số thì nói thiếu gì", "Thiếu số hiệu" in _bao.tra_loi(c4, "nhan", ""))
check("/nhan số lạ thì không nổ, chỉ báo không thấy",
      "Không thấy" in _bao.tra_loi(c4, "nhan", "99999"))
_tt = _bao.tra_loi(c4, "trangthai", "")
for _so in ("tìm được", "nộp", "gọi tiếp", "trượt", "trạm trực"):
    check(f"/trangthai có «{_so}»", _so in _tt)
c4.close()

print("\n[KHÔNG BỊA — kho rỗng vẫn phải vẽ được]")
_r = db.connect(":memory:")
_hr = home.render({"gate_open": True}, so=T.tat_ca(_r), stage={})
check("kho rỗng không làm trang nổ", "Tổng quan" in _hr)
check("và nói thẳng là chưa có gì để đánh giá", "chưa nộp chỗ nào" in _hr)
check("không bịa ra tỉ lệ nào", "%" not in re.sub(r"width:[\d.]+%", "", _hr))
c.close(); c2.close(); _r.close()

print(f"\n{ok} ok, {fail} fail")
sys.exit(1 if fail else 0)
