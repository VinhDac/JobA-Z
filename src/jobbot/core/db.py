"""SQLite — một file, không cần server, restart không mất dữ liệu.

Migration chạy tiến, không lùi. Mỗi thay đổi schema thêm một phần tử vào
MIGRATIONS, không bao giờ sửa phần tử cũ — DB đang chạy thật ngoài kia.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from .paths import db_path

# Chỉ THÊM vào cuối. Không sửa, không xoá phần tử đã có.
MIGRATIONS: list[str] = [
    # 1 — hồ sơ người dùng, lưu theo phiên bản (M0)
    """
    CREATE TABLE profile_version (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        created_at TEXT    NOT NULL,
        note       TEXT
    );
    CREATE TABLE profile_answer (
        version_id  INTEGER NOT NULL REFERENCES profile_version(id) ON DELETE CASCADE,
        question_id TEXT    NOT NULL,
        value_json  TEXT    NOT NULL,
        PRIMARY KEY (version_id, question_id)
    );
    """,
    # 2 — tin tuyển dụng: raw (nguyên văn) / posting (đã chuẩn hoá) / nhật ký
    """
    CREATE TABLE raw_posting (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        source      TEXT    NOT NULL,     -- 'linkedin' | 'greenhouse:monzo'
        source_id   TEXT    NOT NULL,     -- id bên nguồn
        url         TEXT,
        fetched_at  TEXT    NOT NULL,
        payload     TEXT    NOT NULL,     -- JSON nguyên văn, không đụng vào
        UNIQUE (source, source_id)
    );

    CREATE TABLE posting (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        raw_id       INTEGER NOT NULL REFERENCES raw_posting(id) ON DELETE CASCADE,
        source       TEXT    NOT NULL,
        title        TEXT    NOT NULL,
        company      TEXT    NOT NULL,
        location     TEXT    NOT NULL DEFAULT '',
        remote       INTEGER NOT NULL DEFAULT 0,
        salary       TEXT    NOT NULL DEFAULT '',
        url          TEXT    NOT NULL DEFAULT '',
        posted_at    TEXT    NOT NULL DEFAULT '',
        description  TEXT    NOT NULL DEFAULT '',
        fingerprint  TEXT    NOT NULL,    -- công ty + chức danh đã chuẩn hoá
        group_id     TEXT,                -- cùng group_id = cùng một việc
        kept         INTEGER NOT NULL DEFAULT 1,   -- 0 = bị lọc bỏ
        drop_reason  TEXT    NOT NULL DEFAULT '',
        UNIQUE (raw_id)
    );
    CREATE INDEX posting_fp    ON posting(fingerprint);
    CREATE INDEX posting_group ON posting(group_id);
    CREATE INDEX posting_kept  ON posting(kept);

    CREATE TABLE source_run (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        source     TEXT    NOT NULL,
        started_at TEXT    NOT NULL,
        ok         INTEGER NOT NULL,
        fetched    INTEGER NOT NULL DEFAULT 0,
        new_rows   INTEGER NOT NULL DEFAULT 0,
        error      TEXT    NOT NULL DEFAULT ''
    );

    -- Ghi từ BƯỚC 1. Thiếu thì đến bước 6 không có gì để đếm và không lấy lại được.
    CREATE TABLE audit (
        id     INTEGER PRIMARY KEY AUTOINCREMENT,
        at     TEXT NOT NULL,
        kind   TEXT NOT NULL,
        detail TEXT NOT NULL DEFAULT ''
    );
    CREATE INDEX audit_at ON audit(at);
    """,
    # 3 — vòng đời ứng tuyển + thư đọc từ hộp thư
    """
    CREATE TABLE application (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        company       TEXT    NOT NULL,
        company_key   TEXT    NOT NULL,          -- tên đã chuẩn hoá, để khớp
        role          TEXT    NOT NULL DEFAULT '',
        posting_id    INTEGER REFERENCES posting(id),
        origin        TEXT    NOT NULL DEFAULT 'mail',   -- mail | manual | auto
        applied_at    TEXT    NOT NULL,
        stage         TEXT    NOT NULL DEFAULT 'applied',
        last_event_at TEXT    NOT NULL DEFAULT '',
        last_event    TEXT    NOT NULL DEFAULT '',
        UNIQUE (company_key, role)
    );
    CREATE INDEX application_stage ON application(stage);

    CREATE TABLE message (
        id             INTEGER PRIMARY KEY AUTOINCREMENT,
        msg_id         TEXT    NOT NULL UNIQUE,  -- Message-ID của thư
        from_addr      TEXT    NOT NULL DEFAULT '',
        from_name      TEXT    NOT NULL DEFAULT '',
        subject        TEXT    NOT NULL DEFAULT '',
        received_at    TEXT    NOT NULL DEFAULT '',
        snippet        TEXT    NOT NULL DEFAULT '',
        kind           TEXT    NOT NULL DEFAULT 'other',
        company_guess  TEXT    NOT NULL DEFAULT '',
        application_id INTEGER REFERENCES application(id),
        needs_you      INTEGER NOT NULL DEFAULT 0
    );
    CREATE INDEX message_kind ON message(kind);
    CREATE INDEX message_app  ON message(application_id);
    """,
    # 4 — mốc thời gian dạng số. posted_at là chuỗi và mỗi nguồn một kiểu
    # (ISO của Greenhouse/Lever, unix của Arbeitnow) nên SQL không so được.
    """
    ALTER TABLE posting ADD COLUMN posted_ts INTEGER NOT NULL DEFAULT 0;
    CREATE INDEX posting_ts ON posting(posted_ts);
    """,
    # 5 — điểm khớp. score NULL = chưa chấm HOẶC không đọc được yêu cầu;
    # score_conf phân biệt hai trường hợp đó.
    """
    ALTER TABLE posting ADD COLUMN score INTEGER;
    ALTER TABLE posting ADD COLUMN score_conf TEXT NOT NULL DEFAULT '';
    ALTER TABLE posting ADD COLUMN score_json TEXT NOT NULL DEFAULT '';
    CREATE INDEX posting_score ON posting(score);
    """,
    # 6 — công ty mục tiêu. Đi thẳng trang tuyển dụng của họ thay vì qua
    # board trung gian: tên công ty không mơ hồ, JD nguyên bản, và có sẵn
    # đúng form để nộp ở bước 5.
    """
    CREATE TABLE company (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        name         TEXT    NOT NULL,
        key          TEXT    NOT NULL UNIQUE,     -- tên đã chuẩn hoá
        domain       TEXT    NOT NULL DEFAULT '',
        careers_url  TEXT    NOT NULL DEFAULT '',
        ats          TEXT    NOT NULL DEFAULT '', -- greenhouse|lever|ashby|workday|...
        ats_slug     TEXT    NOT NULL DEFAULT '',
        is_agency    INTEGER NOT NULL DEFAULT 0,  -- 1 = môi giới, không phải chủ việc
        checked_at   TEXT    NOT NULL DEFAULT '',
        roles_found  INTEGER NOT NULL DEFAULT 0,
        note         TEXT    NOT NULL DEFAULT ''
    );
    CREATE INDEX company_ats ON company(ats);
    ALTER TABLE posting ADD COLUMN via_agency INTEGER NOT NULL DEFAULT 0;
    """,
    # 7 — `kept` mặc định 1 nghĩa là tin vừa nạp đã được coi là "giữ" trước khi
    # vòng lọc chạy. Bất cứ ai đọc DB giữa hai bước đó đều thấy tin chưa lọc.
    # Mặc định đúng là 0: chưa phán thì chưa hiện.
    """
    CREATE TABLE posting_new (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        raw_id INTEGER NOT NULL REFERENCES raw_posting(id) ON DELETE CASCADE,
        source TEXT NOT NULL, title TEXT NOT NULL, company TEXT NOT NULL,
        location TEXT NOT NULL DEFAULT '', remote INTEGER NOT NULL DEFAULT 0,
        salary TEXT NOT NULL DEFAULT '', url TEXT NOT NULL DEFAULT '',
        posted_at TEXT NOT NULL DEFAULT '', description TEXT NOT NULL DEFAULT '',
        fingerprint TEXT NOT NULL, group_id TEXT,
        kept INTEGER NOT NULL DEFAULT 0,           -- 0 = chưa phán HOẶC đã bị lọc
        drop_reason TEXT NOT NULL DEFAULT 'not judged yet',
        posted_ts INTEGER NOT NULL DEFAULT 0,
        score INTEGER, score_conf TEXT NOT NULL DEFAULT '',
        score_json TEXT NOT NULL DEFAULT '',
        via_agency INTEGER NOT NULL DEFAULT 0,
        UNIQUE (raw_id)
    );
    INSERT INTO posting_new SELECT id, raw_id, source, title, company, location,
        remote, salary, url, posted_at, description, fingerprint, group_id, kept,
        drop_reason, posted_ts, score, score_conf, score_json, via_agency FROM posting;
    DROP TABLE posting;
    ALTER TABLE posting_new RENAME TO posting;
    CREATE INDEX posting_fp    ON posting(fingerprint);
    CREATE INDEX posting_group ON posting(group_id);
    CREATE INDEX posting_kept  ON posting(kept);
    CREATE INDEX posting_ts    ON posting(posted_ts);
    CREATE INDEX posting_score ON posting(score);
    """,
    # 8 — sửa ba lỗi LÕI, không phải vá:
    #
    # (a) Tầng raw không thật sự raw. `posting.description` là bản DUY NHẤT của
    #     mô tả; strip_html sai là mất gốc, mà tin LinkedIn hết hạn thì không
    #     fetch lại được. Giờ giữ nguyên văn trong raw_posting.body.
    #
    # (b) Phán quyết (kept/score) không gắn với PHIÊN BẢN hồ sơ và PHIÊN BẢN
    #     luật đã sinh ra nó. Đổi hồ sơ hay đổi luật thì mọi phán quyết cũ
    #     thành sai — im lặng, không ai biết cái nào còn dùng được.
    #
    # (c) Không có cách tính lại toàn bộ tầng suy diễn từ tầng raw.
    """
    ALTER TABLE raw_posting ADD COLUMN body TEXT NOT NULL DEFAULT '';
    ALTER TABLE posting ADD COLUMN judged_profile INTEGER NOT NULL DEFAULT 0;
    ALTER TABLE posting ADD COLUMN judged_rules TEXT NOT NULL DEFAULT '';
    ALTER TABLE posting ADD COLUMN scored_rules TEXT NOT NULL DEFAULT '';
    CREATE INDEX posting_judged ON posting(judged_profile, judged_rules);
    """,
    # 9 — nguồn hỏng phải TRÔNG khác nguồn chạy tốt.
    # Trước đây vòng đọc kỹ nuốt mọi ngoại lệ (`except Exception: continue`),
    # nên một nguồn đổi giao diện và hỏng 100% trông y hệt nguồn bình thường:
    # ok=1, không có mô tả nào, không ai biết.
    """
    ALTER TABLE source_run ADD COLUMN attempted INTEGER NOT NULL DEFAULT 0;
    ALTER TABLE source_run ADD COLUMN failed INTEGER NOT NULL DEFAULT 0;
    """,
    # 10 — "khớp" khác "có cửa". Điểm khớp cao ở một tin đòi PhD và 5 năm kinh
    # nghiệm không nói lên gì về xác suất được gọi. Tách hai thứ ra.
    """
    ALTER TABLE posting ADD COLUMN realism TEXT NOT NULL DEFAULT '';
    ALTER TABLE posting ADD COLUMN realism_why TEXT NOT NULL DEFAULT '';
    ALTER TABLE posting ADD COLUMN deadline TEXT NOT NULL DEFAULT '';
    ALTER TABLE posting ADD COLUMN deadline_ts INTEGER NOT NULL DEFAULT 0;
    CREATE INDEX posting_realism ON posting(realism);
    """,
    # 11 — điểm cũng phải gắn phiên bản HỒ SƠ, không chỉ phiên bản luật.
    # Thiếu cột này thì đổi hồ sơ chỉ lọc lại chứ không chấm lại: 72/204 tin
    # đang giữ bị đóng băng ở score=NULL vì chúng được chấm lúc còn rỗng mô tả.
    # DEFAULT 0 = "chưa chấm với hồ sơ nào" -> mọi tin cũ tự thành cần chấm lại.
    """
    ALTER TABLE posting ADD COLUMN scored_profile INTEGER NOT NULL DEFAULT 0;
    """,
    # 12 — nhật ký chạy: mỗi dòng thuộc một LUỒNG và có MỨC.
    # Nhờ luồng mà tab Search chỉ hiện việc của Search; nhờ mức mà lỗi không
    # nằm lẫn với dòng thường. Dòng cũ không có -> mặc định 'system'/'info'.
    """
    ALTER TABLE audit ADD COLUMN stream TEXT NOT NULL DEFAULT 'system';
    ALTER TABLE audit ADD COLUMN level  TEXT NOT NULL DEFAULT 'info';
    CREATE INDEX audit_stream ON audit(stream, id);
    """,
    # 13 — tuỳ chọn của APP (khác profile_answer: đó là hồ sơ NGƯỜI DÙNG).
    # Chỗ để nhớ "có tự quét khi mở app không" qua các lần khởi động.
    """
    CREATE TABLE pref (
        key   TEXT PRIMARY KEY,
        value TEXT NOT NULL
    );
    """,
    # 14 — KHO PROJECT. Trước đây pipeline sinh đề bài rồi vẽ ra màn hình và
    # VỨT: mỗi lần mở trang chạy lại cả bảy chặng, không có gì tích lại.
    # Một project làm mất 2-3 ngày thì nó phải sống lâu hơn một lần vẽ trang.
    #
    # skills = TRỤC (kỹ năng nào project này chứng minh được)
    # industries = NHÃN (ngành nào kể được câu chuyện này)
    # Trục là kỹ năng chứ không phải nhóm JD: nhóm sinh ra từ dữ liệu nên đổi
    # là đề bài mồ côi — đã xảy ra thật với nhóm ma 'excel'.
    """
    CREATE TABLE project (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        question    TEXT NOT NULL,
        skills      TEXT NOT NULL DEFAULT '',
        industries  TEXT NOT NULL DEFAULT '',
        state       TEXT NOT NULL DEFAULT 'de_bai',
        brief_json  TEXT NOT NULL DEFAULT '',
        link        TEXT NOT NULL DEFAULT '',
        made_at     TEXT NOT NULL
    );
    CREATE INDEX project_state ON project(state);
    """,
    # 15 — BẢN CV nào đã gửi cho lần nộp nào. Không có cột này thì mở bảng ra
    # chỉ biết "đã nộp Point72", không biết đã đưa họ bản nào — mà 43 bản khác
    # nhau, và khi họ gọi phỏng vấn thì phải đọc lại đúng bản đó.
    """
    ALTER TABLE application ADD COLUMN cv_file TEXT NOT NULL DEFAULT '';
    ALTER TABLE application ADD COLUMN note    TEXT NOT NULL DEFAULT '';
    """,
    # 16 — TÊN KHỐI mà máy đã chèn vào CV. Chèn xong thì trong cv_text nó
    # không khác gì project người dùng tự viết — không có cột này thì sau đó
    # không cách nào chỉ ra "cái này máy đẻ ra". Đã xảy ra thật: khối "Alpha
    # Research" nằm trong CV suốt và phải so hai phiên bản liền nhau mới truy
    # ra được.
    #
    # Dấu để Ở ĐÂY chứ KHÔNG để trong cv_text: bản CV đó gửi cho nhà tuyển
    # dụng, không được mang chú thích nội bộ nào.
    """
    ALTER TABLE project ADD COLUMN cv_title TEXT NOT NULL DEFAULT '';
    """,
    # 17 — NGƯỜI giữ lại một tin máy đã loại.
    #
    # `kept` là cột SUY RA: derive() tính lại nó từ luật + hồ sơ, và tính lại
    # MỖI LẦN hồ sơ đổi phiên bản. Nên sửa thẳng kept=1 bằng tay là một quyết
    # định có hạn sử dụng: lần sau Vin chỉnh một chữ trong hồ sơ là nó bị ghi
    # đè, im lặng, không báo gì — và điểm vừa chấm cũng bị xoá theo.
    #
    # Quyết định của NGƯỜI phải nằm ở cột RIÊNG, và derive() đọc nó. Đây đúng
    # là luật "máy đề xuất, người duyệt" của cả app, chỉ là lần này người
    # duyệt ngược lại máy.
    """
    ALTER TABLE posting ADD COLUMN user_keep INTEGER NOT NULL DEFAULT 0;
    CREATE INDEX posting_user_keep ON posting(user_keep);
    """,
    # 18 — BỎ HẲN personal project. Máy không nghĩ đề bài nữa; Vin tự chọn
    # project của mình.
    #
    # Vì sao bỏ: bảng này sống được 14 bước migration và giữ đúng 0 dòng.
    # Đổi lại là 1.253 dòng máy dựng đề bài cộng 955 dòng khung repo. Cách
    # thay thế — lấy project mẫu trên YouTube — đo ra không sạch: lượt tìm
    # "data science portfolio project tutorial" cho 0/10 là project thật
    # (9/10 là video dạy làm website), nên máy khớp từ khoá không có cách nào
    # chọn đúng; và chính cổng TUTORIAL trong brief.py đã loại sẵn lớp đó.
    #
    # Bước 14 và 16 KHÔNG sửa: DB nào đã chạy qua chúng rồi thì sửa lại là
    # viết lại lịch sử. Danh sách này chỉ được thêm vào đuôi.
    #
    # Hai thứ trong cụm đó KHÔNG chết theo, vì chúng chưa bao giờ thuộc về
    # nó: phép đếm thị trường (-> scoring/market.py) và bộ từ ngành
    # (-> scoring/vocab.py). Cả hai chỉ đọc `posting`, không biết project là gì.
    """
    DROP INDEX IF EXISTS project_state;
    DROP TABLE IF EXISTS project;
    """,
    # 19 — BẢN CV ĐÃ DỰNG, cất lại. Trước đây tab CV dựng ngay lúc vẽ trang:
    # đo được 5,3 giây cho 364 tin, mỗi lần mở tab. Người vừa search xong chưa
    # tới bước làm CV, mà vẫn phải chờ 5 giây để xem thứ mình chưa yêu cầu.
    #
    # ĐÚNG MỘT DÒNG (CHECK id = 1). Không giữ lịch sử: "trước" trong bản so
    # sánh before/after là CV GỐC của Vin, không phải lần dựng trước — giữ
    # lịch sử ở đây là giữ thứ không ai đọc.
    #
    # `stamp` là dấu cũ-mới: chữ CV + luật viết + luật chấm + tập tin. Nút
    # Chạy đọc nó để biết nên ghi "Chạy", "Cập nhật" hay "Dựng lại".
    """
    CREATE TABLE cv_build (
        id       INTEGER PRIMARY KEY CHECK (id = 1),
        made_at  TEXT NOT NULL,
        stamp    TEXT NOT NULL,
        payload  TEXT NOT NULL
    );
    """,
]


SECRET = 0o600      # chỉ chủ máy đọc — xem _lock_down


def _lock_down(path: Path) -> None:
    """Chỉ chủ máy đọc được DB, và cả tệp WAL/SHM đi kèm.

    Trong đó có TOÀN VĂN CV, hồ sơ cá nhân, và tiêu đề + 400 ký tự đầu của mọi
    thư tuyển dụng. Mặc định của sqlite là 0644 — bất kỳ tài khoản nào trên
    máy cũng đọc được. Đặt một lần lúc mở kết nối thì không phải nhớ.
    """
    for suffix in ("", "-wal", "-shm"):
        try:
            target = Path(str(path) + suffix)
            if target.exists() and (target.stat().st_mode & 0o077):
                target.chmod(SECRET)
        except OSError:
            pass


def connect(path: Path | None = None) -> sqlite3.Connection:
    path = path or db_path()
    conn = sqlite3.connect(path)
    _lock_down(Path(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")   # đọc được trong lúc đang ghi (chạy 24/7)
    migrate(conn)
    return conn


def migrate(conn: sqlite3.Connection) -> int:
    """Chạy các migration còn thiếu. Trả về số migration vừa chạy."""
    current = conn.execute("PRAGMA user_version").fetchone()[0]
    ran = 0
    for index in range(current, len(MIGRATIONS)):
        conn.executescript(MIGRATIONS[index])
        conn.execute(f"PRAGMA user_version = {index + 1}")
        conn.commit()
        ran += 1
    return ran
