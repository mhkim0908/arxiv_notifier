# arXiv Email Notifier

Receive a daily e‑mail digest of new arXiv papers that match **your** keywords.

---

## 1  Features

| Option                      | Default                | Description                                                                                                             |
| --------------------------- | ---------------------- | ----------------------------------------------------------------------------------------------------------------------- |
| **Keyword/Category filter** | –                      | Collect papers by topic definitions in `topics.json`.                                                                   |
| **AI 3‑line summary**       | `AI_SUMMARIZE = False` | If enabled, the script uses an OpenAI model to add **Problem / Result / Method** (one sentence each) under every paper. |
| **GitHub Actions support**  | –                      | Sample workflow automates sending the digest at a fixed time every day.                                                 |

---

## 2  Requirements

| Item          | Notes                                                                                                 |
| ------------- | ----------------------------------------------------------------------------------------------------- |
| Python ≥ 3.11 | `pip install -r requirements.txt` installs **feedparser** (always) and **openai** (when summarising). |
| Gmail account | Turn on 2‑Step Verification → create an **App Password** (16‑digit) for SMTP.                         |
| `topics.json` | Defines search terms, arXiv categories, and optional filters (see §4).                                |

> **Another mail provider?**  Edit `send_email()` in `arxiv_notifier.py` (SMTP host / port / login).
> **Another LLM?**  Adjust `summarize()` inside the script.

---

## 3  Environment variables

| Variable         | Purpose                                   | Needed when                   |
| ---------------- | ----------------------------------------- | ----------------------------- |
| `EMAIL_ADDRESS`  | Gmail address that sends the digest       | Always                        |
| `EMAIL_PASSWORD` | Gmail **App Password** (not normal login) | Always                        |
| `TO_EMAIL`       | Recipient address                         | Always                        |
| `OPENAI_API_KEY` | OpenAI key for Chat Completion API        | Only if `AI_SUMMARIZE = True` |

Set them with `export …` (Linux/macOS) or `set …` (Windows cmd) when running locally,
or store them as *Repository → Settings → Secrets* for GitHub Actions.

---

## 4  `topics.json` format

```jsonc
{
  "NV Center": {
    "keywords": ["nv center"],
    "categories": ["quant-ph", "cond-mat.mes-hall"],
    "exclude_keywords": ["review", "tutorial"],
    "max_results": 15
  },
  "Holography": {
    "keywords": [
      "digital holography",
      "computer generated holography"
    ],
    "categories": ["quant-ph", "cs.IT", "physics.optics"]
  }
}
```

* **keywords** – searched as *exact phrases* in *title ∨ abstract*.
* **categories** – arXiv subject tags (OR‑joined).
* **exclude\_keywords** – if any occur in title/abstract the paper is skipped.
* **max\_results** – per‑keyword cap (per run).

---

## 5  Run locally

1. Clone the repo and edit `topics.json` to taste.
2. Ensure environment variables are set:

   ```bash
   export EMAIL_ADDRESS="you@gmail.com"
   export EMAIL_PASSWORD="16‑digit‑app‑password"
   export TO_EMAIL="you@domain.tld"
   export OPENAI_API_KEY="sk‑…"      # only if summarising
   ```
3. Toggle summarising inside the script (top of `arxiv_notifier.py`):

   ```python
   AI_SUMMARIZE = True     # or False
   MODEL_ID = "gpt-4o-mini"
   ```
4. Run:

   ```bash
   python arxiv_notifier.py
   ```

Output:

* `[ok] email sent` – new papers found and mailed.
* `[info] no new papers` – nothing matched today.

---

## 6  Automate with GitHub Actions

Example workflow sending at **08:00 KST** (23:00 UTC):

```yaml
name: arXiv Email Notifier

on:
  schedule:
    - cron:  "0 23 * * *"   # daily 23:00 UTC = 08:00 KST
  workflow_dispatch:

jobs:
  send-email:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      - name: Install dependencies
        run: pip install -r requirements.txt   # installs feedparser (+ openai if listed)   # openai not strictly needed if summarising off
      - name: Send digest
        env:
          EMAIL_ADDRESS:   ${{ secrets.EMAIL_ADDRESS }}
          EMAIL_PASSWORD:  ${{ secrets.EMAIL_PASSWORD }}
          TO_EMAIL:        ${{ secrets.TO_EMAIL }}
          OPENAI_API_KEY:  ${{ secrets.OPENAI_API_KEY }}   # omit if summarising off
        run: python arxiv_notifier.py
```

Adjust the cron time for your timezone and toggle `AI_SUMMARIZE` in the script.

---

## 7  Quick customisation points

| Constant (in `arxiv_notifier.py`) | Meaning                           |
| --------------------------------- | --------------------------------- |
| `TITLE_MAX`, `ABSTRACT_MAX`       | Max. characters before truncation |
| `GLOBAL_EXCLUDE`                  | Always‑ignored keywords           |
| `AI_SUMMARIZE`, `MODEL_ID`        | Toggle AI summary & model choice  |

---

## 8  Troubleshooting

* **SMTP auth error** → Verify Gmail *App Password* is used.
* **No mail received** → Check spam or GitHub Actions logs.
* **topics file not found** → Ensure `topics.json` sits beside the script or adjust `TOPIC_FILE`.

---

Enjoy an automated daily research digest! 🎉
