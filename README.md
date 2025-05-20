# arXiv Email Notifier 📧

Receive a daily e-mail digest of **recent** arXiv papers that match the keywords **you** choose.

---

## 1  Key features

| Item                               | Description                                                                                                                                                          |
| ---------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **`arxiv_notifier.py`**            | Stand-alone Python 3 script. Sends only papers submitted in the last ***N* days\_** (`DAYS_BACK`, default `1`). Optional 3-line GPT summary (toggle `AI_SUMMARIZE`). |
| **`.github/workflows/notify.yml`** | GitHub Actions workflow that mails the digest every day.                                                                                                             |
| **`topics.json`**                  | Your personal keyword & category definitions.                                                                                                                        |

---

## 2  Requirements

| Item          | Notes                                                                                            |
| ------------- | ------------------------------------------------------------------------------------------------ |
| Python ≥ 3.11 | `pip install -r requirements.txt` installs *feedparser* (and *openai* if summaries are enabled). |
| Gmail account | Enable 2-Step Verification → create a **16-digit App Password** for SMTP.                        |
| `topics.json` | Configure search terms, categories, and optional filters (see §4).                               |

> **Different mail provider?** Edit `send_email()` inside `arxiv_notifier.py`.

---

## 3  Environment variables

| Variable         | Purpose                             | Needed when                   |
| ---------------- | ----------------------------------- | ----------------------------- |
| `EMAIL_ADDRESS`  | Gmail address that sends the digest | Always                        |
| `EMAIL_PASSWORD` | Gmail **App Password**              | Always                        |
| `TO_EMAIL`       | Recipient address                   | Always                        |
| `OPENAI_API_KEY` | OpenAI key for summaries            | Only if `AI_SUMMARIZE = True` |

Set them locally (`export …`) or store as *Repository → Settings → Secrets* in GitHub.

---

## 4  `topics.json` example

```jsonc
{
  "NV Center": {
    "keywords": ["nv center"],
    "categories": ["quant-ph", "cond-mat.mes-hall"],
    "max_results": 15
  },
  "Holography": {
    "keywords": [
      "digital holography",
      "computer generated holography"
    ],
    "categories": ["physics.optics", "cs.IT"]
  }
}
```

* **keywords** – searched as exact phrases in *title ∨ abstract*.
* **categories** – OR-joined arXiv tags.
* **max\_results** – per-keyword cap per run (default 10).
* **exclude\_keywords** – if any match, the paper is skipped.

---

## 5  Running locally

```bash
# 1  Set environment variables
export EMAIL_ADDRESS="you@gmail.com"
export EMAIL_PASSWORD="16-digit-app-password"
export TO_EMAIL="you@domain.tld"
export OPENAI_API_KEY="sk-…"        # only if summaries enabled

# 2  Run
python arxiv_notifier.py
```

Output:

* `[ok] email sent` – new papers found (within `DAYS_BACK` days) and mailed.
* `[info] no new papers` – nothing matched.

---

## 6  Automate with GitHub Actions

```yaml
name: arXiv Email Notifier

on:
  schedule:
    - cron: "0 23 * * *"   # every day 23:00 UTC = 08:00 KST
  workflow_dispatch:

jobs:
  send-email:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - name: Install deps
        run: pip install -r requirements.txt
      - name: Send digest
        env:
          EMAIL_ADDRESS:  ${{ secrets.EMAIL_ADDRESS }}
          EMAIL_PASSWORD: ${{ secrets.EMAIL_PASSWORD }}
          TO_EMAIL:       ${{ secrets.TO_EMAIL }}
          OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
        run: python arxiv_notifier.py
```

---

## 7  Quick-tweak constants (`arxiv_notifier.py`)

| Constant                    | Role                                                    |
| --------------------------- | ------------------------------------------------------- |
| `AI_SUMMARIZE`              | `True/False` – add GPT 3-line summary                   |
| `MODEL_ID`                  | OpenAI model (e.g. `gpt-4.5-preview`, `gpt-4o-mini`)    |
| `DAYS_BACK`                 | **Number of days back** to include papers (default `1`) |
| `TITLE_MAX`, `ABSTRACT_MAX` | Truncation limits                                       |
| `GLOBAL_EXCLUDE`            | Always-ignored keywords                                 |

---

## 8  Troubleshooting

* **SMTP auth error** – verify App Password.
* **No mail received** – check spam or Actions log.
* **No new papers** – no matches in the last `DAYS_BACK` days.
* **Summary fails** – ensure `OPENAI_API_KEY` is valid and model available.

---

Enjoy your automated daily research digest 🎉
