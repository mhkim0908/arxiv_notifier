#!/usr/bin/env python3
"""
arxiv_notifier_test.py – dry-run for CI / local debugging
Fetch→filter→summarize→construct e-mail, but never send SMTP.
"""

from __future__ import annotations
import json, pathlib, sys, os
from datetime import datetime

ROOT = pathlib.Path(__file__).resolve().parent
ARTIFACT_DIR = ROOT / "artifacts"
ARTIFACT_DIR.mkdir(exist_ok=True)

from arxiv_notifier import (
    load_topics,
    make_query,
    fetch_entries,
    is_in_time_window,
    GLOBAL_EXCLUDE,
    truncate,
    summarize,
    build_email,
    KST,
    MAX_RESULTS_DEFAULT,
    _get_entry_timestamp,  # Add this import
)

TOPIC_FILE = "topics.json"
ARTIFACT_DIR = pathlib.Path("artifacts")
ARTIFACT_DIR.mkdir(exist_ok=True)

### NEW: counters
stats = {"total": 0, "kept": 0, "per_topic": {}}


def format_date(entry):
    """Helper function to safely format date using the same logic as main module"""
    dt = _get_entry_timestamp(entry)
    if dt:
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    else:
        # Fallback: try to use published string directly
        published = getattr(entry, "published", "Unknown date")
        return published if isinstance(published, str) else str(published)


def collect_with_stats(topics):
    """clone of collect_papers(), but records totals"""
    out, seen = {}, set()

    for topic, cfg in topics.items():
        kept_here, total_here = 0, 0
        for kw in cfg["keywords"]:
            entries = fetch_entries(
                make_query(kw, cfg["categories"]),
                int(cfg.get("max_results", MAX_RESULTS_DEFAULT)),
            )
            total_here += len(entries)
            for e in entries:
                if not is_in_time_window(e):
                    continue
                if any(x in e.summary.lower() for x in GLOBAL_EXCLUDE):
                    continue
                uid = e.id
                if uid in seen:
                    continue
                seen.add(uid)
                kept_here += 1
                out.setdefault(topic, []).append(
                    {
                        "title": truncate(e.title, 120),
                        "link": e.link,
                        "abstract": truncate(e.summary, 500),
                        "authors": ", ".join(a.name for a in e.authors),
                        "categories": [t.term for t in e.tags],
                        "summary": summarize(e.title, e.summary) if e.summary else "",
                        "date": format_date(
                            e
                        ),  # Fixed: pass entire entry, not e.published
                    }
                )
        ### NEW: accumulate per-topic
        stats["per_topic"][topic] = {"total": total_here, "kept": kept_here}
        stats["total"] += total_here
        stats["kept"] += kept_here
    return out


def main() -> None:
    topics = load_topics(TOPIC_FILE)
    papers = collect_with_stats(topics)

    # 1) artefacts
    (ARTIFACT_DIR / "papers.json").write_text(json.dumps(papers, indent=2))
    (ARTIFACT_DIR / "email.txt").write_text(build_email(papers))

    # 2) console summary
    print(f"=== Stats (last {os.getenv('WINDOW_DAYS', 1)} day(s)) ===")
    print(f"TOTAL fetched : {stats['total']}")
    print(f"TOTAL kept    : {stats['kept']}")
    for t, s in stats["per_topic"].items():
        print(f"  • {t:25s} {s['kept']:3d} / {s['total']}")
    print("================================\n")

    # 3) print the email body
    print((ARTIFACT_DIR / "email.txt").read_text())


if __name__ == "__main__":
    sys.exit(main())
