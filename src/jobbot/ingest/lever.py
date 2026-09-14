"""Lever — per company, no API key needed. descriptionPlain is already plain text."""

from __future__ import annotations

from .base import Posting, get_json

NAME = "lever"
URL = "https://api.lever.co/v0/postings/{board}?mode=json"


def fetch_board(board: str) -> list[Posting]:
    rows = get_json(URL.format(board=board))
    out: list[Posting] = []
    for row in rows if isinstance(rows, list) else []:
        cat = row.get("categories") or {}
        body = " ".join(filter(None, [row.get("descriptionPlain", ""),
                                      row.get("additionalPlain", "")]))
        out.append(Posting(
            source_id=f"{board}:{row.get('id')}",
            title=(row.get("text") or "").strip(),
            company=board,
            location=(cat.get("location") or row.get("country") or "").strip(),
            remote=str(row.get("workplaceType", "")).lower() == "remote",
            url=row.get("hostedUrl") or row.get("applyUrl", ""),
            posted_at=str(row.get("createdAt") or ""),
            description=body.strip()[:20000],
            raw_body=body.strip()[:60000],
            payload={"board": board, "id": row.get("id"),
                     "commitment": cat.get("commitment"), "team": cat.get("team")},
        ))
    return out
