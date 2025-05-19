import os
import feedparser
import smtplib
import hashlib
from email.mime.text import MIMEText

# === 설정 ===
EMAIL_ADDRESS = os.getenv("EMAIL_ADDRESS")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")
TO_EMAIL = os.getenv("TO_EMAIL")
TOPIC_FILE = "topics.txt"
MAX_RESULTS = 10
TITLE_MAX_CHARS = 150
ABSTRACT_MAX_CHARS = 800
EXCLUDE_KEYWORDS = ["review", "survey", "comment on", "corrigendum"]
# =========================


def load_topics(filepath):
    topics = {}
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            if ":" in line:
                category, keywords = line.strip().split(":", 1)
                topics[category.strip()] = [
                    kw.strip().replace(" ", "+") for kw in keywords.split(",")
                ]
    return topics


def send_email(subject, body):
    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = EMAIL_ADDRESS
    msg["To"] = TO_EMAIL
    with smtplib.SMTP("smtp.gmail.com", 587) as server:
        server.starttls()
        server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
        server.sendmail(EMAIL_ADDRESS, TO_EMAIL, msg.as_string())


def fetch_arxiv_entries(keyword):
    url = f"http://export.arxiv.org/api/query?search_query=all:{keyword}&start=0&max_results={MAX_RESULTS}"
    return feedparser.parse(url).entries


def normalize_text(text):
    # 마침표 뒤 줄바꿈 정리
    lines = text.strip().replace("\n", " ").split(". ")
    return "\n    " + "\n    ".join(
        line.strip() + "." if not line.endswith(".") else line for line in lines
    )


def should_skip(title, summary):
    lower_text = f"{title.lower()} {summary.lower()}"
    return any(keyword.lower() in lower_text for keyword in EXCLUDE_KEYWORDS)


def truncate_text(text, max_len):
    return text if len(text) <= max_len else text[:max_len].rstrip() + "..."


def fetch_and_group_papers(topics):
    results = {}
    seen_ids = set()
    for category, keyword_list in topics.items():
        combined_entries = []
        for keyword in keyword_list:
            entries = fetch_arxiv_entries(keyword)
            for entry in entries:
                uid = hashlib.sha1(entry.id.encode()).hexdigest()
                if uid in seen_ids:
                    continue
                title = entry.title.strip()
                summary = entry.summary.strip().replace("\n", " ")
                if should_skip(title, summary):
                    continue
                summary = normalize_text(summary)
                combined_entries.append(
                    {
                        "title": truncate_text(title, TITLE_MAX_CHARS),
                        "link": entry.link.strip(),
                        "summary": truncate_text(summary, ABSTRACT_MAX_CHARS),
                    }
                )
                seen_ids.add(uid)
        if combined_entries:
            results[category] = combined_entries
    return results


def format_email(papers_by_topic):
    if not papers_by_topic:
        return None
    email = "📰 New arXiv Papers by Topic\n\n"
    for category, papers in papers_by_topic.items():
        email += f"🔹 {category}\n"
        for paper in papers:
            email += f"• {paper['title']}\n  ↳ {paper['link']}\n  Abstract:\n{paper['summary']}\n\n"
    return email


if __name__ == "__main__":
    topics = load_topics(TOPIC_FILE)
    papers = fetch_and_group_papers(topics)
    email_body = format_email(papers)
    if email_body:
        send_email("📰 New arXiv Papers: NV / Holography / CGH", email_body)
        print("✅ Email sent.")
    else:
        print("📭 No new papers.")
