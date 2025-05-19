#!/usr/bin/env python3
"""
arxiv_notifier.py
-----------------
Send daily arXiv digests for user‑defined topics.

Highlights
~~~~~~~~~~
* Topics & category filters are stored in ``topics.json``.
* Ignores papers whose title/abstract contain any keyword in ``exclude_keywords``.
* Truncates long titles / abstracts.
* Plain‑text email formatted for readability.
"""

from __future__ import annotations

import hashlib
import json
import os
import smtplib
import textwrap
from email.mime.text import MIMEText
import urllib.parse  # ← 상단 import 추가

import feedparser


from typing import Any, Dict, List, Optional

# ---------------------------------------------------------
# User‑adjustable constants
# ---------------------------------------------------------

ENV_VARS = ("EMAIL_ADDRESS", "EMAIL_PASSWORD", "TO_EMAIL")
TOPIC_FILE = "topics.json"

MAX_RESULTS_DEFAULT = 10  # fallback per‑query result count
TITLE_MAX = 120  # characters
ABSTRACT_MAX = 600  # characters
WRAP_WIDTH = None  # characters when wrapping abstract text

GLOBAL_EXCLUDE = {
    "review",
    "survey",
    "comment on",
    "corrigendum",
}

# ---------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------


def getenv_or_exit(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise SystemExit(f"[config] required environment variable '{name}' is missing")
    return value


def load_topics(path: str) -> Dict[str, Any]:
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError as exc:
        raise SystemExit(f"[config] topics file '{path}' not found") from exc
    except json.JSONDecodeError as exc:
        raise SystemExit(f"[config] invalid JSON in '{path}'") from exc


def make_query(keyword: str, categories: List[str]) -> str:
    kw_enc = urllib.parse.quote_plus(keyword)  # 공백 → '+', 기타 특수문자 인코딩
    kw = f"all:{kw_enc}"

    if categories:
        cat = "+OR+".join(f"cat:{c}" for c in categories)
        return f"({cat})+AND+{kw}"
    return kw


def fetch_entries(query: str, max_results: int) -> List[Any]:
    url = (
        "http://export.arxiv.org/api/query?search_query="
        f"{query}&start=0&max_results={max_results}"
    )
    feed = feedparser.parse(url)
    return feed.entries


def normalize(text: str) -> str:
    """Collapse whitespace and ensure each sentence ends with a period."""
    sentences = [
        s.strip().rstrip(".") + "."
        for s in text.replace("\n", " ").split(". ")
        if s.strip()
    ]
    return " ".join(sentences)


def wrap(text: str) -> str:
    if WRAP_WIDTH is None:
        return text
    return textwrap.fill(text, WRAP_WIDTH, subsequent_indent="    ")


def truncate(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 3].rstrip() + "..."


def should_skip(text: str, exclude: set[str]) -> bool:
    lower = text.lower()
    return any(k in lower for k in exclude)


# ---------------------------------------------------------
# Core logic
# ---------------------------------------------------------


def collect_papers(topics: Dict[str, Any]) -> Dict[str, List[Dict[str, str]]]:
    results: Dict[str, List[Dict[str, str]]] = {}
    seen: set[str] = set()

    for topic, cfg in topics.items():
        kw_list: List[str] = cfg.get("keywords", [])
        cat_filter: List[str] = cfg.get("categories", [])
        exclude = set(cfg.get("exclude_keywords", [])) | GLOBAL_EXCLUDE
        max_results = int(cfg.get("max_results", MAX_RESULTS_DEFAULT))

        papers: List[Dict[str, str]] = []
        for kw in kw_list:
            for entry in fetch_entries(make_query(kw, cat_filter), max_results):
                uid = hashlib.sha1(entry.id.encode()).hexdigest()
                if uid in seen:
                    continue
                seen.add(uid)

                title = " ".join(entry.title.split())
                abstract = entry.summary

                if should_skip(f"{title} {abstract}", exclude):
                    continue

                papers.append(
                    {
                        "title": truncate(title, TITLE_MAX),
                        "link": entry.link,
                        "abstract": truncate(normalize(abstract), ABSTRACT_MAX),
                    }
                )

        if papers:
            results[topic] = papers
    return results


def build_email(papers: Dict[str, List[Dict[str, str]]]) -> Optional[str]:
    if not papers:
        return None

    parts: List[str] = ["📰  Daily arXiv digest", ""]

    for i, (topic, plist) in enumerate(papers.items()):
        # 주제별 상단 구분선 추가
        topic_header = f"📌 {topic.upper()} ({len(plist)})"
        parts.extend([topic_header, "=" * len(topic_header)])

        for j, p in enumerate(plist):
            # 논문 번호 추가 및 제목 강조
            parts.append(f"{j+1}. 📄 {p['title']}")
            parts.append(f"   🔗 {p['link']}")
            parts.append("")  # 제목/링크와 초록 사이 공백
            parts.append("   📝 Abstract:")
            # 초록 들여쓰기 및 포맷팅 개선
            abstract_lines = wrap(p["abstract"]).split("\n")
            parts.extend([f"      {line}" for line in abstract_lines])

            # 논문 간 구분선 (마지막 논문 제외)
            if j < len(plist) - 1:
                parts.append("")
                parts.append("   " + "-" * 40)
                parts.append("")

        # 주제 간 구분 (마지막 주제 제외)
        if i < len(papers) - 1:
            parts.append("")
            parts.append("・" * 30)
            parts.append("")

    # 푸터 추가
    parts.extend(
        [
            "",
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            "Automatically generated arXiv paper notification.",
            "설정을 변경하려면 topics.json 파일을 수정하세요.",
        ]
    )

    return "\n".join(parts)


def send_email(
    subject: str, body: str, sender: str, password: str, recipient: str
) -> None:
    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = recipient

    with smtplib.SMTP("smtp.gmail.com", 587) as s:
        s.starttls()
        s.login(sender, password)
        s.sendmail(sender, [recipient], msg.as_string())


# ---------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------


def main() -> None:
    sender = getenv_or_exit("EMAIL_ADDRESS")
    password = getenv_or_exit("EMAIL_PASSWORD")
    recipient = getenv_or_exit("TO_EMAIL")

    topics = load_topics(TOPIC_FILE)
    papers = collect_papers(topics)
    body = build_email(papers)

    if body:
        subject = "📰 New arXiv papers – " + ", ".join(papers.keys())
        send_email(subject, body, sender, password, recipient)
        print("[ok] email sent")
    else:
        print("[info] no new papers")


if __name__ == "__main__":
    main()
