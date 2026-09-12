"""Định nghĩa câu hỏi hồ sơ — DỮ LIỆU, không phải giao diện.

Chữ hiện ra màn hình là tiếng Anh (thị trường UK/global).
Chú thích trong code giữ tiếng Việt — đây là phần giải thích thiết kế, không phải giao diện.

Chia theo AI DÙNG, không theo thứ tự tiện hỏi:

    1 muc_tieu    Bạn muốn gì        -> ingest, scoring
    2 rang_buoc   Bạn KHÔNG muốn gì  -> bộ lọc (chặn spam)
    3 nang_luc    Bạn có gì          -> scoring, cv
    4 danh_tinh   Bạn là ai          -> cv, mail, outreach
    5 project     Personal project   -> tuỳ chọn, đặc thù Comp Sci

Hai luật:

- **Hỏi cái ingest thật sự dùng được.** Job board tìm theo CHỨC DANH THẬT, không theo
  phân loại. Lưu "backend" thì không khớp tin nào tên "Software Engineer, Platform".
  Nên `job_titles` lưu đúng chuỗi sẽ đem đi tìm — không phân loại rồi dịch.

- **Không danh sách nào là lồng.** allow_other=True mở ô tự do bên cạnh.

Chỉ 3 câu bắt buộc: job_titles + markets + work_auth. Phần còn lại điền dần.
"""

from __future__ import annotations

from dataclasses import dataclass, field

SINGLE, MULTI, TEXT, LONGTEXT = "single", "multi", "text", "longtext"
# ROWS: mỗi bằng một HÀNG có ô rời, không phải một khối chữ thô. Form ghi ra
# đúng dòng mà apply/answer.educations() đọc lại — một ngữ pháp, hai chiều.
ROWS = "rows"
# BLOCKS: kinh nghiệm làm việc và project cá nhân. Đây là THÔNG TIN CÁ NHÂN,
# nên chỗ của nó là hồ sơ — không phải nằm ẩn trong một tài liệu dán vào. Thứ
# máy đẻ ra sau (CV từng bản, project đề xuất) là đầu ra, chuyện khác.
#
# Nơi LƯU vẫn là khối trong cv_text, vì bộ chấm điểm và bộ dựng CV đều đọc ở
# đó — hồ sơ là nơi SỬA, không phải bản sao thứ hai.
BLOCKS = "blocks"


@dataclass(frozen=True)
class Option:
    value: str
    label: str
    note: str = ""


@dataclass(frozen=True)
class Question:
    id: str
    text: str
    kind: str
    why: str = ""
    options: list[Option] = field(default_factory=list)
    placeholder: str = ""
    required: bool = False
    allow_other: bool = False       # mở ô "add your own" cạnh danh sách
    # Ô THẺ. Giá trị = dấu nối lúc lưu ("\n" hay ", "). Có dấu nối nghĩa là
    # câu này thực chất là một DANH SÁCH, nên đừng bắt người dùng gõ chay:
    # họ phải vừa nghĩ ra nội dung, vừa nhớ đúng chính tả, vừa nhớ luật ngăn
    # cách của riêng ô đó — ba gánh cho một giá trị.
    tags: str = ""
    suggest: str = ""               # kho gợi ý: "titles" hay "skills"
    block_kind: str = ""            # với kind=BLOCKS: "experience" hay "project"
    # Có trong schema nhưng KHÔNG vẽ ra form. store.save() lọc theo schema, nên
    # gỡ một câu khỏi đây là làm nó KHÔNG LƯU ĐƯỢC NỮA — lặng lẽ. Đã mất
    # nguyên toàn văn CV vì đúng chuyện đó: nhập CV báo "13 fields", lưu 12.
    hidden: bool = False


@dataclass(frozen=True)
class Section:
    id: str
    title: str
    why: str
    questions: list[Question]
    optional: bool = False


