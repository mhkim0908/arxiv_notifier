#!/usr/bin/env python3
"""
arxiv_notifier.py
────────────────────────────────────────────────────────────
* AI 요약 토글: AI_SUMMARIZE = True / False
* DAYS_BACK: 최근 N 일 논문만 메일에 포함
* GPT 모델 · API 키는 환경변수(OPENAI_API_KEY)로 관리
"""

from __future__ import annotations

import email.utils as eut
import hashlib
import json
import os
import smtplib
import urllib.parse
from datetime import date, datetime, timedelta, timezone
from email.header import Header
from email.mime.text import MIMEText
from typing import Any, Dict, List, Optional

import feedparser

# ──────────────── AI 요약 설정 ────────────────
AI_SUMMARIZE = True                # ← True/False
MODEL_ID = "gpt-4.5-preview"       # 필요 시 변경
if AI_SUMMARIZE:
    import openai

    openai.api_key = os.getenv("OPENAI_API_KEY")

# ─────────────── 기본 설정 ────────────────
ENV_VARS = ("EMAIL_ADDRESS", "EMAIL_PASSWORD", "TO_EMAIL")
TOPIC_FILE = "topics.json"
MAX_RESULTS_DEFAULT = 10
DAYS_BACK = 1                      # 최근 N 일 논문
TITLE_MAX, ABSTRACT_MAX = 120, 600
GLOBAL_EXCLUDE = {"review", "survey", "comment on", "corrigendum"}

# ────────────── 유틸 함수 ────────────────
def getenv_or_exit(name: str) -> str:
    val = os.getenv(name)
    if not val:
        raise SystemExit(f"[config] '{name}' 환경변수가 없습니다")
    return val


def load_topics(path: str) -> Dict[str, Any]:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def make_query(keyword: str, cats: List[str]) -> str:
    phrase = urllib.parse.quote_plus(f'"{keyword}"')
    kw = f"(ti:{phrase}+OR+abs:{phrase})"
    if cats:
        cat = "+OR+".join(f"cat:{c}" for c in cats)
        return f"({cat})+AND+{kw}"
    return kw


def fetch_entries(query: str, n: int) -> List[Any]:
    url = (
        "http://export.arxiv.org/api/query?search_query="
        f"{query}&start=0&max_results={n}"
        "&sortBy=submittedDate&sortOrder=descending"
    )
    return feedparser.parse(url).entries


def _get_entry_datetime(entry) -> Optional[datetime]:
    """Return the first parseable date field in UTC, else None."""
    for field in ("published", "updated", "created"):
        val = getattr(entry, field, None)
        if not val:
            continue
        tup = eut.parsedate_tz(val)
        if tup:
            return datetime.fromtimestamp(eut.mktime_tz(tup), tz=timezone.utc)
    return None


def is_recent(entry) -> bool:
    """True ↔ entry submitted within DAYS_BACK days; False otherwise."""
    dt = _get_entry_datetime(entry)
    if dt is None:
        return False  # skip if no valid date
    return dt >= datetime.now(tz=timezone.utc) - timedelta(days=DAYS_BACK)


def truncate(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 3].rstrip() + "..."


def summarize(title: str, abstract: str) -> str:
    resp = openai.chat.completions.create(
        model=MODEL_ID,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a scientific summarizer.\n"
                    "Return exactly three lines:\n"
                    "1) Problem: <one concise sentence>\n"
                    "2) Result: <one concise sentence>\n"
                    "3) Method: <one concise sentence>"
                ),
            },
            {"role": "user", "content": f"TITLE: {title}\nTEXT: {abstract}"},
        ],
        temperature=0.3,
        max_tokens=120,
    )
    return resp.choices[0].message.content.strip()


# ────────────── 논문 수집 ───────────────
def collect_papers(topics: Dict[str, Any]) -> Dict[str, List[Dict[str, str]]]:
    results, seen = {}, set()

    for topic, cfg in topics.items():
        papers = []
        for kw in cfg.get("keywords", []):
            for entry in fetch_entries(
                make_query(kw, cfg.get("categories", [])),
                int(cfg.get("max_results", MAX_RESULTS_DEFAULT)),
            ):
                if not is_recent(entry):
                    continue  # too old or no date

                uid = hashlib.sha1(entry.id.encode()).hexdigest()
                if uid in seen:
                    continue
                seen.add(uid)

                title = " ".join(entry.title.split())
                abstract = " ".join(entry.summary.split())
                if any(k in abstract.lower() for k in GLOBAL_EXCLUDE):
                    continue

                info = {
                    "title": truncate(title, TITLE_MAX),
                    "link": entry.link,
                    "abstract": truncate(abstract, ABSTRACT_MAX),
                }
                if AI_SUMMARIZE:
                    try:
                        info["summary"] = summarize(title, abstract)
                    except Exception as err:
                        info["summary"] = f"(요약 실패: {err})"

                papers.append(info)

        if papers:
            results[topic] = papers

    return results


# ─────────────── 메일 본문 ───────────────
def build_email(papers: Dict[str, List[Dict[str, str]]]) -> str:
    lines = ["📰  오늘의 arXiv\n"]
    for i, (topic, plist) in enumerate(papers.items()):
        lines += [f"📌 {topic.upper()} ({len(plist)})", "=" * (len(topic) + 7)]

        for j, p in enumerate(plist, 1):
            if AI_SUMMARIZE:
                lines.append("   💡 3-line summary:")
                for line in p["summary"].splitlines():
                    lines.append(f"      {line}")
                lines.append("")

            lines += [
                f"{j}. 📄 {p['title']}",
                f"   🔗 {p['link']}\n",
                "   📝 Abstract:",
                f"      {p['abstract']}\n",
            ]
            if j < len(plist):
                lines.append("   " + "-" * 40 + "\n")

        if i < len(papers) - 1:
            lines.append("・" * 30 + "\n")

    lines += [
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"지난 {DAYS_BACK}일 이내에 제출된 논문만 포함했습니다.",
    ]
    return "\n".join(lines)


# ─────────────── 이메일 발송 ───────────────
def send_email(subject: str, body: str, sender: str, pwd: str, recipient: str) -> None:
    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"], msg["From"], msg["To"] = subject, sender, recipient
    with smtplib.SMTP("smtp.gmail.com", 587) as s:
        s.starttls()
        s.login(sender, pwd)
        s.sendmail(sender, [recipient], msg.as_string())


# ─────────────────── 메인 ───────────────────
def main() -> None:
    sender, pwd, rcpt = (getenv_or_exit(k) for k in ENV_VARS)
    papers = collect_papers(load_topics(TOPIC_FILE))
    if not papers:
        print("[info] no new papers")
        return

    first_topic, first_list = next(iter(papers.items()))
    subject = str(
        Header(
            f"{date.today():%Y-%m-%d} - 오늘의 arXiv - "
            f"{first_topic} ({len(first_list)})",
            "utf-8",
        )
    )
    send_email(subject, build_email(papers), sender, pwd, rcpt)
    print("[ok] email sent")


if __name__ == "__main__":
    main()
