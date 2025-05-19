import os
import feedparser
import smtplib
import hashlib
import textwrap
import json
from email.mime.text import MIMEText
from typing import List, Dict, Any, Optional

EMAIL_ADDRESS_ENV = "EMAIL_ADDRESS"
EMAIL_PASSWORD_ENV = "EMAIL_PASSWORD"
TO_EMAIL_ENV = "TO_EMAIL"
TOPIC_FILE = "topics.json"
MAX_RESULTS = 10
TITLE_MAX_CHARS = 150
ABSTRACT_MAX_CHARS = 800
GLOBAL_EXCLUDE_KEYWORDS = ["review", "survey", "comment on", "corrigendum"]


def check_env_vars():
    required_vars = [EMAIL_ADDRESS_ENV, EMAIL_PASSWORD_ENV, TO_EMAIL_ENV]
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    if missing_vars:
        print(
            f"Error: The following environment variables are not set: {', '.join(missing_vars)}"
        )
        exit(1)


def load_topics_from_json(filepath: str) -> Dict[str, Dict[str, Any]]:
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"Error: Configuration file ({filepath}) not found.")
        exit(1)
    except json.JSONDecodeError:
        print(
            f"Error: The JSON format of the configuration file ({filepath}) is invalid."
        )
        exit(1)


def build_query(keyword: str, categories: List[str]) -> str:
    if categories:
        cat_part = "(" + "+OR+".join(f"cat:{c.strip()}" for c in categories) + ")"
        return f"{cat_part}+AND+all:{keyword}"
    else:
        return f"all:{keyword}"


def send_email(
    subject: str, body: str, email_address: str, email_password: str, to_email: str
) -> None:
    try:
        msg = MIMEText(body, "plain", "utf-8")
        msg["Subject"] = subject
        msg["From"] = email_address
        msg["To"] = to_email
        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            server.login(email_address, email_password)
            server.sendmail(email_address, to_email, msg.as_string())
    except smtplib.SMTPException as e:
        print(f"Error occurred while sending email: {e}")
    except Exception as e:
        print(f"Unknown error occurred while sending email: {e}")


def fetch_arxiv_entries(query: str, max_results: int) -> List[Any]:
    url = f"http://export.arxiv.org/api/query?search_query={query}&start=0&max_results={max_results}"
    try:
        feed = feedparser.parse(url)
        if feed.bozo:
            print(
                f"Warning: There might be an issue parsing the feed. URL: {url}, Reason: {feed.bozo_exception}"
            )
        return feed.entries
    except Exception as e:
        print(f"Error occurred during arXiv API call (URL: {url}): {e}")
        return []


def normalize_text(text: str) -> str:
    lines = text.strip().replace("\n", " ").split(". ")
    cleaned_lines = []
    for line in lines:
        stripped_line = line.strip()
        if stripped_line:
            if not stripped_line.endswith("."):
                stripped_line += "."
            cleaned_lines.append(stripped_line)
    cleaned = "\n".join(cleaned_lines)
    return textwrap.indent(cleaned, "    ")


def should_skip(title: str, summary: str, exclude_keywords: List[str]) -> bool:
    lower_text = f"{title.lower()} {summary.lower()}"
    return any(keyword.lower() in lower_text for keyword in exclude_keywords)


def truncate_text(text: str, max_len: int) -> str:
    return text if len(text) <= max_len else text[:max_len].rstrip() + "..."


def fetch_and_group_papers(
    topics_config: Dict[str, Dict[str, Any]],
) -> Dict[str, List[Dict[str, str]]]:
    results: Dict[str, List[Dict[str, str]]] = {}
    seen_ids = set()

    for topic_name, config_data in topics_config.items():
        keyword_list = config_data.get("keywords", [])
        category_filters = config_data.get("categories", [])
        topic_specific_exclude_keywords = config_data.get(
            "exclude_keywords", GLOBAL_EXCLUDE_KEYWORDS
        )
        topic_max_results = config_data.get("max_results", MAX_RESULTS)

        collected_papers_for_topic: List[Dict[str, str]] = []
        for kw in keyword_list:
            print(f"Searching for keyword '{kw}' under topic '{topic_name}'...")
            query = build_query(kw, category_filters)
            entries = fetch_arxiv_entries(query, topic_max_results)
            if not entries:
                print(f"  No results found for keyword '{kw}'.")
                continue

            for entry in entries:
                entry_id_suffix = entry.id.split("/")[-1]
                uid = hashlib.sha1(entry_id_suffix.encode()).hexdigest()

                if uid in seen_ids:
                    continue
                seen_ids.add(uid)

                title = entry.title.strip()
                summary = entry.summary

                if should_skip(title, summary, topic_specific_exclude_keywords):
                    continue

                normalized_summary = normalize_text(summary)
                collected_papers_for_topic.append(
                    {
                        "title": truncate_text(title, TITLE_MAX_CHARS),
                        "link": entry.link.strip(),
                        "summary": truncate_text(
                            normalized_summary, ABSTRACT_MAX_CHARS
                        ),
                    }
                )

        if collected_papers_for_topic:
            results[topic_name] = collected_papers_for_topic
            print(
                f"Found {len(collected_papers_for_topic)} new paper(s) for topic '{topic_name}'."
            )
        else:
            print(f"No new papers found for topic '{topic_name}'.")

    return results


def format_email_body(
    papers_by_topic: Dict[str, List[Dict[str, str]]],
) -> Optional[str]:
    if not papers_by_topic:
        return None

    email_parts: List[str] = ["📰 *New arXiv Papers by Topic*\n"]
    for topic_name, papers in papers_by_topic.items():
        email_parts.append(f"🔹 *{topic_name}* ({len(papers)} papers)\n")
        for paper in papers:
            title = paper["title"].replace("\n", " ").strip()
            email_parts.append(f"• {title}")
            email_parts.append(f"  🔗 {paper['link']}")
            email_parts.append(f"  📄 Abstract:\n{paper['summary']}")
        email_parts.append("")

    return "\n".join(email_parts)


if __name__ == "__main__":
    check_env_vars()

    EMAIL_ADDRESS = os.getenv(EMAIL_ADDRESS_ENV)
    EMAIL_PASSWORD = os.getenv(EMAIL_PASSWORD_ENV)
    TO_EMAIL = os.getenv(TO_EMAIL_ENV)

    topics_data = load_topics_from_json(TOPIC_FILE)
    papers_found = fetch_and_group_papers(topics_data)

    email_body_content = format_email_body(papers_found)

    if email_body_content:
        found_topic_names = list(papers_found.keys())
        subject_detail = (
            ", ".join(found_topic_names) if found_topic_names else "General Topics"
        )
        email_subject = f"📰 New arXiv Papers: {subject_detail}"

        print(f"\nAttempting to send email with subject: {email_subject}")
        send_email(
            email_subject, email_body_content, EMAIL_ADDRESS, EMAIL_PASSWORD, TO_EMAIL
        )
        print("✅ Email sent.")
    else:
        print("\n📭 No new papers to report.")
