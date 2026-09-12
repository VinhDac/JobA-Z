"""Từ vựng để nhận ra một dòng yêu cầu đang đòi cái gì.

Không có LLM ở đây. Cố ý:
  - Chạy trên 4.000 tin mà không tốn xu nào
  - Cùng đầu vào luôn cho cùng đầu ra -> test được -> bắt được lỗi
  - LLM để dành cho chỗ so chuỗi bó tay (bước 2b)

Từ vựng nghiêng về mảng quant / tài chính / dữ liệu — đúng dải của người dùng.
Thiếu từ thì thêm vào đây, không sửa chỗ khác.
"""

from __future__ import annotations

import re

# --------------------------------------------------------------- kỹ năng
# key = tên chuẩn, value = các cách viết khác (đã thường hoá)
SKILLS: dict[str, set[str]] = {
    # ngôn ngữ
    "python": {"python", "python3"},
    "c++": {"c++", "cpp"},
    "java": {"java"},
    "scala": {"scala"},
    "go": {"go", "golang"},
    "rust": {"rust"},
    "r": {" r ", "r language"},
    "matlab": {"matlab"},
    "sql": {"sql", "postgres", "postgresql", "mysql", "t-sql"},
    "kdb": {"kdb", "kdb+", "q language"},
    "javascript": {"javascript", "typescript", "js"},
    "excel": {"excel", "vba"},
    # dữ liệu / ML
    "pandas": {"pandas"},
    "numpy": {"numpy"},
    "scipy": {"scipy"},
    "scikit-learn": {"scikit-learn", "sklearn", "scikit learn"},
    "pytorch": {"pytorch", "torch"},
    "tensorflow": {"tensorflow", "keras"},
    "spark": {"spark", "pyspark"},
    "machine learning": {"machine learning", "ml ", "supervised learning"},
    "deep learning": {"deep learning", "neural network", "neural networks"},
    "nlp": {"nlp", "natural language processing", "llm", "large language model"},
    "time series": {"time series", "time-series", "timeseries"},
    "statistics": {"statistics", "statistical", "econometric", "econometrics"},
    "probability": {"probability", "stochastic"},
    "optimisation": {"optimisation", "optimization", "convex"},
    "bayesian": {"bayesian"},
    "data pipeline": {"etl", "data pipeline", "airflow", "dbt", "kafka"},
    "visualisation": {"visualisation", "visualization", "tableau", "power bi", "matplotlib"},
    # tài chính
    "portfolio": {"portfolio", "asset allocation", "efficient frontier",
                  "portfolio construction", "rebalanc", "position sizing"},
    "derivatives": {"derivative", "derivatives", "options", "futures", "swaps"},
    "equities": {"equity", "equities", "stocks"},
    "fixed income": {"fixed income", "bonds", "credit"},
    "risk": {"risk management", "market risk", "credit risk", "var ", "value at risk",
             "drawdown", "sharpe", "risk limit", "risk budget"},
    "alpha research": {"alpha", "signal research", "systematic trading", "quant research"},
    "backtesting": {"backtest", "backtesting", "walk-forward", "walk forward",
                    "paper trading", "simulation"},
    # Nhóm này thiếu hẳn, mà nó chính là chuyên môn phân biệt người biết việc
    # với người mới học: biết một con số có đáng tin không.
    "validation": {"out-of-sample", "out of sample", "cross-validation",
                   "cross validation", "look-ahead", "look ahead bias",
                   "data leakage", "data snooping", "overfit", "overfitting",
                   "train/test", "train test split", "holdout", "regime"},
    "market data": {"market data", "bloomberg", "refinitiv", "reuters"},
    "asset pricing": {"asset pricing", "pricing model", "valuation"},
    "factor models": {"factor model", "factor models", "fama"},
    "cfa": {"cfa"},
    "frm": {"frm"},
    # hạ tầng
    "linux": {"linux", "unix", "bash", "shell scripting"},
    "docker": {"docker", "container"},
    "kubernetes": {"kubernetes", "k8s"},
    "cloud": {"aws", "gcp", "azure", "cloud"},
    "git": {"git", "version control"},
    "ci/cd": {"ci/cd", "continuous integration", "jenkins"},
}

# --------------------------------------------------------- bằng cấp / năm
DEGREE_WORDS = {
    "phd": {"phd", "ph.d", "doctorate", "doctoral"},
    "masters": {"master", "masters", "msc", "ms", "m.sc", "mba", "postgraduate", "meng"},
    "bachelors": {"bachelor", "bachelors", "bsc", "b.sc", "ba", "bs", "beng",
                  "undergraduate", "degree"},
}
QUANT_FIELD = {"mathematics", "maths", "math", "physics", "statistics", "computer science",
               "engineering", "quantitative", "computational", "economics", "finance",
               "econometrics", "operations research", "stem"}

YEARS = re.compile(r"(\d+)\s*(?:\+|\s*-\s*\d+)?\s*(?:or more\s*)?year", re.I)

# ------------------------------------------------------------- phân loại
# Tiêu đề mở đầu một phần YÊU CẦU
REQ_HEADS = re.compile(
    r"^\s*(requirements?|qualifications?|what we(?:'re| are)? looking for|"
    r"who you are|about you|you(?:'ll| will)? have|you have|your profile|"
    r"skills? (?:and|&) experience|experience required|what you(?:'ll| will)? bring|"
    r"ideal candidate|must[- ]haves?|essential|the ideal)", re.I)

