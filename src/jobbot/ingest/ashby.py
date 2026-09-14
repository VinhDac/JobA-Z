"""Ashby — per company, no API key needed."""

from __future__ import annotations

from .base import Posting, get_json

NAME = "ashby"
URL = "https://api.ashbyhq.com/posting-api/job-board/{board}"


def fetch_board(board: str) -> list[Posting]:
    data = get_json(URL.format(board=board))
    out: list[Posting] = []
    for row in data.get("jobs") or []:
        if row.get("isListed") is False:
            continue
        out.append(Posting(
            source_id=f"{board}:{row.get('id')}",
            title=(row.get("title") or "").strip(),
            company=board,
            location=(row.get("location") or "").strip(),
            remote=bool(row.get("isRemote")),
            url=row.get("jobUrl") or row.get("applyUrl", ""),
            posted_at=str(row.get("publishedAt") or ""),
            description=(row.get("descriptionPlain") or "").strip()[:20000],
            raw_body=(row.get("descriptionHtml") or row.get("descriptionPlain") or "")[:60000],
            payload={"board": board, "id": row.get("id"),
                     "team": row.get("team"), "employmentType": row.get("employmentType")},
        ))
    return out