def _o(v: str, l: str, n: str = "") -> Option:
    return Option(v, l, n)


SECTIONS: list[Section] = [
    # ------------------------------------------------------------------ 1
    Section(
        id="muc_tieu",
        title="What you want",
        why="The only section with required questions. Finish this and the system can start searching.",
        questions=[
            Question(
                id="job_titles",
            tags="\n", suggest="titles",
                text="Which job titles would you take? Write them EXACTLY as they appear on postings.",
                kind=LONGTEXT,
                required=True,
                why=(
                    "This string is sent to the job boards as-is — nothing translates it. "
                    "\"backend\" matches nothing titled \"Software Engineer, Platform\". "
                    "Cast wide, one title per line. You can narrow it later; start broad."
                ),
                placeholder="Quantitative Analyst\nData Scientist\nRisk Analyst\nGraduate Analyst\nBackend Engineer",
            ),
            Question(
                id="search_keywords",
            tags=", ", suggest="skills",
                text="Other keywords that should appear in the posting",
                kind=TEXT,
                why="Technologies, domains, tools. Used to filter after the title search.",
                placeholder="Python, PostgreSQL, Kafka, fintech, microservices",
            ),
            Question(
                id="seniority",
                text="Levels you'd accept",
                kind=MULTI,
                allow_other=True,
                why="Level is usually right in the title. Wrong level is the single biggest source of noise.",
                options=[
                    _o("intern", "Intern / Placement"),
                    _o("grad", "Graduate / Entry level"),
                    _o("grad_scheme", "Graduate scheme / structured programme",
                       "UK-specific: fixed intake windows, applications open Sep–Nov "
                       "for the following year. Miss the window and you wait 12 months."),
                    _o("junior", "Junior"),
                    _o("mid", "Mid-level"),
                    _o("senior", "Senior"),
                    _o("lead", "Lead / Staff / Principal"),
                ],
            ),
            Question(
                id="markets",
                text="Which markets?",
                kind=MULTI,
                required=True,
                allow_other=True,
                why="Decides which sources are used — and which are useless.",
                options=[
                    _o("uk_onsite", "UK — on-site / hybrid",
                       "Greenhouse, Lever, Ashby, LinkedIn. Filtered further by your area."),
                    _o("uk_remote", "UK — remote, UK-based company",
                       "Same sources, remote postings only. No cross-border tax or legal mess."),
                    _o("eu_remote", "Europe — remote",
                       "1–2h offset, easy to live with. LinkedIn has no remote "
                       "filter, so these come back mixed with on-site roles."),
                    _o("us_remote", "US — remote",
                       "5–8h offset. Many US companies hire only people already authorised to "
                       "work in the US — needs careful filtering."),
                    _o("global_remote", "Remote, anywhere",
                       "Greenhouse, Lever, Ashby. Most competitive of all."),
                    _o("relocate", "Willing to relocate abroad",
                       "Needs filtering for visa sponsorship."),
                ],
            ),
            Question(
                id="work_auth",
                text="Your right to work in the UK",
                kind=SINGLE,
                required=True,
                allow_other=True,
                why=(
                    "The HARSHEST filter in the UK market. A great many postings state plainly "
                    "\"we cannot provide sponsorship\". Get this wrong and most of what the system "
                    "shows you is worthless — you aren't eligible to apply."
                ),
                options=[
                    _o("citizen", "UK / Irish citizen", "No constraints"),
                    _o("settled", "ILR / Settled status", "Same as a citizen for hiring purposes"),
                    _o("visa_no_sponsor", "Have a work visa, sponsorship NOT needed",
                       "Graduate visa, pre-settled status, spouse visa…"),
                    _o("need_sponsor", "Need Skilled Worker sponsorship",
                       "Filters to licensed sponsors only. Cuts the pool sharply."),
                    _o("student", "Student visa — 20 hrs/week limit",
                       "Part-time, internships and placements only"),
                ],
            ),
            Question(
                id="visa_expiry",
                text="When does that visa expire?",
                kind=TEXT,
                why=(
                    "On a time-limited visa this is the real deadline, not your job search. "
                    "A Graduate visa lets you work anywhere for 2 years without sponsorship — "
                    "but to stay past it an employer must switch you to Skilled Worker. That "
                    "conversation has to happen well before the expiry date, so it shapes which "
                    "employers are worth applying to today."
                ),
                placeholder="July 2028   ·   or 'not applicable'",
            ),
            Question(
                id="sponsor_future",
                text="Do you need the employer to be able to sponsor you later?",
                kind=SINGLE,
                why=(
                    "The UK government publishes the register of licensed sponsors daily "
                    "(143,000 organisations). The system can check every employer against it, "
                    "so a company that could never keep you is filtered out before you spend "
                    "an application on it."
                ),
                options=[
                    _o("required", "Yes — only licensed sponsors",
                       "Strictest. Cuts the pool, but every application can lead somewhere long-term."),
                    _o("preferred", "Prefer them, but show me everything",
                       "Licensed sponsors ranked higher, others still shown."),
                    _o("dont_care", "No — I don't need sponsorship later",
                       "Settled, citizen, or leaving the UK anyway."),
                ],
            ),
            Question(
                id="work_mode",
                text="Working arrangement",
                kind=MULTI,
                allow_other=True,
                options=[
                    _o("remote", "Fully remote"),
                    _o("hybrid", "Hybrid"),
                    _o("onsite", "On-site"),
                ],
            ),
            Question(
                id="salary_floor",
                text="Lowest you'd accept (include the unit)",
                kind=TEXT,
                why="Without a floor the system will propose jobs you would certainly turn down.",
                placeholder="£45,000/year   ·   or £350/day for contract",
            ),
            Question(
                id="urgency",
                text="Where you are right now",
                kind=SINGLE,
                why=(
                    "Changes the whole acceptance threshold. Out of work means loosening the bar "
                    "and favouring speed; comfortably employed means tightening it and only "
                    "surfacing things genuinely worth your time."
                ),
                options=[
                    _o("urgent", "Out of work — need something soon", "Loosen the bar, favour volume"),
                    _o("switching", "Employed, actively looking to move", "Middle bar"),
                    _o("browsing", "Comfortable, just seeing what's out there", "Tight bar, only strong matches"),
                ],
            ),
            Question(
                id="company_size",
                text="Company size you'd like",
                kind=MULTI,
                allow_other=True,
                options=[
                    _o("startup_early", "Early startup (under 30)"),
                    _o("startup_growth", "Scaling startup (30 – 200)"),
                    _o("midsize", "Mid-size (200 – 1,000)"),
                    _o("large", "Large company (1,000+)"),
                ],
            ),
            Question(
                id="industries",
                tags=", ", suggest="industries",
                text="Industries or domains you want",
                kind=TEXT,
                # "Tích hết" chính là ĐỂ TRỐNG — nhưng trước đây không chỗ nào
                # nói ra, nên ô trống trông như một câu bị bỏ quên.
                why=("Để TRỐNG nghĩa là không kén ngành. Chọn vài ngành chỉ để "
                     "nói rõ mình ưu tiên chỗ nào — kho này đúng bằng bộ ngành "
                     "mà máy nhận ra được trên tin thật."),
                placeholder="fintech, healthtech, e-commerce, games…",
            ),
            Question(
                id="doc_language",
                text="What language are your CV and the postings in?",
                kind=SINGLE,
                why="Decides how text is tokenised for matching, and which CV the builder produces.",
                options=[
                    _o("en", "English", "Default for the UK / global market"),
                    _o("both", "English + Vietnamese", "Only needed if you're also targeting Vietnam"),
                ],
            ),
        ],
    ),
    # ------------------------------------------------------------------ 2
    Section(
        id="rang_buoc",
        title="What you won't take",
        why=(
            "The most-skipped section, but filtering here is far cheaper than reading and "
            "discarding later. Nothing comes to mind? Leave it blank — every time you reject "
            "a posting the system will ask why and add the reason here itself."
        ),
        questions=[
            Question(
                id="no_go",
                text="Things you would definitely not accept",
                kind=MULTI,
                allow_other=True,
                options=[
                    _o("onsite_only", "Fully on-site, no flexibility"),
                    _o("agency", "Posted through a recruitment agency",
                       "Middlemen, usually won't name the actual employer"),
                    _o("inside_ir35", "Contract inside IR35",
                       "Taxed as an employee without any of the employee benefits"),
                    _o("clearance", "Requires security clearance (SC / DV)",
                       "Usually needs 5–10 years of UK residency"),
                    _o("night_shift", "Night shifts on US hours"),
                    _o("contract", "Short-term contract / freelance"),
                    _o("crypto", "Crypto, gambling, MLM"),
                ],
            ),
            Question(
                id="tz_tolerance",
                text="How much time-zone offset can you live with?",
                kind=SINGLE,
                why="Measured from UK time. Remote postings almost always state an overlap requirement.",
                options=[
                    _o("uk_eu", "UK / Europe only", "0–2h offset"),
                    _o("us_east", "As far as US East Coast", "~5h — late afternoon meetings"),
                    _o("us_west", "As far as US West Coast", "~8h — evening meetings"),
                    _o("any", "Anything goes"),
                ],
            ),
            Question(
                id="no_go_other",
                text="Anything else you won't take?",
                kind=LONGTEXT,
                why="Để TRỐNG nghĩa là không kén ngành — app không lọc theo ngành nữa. "
                    "Chọn vài ngành chỉ để nói rõ mình ưu tiên chỗ nào.",
                placeholder="no PHP · no companies under 20 people · no frequent travel",
            ),
        ],
    ),
    # ------------------------------------------------------------------ 3
    Section(
        id="nang_luc",
        title="What you have",
        why="Raw material for matching and for building CVs. Without it, scoring is guesswork.",
        questions=[
            # `cv_text` KHÔNG vẽ ra form (đã có Import CV và tab CV lo việc
            # sửa), nhưng PHẢI ở lại schema: store.save() lọc theo schema, gỡ
            # khỏi đây là nó không lưu được nữa — và đó là nguồn sự thật nặng
            # nhất app, cv/blocks.py đọc nó ra khối kinh nghiệm, score.py chấm
            # theo từng khối.
            Question(
                id="cv_text",
                text="Toàn văn CV",
                kind=LONGTEXT,
                hidden=True,
            ),
            Question(
                id="years_real",
                text="How many years have you ACTUALLY worked?",
                kind=SINGLE,
                why=(
                    "Aim too high and you're filtered out before anyone reads the interesting part. "
                    "Aim too low and you're rejected as overqualified. Put the real number."
                ),
                options=[
                    _o("0-1", "Not yet / under 1 year"),
                    _o("1-3", "1 – 3 years"),
                    _o("3-5", "3 – 5 years"),
                    _o("5-8", "5 – 8 years"),
                    _o("8+", "8+ years"),
                ],
            ),
            Question(
                id="skills_strong",
            tags=", ", suggest="skills",
                text="Skills you're GENUINELY strong in",
                kind=TEXT,
                why="Matched directly against the requirements in the posting. Only list what you'd survive being grilled on.",
                placeholder="Python, pandas, SQL, portfolio optimisation, financial modelling",
            ),
            Question(
                id="skills_weak",
            tags=", ", suggest="skills",
                text="Skills you've touched or are learning",
                kind=TEXT,
                why=(
                    "Kept separate so they score differently. Lumping these in with your strong "
                    "skills is the fastest route to an interview that falls apart."
                ),
                placeholder="PyTorch, Bloomberg Terminal, kdb+",
            ),
            Question(
                id="stack_want",
            tags=", ", suggest="skills",
                text="Areas or tools you WANT to move into, even if you're not strong yet",
                kind=TEXT,
                why="Different from what you have. Used to rank postings, never to score a match.",
            ),
        ],
    ),
    # ------------------------------------------------------------------ 4
    # ------------------------------------------------------------------ 4
    Section(
        id="kinh_nghiem",
        title="Work experience",
        why=("Chỗ nhà tuyển dụng đọc đầu tiên. Mỗi việc một khối: chức danh, "
             "nơi làm, thời gian, rồi những câu nói bạn ĐÃ LÀM ĐƯỢC GÌ — "
             "có số thì càng tốt."),
        questions=[
            Question(
                id="experience_blocks",
                text="Việc đã làm",
                kind=BLOCKS,
                block_kind="experience",
                why=("Mỗi dòng trong phần mô tả là một câu có thể lên CV. Máy "
                     "chọn câu nào hợp tin nào — nên viết thêm câu là CV trúng "
                     "hơn, không phải chọn khéo hơn."),
                placeholder="Backtested alpha signals across 49 industry portfolios",
            ),
        ],
    ),
    # ------------------------------------------------------------------ 5
    Section(
        id="project",
        title="Personal project",
        optional=True,
        why=("Thứ tách bạn khỏi 40 người khác cùng khớp một tin: khớp thì qua "
             "được bộ lọc, còn BẰNG CHỨNG mới đưa bạn vào nhóm được gọi."),
        questions=[
            Question(
                id="project_blocks",
                text="Project của bạn",
                kind=BLOCKS,
                block_kind="project",
                why=("Làm dở cũng tính. Nhiều cái chỉ thiếu mỗi việc đo lại và "
                     "viết cho tử tế."),
                placeholder="Sharpe 0.74 in sample against 0.322 out-of-sample",
            ),
        ],
    ),
    Section(
        id="danh_tinh",
        title="Who you are",
        why="Needed when building CVs and sending applications. Leave blank until you get there.",
        questions=[
            Question(id="full_name", text="Full name", kind=TEXT),
            Question(id="email", text="Contact email", kind=TEXT,
                     placeholder="used to send applications and catch replies"),
            Question(id="phone", text="Phone", kind=TEXT),
            # Ô này TỪNG hứa hão: câu why nói nó lọc theo khu vực, mà cho
            # tới 12/09 không một dòng nào trong tìm/lọc đọc nó — chỉ CV và
            # điền form dùng. Còn "UK" thì đóng cứng ở ba chỗ trong mã nguồn.
            # Giờ nó quyết định thật: `filter.noi_o()` suy ra vùng, và việc
            # ngoài vùng đó bị loại kèm lý do ghi rõ vùng nào.
            Question(id="location", text="Where you're based", kind=TEXT,
                     why="Decides what counts as near you: postings outside "
                         "this area are dropped. Also printed on your CV and "
                         "filled into application forms.",
                     placeholder="London, UK"),
            Question(
                id="links",
                text="Profile links",
                kind=LONGTEXT,
                why="GitHub, LinkedIn, portfolio, blog. One per line.",
                placeholder="https://github.com/…\nhttps://linkedin.com/in/…",
            ),
            Question(
                id="notice_period",
                text="How much notice do you have to give?",
                kind=SINGLE,
                why="UK postings nearly always ask when you can start. Having it saves a round-trip.",
                options=[
                    _o("now", "Available immediately"),
                    _o("2w", "2 weeks"),
                    _o("1m", "1 month"),
                    _o("3m", "3 months"),
                ],
            ),
            Question(
                id="english_level",
                text="English level",
                kind=SINGLE,
                why="Decides whether international postings are filtered out. Judge honestly.",
                options=[
                    _o("basic", "Read documentation fine, speaking is hard"),
                    _o("working", "Working level — chat, email, ordinary meetings"),
                    _o("fluent", "Fluent — interviews and presentations are comfortable"),
                ],
            ),
            Question(
                id="education",
                text="Education",
                kind=ROWS,
                why=(
                    "For an early-career application this IS the main body of the CV, not a "
                    "footnote. Include module grades and classification — graduate schemes "
                    "filter on them directly.\n"
                    "MỘT BẰNG MỘT DÒNG, theo đúng dạng này thì máy điền hộ được form xin "
                    "việc: Bằng — Trường, Tháng Năm – Tháng Năm. Thiếu tháng thì mỗi lá đơn "
                    "bạn phải tự chọn lại ngày tốt nghiệp."
                ),
                placeholder="MSc Computational Finance — Royal Holloway, University of London, "
                            "2025–2026\n  Investment & Portfolio Management 86 · Deep Learning 83\n"
                            "BSc Economics — …, GPA 3.5/4.0, 2025",
            ),
            Question(
                id="certifications",
                tags="\n",
                text="Certifications and awards",
                kind=LONGTEXT,
                why=(
                    "Often the single strongest signal on an early-career CV, and postings "
                    "frequently name them outright. A ranked result is worth stating."
                ),
                placeholder="CFA Level I — Oct 2024, top 10% of global candidates\n"
                            "IBM Data Science Professional Certificate",
            ),
            Question(
                id="available_from",
                text="Available from",
                kind=TEXT,
                why="Still studying? Give the date you can start full-time. Postings ask this constantly.",
                placeholder="immediately   ·   or from October 2026",
            ),
            Question(
                id="languages",
                text="Languages you speak",
                kind=TEXT,
                why="Occasionally a real differentiator — desks covering a region want the language.",
                placeholder="English (fluent), Vietnamese (native)",
            ),
        ],
    ),
    # ------------------------------------------------------------------ 5
]


