#!/usr/bin/env python3
"""
arxiv_notifier.py
────────────────────────────────────────────────────────────
* arXiv 검색 → (선택) GPT 요약 → 메일 발송
* --summary       : Problem / Result / Method  3-line 요약 추가
* --model MODEL   : OpenAI 모델명 (기본 gpt-4o-mini)
* GitHub Actions  : secrets.OPENAI_API_KEY, EMAIL_ADDRESS, EMAIL_PASSWORD, TO_EMAIL
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import smtplib
import urllib.parse
from datetime import date
from email.header import Header
from email.mime.text import MIMEText
from typing import Any, Dict, List, Optional

import feedparser

# ──────────────── LLM (옵션) ────────────────
try:
    import openai
except ImportError:
    openai = None  # --summary 안 쓰면 필요 없음

# ─────────────── 기본 설정 ────────────────
ENV_VARS = ("EMAIL_ADDRESS", "EMAIL_PASSWORD", "TO_EMAIL")
TOPIC_FILE = "topics.json"

MAX_RESULTS_DEFAULT = 10
TITLE_MAX = 120
ABSTRACT_MAX = 600

GLOBAL_EXCLUDE = {"review", "survey", "comment on", "corrigendum"}


# ────────────── 유틸 함수 ────────────────
def getenv_or_exit(name: str) -> str:
    val = os.getenv(name)
    if not val:
        raise SystemExit(f"[config] '{name}' 환경변수가 비어 있습니다")
    return val


def load_topics(path: str) -> Dict[str, Any]:
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError:
        raise SystemExit(f"[config] topics 파일 '{path}'을 찾을 수 없습니다")


def make_query(keyword: str, categories: List[str]) -> str:
    phrase = f'"{keyword}"'
    kw_enc = urllib.parse.quote_plus(phrase)
    kw_part = f"(ti:{kw_enc}+OR+abs:{kw_enc})"
    if categories:
        cat_part = "+OR+".join(f"cat:{c}" for c in categories)
        return f"({cat_part})+AND+{kw_part}"
    return kw_part


def fetch_entries(query: str, max_results: int) -> List[Any]:
    url = (
        "http://export.arxiv.org/api/query?search_query="
        f"{query}&start=0&max_results={max_results}"
    )
    return feedparser.parse(url).entries


def truncate(txt: str, limit: int) -> str:
    return txt if len(txt) <= limit else txt[: limit - 3].rstrip() + "..."


def should_skip(txt: str, exclude: set[str]) -> bool:
    lower = txt.lower()
    return any(k in lower for k in exclude)


# ──────────────── LLM 요약 ────────────────
def summarize(title: str, abstract: str, model: str) -> str:
    if openai is None:
        raise RuntimeError("openai 패키지가 설치되어 있지 않습니다.")
    openai.api_key = getenv_or_exit("OPENAI_API_KEY")

    sys_prompt = (
        "You are a scientific summarizer.\n"
        "Return exactly three lines:\n"
        "1) Problem: <one concise sentence>\n"
        "2) Result: <one concise sentence>\n"
        "3) Method: <one concise sentence>"
    )
    user_msg = f"TITLE: {title}\nTEXT: {abstract}"
    resp = openai.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": user_msg},
        ],
        temperature=0.3,
        max_tokens=120,
    )
    return resp.choices[0].message.content.strip()


# ────────────── 논문 수집 ───────────────
def collect_papers(
    topics: Dict[str, Any], do_summary: bool, model: str
) -> Dict[str, List[Dict[str, str]]]:
    results: Dict[str, List[Dict[str, str]]] = {}
    seen: set[str] = set()

    for topic, cfg in topics.items():
        kw_list = cfg.get("keywords", [])
        cats = cfg.get("categories", [])
        exclude = set(cfg.get("exclude_keywords", [])) | GLOBAL_EXCLUDE
        max_results = int(cfg.get("max_results", MAX_RESULTS_DEFAULT))

        papers: List[Dict[str, str]] = []
        for kw in kw_list:
            for e in fetch_entries(make_query(kw, cats), max_results):
                uid = hashlib.sha1(e.id.encode()).hexdigest()
                if uid in seen:
                    continue
                seen.add(uid)

                title = " ".join(e.title.split())
                abstract = " ".join(e.summary.split())

                if should_skip(f"{title} {abstract}", exclude):
                    continue

                info = {
                    "title": truncate(title, TITLE_MAX),
                    "link": e.link,
                    "abstract": truncate(abstract, ABSTRACT_MAX),
                }

                if do_summary:
                    try:
                        info["summary"] = summarize(title, abstract, model)
                    except Exception as err:
                        info["summary"] = f"(요약 실패: {err})"

                papers.append(info)

        if papers:
            results[topic] = papers
    return results


# ─────────────── 메일 본문 ───────────────
def build_email(papers: Dict[str, List[Dict[str, str]]], include_summary: bool) -> str:
    lines: List[str] = ["📰  오늘의 arXiv\n"]
    for i, (topic, plist) in enumerate(papers.items()):
        header = f"📌 {topic.upper()} ({len(plist)})"
        lines += [header, "=" * len(header)]

        for j, p in enumerate(plist, 1):
            lines.append(f"{j}. 📄 {p['title']}")
            lines.append(f"   🔗 {p['link']}\n")
            lines.append("   📝 Abstract:")
            lines.append(f"      {p['abstract']}\n")

            if include_summary and "summary" in p:
                lines.append("   💡 3-line summary:")
                for line in p["summary"].splitlines():
                    lines.append(f"      {line}")
                lines.append("")

            if j < len(plist):
                lines.append("   " + "-" * 40 + "\n")

        if i < len(papers) - 1:
            lines.append("・" * 30 + "\n")

    lines += [
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "자동 생성된 arXiv 알림입니다. " "주제·키워드는 topics.json에서 변경하세요.",
    ]
    return "\n".join(lines)


# ─────────────── 이메일 발송 ───────────────
def send_email(subj: str, body: str, sender: str, pwd: str, rcpt: str) -> None:
    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subj
    msg["From"] = sender
    msg["To"] = rcpt

    with smtplib.SMTP("smtp.gmail.com", 587) as s:
        s.starttls()
        s.login(sender, pwd)
        s.sendmail(sender, [rcpt], msg.as_string())


# ─────────────────── 메인 ───────────────────
def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--summary", action="store_true", help="Problem/Result/Method 요약 추가"
    )
    ap.add_argument(
        "--model", default="gpt-4o-mini", help="OpenAI 모델 ID (default: gpt-4o-mini)"
    )
    args = ap.parse_args()

    sender = getenv_or_exit("EMAIL_ADDRESS")
    password = getenv_or_exit("EMAIL_PASSWORD")
    recipient = getenv_or_exit("TO_EMAIL")

    if args.summary and openai is None:
        raise SystemExit(
            "openai 패키지가 설치되어 있지 않습니다. "
            "pip install openai 후 다시 시도하세요."
        )

    topics = load_topics(TOPIC_FILE)
    papers = collect_papers(topics, args.summary, args.model)
    if not papers:
        print("[info] no new papers")
        return

    body = build_email(papers, args.summary)
    first_topic, first_list = next(iter(papers.items()))
    subj_plain = (
        f"{date.today():%Y-%m-%d} - 오늘의 arXiv - "
        f"{first_topic} ({len(first_list)})"
    )
    subj_hdr = str(Header(subj_plain, "utf-8"))
    send_email(subj_hdr, body, sender, password, recipient)
    print("[ok] email sent")


if __name__ == "__main__":
    main()
# ──────────────────────────────────────────────
