#!/usr/bin/env python3
"""
arxiv_notifier.py

Daily arXiv digest (09:00 KST window).
* Optional 3‑line GPT summary (toggle AI_SUMMARIZE)
* SMTP credentials and recipient list via environment variables
"""

from __future__ import annotations

import hashlib
import json
import os
import smtplib
import time
from datetime import date, datetime, timedelta, timezone
from email.header import Header
from email.mime.text import MIMEText
from typing import Any, Dict, List, Optional
from urllib.parse import quote_plus

import feedparser

# ───────────────────── configuration ─────────────────────
AI_SUMMARIZE = True  # Toggle GPT‑based summarization
MODEL_ID = "gpt-4.1"

ENV_VARS = ("EMAIL_ADDRESS", "EMAIL_PASSWORD", "TO_EMAIL")
TOPIC_FILE = "topics.json"

MAX_RESULTS_DEFAULT = 20
TITLE_MAX = 120
ABSTRACT_MAX = 600

GLOBAL_EXCLUDE = {"review", "survey", "comment on", "corrigendum"}

KST = timezone(timedelta(hours=9))
WINDOW_DAYS = int(os.getenv("WINDOW_DAYS", "1"))
API_RATE_SEC = 3  # arXiv ToS: ≤ 1 request / 3 s
# ──────────────────────────────────────────────────────────

if AI_SUMMARIZE:
    try:
        import openai

        openai.api_key = os.getenv("OPENAI_API_KEY")
    except ImportError:
        print("[warn] openai package not installed, disabling summaries")
        AI_SUMMARIZE = False


# ───────────────────── helper functions ───────────────────


def getenv_or_exit(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise SystemExit(f"Missing env var: {name}")
    return value


def load_topics(path: str) -> Dict[str, Any]:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def make_query(keyword: str, cats: list[str]) -> str:
    """Build an arXiv API query string."""
    if " " in keyword:
        phrase = quote_plus(keyword, safe="")
        kw_part = f"(ti:%22{phrase}%22+OR+abs:%22{phrase}%22)"
    else:
        token = keyword if "*" in keyword else f"{keyword}*"
        kw_part = f"(ti:{token}+OR+abs:{token})"

    if cats:
        cat_part = "+OR+".join(f"cat:{c}" for c in cats)
        return f"({cat_part})+AND+{kw_part}"
    return kw_part


def fetch_entries(q: str, n: int) -> List[Any]:
    url = (
        "http://export.arxiv.org/api/query?"
        f"search_query={q}&start=0&max_results={n}"
        "&sortBy=submittedDate&sortOrder=descending"
    )
    feed = feedparser.parse(url)
    time.sleep(API_RATE_SEC)  # Respect arXiv rate limit
    return feed.entries


def _entry_datetime(entry) -> Optional[datetime]:
    """Return the most recently available timestamp for an entry (UTC)."""
    for field in ("updated_parsed", "published_parsed", "created_parsed"):
        tup = getattr(entry, field, None)
        if tup:
            return datetime.fromtimestamp(time.mktime(tup), tz=timezone.utc)
    return None


def in_kst_window(entry) -> bool:
    """Keep papers submitted between yesterday 09:00 and today 09:00 KST."""
    dt_utc = _entry_datetime(entry)
    if dt_utc is None:
        return False
    dt_kst = dt_utc.astimezone(KST)

    now_kst = datetime.now(tz=KST)
    today_09 = now_kst.replace(hour=9, minute=0, second=0, microsecond=0)
    if now_kst < today_09:  # Executed before 09:00 → shift window back one day
        today_09 -= timedelta(days=1)
    start = today_09 - timedelta(days=WINDOW_DAYS)

    return start <= dt_kst < today_09


def truncate(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 3].rstrip() + "..."


def summarize(title: str, abstract: str) -> str:
    resp = openai.chat.completions.create(
        model=MODEL_ID,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a scientific summarizer. "
                    "Return exactly three lines:\n"
                    "1) Problem: <one sentence>\n"
                    "2) Result: <one sentence>\n"
                    "3) Method: <one sentence>"
                ),
            },
            {"role": "user", "content": f"TITLE: {title}\nTEXT: {abstract}"},
        ],
        temperature=0.3,
        max_tokens=120,
    )
    return resp.choices[0].message.content.strip()