def all_questions() -> dict[str, Question]:
    return {q.id: q for s in SECTIONS for q in s.questions}


def section_by_id(section_id: str) -> Section | None:
    return next((s for s in SECTIONS if s.id == section_id), None)


def section_index(section_id: str) -> int:
    return next((i for i, s in enumerate(SECTIONS) if s.id == section_id), -1)


# Ba câu này là cổng chặn ingest. Thiếu là tìm ra rác.
#   job_titles  chuỗi đem đi tìm
#   markets     dùng nguồn nào
#   work_auth   ở UK đây là bộ lọc gắt nhất — thiếu thì đề xuất toàn tin không nộp được
INGEST_GATE = ("job_titles", "markets", "work_auth")

def suggestions(name: str) -> list[str]:
    """Kho gợi ý cho ô thẻ.

    "skills" lấy thẳng từ vựng chấm điểm: đó là danh sách máy THẬT SỰ nhận ra
    khi đọc tin. Bịa một danh sách riêng cho màn hình thì người dùng chọn được
    từ mà máy không biết đọc — gợi ý xong vẫn không ăn thua.

    "titles" KHÔNG nằm ở đây, cố ý. Chức danh phải rút từ TIN THẬT (xem
    profile/titles.py): một danh sách gõ tay trong mã sai ngay từ ngày viết và
    mục dần từ đó — thị trường đẻ chức danh mới liên tục mà không ai nhớ vào
    sửa file. Bên gọi truyền kho vào.
    """
    if name == "skills":
        from ..scoring.vocab import ALIASES
        return sorted(set(ALIASES.values()))
    if name == "industries":
        # Kho ngành ĐÃ CÓ trong scoring/vocab.py — cùng bộ từ máy dùng để
        # đọc tin. Gõ một danh sách riêng cho màn hình thì người dùng chọn
        # được ngành mà máy không biết nhận ra.
        from ..scoring.vocab import INDUSTRY
        return sorted(INDUSTRY)
    return []