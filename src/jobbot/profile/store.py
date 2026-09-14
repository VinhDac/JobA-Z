"""Store the profile by version.

Every save creates A NEW VERSION = a full snapshot (the old answers carried
forward + what was just edited). Nothing is overwritten, because the profile
is living data — after 50 rejections what someone wants is different from
what they wanted at the start, and it must be possible to look back at how it
changed.

The cost: disk space. For a few dozen text versions it is negligible.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any

from .schema import INGEST_GATE, SECTIONS, Section, all_questions, section_index

Answers = dict[str, Any]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def latest_version_id(conn: sqlite3.Connection) -> int | None:
    row = conn.execute("SELECT MAX(id) AS id FROM profile_version").fetchone()
    return row["id"] if row and row["id"] is not None else None


def load(conn: sqlite3.Connection) -> Answers:
    """The current profile = the newest version. Empty if there is none."""
    version_id = latest_version_id(conn)
    if version_id is None:
        return {}
    rows = conn.execute(
        "SELECT question_id, value_json FROM profile_answer WHERE version_id = ?",
        (version_id,),
    ).fetchall()
    return {r["question_id"]: json.loads(r["value_json"]) for r in rows}


def save(conn: sqlite3.Connection, changed: Answers, note: str = "") -> int:
    """Create a new version = the old profile + the edit. Returns its id."""
    known = all_questions()
    merged = load(conn)
    merged.update({k: v for k, v in changed.items() if k in known})

    cursor = conn.execute(
        "INSERT INTO profile_version (created_at, note) VALUES (?, ?)", (_now(), note)
    )
    version_id = int(cursor.lastrowid)
    conn.executemany(
        "INSERT INTO profile_answer (version_id, question_id, value_json) VALUES (?, ?, ?)",
        [(version_id, qid, json.dumps(val, ensure_ascii=False)) for qid, val in merged.items()],
    )
    conn.commit()
    return version_id


def history(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT id, created_at, note FROM profile_version ORDER BY id DESC"
    ).fetchall()


def _has_value(answers: Answers, question_id: str) -> bool:
    value = answers.get(question_id)
    if value is None:
        return False
    if isinstance(value, (list, str)):
        return len(value) > 0
    return True


def has_answer(answers: Answers, question) -> bool:
    """Does this question have content — ASKED WHERE IT ACTUALLY LIVES.

    BLOCKS questions (experience, projects) are not stored in
    profile_answer; they are stored as blocks inside cv_text. Look only at
    profile_answer and, after importing a CV from which the machine extracted
    2 experience blocks and 3 projects, Home still reports "0/1 — not done".
    """
    from .schema import BLOCKS
    if getattr(question, "kind", "") == BLOCKS:
        from ..cv.blocks import parse as parse_cv
        return any(b.kind == question.block_kind
                   for b in parse_cv(str(answers.get("cv_text") or "")))
    return _has_value(answers, question.id)


def missing_in_section(answers: Answers, section: Section) -> list[str]:
    """The required questions still missing in one section."""
    return [q.id for q in section.questions
            if q.required and not q.hidden and not has_answer(answers, q)]


def is_section_done(answers: Answers, section: Section) -> bool:
    """Done = no required question missing AND at least one answer given."""
    if missing_in_section(answers, section):
        return False
    return any(has_answer(answers, q)
               for q in section.questions if not q.hidden)


def next_section(section_id: str) -> Section | None:
    """The next section in order. None at the end -> the summary page."""
    index = section_index(section_id)
    return SECTIONS[index + 1] if 0 <= index < len(SECTIONS) - 1 else None


def first_unfinished_section(answers: Answers) -> Section | None:
    return next((s for s in SECTIONS if not is_section_done(answers, s)), None)


def missing_for_ingest(answers: Answers) -> list[str]:
    """The questions still missing before fetching postings is allowed."""
    return [qid for qid in INGEST_GATE if not _has_value(answers, qid)]


def section_of(question_id: str) -> Section | None:
    """Which section a question belongs to. Used to TAKE THE USER to what
    is missing."""
    return next((s for s in SECTIONS
                 if any(q.id == question_id for q in s.questions)), None)


def next_gate_stop(answers: Answers) -> str | None:
    """The next place that MUST be visited, or None once the app can run.

    This is the loop of the onboarding cycle: after saving a section, ask
    this function again — still missing means back to the section holding the
    missing question, complete means released. It does not walk section 1 ->
    2 -> 3: the user is only held at what is MISSING, not herded through 35
    questions before they can use the app.
    """
    thieu = missing_for_ingest(answers)
    if not thieu:
        return None
    phan = section_of(thieu[0])
    return f"/profile/{phan.id}" if phan else None


def can_ingest(answers: Answers) -> bool:
    """The gate: with no job titles and no markets, a search finds nothing."""
    return not missing_for_ingest(answers)
