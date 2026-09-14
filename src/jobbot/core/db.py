"""SQLite — one file, no server, nothing lost on restart.

Migrations run forward only. Every schema change appends an entry to
MIGRATIONS and never edits an old one — there is a real DB running out there.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from .paths import db_path

# APPEND only. Never edit, never delete an existing entry.
MIGRATIONS: list[str] = [
    # 1 — the user profile, stored per version (M0)
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
    # 2 — postings: raw (verbatim) / posting (normalised) / the audit log
    """
    CREATE TABLE raw_posting (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        source      TEXT    NOT NULL,     -- 'linkedin' | 'greenhouse:monzo'
        source_id   TEXT    NOT NULL,     -- the id on the source side
        url         TEXT,
        fetched_at  TEXT    NOT NULL,
        payload     TEXT    NOT NULL,     -- verbatim JSON, never touched
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
        fingerprint  TEXT    NOT NULL,    -- normalised company + title
        group_id     TEXT,                -- same group_id = the same job
        kept         INTEGER NOT NULL DEFAULT 1,   -- 0 = filtered out
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

    -- Written from STEP 1. Without it, step 6 has nothing to count and no
    -- way to reconstruct it.
    CREATE TABLE audit (
        id     INTEGER PRIMARY KEY AUTOINCREMENT,
        at     TEXT NOT NULL,
        kind   TEXT NOT NULL,
        detail TEXT NOT NULL DEFAULT ''
    );
    CREATE INDEX audit_at ON audit(at);
    """,
    # 3 — the application lifecycle + mail read from the mailbox
    """
    CREATE TABLE application (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        company       TEXT    NOT NULL,
        company_key   TEXT    NOT NULL,          -- normalised name, for matching
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
        msg_id         TEXT    NOT NULL UNIQUE,  -- the mail's Message-ID
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
    # 4 — a numeric timestamp. posted_at is a string and each source uses a
    # different shape (ISO for Greenhouse/Lever, unix for Arbeitnow), so SQL
    # cannot compare them.
    """
    ALTER TABLE posting ADD COLUMN posted_ts INTEGER NOT NULL DEFAULT 0;
    CREATE INDEX posting_ts ON posting(posted_ts);
    """,
    # 5 — the match score. score NULL = not scored yet OR the requirements
    # could not be read; score_conf tells those two apart.
    """
    ALTER TABLE posting ADD COLUMN score INTEGER;
    ALTER TABLE posting ADD COLUMN score_conf TEXT NOT NULL DEFAULT '';
    ALTER TABLE posting ADD COLUMN score_json TEXT NOT NULL DEFAULT '';
    CREATE INDEX posting_score ON posting(score);
    """,
    # 6 — target companies. Going straight to their careers page rather than
    # through an intermediary board: the company name is unambiguous, the JD
    # is the original, and the right application form is already there for
    # step 5.
    """
    CREATE TABLE company (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        name         TEXT    NOT NULL,
        key          TEXT    NOT NULL UNIQUE,     -- the normalised name
        domain       TEXT    NOT NULL DEFAULT '',
        careers_url  TEXT    NOT NULL DEFAULT '',
        ats          TEXT    NOT NULL DEFAULT '', -- greenhouse|lever|ashby|workday|...
        ats_slug     TEXT    NOT NULL DEFAULT '',
        is_agency    INTEGER NOT NULL DEFAULT 0,  -- 1 = an agency, not the employer
        checked_at   TEXT    NOT NULL DEFAULT '',
        roles_found  INTEGER NOT NULL DEFAULT 0,
        note         TEXT    NOT NULL DEFAULT ''
    );
    CREATE INDEX company_ats ON company(ats);
    ALTER TABLE posting ADD COLUMN via_agency INTEGER NOT NULL DEFAULT 0;
    """,
    # 7 — `kept` defaulting to 1 meant a freshly loaded posting counted as
    # "kept" before the filter had run. Anyone reading the DB between those
    # two steps saw unfiltered postings. The right default is 0: not judged,
    # not shown.
    """
    CREATE TABLE posting_new (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        raw_id INTEGER NOT NULL REFERENCES raw_posting(id) ON DELETE CASCADE,
        source TEXT NOT NULL, title TEXT NOT NULL, company TEXT NOT NULL,
        location TEXT NOT NULL DEFAULT '', remote INTEGER NOT NULL DEFAULT 0,
        salary TEXT NOT NULL DEFAULT '', url TEXT NOT NULL DEFAULT '',
        posted_at TEXT NOT NULL DEFAULT '', description TEXT NOT NULL DEFAULT '',
        fingerprint TEXT NOT NULL, group_id TEXT,
        kept INTEGER NOT NULL DEFAULT 0,           -- 0 = not judged yet OR filtered out
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
    # 8 — fixes three CORE defects, not patches:
    #
    # (a) The raw layer was not actually raw. `posting.description` was the
    #     ONLY copy of the description; a bug in strip_html lost the
    #     original, and an expired LinkedIn posting cannot be refetched. Now
    #     the verbatim text lives in raw_posting.body.
    #
    # (b) A judgement (kept/score) was not tied to the profile VERSION and
    #     rule VERSION that produced it. Change the profile or the rules and
    #     every old judgement is wrong — silently, with nobody able to tell
    #     which ones still hold.
    #
    # (c) There was no way to recompute the whole derived layer from raw.
    """
    ALTER TABLE raw_posting ADD COLUMN body TEXT NOT NULL DEFAULT '';
    ALTER TABLE posting ADD COLUMN judged_profile INTEGER NOT NULL DEFAULT 0;
    ALTER TABLE posting ADD COLUMN judged_rules TEXT NOT NULL DEFAULT '';
    ALTER TABLE posting ADD COLUMN scored_rules TEXT NOT NULL DEFAULT '';
    CREATE INDEX posting_judged ON posting(judged_profile, judged_rules);
    """,
    # 9 — a broken source has to LOOK different from a healthy one.
    # The deep-read pass used to swallow every exception
    # (`except Exception: continue`), so a source that changed its markup and
    # failed 100% looked exactly like a normal one: ok=1, no descriptions,
    # nobody the wiser.
    """
    ALTER TABLE source_run ADD COLUMN attempted INTEGER NOT NULL DEFAULT 0;
    ALTER TABLE source_run ADD COLUMN failed INTEGER NOT NULL DEFAULT 0;
    """,
    # 10 — "matches" is not "stands a chance". A high match score on a
    # posting demanding a PhD and 5 years says nothing about the odds of a
    # callback. Keep the two apart.
    """
    ALTER TABLE posting ADD COLUMN realism TEXT NOT NULL DEFAULT '';
    ALTER TABLE posting ADD COLUMN realism_why TEXT NOT NULL DEFAULT '';
    ALTER TABLE posting ADD COLUMN deadline TEXT NOT NULL DEFAULT '';
    ALTER TABLE posting ADD COLUMN deadline_ts INTEGER NOT NULL DEFAULT 0;
    CREATE INDEX posting_realism ON posting(realism);
    """,
    # 11 — the score must also carry the PROFILE version, not just the rule
    # version. Without this column a profile change only re-filtered and
    # never rescored: 72 of 204 kept postings were frozen at score=NULL
    # because they had been scored while their description was still empty.
    # DEFAULT 0 = "scored against no profile" -> every old posting becomes
    # due for rescoring on its own.
    """
    ALTER TABLE posting ADD COLUMN scored_profile INTEGER NOT NULL DEFAULT 0;
    """,
    # 12 — the run journal: every line belongs to a STREAM and has a LEVEL.
    # The stream is what lets the Search tab show only Search's work; the
    # level is what keeps errors from sitting among ordinary lines. Old rows
    # have neither -> default 'system'/'info'.
    """
    ALTER TABLE audit ADD COLUMN stream TEXT NOT NULL DEFAULT 'system';
    ALTER TABLE audit ADD COLUMN level  TEXT NOT NULL DEFAULT 'info';
    CREATE INDEX audit_stream ON audit(stream, id);
    """,
    # 13 — APP preferences (not profile_answer: that is the USER's profile).
    # Where "auto-scan at boot?" is remembered across restarts.
    """
    CREATE TABLE pref (
        key   TEXT PRIMARY KEY,
        value TEXT NOT NULL
    );
    """,
    # 14 — THE PROJECT STORE. The pipeline used to generate briefs, draw
    # them on screen and THROW THEM AWAY: every page load re-ran all seven
    # stages and nothing accumulated. A project that costs 2-3 days has to
    # outlive one page render.
    #
    # skills = the AXIS (which skill this project proves)
    # industries = the LABEL (which industry this story can be told in)
    # The axis is a skill, not a JD cluster: clusters are derived from data,
    # so when they shift the brief is orphaned — which really happened, with
    # the phantom 'excel' cluster.
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
    # 15 — WHICH CV version went with which application. Without this column
    # the table only says "applied to Point72" and not which version they
    # were given — and there are 43 different ones, and when they call for an
    # interview you have to re-read exactly that one.
    """
    ALTER TABLE application ADD COLUMN cv_file TEXT NOT NULL DEFAULT '';
    ALTER TABLE application ADD COLUMN note    TEXT NOT NULL DEFAULT '';
    """,
    # 16 — THE BLOCK NAME the machine inserted into the CV. Once inserted,
    # inside cv_text it is indistinguishable from a project the user wrote
    # themselves — without this column there is no later way to point at
    # "the machine produced this". It really happened: an "Alpha Research"
    # block sat in the CV for ages and only a diff of two adjacent versions
    # traced it.
    #
    # The marker lives HERE and NOT in cv_text: that CV goes to an employer
    # and must carry no internal annotation.
    """
    ALTER TABLE project ADD COLUMN cv_title TEXT NOT NULL DEFAULT '';
    """,
    # 17 — THE HUMAN keeping a posting the machine dropped.
    #
    # `kept` is a DERIVED column: derive() recomputes it from the rules + the
    # profile, and recomputes it EVERY TIME the profile version changes. So
    # setting kept=1 by hand is a decision with an expiry date: the next time
    # Vin edits one word in the profile it is overwritten, silently, with no
    # warning — and the score just computed is deleted with it.
    #
    # A HUMAN's decision has to live in its OWN column, which derive() reads.
    # This is exactly the app's "machine proposes, human approves" rule, only
    # this time the human is overruling the machine.
    """
    ALTER TABLE posting ADD COLUMN user_keep INTEGER NOT NULL DEFAULT 0;
    CREATE INDEX posting_user_keep ON posting(user_keep);
    """,
    # 18 — DROP personal projects entirely. The machine no longer invents
    # briefs; Vin picks his own projects.
    #
    # Why: this table survived 14 migrations holding exactly 0 rows. The
    # price was 1,253 lines of brief generation plus 955 lines of repo
    # scaffolding. The alternative — pulling sample projects off YouTube —
    # measured badly: a search for "data science portfolio project tutorial"
    # returned 0/10 real projects (9/10 were website-building videos), so
    # keyword matching had no way to pick right; and brief.py's own TUTORIAL
    # gate already excluded that whole class.
    #
    # Migrations 14 and 16 are NOT edited: any DB that has already run them
    # would be having its history rewritten. This list is append-only.
    #
    # Two things in that cluster did NOT die with it, because they never
    # belonged to it: the market counts (-> scoring/market.py) and the
    # industry vocabulary (-> scoring/vocab.py). Both only read `posting` and
    # have no idea what a project is.
    """
    DROP INDEX IF EXISTS project_state;
    DROP TABLE IF EXISTS project;
    """,
    # 19 — THE BUILT CVs, stored. The CV tab used to build them during the
    # page render: measured at 5.3 seconds for 364 postings, every time the
    # tab opened. Someone who just finished a search is nowhere near making a
    # CV, yet still waited 5 seconds for something they did not ask for.
    #
    # EXACTLY ONE ROW (CHECK id = 1). No history: the "before" in a
    # before/after comparison is Vin's ORIGINAL CV, not the previous build —
    # keeping history here is keeping something nobody reads.
    #
    # `stamp` is the freshness stamp: CV text + writing rules + scoring rules
    # + the posting set. The Run button reads it to decide whether to say
    # "Run", "Update" or "Rebuild".
    """
    CREATE TABLE cv_build (
        id       INTEGER PRIMARY KEY CHECK (id = 1),
        made_at  TEXT NOT NULL,
        stamp    TEXT NOT NULL,
        payload  TEXT NOT NULL
    );
    """,
    # 20 — THE HUMAN RE-PICKING SENTENCES for ONE specific posting.
    #
    # The machine orders sentences by weight, and weights are a general rule
    # — it does not know who Vin just spoke to, or which way this posting
    # leans. So Vin has to be able to re-pick: pin a sentence in, push one
    # out.
    #
    # THIS IS STILL PICKING, NOT WRITING. A pinned sentence must already
    # exist in the profile — the founding rule, "every sentence on the CV is
    # one Vin wrote".
    #
    # Stored by the VERBATIM SENTENCE, not by index: the order changes on
    # every rebuild, the sentence does not. Edit that sentence in the profile
    # and the old choice lapses on its own — correctly, because it is no
    # longer that sentence.
    """
    CREATE TABLE cv_pick (
        posting_id INTEGER NOT NULL REFERENCES posting(id) ON DELETE CASCADE,
        text       TEXT    NOT NULL,
        mode       TEXT    NOT NULL CHECK (mode IN ('pin','drop')),
        made_at    TEXT    NOT NULL,
        PRIMARY KEY (posting_id, text)
    );
    """,
    # 21 — clean out the dropped "keyword density" knob.
    #
    # Measured over 60 postings: turning it to "dense" changed EXACTLY 0 CV
    # builds. And it rested on "keyword density" — something no ATS vendor
    # publishes a formula for. The old value sitting in the pref table harms
    # nothing, but a later reader will assume it is still in use.
    """
    DELETE FROM pref WHERE key = 'cv_khoa';
    """,
    # 22 — NORMALISE received_at TO UTC.
    #
    # Mail used to be stored in whatever timezone the sender used. Three
    # places compare timestamps by STRING COMPARISON (scan.settle,
    # board.all max(), ORDER BY), so every non-UTC mail was wrong:
    # '...01:30-04:00' (05:30 UTC) sorts BEFORE '...02:00+00:00'
    # alphabetically, so mail 3.5 hours newer counted as older and was
    # dropped. Measured on the real mailbox: 200 of 1,046 messages.
    #
    # Only touches rows that HAVE an offset and are NOT +00:00 — it does not
    # rewrite what is already right.
    """
    UPDATE message
       SET received_at = strftime('%Y-%m-%dT%H:%M:%S+00:00', received_at)
     WHERE received_at IS NOT NULL
       AND length(received_at) >= 25
       AND substr(received_at, -6) <> '+00:00'
       AND strftime('%Y-%m-%dT%H:%M:%S+00:00', received_at) IS NOT NULL;
    """,

    # 23 — clean three DEAD preferences out of the pref table.
    #
    # `cv_bo_cuc`, `cv_giong`, `cv_giu_rui_ro` belonged to an older CV
    # builder. The code that read them was deleted long ago, but THE ROWS
    # STAYED IN THE DB — measured on Vin's machine: all three still there.
    # They harm nothing, but open the pref table and those three rows claim
    # there are three knobs somewhere driving them, and sooner or later
    # somebody goes looking for a knob that does not exist.
    #
    # DELETED BY NAME, not "every unknown key": `title_vocab` and a few
    # others are also absent from DEFAULTS and very much alive — an
    # allowlist sweep would delete 60 job titles the user typed themselves.
    """
    DELETE FROM pref WHERE key IN ('cv_bo_cuc', 'cv_giong', 'cv_giu_rui_ro');
    """,
]

SECRET = 0o600      # owner-only — see _lock_down


def _lock_down(path: Path) -> None:
    """Only the owner can read the DB, and the WAL/SHM files beside it.

    It holds the FULL TEXT of the CV, the personal profile, and the subject
    plus first 400 characters of every recruiting email. sqlite's default is
    0644 — any account on the machine can read it. Setting it once at connect
    time means nobody has to remember.
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
    conn.execute("PRAGMA journal_mode = WAL")   # readable while writing (24/7)
    migrate(conn)
    return conn


def migrate(conn: sqlite3.Connection) -> int:
    """Run the migrations still missing. Returns how many ran."""
    current = conn.execute("PRAGMA user_version").fetchone()[0]
    ran = 0
    for index in range(current, len(MIGRATIONS)):
        # EACH MIGRATION IS ONE TRANSACTION, and `user_version` advances
        # INSIDE that same transaction.
        #
        # The previous version ran executescript and committed afterwards:
        # executescript COMMITS BY ITSELF before running, so if the third
        # statement of a migration failed (power cut, full disk, a foreign
        # key), the first two were already in the DB while user_version still
        # held the old number. The next boot ran that migration AGAIN from
        # the top — and a migration run twice makes "ADD COLUMN" raise and
        # "INSERT" duplicate. The DB dies permanently, with no way back.
        try:
            conn.execute("BEGIN")
            for cau in _tach_cau(MIGRATIONS[index]):
                conn.execute(cau)
            conn.execute(f"PRAGMA user_version = {index + 1}")
            conn.commit()
        except Exception:                   # noqa: BLE001
            conn.rollback()
            raise
        ran += 1
    return ran


def _tach_cau(script: str) -> list[str]:
    """Split a migration into statements, so it can run INSIDE a transaction.

    `executescript` is more convenient but it COMMITS by itself before
    running — which means it cannot be inside any transaction at all. That is
    precisely why this splits by hand.
    """
    return [c.strip() for c in script.split(";") if c.strip()]
