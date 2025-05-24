#!/usr/bin/env python3
"""
arxiv_notifier_test.py
Run the full arXiv → filter → GPT-summary → e-mail pipeline
without touching SMTP.  Designed for CI / GitHub Actions.
"""
from __future__ import annotations
import json
import pathlib
import sys
from arxiv_notifier import (
    load_topics,
    collect_papers,
    build_email,
    summarize,  # re-exports openai-based summarizer
)

TOPIC_FILE = "topics.json"
ARTIFACT_DIR = pathlib.Path("artifacts")
ARTIFACT_DIR.mkdir(exist_ok=True)


def main() -> None:
    topics = load_topics(TOPIC_FILE)

    # 1) fetch + filter
    papers = collect_papers(topics)

    # 2) dump raw structure for later inspection
    (ARTIFACT_DIR / "papers.json").write_text(
        json.dumps(papers, indent=2, ensure_ascii=False)
    )

    # 3) build the final e-mail body
    body = build_email(papers)
    (ARTIFACT_DIR / "email.txt").write_text(body)

    # 4) also print to stdout (Actions → step log / $GITHUB_STEP_SUMMARY)
    print(body)


if __name__ == "__main__":
    sys.exit(main())