# Tiêu đề mở đầu phần VIỆC PHẢI LÀM.
#
# Nửa này của JD trước giờ bị vứt. Đo ngày 10/09 trên 176 tin: 48% có phần YÊU
# CẦU (đang đọc), 47% có phần VIỆC PHẢI LÀM (bỏ qua) — mà chính nửa thứ hai
# mới mô tả công việc, tức là mô tả sẵn một project trông thế nào.
DO_HEADS = re.compile(
    r"^\s*(responsibilit\w+|the role|your role|role (?:overview|summary)|"
    r"what you(?:'ll| will)? (?:do|be doing)|key (?:duties|responsibilities|tasks)|"
    r"duties|day[- ]to[- ]day|the job|what the (?:role|job) involves|"
    r"in this role|you will be|your impact|the opportunity|"
    r"about the (?:role|position)|job description)", re.I)

# Tiêu đề mở đầu phần ĐIỂM CỘNG
NICE_HEADS = re.compile(
    r"^\s*(nice[- ]to[- ]haves?|bonus|preferred|desirable|advantageous|"
    r"plus(?:es)?|it would be great|good to have)", re.I)

# Tiêu đề KHÔNG phải yêu cầu — phải loại, nếu không sẽ chấm điểm dựa trên
# phúc lợi công ty ("we offer 25 days holiday")
STOP_HEADS = re.compile(
    r"^\s*(what we offer|benefits?|perks?|our offer|compensation|salary|"
    r"about (?:us|the (?:company|team|firm))|why join|diversity|equal opportunit|"
    r"how to apply|application process|next steps|our values?|life at)", re.I)

# Dấu hiệu bắt buộc / không bắt buộc ngay trong câu
MUST_WORDS = re.compile(r"\b(must|required|essential|strong|proven|solid|demonstrated)\b", re.I)
NICE_WORDS = re.compile(
    r"\b(nice to have|bonus|preferred|desirable|advantage|a plus|would be great|"
    r"ideally|familiarity)\b", re.I)


def alias_map() -> dict[str, str]:
    """Mọi cách viết -> tên chuẩn."""
    out: dict[str, str] = {}
    for canonical, forms in SKILLS.items():
        out[canonical] = canonical
        for form in forms:
            out[form.strip()] = canonical
    return out


ALIASES = alias_map()


# --------------------------------------------------------------- khớp alias
# Khớp CHUỖI CON là sai, và sai to: 'excel' nằm trong 'excellent', nên 70 tin
# đang giữ được gắn kỹ năng Excel chỉ vì JD viết "excellent communication" —
# và nhóm project lớn nhất trên màn hình /projects mọc lên từ đó. Cùng kiểu:
# 'scala' trong 'scalable' (46 tin), 'rust' trong 'trust' (35), 'valuation'
# trong 'evaluation' (10).
#
# Nhưng cấm hẳn chuỗi con thì mất phần lớn cái ĐÚNG, vì tiếng Anh chia đuôi:
# backtesting, derivatives, pipelines, containerisation, portfolios. Nên luật
# là: phải đúng RANH GIỚI TỪ ở đầu, và chỉ cho phép một cái ĐUÔI CHIA ở cuối.
_TAIL = r"(?:s|es|ed|ing|ings|ation|ations|isation|isations|ization|izations)?"


def _alias_pattern(alias: str) -> re.Pattern:
    return re.compile(r"\b" + re.escape(alias) + _TAIL + r"\b")


_ALIAS_RE: dict[str, tuple[re.Pattern, str]] = {
    alias: (_alias_pattern(alias), canonical)
    for alias, canonical in ALIASES.items() if alias.strip()
}


def alias_hits(normed: str) -> list[str]:
    """Tên chuẩn của mọi kỹ năng có mặt trong CHỮ ĐÃ CHUẨN HOÁ, giữ thứ tự.

    Đầu vào phải đi qua ingest.base.norm trước — luật ranh giới từ dựa vào
    việc dấu câu đã thành khoảng trắng.
    """
    found: list[str] = []
    for pattern, canonical in _ALIAS_RE.values():
        if canonical not in found and pattern.search(normed):
            found.append(canonical)
    return found


# ------------------------------------------------------------------ ngành
# BẢY NHÃN, không hơn. Đây là bộ từ dùng cho ô "ngành" trong hồ sơ: gõ một
# danh sách riêng cho màn hình thì người dùng chọn được ngành mà máy không
# biết nhận ra.
#
# Trước ở projects/inventory.py. Nó chưa bao giờ thuộc về tính năng đó — đây
# là TỪ VỰNG, mà từ vựng thì ở đây: "thiếu từ thì thêm vào đây, không sửa chỗ
# khác".
INDUSTRY: dict[str, set[str]] = {
    "hedge fund": {"hedge fund", "systematic fund", "multi-strategy",
                   "multi strategy", "prop trading", "proprietary trading",
                   "market making", "market maker", "quant fund"},
    # "structuring" trần bị bỏ: đo được nó khớp vào "cleansing and structuring
    # for downstream" — cấu trúc DỮ LIỆU, không phải cấu trúc sản phẩm tài chính.
    "investment bank": {"investment bank", "sell-side", "sell side",
                        "trading desk", "front office", "deal structuring",
                        "product structuring"},
    "asset management": {"asset management", "asset manager", "buy-side",
                         "buy side", "wealth management", "pension fund",
                         "fund management", "institutional investor"},
    "fintech": {"fintech", "payment", "neobank", "challenger bank",
                "lending platform", "e-money"},
    "insurance": {"insurance", "insurer", "actuarial", "reinsurance",
                  "underwriting"},
    "crypto": {"crypto", "cryptocurrency", "cryptocurrencies", "cryptoasset",
               "digital asset", "blockchain", "defi"},
    "energy": {"energy trading", "commodity trading", "commodities trading",
               "power trading", "carbon market"},
}
