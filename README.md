name: arXiv Email Notifier

on:
  schedule:
    - cron:  "0 23 * * *"           # 매일 23:00 UTC = 08:00 KST
  workflow_dispatch:                # 수동 실행 허용

jobs:
  send-email:
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      # 🔹 requirements.txt에 명시된 패키지 설치
      - name: Install Python dependencies
        run: pip install -r requirements.txt

      - name: Run arXiv notifier
        env:
          EMAIL_ADDRESS:  ${{ secrets.EMAIL_ADDRESS }}
          EMAIL_PASSWORD: ${{ secrets.EMAIL_PASSWORD }}
          TO_EMAIL:       ${{ secrets.TO_EMAIL }}
          OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}   # AI_SUMMARIZE=True 면 필요
        run: python arxiv_notifier.py
