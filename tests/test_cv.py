"""Test bước 3 — dựng CV theo từng JD.  python3 tests/test_cv.py"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from jobbot.cv import rules
from jobbot.cv.blocks import parse, sentences
from jobbot.cv.build import build

ok = fail = 0
def check(name, cond):
    global ok, fail
    if cond: ok += 1; print(f"  ok   {name}")
    else:    fail += 1; print(f"  FAIL {name}")

CV = """DAC VINH NGUYEN
London, UK · +44 7000 000000 · me@example.com
Eligible for UK Graduate visa — no employer sponsorship required.
I want to work on interesting problems.
EXPERIENCE
Founder / Quantitative Developer — Trading Startup Jan 2026 – Present
Self-funded, across 17 instruments and five years of data. I designed and built two
systems in Python: signals, validation and risk. I was optimising for peak profit in the
most recent window — which rewards luck. A random train/test split leaks, because
adjacent dates are correlated. Live drawdown ran roughly 30% deeper than the model
predicted. The mistake was mine.
Research Consultant — WorldQuant Jan 2025 – Sep 2025
Generated systematic alpha signals in Python, scored on Sharpe ratio and drawdown.
I trained deep learning models in PyTorch on five years of tick data.
I built portfolio construction on the efficient frontier with explicit risk limits.
I wrote backtesting and walk-forward validation harnesses in pandas and NumPy.
Profit on its own means nothing: an edge can be faked.
SELECTED PROJECTS
Quant Trading Studio — the whole pipeline you can run: backtesting and risk budgeting.
EDUCATION
MSc Computational Finance — Royal Holloway 2025 – 2026
Deep Learning 83 · Data Analysis 83
Certifications — CFA Level I, top 10% of global candidates
TECHNICAL SKILLS
Programming — Python (pandas, NumPy, PyTorch), C++, SQL.
Compute — a GPU is fast at many simple operations at once.
Method — I direct Claude Code and Copilot rather than prompt them.
"""

PROFILE = {"cv_text": CV, "full_name": "Ada Grace Lovelace", "email": "me@example.com",
           "location": "London, UK", "skills_strong": "Python, pandas, PyTorch, C++, SQL",
           "education": "MSc Computational Finance — Royal Holloway 2025-2026",
           "certifications": "CFA Level I, top 10% of global candidates"}

print("\n[tách khối]")
bs = parse(CV)
kinds = [b.kind for b in bs]
check("nhận ra đủ loại khối", {"header", "experience", "project", "education", "skill"} <= set(kinds))
exp = [b for b in bs if b.kind == "experience"]
check("đúng 2 vai trò, không bị câu có gạch ngang xé đôi", len(exp) == 2)
check("đọc được ngày tháng", exp[0].meta == "Jan 2026 – Present")
check("tách nhóm kỹ năng riêng", len([b for b in bs if b.kind == "skill"]) == 3)

joined = sentences(exp[0])
check("nối lại dòng PDF bị ngắt giữa câu",
      any("adjacent dates are correlated" in s for s in joined))

print("\n[luật — phân biệt kiến thức với thất bại]")
keep_cases = [
    "A random train/test split leaks, because adjacent dates are correlated",
    "I designed and built two systems in Python: signals, validation and risk",
]
drop_cases = [
    "Live drawdown ran roughly 30% deeper than the model predicted",
    "The mistake was mine: the regime split was a valid partition",
    "I never budgeted the time a proof would take, and the capital ran out",
]
# Ý KIẾN GIỜ LÀ 'HỎI', KHÔNG PHẢI 'XOÁ'. Ý kiến và kiến thức cùng hình dạng —
# hiện tại đơn, không số, không hành động — mà kiến thức là thứ MẠNH NHẤT của
# một CV kỹ thuật. Máy đoán là có ngày đoán sai một trong hai, và đoán sai
# nghĩa là xoá mất câu mạnh nhất. Nên nó đánh dấu để người viết tự quyết.
review_cases = [
    "Profit on its own means nothing: an edge can be faked",
    "Good code is code other people can delete",
    "Reporting is only useful when someone acts on it",
]
for text in keep_cases:
    check(f"GIỮ kiến thức: {text[:40]}…", rules.sentence_ok(text)[0] == "keep")
for text in drop_cases:
    check(f"BỎ thất bại: {text[:40]}…", rules.sentence_ok(text)[0] == "drop")
for text in review_cases:
    check(f"HỎI, không xoá: {text[:38]}…", rules.sentence_ok(text)[0] == "review")

# LUẬT PHẢI TỔNG QUÁT, không phải bảng tra chép từ một hồ sơ. Bản cũ là danh
# sách cụm từ lấy thẳng từ CV của một người ("i was optimising for peak",
# "nobody has exploited"); đo trên hai hồ sơ khác thì bắt 0/5 câu, dù cả hai
# đều có câu kể thất bại rành rành.
for _t in ("I honestly struggled with the first rebuild and it shipped two weeks late",
           "My first design leaked memory under load and I had to roll it back",
           "We missed the deadline and the pilot was rolled back"):
    check(f"hồ sơ NGƯỜI KHÁC cũng bắt được: {_t[:34]}…",
          rules.sentence_ok(_t)[0] == "drop")
# Và KHÔNG bắt nhầm câu khoe việc chứa cùng chữ đó — đây là vế thứ hai của
# luật: "prevented data leakage" và "my design leaked" cùng gốc `leak`.
for _t in ("Prevented data leakage by splitting on regime boundaries",
           "Reduced failed builds from 12 a week to 1",
           "Detected and fixed a memory leak in the pricing loop"):
    check(f"KHÔNG bắt nhầm câu khoe việc: {_t[:34]}…",
          rules.sentence_ok(_t)[0] == "keep")
# Vế thứ ba: THÌ. "leaked" là chuyện đã xảy ra với mình, "leaks" là sự thật
# chung. Tác giả luật gốc đã ghi lại đúng cái bẫy này, và bản cấu trúc đầu
# tiên của tôi giẫm lại y nguyên.
check("câu KIẾN THỨC thì hiện tại KHÔNG bị coi là thất bại",
      rules.sentence_ok(
          "A random train/test split leaks, because adjacent dates are "
          "correlated and information from the future ends up in training"
      )[0] == "keep")
# Và phán quyết KHÔNG được đổi theo chữ ký lời gọi.
_c1 = rules.sentence_ok("A random train/test split leaks, because adjacent "
                        "dates are correlated and future data leaks in")[0]
_c2 = rules.sentence_ok("A random train/test split leaks, because adjacent "
                        "dates are correlated and future data leaks in",
                        ["validation"])[0]
check("cùng một câu -> cùng một phán quyết, dù có truyền tags hay không",
      _c1 == _c2)

verdict, why = rules.sentence_ok("Self-funded, across 17 instruments and five years of data")
check("câu nhạy cảm NHƯNG có số -> đánh dấu xem lại, không vứt", verdict == "review")
check("và nói rõ vì sao", "your call" in why)
check("bỏ chữ nút bấm dính đầu câu",
      rules.clean("Demo MetaTrader's backtester only measures edge").startswith("MetaTrader"))

print("\n[sửa câu: chỉ cắt và xếp lại chữ của Vin]")
from jobbot.cv import rewrite as _rw
# LƯỢC CHỦ NGỮ — quy ước CV. Không thêm sự thật nào.
for _t, _mong in (
    ("I designed and built every layer.", "Designed and built every layer."),
    ("I classified the market on two axes.", "Classified the market on two axes."),
    ("I rebuilt it without free parameters.", "Rebuilt it without free parameters."),
    ("I wrote the operating manual.", "Wrote the operating manual."),
):
    _ra, _da = _rw.sua(_t)
    check(f"lược 'I' -> {_mong[:34]}", _ra == _mong)
check("và nói rõ vì sao, bằng tiếng người",
      "lược chủ ngữ" in _rw.sua("I built it and shipped it.")[1][0].vi_sao)

# CHỖ NGUY: trợ động từ. "I was optimising" -> "Was optimising" là sai ngữ pháp.
# Luật đuôi -ed / bất-quy-tắc tự loại chúng — test để nó không bị nới ra sau này.
for _t in ("I was optimising for peak profit.", "I had no capital left.",
           "My own capital ran out.", "I could not reproduce it.",
           "I am a quantitative developer."):
    check(f"KHÔNG đụng trợ động từ: {_t[:30]}", _rw.sua(_t)[0] == _t)
# Giữa câu thì không sửa: đổi giữa câu là đổi cấu trúc, không còn là cắt chữ.
check("KHÔNG sửa ngôi thứ nhất ở GIỮA câu",
      _rw.sua("One signal has many configurations, so I chose on average.")[0]
      == "One signal has many configurations, so I chose on average.")

check("hoa chữ đầu câu bị thường",
      _rw.sua("the whole pipeline turned into something you can run.")[0]
      .startswith("The whole"))
check("câu đã đúng thì KHÔNG sinh phép nào",
      _rw.sua("Built two systems in Python.")[1] == [])

# MỌI TỪ phải có sẵn trong câu gốc — đây là luật gốc, ở dạng nhỏ nhất.
for _t in ("I designed and built every layer of two systems in MQL5.",
           "the whole pipeline turned into something you can run.",
           "I validated on two separate occurrences."):
    _ra, _ = _rw.sua(_t)
    check(f"không thêm từ nào: {_t[:28]}",
          not (set(_ra.lower().split()) - set(_t.lower().split())))

print("\n[điểm yếu: máy CHỈ RA, người tự viết]")
# Nửa này máy không được làm thay: câu thiếu số đo thì thứ thiếu là MỘT CON SỐ
# THẬT, chỉ Vin biết. Máy bịa vào là đẻ ra câu Vin không đỡ được lúc phỏng vấn.
# MỘT CÂU CV LÀ MỘT TRONG HAI THỨ, đòi hai chuẩn khác nhau. Đo trên hồ sơ
# thật: 12/16 câu là KIẾN THỨC. Đòi số đo ở cả 16 thì 12 dấu là báo động giả —
# mà dấu nào dòng nào cũng có thì nó thành cái nền, và người dùng học được
# rằng đừng nhìn dấu nữa.
check("KHOE VIỆC mà thiếu số -> bắt",
      "khong_so" in {y.ma for y in _rw.diem_yeu("Built some models.", [], set())})
check("KIẾN THỨC thì KHÔNG đòi số — không có số nào để mà thêm",
      "khong_so" not in {y.ma for y in _rw.diem_yeu(
          "A random train/test split leaks, because adjacent dates correlate.",
          [], set())})
check("và KHÔNG còn chê câu kiến thức vì không mở bằng động từ",
      "khong_dong_tu" not in {y.ma for y in _rw.diem_yeu(
          "A random train/test split leaks.", [], set())})
check("khoe việc CÓ số thì không báo bừa",
      "khong_so" not in {y.ma for y in _rw.diem_yeu(
          "Built 17 models across five years of data.", [], set())})
check("bắt câu quá dài", "qua_dai" in {y.ma for y in _rw.diem_yeu(
      "Built " + "x" * 210, [], set())})
check("bắt câu không chạm yêu cầu nào của tin",
      "khong_tra_loi" in {y.ma for y in _rw.diem_yeu(
          "Built models in Python.", ["python"], {"c++"})})
check("mỗi điểm yếu phải kèm VIỆC LÀM ĐƯỢC, không phải lời khuyên chung",
      all(y.lam_gi and len(y.lam_gi) > 20
          for y in _rw.diem_yeu("Built some models.", [], set())))

print("\n[dựng CV]")
JD_ML = {"requirements": [{"text": "Strong Python and PyTorch for deep learning", "met": True,
                           "must": True, "evidence": ""}]}
JD_RISK = {"requirements": [{"text": "Portfolio construction and risk management", "met": True,
                             "must": True, "evidence": ""}]}
ml = build(PROFILE, JD_ML, "deep learning pytorch python")
risk = build(PROFILE, JD_RISK, "portfolio risk management")

def top_of(cv, title_part):
    section = next(s for s in cv.sections if title_part in s.title)
    return section.lines[0].text.lower()

check("JD deep learning -> dòng đầu nói về PyTorch/deep learning",
      "pytorch" in top_of(ml, "WorldQuant") or "deep learning" in top_of(ml, "WorldQuant"))
check("JD risk -> dòng đầu nói về portfolio/risk",
      "risk" in top_of(risk, "WorldQuant") or "portfolio" in top_of(risk, "WorldQuant"))
check("hai JD khác nhau -> thứ tự khác nhau",
      [l.text for s in ml.sections for l in s.lines] !=
      [l.text for s in risk.sections for l in s.lines])

all_text = " ".join(l.text for s in ml.sections for l in s.lines)
# LUẬT GỐC CỦA CẢ TẦNG CV, và đây là chỗ canh nó. Máy được CẮT và XẾP LẠI chữ
# của Vin; máy KHÔNG được thêm chữ nào Vin chưa viết.
#
# Test cũ đòi câu in ra phải nằm NGUYÊN VĂN trong CV gốc. Chặt, nhưng chặt sai
# chỗ: nó cấm luôn cả việc bỏ chữ "I" ở đầu câu — một phép không thêm gì cả.
# Bản này đòi thứ mạnh hơn: mọi TỪ trên bản in ra phải có mặt trong câu gốc.
# Bỏ từ thì được, thêm một từ là vỡ test.
_goc_all = CV.replace("\n", " ")
_bia = []
for _s in ml.sections:
    if _s.kind not in ("experience", "project"):
        continue
    for _l in _s.lines:
        _goc = _l.goc or _l.text
        if _goc.strip()[:40] not in _goc_all:
            _bia.append(("câu gốc không có trong CV", _goc[:60]))
            continue
        _them = set(_l.text.lower().split()) - set(_goc.lower().split())
        # Chữ đầu câu được hoa lên -> 'the' thành 'The'; so bằng chữ thường
        # rồi thì phép đó không đẻ ra từ mới, nên mọi từ dư đều là bịa thật.
        if _them:
            _bia.append((f"thêm từ {sorted(_them)}", _l.text[:60]))
check("KHÔNG bịa: mọi TỪ in ra đều có trong câu Vin viết — " + str(_bia[:2]),
      not _bia)
# Và mọi câu đã sửa phải để lại dấu vết — sửa mà không ghi lại thì không có
# "trước" nào để so, và bản so sánh before/after thành lời nói một chiều.
check("câu nào bị sửa thì có ghi lại phép và lý do",
      all(l.sua and all(x.vi_sao for x in l.sua)
          for s in ml.sections for l in s.lines
          if s.kind in ("experience", "project") and l.goc and l.goc != l.text))
check("không đưa thất bại lên CV", "mistake was mine" not in all_text)
check("không đưa ý kiến lên CV", "means nothing" not in all_text)

skill_titles = [s.title for s in ml.sections if s.kind == "skill"]
# MỤC KỸ NĂNG XÉT THEO NỘI DUNG, KHÔNG THEO TÊN. Luật cũ là một tập hai tên
# mục lấy từ CV của một người (`{"compute","method"}`); hồ sơ khác thì nó bỏ
# sót đúng mục đáng bỏ nhất — "Soft — communication, teamwork".
check("giữ mục CÓ kỹ năng máy nhận ra", "Programming" in skill_titles)
from jobbot.cv.rules import bo_muc_ky_nang as _bmk
check("bỏ mục mềm dù tên mục là gì", _bmk("Soft", "communication, teamwork"))
check("bỏ mục sở thích", _bmk("Interests", "chess, running"))
check("GIỮ mục công nghệ lạ máy chưa biết tên — bỏ nhầm là mất thật",
      not _bmk("Hardware", "VHDL, oscilloscopes"))
check("giữ mục có kỹ năng thật, bất kể tên mục",
      not _bmk("Compute", "deep learning, machine learning"))

check("có ghi lại những câu đã bỏ", len(ml.dropped) >= 4)
check("mỗi câu bỏ đều kèm lý do", all(why for _, why in ml.dropped))
check("tóm tắt ghép từ sự thật, không viết mới",
      "MSc Computational Finance" in ml.summary and "CFA Level I" in ml.summary)

print("\n[thiếu kỹ năng — danh sách 'hoặc']")
JD_OR = {"requirements": [{"text": "Programming in any of: C++, Java, MATLAB, R or Python",
                           "met": True, "must": True, "evidence": ""}]}
either = build(PROFILE, JD_OR, "C++ Java MATLAB R Python")
check("có C++/Python rồi thì Java/MATLAB/R KHÔNG tính là thiếu",
      not ({"java", "matlab", "r"} & set(either.missing)))

JD_GAP = {"requirements": [{"text": "Experience with equities and derivatives pricing",
                            "met": False, "must": True, "evidence": ""}]}
gap = build(PROFILE, JD_GAP, "equities derivatives")
check("thiếu thật thì vẫn báo", {"equities", "derivatives"} & set(gap.missing))


print("\n[soạn khối — sửa một khối, mọi khối khác NGUYÊN VẸN]")
from jobbot.cv.blocks import write_block

CV_IN = PROFILE["cv_text"]
base = [(b.kind, b.title, b.meta) for b in parse(CV_IN)]
check("hồ sơ mẫu có khối để sửa", len(base) >= 3)

for blk in parse(CV_IN):
    if blk.kind not in ("experience", "project"):
        continue
    out = write_block(CV_IN, blk.kind, blk.title, blk.meta, ["I built a walk-forward tester across 17 instruments.",
                        "Live drawdown ran 30% deeper than the model said."])
    got = [(b.kind, b.title, b.meta) for b in parse(out)]
    # BẤT BIẾN: đây là chỗ dễ hỏng nhất. parse() nhận ra khối mới bằng HÌNH
    # DẠNG dòng tiêu đề — project cần " — ", kinh nghiệm cần đuôi ngày tháng.
    # Ghi sai hình dạng thì khối bị nuốt vào khối trước và BIẾN MẤT; ghi mà
    # không định vị được thì đẻ thêm một khối trùng tên.
    check(f"[{blk.kind}] {blk.title[:26]} — danh sách khối không đổi", got == base)
    again = [b for b in parse(out) if b.title == blk.title]
    check(f"[{blk.kind}] {blk.title[:26]} — đọc lại đúng nội dung mới",
          bool(again) and again[0].lines == ["I built a walk-forward tester across 17 instruments.",
                        "Live drawdown ran 30% deeper than the model said."])

fresh = write_block(CV_IN, "project", "Regime Detector", "", ["I built a walk-forward tester across 17 instruments.",
                        "Live drawdown ran 30% deeper than the model said."])
made = [b for b in parse(fresh) if b.title == "Regime Detector"]
check("khối mới thêm được", bool(made))
check("khối mới nằm đúng mục project", bool(made) and made[0].kind == "project")
check("thêm khối KHÔNG đụng khối cũ",
      all(x in [(b.kind, b.title, b.meta) for b in parse(fresh)] for x in base))
check("khối mới vào được chỉ số bằng chứng ngay",
      any("Regime Detector" in e.where
          for e in __import__("jobbot.scoring.score", fromlist=["x"])
          .build_index({**PROFILE, "cv_text": fresh})))

print("\n[chứng chỉ — tên mục không in hai lần]")
from jobbot.cv.blocks import parse as _parse
_cv = ("EDUCATION\n"
       "MSc Computational Finance — Royal Holloway Sep 2025 – Sep 2026\n"
       "Certifications — CFA Level I, October 2024 · IBM Data Science\n"
       "TECHNICAL SKILLS\n"
       "Programming — Python, C++\n")
_cert = [b for b in _parse(_cv) if b.kind == "cert"]
check("có đúng một khối chứng chỉ", len(_cert) == 1)
# render.py đặt tiêu đề mục theo kind ("cert" -> "Certifications"). Giữ chữ đó
# trong thân nữa thì bản in ra hai dòng chồng nhau — đo được trên CV thật.
check("thân KHÔNG lặp lại chữ Certifications",
      bool(_cert) and not _cert[0].lines[0].lower().startswith("certification"))
check("nội dung còn nguyên",
      bool(_cert) and _cert[0].lines[0].startswith("CFA Level I"))
check("nhãn thành tiêu đề khối", bool(_cert) and _cert[0].title == "Certifications")

print("\n[đổi tên khối CV — không được nhân đôi]")
from jobbot.cv.blocks import write_block as _wb, parse as _pp
_cv2 = ("SELECTED PROJECTS\n"
        "Alpha Research — a cross-sectional alpha signal on equity data\n"
        "Walk-forward by construction.\n")
# Route phải xoá khối tên CŨ trước khi ghi tên MỚI: write_block tìm theo tên
# mới, không thấy, nên chỉ THÊM — CV còn cả hai và bản in ra có hai mục trùng.
_renamed = _wb(_wb(_cv2, "project", "Alpha Research", "", []),
               "project", "Alpha Signal", "", ["a cross-sectional alpha signal"])
_titles = [b.title for b in _pp(_renamed) if b.kind == "project"]
check("chỉ còn MỘT khối sau khi đổi tên", len(_titles) == 1)
check("và mang tên mới", _titles == ["Alpha Signal"])
_srv3 = (Path(__file__).resolve().parent.parent
         / "src/jobbot/dashboard/server.py").read_text(encoding="utf-8")
check("route đọc trường 'was'", 'form.get("was"' in _srv3)
check("và xoá khối cũ trước khi ghi", "was != title" in _srv3)

print("\n[tiêu đề khối vào URL phải URL-encode]")
from urllib.parse import quote as _q
# KHO KHỐI ĐÃ RỜI khỏi tab CV sang màn Sửa khối — nó có nhà riêng ở đó, nơi
# bấm vào một khối là soạn được luôn.
_lst = (Path(__file__).resolve().parent.parent
        / "src/jobbot/dashboard/views/cvsoan.py").read_text(encoding="utf-8")
# esc() là để chữ hiện an toàn trong HTML; nó KHÔNG làm dấu & hết cắt tham số.
check("dùng quote() cho tham số URL", "quote(b['title']" in _lst)
check("ký tự & được mã hoá", _q("Research & Development", safe="") == "Research%20%26%20Development")

print("\n[KHOẢNG TRỐNG: khối kinh nghiệm không bao giờ bị bỏ cả khối]")
# Lọc khối theo "có trúng thứ tin này đòi không" đúng với PROJECT (tự chọn,
# bỏ không để lại dấu vết) nhưng SAI với KINH NGHIỆM: nó đục một lỗ trên dòng
# thời gian. Đo trên kho thật: 6/12 bản CV đầu bảng rơi mất hẳn khối
# "WorldQuant, Jan–Sep 2025" — bản gửi đi tự khai khoảng trống 9 tháng.
# Khảo sát HBS/Accenture 2021: gần một nửa nhà tuyển dụng tự loại CV có
# khoảng trống quá 6 tháng. Một khối ít liên quan chỉ tốn ba dòng giấy.
_moi_viec = [b.title for b in parse(CV) if b.kind == "experience"]
for _cv_thu, _ten in ((ml, "JD deep learning"), (risk, "JD risk")):
    _ra = [x.title for x in _cv_thu.sections if x.kind == "experience"]
    check(f"{_ten}: giữ đủ mọi khối kinh nghiệm ({len(_ra)}/{len(_moi_viec)})",
          len(_ra) == len(_moi_viec))
# Một JD chẳng dính gì tới khối nào cũng KHÔNG được làm rơi khối nào.
_la = build(PROFILE, None, "we sell industrial adhesives to the marine sector")
check("JD hoàn toàn lạc đề cũng không đục khoảng trống",
      len([x for x in _la.sections if x.kind == "experience"]) == len(_moi_viec))

print("\n[chấm bài NGAY TRÊN tờ CV]")
# Bản trước vẽ tờ CV rồi liệt kê lại từng câu ở dưới — cùng một câu hiện hai
# lần, người đọc phải tự ghép "câu 3 ở dưới" với câu nào ở trên.
from jobbot.cv.render import paper as _pp, dem_lai as _dl
from jobbot.cv.report import head as _hd, chi_tiet as _ct
from jobbot.cv.build import dang_ke as _dk
import re as _re2

_dl(); _to = _pp(ml, cham=True)
_dl(); _to_sach = _pp(ml)
check("không chấm -> tờ CV trơn như cũ", "cjump" not in _to_sach
      and "cvpaper" in _to_sach and "cham" not in _to_sach)
check("chấm -> mỗi câu có neo riêng", _re2.search(r"id='cau1'", _to))
check("và có dấu theo LOẠI VIỆC, không phải màu trang trí",
      "dsua" in _to or "dhong" in _to)
check("bấm vào dòng là mở thẻ chữa bài NGAY TẠI CHỖ", "class=cdet" in _to
      and "class=ccard" in _to)
check("tô từ khoá tin này ĐÒI ngay trong câu", "'kw'" in _to or "kw " in _to)
check("có chữ GỐC sẵn trong DOM để nút Trước/Sau bật tắt", "class=ctruoc" in _to)

# MỖI CÂU MỘT CHỖ. Câu chỉ được nằm trên tờ giấy; phần dưới nói thứ tờ giấy
# không nói được (tin đòi gì, vì sao sửa), KHÔNG chép lại toàn văn câu.
_dl(); _to2 = _pp(ml, cham=True); _duoi = _ct(ml)
_cau_dai = [l.text for s2 in ml.sections for l in s2.lines
            if s2.kind in ("experience", "project") and len(l.text) > 40]
if _cau_dai:
    _c0 = _cau_dai[0][:40]
    check("câu KHÔNG bị chép lại ở phần chi tiết", _c0 not in _duoi)

# LINK CHẾT. Bút đỏ trên bài và khối chi tiết phải hỏi CÙNG một câu hỏi; hỏi
# ở hai chỗ thì chúng trôi khỏi nhau và bấm vào không nhảy đi đâu — im lặng.
# MỖI CÂU MỘT CHỖ. Thẻ chữa bài nằm NGAY TRÊN dòng, nên phần dưới KHÔNG
# được nhắc lại từng câu nữa — nhắc lại là bắt đọc hai lần rồi tự ghép.
check("phần dưới KHÔNG còn lặp lại từng câu", "class='gcau" not in _duoi
      and "class=gcau" not in _duoi)
check("phần dưới chỉ còn thứ KHÔNG thuộc về một câu nào",
      "hồ sơ câm" in _duoi or "Luật không cho" in _duoi or _duoi.strip()
      .startswith("<div class=cvaudit>"))
check("chỉ câu CÓ GÌ ĐỂ NÓI mới thành thẻ — một chỗ quyết",
      _dk.__module__ == "jobbot.cv.build")

# NÚT TRƯỚC/SAU dùng bộ chọn anh-em, nên checkbox phải CÙNG CẤP với tờ CV.
# Nhét vào trong một <div> thì nó là cháu, và cái nút im lặng không làm gì.
_h = _hd(ml)
check("checkbox Trước/Sau đứng NGOÀI mọi <div> của phần đầu",
      _h.index("id=cvtruoc") < _h.index("<div class=gtoggle>"))
check("phần chấm điểm bọc .cvaudit nên không in ra giấy",
      "<div class=cvaudit>" in _h)
check("nhưng nút Trước/Sau đứng ngoài bọc đó",
      _h.index("id=cvtruoc") < _h.index("<div class=cvaudit>"))

print("\n[chọn lại: máy đưa câu KHÁC BẠN ĐÃ VIẾT, không viết câu mới]")
from jobbot.cv.build import bench as _bench, _pick as _pk2
from jobbot.cv.blocks import Block as _Bk
from jobbot.cv.render import to_khoa as _tk

# BĂNG GHẾ = câu hợp luật trong hồ sơ mà bản này không chọn. Đây là thứ làm
# "chọn lại" thành chọn THẬT chứ không phải lời hứa.
_bg = _bench(PROFILE, ml)
check("có câu dự bị để đổi sang", len(_bg) > 0)
_tren_giay = {l.goc or l.text for s2 in ml.sections for l in s2.lines}
check("câu dự bị KHÔNG phải câu đang in trên bản",
      not any(b["text"] in _tren_giay for b in _bg))
check("mọi câu dự bị đều LÀ CÂU TRONG HỒ SƠ — máy không bịa câu nào",
      all(b["text"][:38] in CV.replace("\n", " ") for b in _bg))
check("xếp câu trúng thứ tin này đòi lên trước",
      not _bg or len(_bg[0]["trung"]) >= len(_bg[-1]["trung"]))
check("mỗi câu dự bị nói rõ đổi sang thì TRÚNG THÊM GÌ",
      all("trung" in b and "khoi" in b for b in _bg))

# GHIM / GẠT: người chọn thắng cách máy xếp.
_kh = _Bk(kind="experience", title="X", meta="",
          lines=[f"Built system number {_i} with Python daily." for _i in range(6)])
_thuong = [l.text for l in _pk2(_kh, set(), {}, 2)]
_ghim = [l.text for l in _pk2(_kh, set(), {}, 2,
                              chon={"pin": [_kh.lines[5]]})]
check("ghim một câu -> nó lên bản dù trọng số không đổi",
      _kh.lines[5] in _ghim)
_gat = [l.text for l in _pk2(_kh, set(), {}, 2, chon={"drop": [_thuong[0]]})]
check("gạt một câu -> nó biến khỏi bản", _thuong[0] not in _gat)
check("ghim KHÔNG phá trần số dòng — một tờ giấy vẫn là một tờ giấy",
      len(_ghim) == 2)

print("\n[tô từ khoá: nhìn phát biết tờ giấy có nói ra thứ họ hỏi không]")
_h = _tk("Built models in Python and managed portfolio risk.", {"python", "risk"})
check("tô đúng chữ có thật trong câu", ">Python<" in _h and "kw" in _h)
check("giữ nguyên phần chữ còn lại", "Built models in" in _h)
check("không đòi thì không tô",
      "kw" not in _tk("Built models in Python.", set()))
# Thẻ lồng nhau là HTML vỡ: "machine learning" và "learning" chồng lên nhau.
_ml = _tk("deep learning and machine learning models",
          {"machine learning", "deep learning"})
check("thẻ mở và đóng cân bằng dù vệt chồng nhau",
      _ml.count("<span") == _ml.count("</span>"))
# VỆT CHỒNG NHAU là chuyện thường: một cụm vừa là từ khoá, vừa nằm trong đoạn
# "thiếu số đo", vừa trong đoạn "quá dài". Bọc lần lượt thì đẻ thẻ cắt chéo.
from jobbot.cv.rewrite import vet as _vt, sua as _sa
_t2 = "Built two systems in MQL5 and Python: signals and risk."
_, _ds = _sa("I built two systems in MQL5 and Python: signals and risk.")
_h2 = _tk(_t2, {"python", "risk"}, _vt(_t2, ["python", "risk"], {"python", "risk"}, _ds))
check("vệt chồng nhau vẫn ra HTML phẳng, cân bằng",
      _h2.count("<span") == _h2.count("</span>"))
check("một cụm mang ĐƯỢC nhiều nhãn cùng lúc", "kw vthieu_so" in _h2)
# Chữ của người dùng phải được escape — tên công ty có & là chuyện thường.
check("chữ vẫn được escape",
      "&amp;" in _tk("Risk & return with Python", {"python"}))

print("\n[VẾT: gạch đúng ĐOẠN CHỮ, không gạch cả dòng]")
# Đây là chỗ bản trước làm sai: nó đánh dấu ở mức DÒNG bằng viền trái 2px, đo
# được 0 dấu nào nằm TRÊN CHỮ. Mở tờ CV ra thấy mấy chữ xanh và không biết có
# vấn đề gì, phải bấm từng dòng mới phát hiện — ngược hẳn với chấm bài.
from jobbot.cv.rewrite import vet as _vt3, sua as _sa3, DAI_NHAT as _DN

# THIẾU SỐ: gạch đúng cụm động từ — chỗ con số ĐÁNG RA phải nằm. Không gạch
# được chỗ trống, nhưng gạch được chỗ nó thuộc về.
_t = "Built two systems in MQL5 and Python: signals and risk."
_v = _vt3(_t, ["python"], {"python"})
_ts = [x for x in _v if x.loai == "thieu_so"]
check("khoe việc mà thiếu số -> có vệt", len(_ts) == 1)
check("vệt dừng ở hết mệnh đề đầu, không nuốt cả câu",
      _ts and _t[_ts[0].dau:_ts[0].cuoi] == "Built two systems in MQL5 and Python")
check("và nói rõ chèn số vào ĐÂU", _ts and "vào đúng đây" in _ts[0].lam_gi)
check("có số rồi thì KHÔNG gạch",
      not [x for x in _vt3("Built 17 systems in Python.", ["python"], {"python"})
           if x.loai == "thieu_so"])
# KIẾN THỨC không bị đòi số — 12/16 câu của hồ sơ là kiến thức.
check("câu kiến thức KHÔNG bị gạch thiếu số",
      not [x for x in _vt3("A random train/test split leaks.", [], set())
           if x.loai == "thieu_so"])

# QUÁ DÀI: gạch ĐÚNG PHẦN THỪA, từ chỗ mắt bắt đầu trượt — không gạch cả câu.
_dai = "Built " + "x" * (_DN + 40)
_qd = [x for x in _vt3(_dai, [], set()) if x.loai == "qua_dai"]
check("quá dài -> gạch từ đúng chỗ vượt trần", _qd and _qd[0].dau == _DN)
check("và không gạch từ đầu câu", _qd and _qd[0].dau > 0)

# MÁY ĐÃ SỬA: đánh dấu chữ đầu — chỗ chữ "I" vừa bị cắt.
_, _ds3 = _sa3("I built two systems.")
_ms = [x for x in _vt3("Built two systems.", [], set(), _ds3) if x.loai == "da_sua"]
check("máy sửa chữ -> đánh dấu đúng chữ đầu", _ms and _ms[0].dau == 0)

# MỖI VẾT phải kèm việc làm được, không phải lời phán.
check("mọi vệt đều kèm CÁCH SỬA cụ thể",
      all(x.lam_gi and len(x.lam_gi) > 15 for x in _vt3(_t, ["python"], {"python"})))

# THANH ĐẾM: mở tờ CV ra là biết có mấy chỗ, không phải bấm từng dòng.
from jobbot.cv.report import cho_xem as _cx
_ds4 = _cx(ml)
check("đếm được chỗ cần xem trên cả tờ", isinstance(_ds4, list))
check("đếm theo CHỖ, không theo câu — một câu có thể có hai việc",
      all(len(x) == 3 and isinstance(x[2], int) for x in _ds4))
_h4 = _hd(ml)
check("thanh đầu nói thẳng còn mấy chỗ cần xem", "chỗ cần bạn xem" in _h4)
check("và có chú giải, không để mấy đường gạch thành câu đố",
      "glegend" in _h4 or not _ds4)

print("\n[KHỨ HỒI: lưu một câu KHÔNG được nuốt mất câu nào]")
# HAI LỖI THẬT, cả hai đều mất dữ liệu, cả hai cùng một gốc: `parse` và
# `_bounds` mỗi bên tự đoán một kiểu "dòng nào mở khối project mới".
from jobbot.cv.blocks import write_block as _wb2, parse as _ps2, _bounds as _bd2

_cv2 = ("SELECTED PROJECTS\nQuant Trading Studio\n"
        "the whole pipeline turned into something you can run.\n"
        "The Number That Lied\nKeep the best of many models.\n")

# LỖI 1 — `_bounds` chỉ dừng ở dòng có " — ", mà write_block ghi tên project
# TRẦN một dòng. Nên lưu một project là xoá sạch mọi project bên dưới nó.
check("ranh giới khối dừng đúng chỗ, không nuốt tới cuối tệp",
      _bd2(_cv2.splitlines(), "Quant Trading Studio") == (1, 3))
_sau2 = _wb2(_cv2, "project", "Quant Trading Studio", "",
             ["the whole pipeline turned into something you can run."])
check("lưu một project KHÔNG xoá project bên dưới", "The Number That Lied" in _sau2)
check("và câu của nó còn nguyên", "Keep the best of many models." in _sau2)

# LỖI 2 — câu người dùng lưu vào thân khối bị đọc lại thành TÊN KHỐI, đẻ ra
# một project rỗng, và câu ấy KHÔNG BAO GIỜ in ra nữa. Xảy ra thật trên hồ sơ
# của Vin với câu "Improved research frameworks, data pipelines".
_cau2 = "Improved research frameworks, data pipelines"
_sau2 = _wb2(_cv2, "project", "Quant Trading Studio", "",
             ["the whole pipeline turned into something you can run.", _cau2])
_pj2 = [b for b in _ps2(_sau2) if b.kind == "project"]
check("câu vừa lưu nằm trong THÂN khối, không thành tên khối",
      any(_cau2 in l for b in _pj2 for l in b.lines))
check("và KHÔNG đẻ ra khối rỗng nào", all(b.lines for b in _pj2))
check("số khối project giữ nguyên", len(_pj2) == 2)
# Câu mở đầu bằng ĐỘNG TỪ HÀNH ĐỘNG không bao giờ là tên project — kể cả khi
# nó có dấu gạch, hình dạng giống hệt một tiêu đề.
from jobbot.cv.blocks import mo_khoi_project as _mkp
check("câu có dấu gạch mà mở bằng động từ -> vẫn là CÂU",
      not _mkp("Improved research frameworks — cut runtime to 90 s.", None))
check("còn tên project thật thì vẫn nhận ra",
      _mkp("Quant Trading Studio", None)
      and _mkp("The Number That Lied — MSc dissertation, PyTorch.", None))

print("\n[ĐỘ MAY ĐO: xếp lại chữ của mình, không thêm không bỏ]")
# Đo trên kho thật: 98 tập yêu cầu KHÁC NHAU trên 120 tin, mà chỉ ra 19 bản
# CV — vì mục kỹ năng, phần dày từ khoá nhất tờ giấy, được đổ ra nguyên xi
# theo thứ tự trong hồ sơ và không bao giờ đụng tới. Xếp lại: 19 -> 46 -> 68.
from jobbot.cv.build import _tach_mon as _tm, _xep_mon as _xm, _la_danh_sach as _lds

_ky = "Python (pandas, NumPy, PyTorch), C++, SQL, MQL5, Excel."
check("KHÔNG cắt trong ngoặc — 'Python (pandas, NumPy)' là MỘT món",
      _tm(_ky.rstrip(".")) [0] == "Python (pandas, NumPy, PyTorch)")
check("và tách đúng số món", len(_tm(_ky.rstrip("."))) == 5)

_sql = _xm(_ky, {"sql"})
check("món tin này hỏi nhảy lên ĐẦU dòng", _sql.startswith("SQL,"))
# KHÔNG ĐƯỢC MẤT MỘT CHỮ NÀO. Đây là CV gửi nhà tuyển dụng.
import re as _reX
check("xếp lại KHÔNG mất chữ nào",
      sorted(_reX.findall(r"\w+", _ky)) == sorted(_reX.findall(r"\w+", _sql)))
check("dấu chấm vẫn ở cuối DÒNG, không dính món cuối", _sql.endswith("."))
check("tin không hỏi gì thì giữ nguyên thứ tự", _xm(_ky, set()) == _ky)
check("danh sách dưới 3 món thì không đụng", _xm("Python, SQL", {"sql"}) == "Python, SQL")

# CHỐT CHẶN THẬT SỰ: dòng VĂN XUÔI không được xếp lại. Bản đầu của tôi xếp
# mọi dòng, và mục "Compute" của hồ sơ thật là một câu văn — xếp lại là đảo
# lộn một LẬP LUẬN thành vô nghĩa, trên tờ giấy gửi đi. 80/120 bản dính.
_van = ("a GPU is fast at many simple operations at once, which suits deep "
        "learning; most classical ML models run slower on one because moving "
        "the data costs more than the speed-up.")
check("nhận ra dòng VĂN XUÔI, không phải danh sách", not _lds(_tm(_van)))
check("và để nguyên nó", _xm(_van, {"machine learning"}) == _van)
check("còn danh sách thật thì nhận ra",
      _lds(_tm("maximum drawdown, Sharpe ratio, risk limits, portfolio construction")))

# BA MỨC phải ra BA KẾT QUẢ KHÁC NHAU — núm không đổi gì là núm trang trí,
# và app này đã bỏ một núm như thế rồi (độ dày từ khoá, đổi 0/60 bản).
from jobbot.core import prefs as _pfX
check("ba mức may đo đều có tên", set(_pfX.RIENG) == {"chung", "vua", "rieng"})

print(f"\n{ok} ok, {fail} fail")
sys.exit(1 if fail else 0)
