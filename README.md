# App Review Insights Analyser

Automated pipeline that fetches app reviews, classifies them into themes, generates weekly summaries, and sends email reports.

## File Structure

```
App-Review-Insights-Analyser/
├── main.py                          # Main entry - runs all 4 layers
├── scheduler.py                     # Weekly automated scheduler
├── config/settings.py               # Configuration
├── layer_1_data_import/             # Step 1: Fetch & validate reviews
│   ├── import_reviews.py           # Main workflow
│   ├── scraper.py                  # Web scraping
│   ├── validator.py                # Quality checks
│   └── storage.py                  # Save by week
├── layer_2_theme_extraction/        # Step 2: Classify into 5 themes
│   ├── classify_reviews.py        # Main workflow
│   └── classifier.py              # AI classification
├── layer_3_content_generation/      # Step 3: Generate summaries
│   ├── generate_pulse.py          # Main workflow
│   └── pulse_assembler.py          # Assemble (≤250 words)
├── layer_4_distribution/            # Step 4: Generate & send emails
│   ├── generate_email.py          # Main workflow
│   ├── email_drafter.py           # Draft email (≤350 words)
│   └── email_sender.py            # Send via SMTP
├── models/review.py                  # Review data model
├── utils/                           # LLM client, logger
└── data/                            # Output files (created at runtime)
    ├── reviews/                    # Processed reviews
    ├── themes/                     # By theme
    ├── pulses/                      # Weekly summaries
    └── emails/                      # Email templates
```

## Basic Architecture

**4-Layer Pipeline:**

1. **Data Import** → Fetches from App Store & Play Store, validates (English, no emojis/PII), stores by week
2. **Theme Extraction** → AI classifies reviews into 5 themes: Feature Requests, Bug Reports, UX Issues, Performance, Other
3. **Content Generation** → Creates weekly summaries (≤250 words) with top themes, quotes, actions
4. **Distribution** → Drafts emails (≤350 words), removes PII, sends via SMTP

**Flow:** Reviews → Themes → Pulses → Emails

## How to Run

### Setup

1. **Install dependencies:**
   ```bash
   python -m venv venv
   venv\Scripts\activate  # Windows
   pip install -r requirements.txt
   ```

2. **Create `.env` file:**
   ```env
   GEMINI_API_KEY=your_api_key
   SMTP_USERNAME=your.email@gmail.com
   SMTP_PASSWORD=your_app_password
   TO_EMAIL=recipient@example.com
   FROM_EMAIL=your.email@gmail.com
   ```

3. **Get API keys:**
   - Gemini API: https://makersuite.google.com/app/apikey
   - Gmail App Password: https://myaccount.google.com/apppasswords (enable 2-Step first)

### Execution

**Full pipeline:**
```bash
python main.py
```

**Individual layers:**
```bash
python layer_1_data_import/import_reviews.py
python layer_2_theme_extraction/classify_reviews.py
python layer_3_content_generation/generate_pulse.py
python layer_4_distribution/generate_email.py          # Preview
python layer_4_distribution/generate_email.py --send   # Send
```

**Scheduled:**
```bash
python scheduler.py
```

## Output Files

- Reviews: `data/reviews/reviews_YYYY-MM-DD.json`
- Themes: `data/themes/themes_YYYY-MM-DD.json`
- Pulses: `data/pulses/pulse_YYYY-MM-DD.json`
- Emails: `data/emails/email_YYYY-MM-DD.json`

## Configuration

Edit `config/settings.py` or set environment variables:
- `WEEKS_TO_FETCH`: Weeks of reviews (default: 12)
- `GEMINI_MODEL`: AI model (default: gemini-1.5-flash)
- `MAX_REVIEWS_PER_WEEK`: Testing limit (0 = no limit)
