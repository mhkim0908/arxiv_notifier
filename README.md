# arXiv Email Notifier

Receive a daily e‑mail digest of new arXiv papers that match the keywords **you** choose.
The package consists of

* **`arxiv_notifier.py`** – a standalone Python 3 script.
* **`.github/workflows/notify.yml`** – an optional GitHub Actions workflow that runs the script automatically every day.
* **`topics.json`** – your personalised search configuration.

---

## 1  Requirements

| Item          | Notes                                                                         |
| ------------- | ----------------------------------------------------------------------------- |
| Python ≥ 3.11 | `pip install -r requirements.txt` installs *feedparser* & dependencies.       |
| Gmail account | Turn on 2‑Step Verification → create an **App Password** (16‑digit) for SMTP. |
| `topics.json` | Defines search terms, arXiv categories, and optional filters (see §3).        |

> **Using another mail provider?**  Edit `send_email()` in `arxiv_notifier.py` with the correct SMTP host, port and login procedure.

---

## 2  Environment variables

| Variable         | Purpose                                      |
| ---------------- | -------------------------------------------- |
| `EMAIL_ADDRESS`  | Gmail address used to send the digest        |
| `EMAIL_PASSWORD` | Gmail *App Password* (not your normal login) |
| `TO_EMAIL`       | Recipient address                            |

Set them with `export …` (Linux/macOS) or `set …` (Windows cmd) when running locally,
or store them as *Repository → Settings → Secrets* for GitHub Actions.

---

## 3  `topics.json` format

```json
{
  "NV Center": {
    "keywords": ["nv center"],
    "categories": ["quant-ph", "quant-comp", "cond-mat.mes-hall"],
    "exclude_keywords": ["review", "tutorial"],   // optional
    "max_results": 15                               // optional (default 10)
  },
  "Holography": {
    "keywords": [
      "digital holography",
      "computer generated holography"
    ],
    "categories": ["physics.optics", "cs.CV"]
  }
}
```

* **keywords** – searched in *title ∧ abstract* (AND between words).
* **categories** – arXiv subject tags (OR between tags).
* **exclude\_keywords** – if any occur in title/abstract the paper is skipped.
* **max\_results** – per‑keyword cap (per day).

---

## 4  Run locally

```bash
# ① Set environment variables (bash/zsh)
export EMAIL_ADDRESS="you@gmail.com"
export EMAIL_PASSWORD="16‑digit‑app‑password"
export TO_EMAIL="you@domain.tld"

# ② Execute
python arxiv_notifier.py
```

Output:

* `[ok] email sent` – new papers found and mailed.
* `[info] no new papers` – nothing matched today.

---

## 5  Automate with GitHub Actions

The sample workflow below sends the digest at **08:00 KST** every day (23:00 UTC).

```yaml
name: arXiv Email Notifier

on:
  schedule:
    - cron:  "0 23 * * *"   # daily 23:00 UTC = 08:00 KST
  workflow_dispatch:         # allow manual run

jobs:
  send-email:
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      - run: pip install -r requirements.txt
      - run: python arxiv_notifier.py
        env:
          EMAIL_ADDRESS: ${{ secrets.EMAIL_ADDRESS }}
          EMAIL_PASSWORD: ${{ secrets.EMAIL_PASSWORD }}
          TO_EMAIL: ${{ secrets.TO_EMAIL }}
```

1. Commit the file under `.github/workflows/notify.yml`.
2. Add the three secrets (`EMAIL_ADDRESS`, `EMAIL_PASSWORD`, `TO_EMAIL`).

---

## 6  Customise quickly

| Constant (in `arxiv_notifier.py`) | Meaning                           |
| --------------------------------- | --------------------------------- |
| `TITLE_MAX`, `ABSTRACT_MAX`       | Max. characters before truncation |
| `WRAP_WIDTH`                      | Line‑wrap width for the abstract  |
| `GLOBAL_EXCLUDE`                  | Always‑ignored keywords           |

---

## 7  Troubleshooting

* **SMTP auth error** – make sure you used the Gmail *App Password*.
* **No mail received** – check spam folder or GitHub Actions logs.
* **topics file not found** – confirm `topics.json` is beside the script or adjust `TOPIC_FILE`.

---
