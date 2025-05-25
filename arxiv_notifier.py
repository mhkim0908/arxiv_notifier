import hashlib
import json
import os
import smtplib
import time
import calendar
from datetime import date, datetime, timedelta, timezone
from email.header import Header
from email.mime.text import MIMEText
from typing import Any, Dict, List, Optional
from urllib.parse import quote_plus

import feedparser

# Configuration
AI_SUMMARIZE = True
MODEL_ID = "gpt-4"

ENV_VARS = ("EMAIL_ADDRESS", "EMAIL_PASSWORD", "TO_EMAIL")
TOPIC_FILE = "topics.json"

MAX_RESULTS_DEFAULT = 20
TITLE_MAX = 120
ABSTRACT_MAX = 600

GLOBAL_EXCLUDE = {"review", "survey", "comment on", "corrigendum"}

KST = timezone(timedelta(hours=9))
WINDOW_DAYS = int(os.getenv("WINDOW_DAYS", "10"))
API_RATE_SEC = 3

if AI_SUMMARIZE:
    try:
        import openai

        openai.api_key = os.getenv("OPENAI_API_KEY")
    except ImportError:
        AI_SUMMARIZE = False


def getenv_or_exit(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise SystemExit(f"Missing env var: {name}")
    return value


def load_topics(path: str) -> Dict[str, Any]:
    if not os.path.exists(path):
        raise FileNotFoundError(f"Topics file not found: {path}")

    with open(path, encoding="utf-8") as fh:
        topics = json.load(fh)

    for topic_name, config in topics.items():
        if not isinstance(config, dict) or "keywords" not in config:
            raise ValueError(f"Invalid topic config: {topic_name}")

    return topics


def make_query(keyword: str, cats: list[str]) -> str:
    if not keyword.strip():
        raise ValueError("Empty keyword")

    keyword = keyword.strip()

    if " " in keyword:
        phrase = quote_plus(keyword, safe="")
        kw_part = f"(ti:%22{phrase}%22+OR+abs:%22{phrase}%22)"
    else:
        token = keyword if "*" in keyword else f"{keyword}*"
        kw_part = f"(ti:{token}+OR+abs:{token})"

    if cats:
        cat_part = "+OR+".join(f"cat:{c}" for c in cats if c.strip())
        if cat_part:
            return f"({cat_part})+AND+{kw_part}"

    return kw_part


def fetch_entries(q: str, n: int) -> List[Any]:
    if n <= 0:
        raise ValueError("Invalid result count")

    url = (
        "http://export.arxiv.org/api/query?"
        f"search_query={q}&start=0&max_results={n}"
        "&sortBy=submittedDate&sortOrder=descending"
    )

    feed = feedparser.parse(url)

    if hasattr(feed, "status") and feed.status >= 400:
        raise Exception(f"arXiv API error: {feed.status}")

    time.sleep(API_RATE_SEC)
    return getattr(feed, "entries", [])


def _get_entry_timestamp(entry) -> Optional[datetime]:
    """Extract most recent timestamp from entry, prioritizing updated > published > created"""
    for field in ("updated_parsed", "published_parsed", "created_parsed"):
        time_tuple = getattr(entry, field, None)
        if time_tuple:
            try:
                # UTC 시간 튜플을 Unix 타임스탬프로 변환
                timestamp = calendar.timegm(time_tuple)
                # UTC 타임존의 datetime 객체로 변환
                return datetime.fromtimestamp(timestamp, tz=timezone.utc)
            except (ValueError, OSError, OverflowError):
                continue
    return None


def is_in_time_window(entry) -> bool:
    """Check if entry falls within KST time window (yesterday 09:00 - today 09:00)"""
    entry_utc = _get_entry_timestamp(entry)
    if not entry_utc:
        return False

    # Convert to KST
    entry_kst = entry_utc.astimezone(KST)

    # Calculate window boundaries
    now_kst = datetime.now(tz=KST)
    today_09 = now_kst.replace(hour=9, minute=0, second=0, microsecond=0)

    # If current time is before 09:00, use yesterday's 09:00 as end
    if now_kst < today_09:
        today_09 -= timedelta(days=1)

    window_start = today_09 - timedelta(days=WINDOW_DAYS)

    # Entry must be >= window_start and < today_09
    return window_start <= entry_kst < today_09


def truncate(text: str, limit: int) -> str:
    if not text or len(text) <= limit:
        return text

    # Try word boundary truncation
    truncated = text[: limit - 3]
    last_space = truncated.rfind(" ")

    if last_space > limit * 0.7:  # Use word boundary if reasonable
        truncated = truncated[:last_space]

    return truncated.rstrip() + "..."


def summarize(title: str, abstract: str) -> str:
    if not AI_SUMMARIZE:
        return "Summary disabled"

    try:
        resp = openai.chat.completions.create(
            model=MODEL_ID,
            messages=[
                {
                    "role": "system",
                    "content": (
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
    except Exception as e:
        return f"Summary error: {e}"


def collect_papers(topics: Dict[str, Any]) -> Dict[str, List[Dict[str, str]]]:
    output = {}
    seen_ids = set()

    for topic, config in topics.items():
        papers = []
        keywords = config.get("keywords", [])

        for keyword in keywords:
            try:
                query = make_query(keyword, config.get("categories", []))
                max_results = int(config.get("max_results", MAX_RESULTS_DEFAULT))

                entries = fetch_entries(query, max_results)

                for entry in entries:
                    # Time window filter - most critical performance check
                    if not is_in_time_window(entry):
                        continue

                    # Deduplication
                    entry_id = getattr(entry, "id", "")
                    uid = hashlib.sha1(entry_id.encode()).hexdigest()
                    if uid in seen_ids:
                        continue
                    seen_ids.add(uid)

                    # Extract paper data
                    title = " ".join(getattr(entry, "title", "").split())
                    abstract = " ".join(getattr(entry, "summary", "").split())

                    # Global exclusions
                    if any(excl in abstract.lower() for excl in GLOBAL_EXCLUDE):
                        continue

                    paper_info = {
                        "title": truncate(title, TITLE_MAX),
                        "link": getattr(entry, "link", ""),
                        "abstract": truncate(abstract, ABSTRACT_MAX),
                        "authors": ", ".join(
                            a.name for a in getattr(entry, "authors", [])
                        ),
                        "categories": [t.term for t in getattr(entry, "tags", [])],
                    }

                    if AI_SUMMARIZE:
                        paper_info["summary"] = summarize(title, abstract)

                    papers.append(paper_info)

            except Exception:
                continue  # Skip failed queries

        if papers:
            output[topic] = papers

    return output


def build_email(papers: Dict[str, List[Dict[str, str]]]) -> str:
    if not papers:
        return "📰 Daily arXiv Digest\n\nNo new papers found."

    lines = ["📰 Daily arXiv Digest\n"]

    for topic, paper_list in papers.items():
        lines.extend(
            [f"📌 {topic.upper()} ({len(paper_list)})", "=" * (len(topic) + 7)]
        )

        for i, paper in enumerate(paper_list, 1):
            categories = ", ".join(paper["categories"])
            lines.append(f"{i}. 📄 {paper['title']} ({categories})")
            lines.append(f"   🔗 {paper['link']}")
            lines.append(f"   👥 {truncate(paper.get('authors', 'Unknown'), 80)}")

            if AI_SUMMARIZE and "summary" in paper:
                lines.append("   💡 Summary:")
                for line in paper["summary"].splitlines():
                    if line.strip():
                        lines.append(f"      {line}")

            if i < len(paper_list):
                lines.append("   " + "-" * 40)

        lines.append("-" * 30)

    lines.extend(
        [
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            f"Window: {WINDOW_DAYS} day(s) ending at today 09:00 KST",
        ]
    )
    return "\n".join(lines)


def send_email(
    subject: str, body: str, sender: str, pwd: str, recipients: list[str]
) -> None:
    if not recipients:
        raise ValueError("No recipients")

    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = ", ".join(recipients)

    with smtplib.SMTP("smtp.gmail.com", 587) as server:
        server.starttls()
        server.login(sender, pwd)
        server.sendmail(sender, recipients, msg.as_string())


def main() -> None:
    try:
        sender, pwd, recipients_raw = (getenv_or_exit(k) for k in ENV_VARS)
        recipients = [e.strip() for e in recipients_raw.split(",") if e.strip()]

        topics = load_topics(TOPIC_FILE)
        papers = collect_papers(topics)

        if not papers:
            return

        subject = str(Header(f"{date.today():%Y-%m-%d} – arXiv Digest"))
        send_email(subject, build_email(papers), sender, pwd, recipients)

    except Exception as e:
        print(f"Error: {e}")
        raise


if __name__ == "__main__":
    main()
