import feedparser
import smtplib
from email.mime.text import MIMEText
import hashlib
import os

TOPICS = {
    "NV Center": "nv+center",
    "Digital Holography": "digital+holography",
    "CGH": "computer+generated+holography",
}
MAX_RESULTS = 10

EMAIL_ADDRESS = os.getenv("EMAIL_ADDRESS")  # GitHub Secrets에 저장됨
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")
TO_EMAIL = os.getenv("TO_EMAIL")


def send_email(subject, body):
    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = EMAIL_ADDRESS
    msg["To"] = TO_EMAIL

    with smtplib.SMTP("smtp.gmail.com", 587) as server:
        server.starttls()
        server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
        server.sendmail(EMAIL_ADDRESS, TO_EMAIL, msg.as_string())


def fetch_and_format():
    notified = set()
    new_papers = {}

    for topic_name, keyword in TOPICS.items():
        rss_url = f"http://export.arxiv.org/api/query?search_query=all:{keyword}&start=0&max_results={MAX_RESULTS}"
        feed = feedparser.parse(rss_url)
        entries = []
        for entry in feed.entries:
            uid = hashlib.sha1(entry.id.encode()).hexdigest()
            if uid not in notified:
                summary = entry.summary.replace("\n", " ").strip()
                summary = "\n    " + "\n    ".join(summary.split(". "))
                entries.append((entry.title.strip(), entry.link.strip(), summary))
                notified.add(uid)
        if entries:
            new_papers[topic_name] = entries
    return new_papers


def format_email_body(papers_dict):
    if not papers_dict:
        return None
    body = "📰 New arXiv Papers by Topic:\n\n"
    for category, papers in papers_dict.items():
        body += f"🔹 {category}:\n"
        for title, link, summary in papers:
            body += f"- {title}\n  {link}\n  Abstract:\n{summary}\n\n"
    return body


if __name__ == "__main__":
    papers = fetch_and_format()
    email_body = format_email_body(papers)
    if email_body:
        send_email("New arXiv Papers: NV / Holography / CGH", email_body)
        print("Email sent.")
    else:
        print("No new papers found.")