# ───────────────────────── core ───────────────────────────


def collect_papers(topics: Dict[str, Any]) -> Dict[str, List[Dict[str, str]]]:
    output: Dict[str, List[Dict[str, str]]] = {}
    seen: set[str] = set()

    for topic, cfg in topics.items():
        papers: List[Dict[str, str]] = []
        for kw in cfg.get("keywords", []):
            for entry in fetch_entries(
                make_query(kw, cfg.get("categories", [])),
                int(cfg.get("max_results", MAX_RESULTS_DEFAULT)),
            ):
                if not in_kst_window(entry):
                    continue

                uid = hashlib.sha1(entry.id.encode()).hexdigest()
                if uid in seen:
                    continue
                seen.add(uid)

                title = " ".join(entry.title.split())
                abstract = " ".join(entry.summary.split())
                if any(excl in abstract.lower() for excl in GLOBAL_EXCLUDE):
                    continue

                info = {
                    "title": truncate(title, TITLE_MAX),
                    "link": entry.link,
                    "abstract": truncate(abstract, ABSTRACT_MAX),
                    "authors": ", ".join(a.name for a in getattr(entry, "authors", [])),
                    "categories": [t.term for t in getattr(entry, "tags", [])],
                }

                if AI_SUMMARIZE:
                    try:
                        info["summary"] = summarize(title, abstract)
                    except Exception as err:
                        info["summary"] = f"(summary error: {err})"

                papers.append(info)

        if papers:
            output[topic] = papers

    return output


def build_email(papers: Dict[str, List[Dict[str, str]]]) -> str:
    lines: List[str] = ["📰  Daily arXiv Digest\n"]

    for t_idx, (topic, plist) in enumerate(papers.items()):
        lines += [f"📌 {topic.upper()} ({len(plist)})", "=" * (len(topic) + 7)]

        for p_idx, p in enumerate(plist, 1):
            cat = ", ".join(p["categories"])
            lines.append(f"{p_idx}. 📄 {p['title']}  ({cat})")
            lines.append(f"      🔗 {p['link']}")
            lines.append(f"      👥 {p.get('authors', 'Unknown authors')}")

            if AI_SUMMARIZE:
                lines.append("      💡 3‑line summary:")
                for ln in p["summary"].splitlines():
                    lines.append(f"         {ln}")

            if p_idx < len(plist):
                lines.append("      " + "-" * 40)

        if t_idx < len(papers) - 1:
            lines.append("-" * 30)

    lines += [
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "Window: yesterday 09:00 – today 09:00 KST",
    ]
    return "\n".join(lines)


def send_email(
    subject: str, body: str, sender: str, pwd: str, recipients: list[str]
) -> None:
    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"], msg["From"] = subject, sender
    msg["To"] = ", ".join(recipients)

    with smtplib.SMTP("smtp.gmail.com", 587) as s:
        s.starttls()
        s.login(sender, pwd)
        s.sendmail(sender, recipients, msg.as_string())


def main() -> None:
    sender, pwd, rcpt_raw = (getenv_or_exit(k) for k in ENV_VARS)
    recipients = [e.strip() for e in rcpt_raw.split(",") if e.strip()]

    papers = collect_papers(load_topics(TOPIC_FILE))
    if not papers:
        print("[info] no new papers")
        return

    subject = str(Header(f"{date.today():%Y-%m-%d} – arXiv Digest"))
    send_email(subject, build_email(papers), sender, pwd, recipients)
    print("[ok] email sent")


if __name__ == "__main__":
    main()
