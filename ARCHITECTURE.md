# App Review Insights Analyser - Architecture Documentation

## Table of Contents
1. [System Overview](#system-overview)
2. [Architecture Layers](#architecture-layers)
3. [Data Flow](#data-flow)
4. [Key Components](#key-components)
5. [Technology Stack](#technology-stack)
6. [Data Storage](#data-storage)
7. [Configuration](#configuration)
8. [Testing](#testing)
9. [Deployment & Scheduling](#deployment--scheduling)

---

## System Overview

The **App Review Insights Analyser** is a 4-layer pipeline that automatically:
1. **Imports** app reviews from App Store and Play Store
2. **Classifies** reviews into themes using LLM-based classification
3. **Generates** weekly one-page pulse notes summarizing key insights
4. **Distributes** insights via email to stakeholders

The system processes reviews week-by-week, grouping them into themes and generating actionable insights for product teams.

---

## Architecture Layers

The system follows a **4-layer pipeline architecture** where each layer processes data and passes it to the next:

```
┌─────────────────────────────────────────────────────────────┐
│                    Layer 1: Data Import                      │
│  Scrape → Validate → Deduplicate → Store (Week Buckets)    │
└──────────────────────┬──────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────────┐
│              Layer 2: Theme Extraction                       │
│  Load Reviews → Classify → Group by Theme → Store Themes    │
└──────────────────────┬──────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────────┐
│            Layer 3: Content Generation                       │
│  Load Themes → Summarize → Assemble Pulse → Store Pulse     │
└──────────────────────┬──────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────────┐
│              Layer 4: Distribution                           │
│  Load Pulse → Draft Email → Check PII → Send Email           │
└─────────────────────────────────────────────────────────────┘
```

### Layer 1: Data Import (`layer_1_data_import/`)

**Purpose**: Fetch, validate, clean, and store app reviews from both stores.

**Components**:
- **`scraper.py`**: Fetches reviews from App Store and Play Store using Playwright
- **`validator.py`**: Validates reviews (language, length, PII, emojis)
  - `ReviewValidator`: Main validation logic
  - `TextCleaner`: Removes special characters, normalizes text
  - `PIIDetector`: Detects and filters PII (emails, phones, etc.)
  - `LanguageDetector`: Ensures English-only reviews
- **`deduplicator.py`**: Removes duplicate reviews using text similarity
- **`storage.py`**: Stores reviews in week-level JSON files
- **`import_reviews.py`**: Main entry point orchestrating the import workflow

**Output**: Week-level review files in `data/reviews/reviews_YYYY-MM-DD.json`

**Key Features**:
- Filters non-English reviews
- Removes reviews with emojis
- Detects and filters PII
- Minimum 20 characters after cleaning
- Deduplication based on text similarity
- Stores raw reviews separately for audit

### Layer 2: Theme Extraction (`layer_2_theme_extraction/`)

**Purpose**: Classify reviews into themes and group them for analysis.

**Components**:
- **`classifier.py`**: LLM-based review classifier
  - Processes reviews in batches of 30
  - Uses Gemini LLM to assign each review to one of 5 themes
  - Includes retry logic and rate limiting
- **`theme_config.py`**: Defines the 5 themes and their descriptions
- **`weekly_processor.py`**: Processes reviews week-by-week
- **`classify_reviews.py`**: Main entry point for theme classification

**Themes** (defined in `theme_config.py`):
1. Feature Requests
2. Bug Reports
3. User Experience Issues
4. Performance Issues
5. Other/General Feedback

**Output**: Week-level theme files in `data/themes/themes_YYYY-MM-DD.json`

**Key Features**:
- Batch processing (30 reviews per LLM call)
- Week-by-week processing
- Theme validation and fallback handling
- Configurable max reviews per week limit
- Comprehensive logging and statistics

### Layer 3: Content Generation (`layer_3_content_generation/`)

**Purpose**: Generate weekly one-page pulse notes from classified themes.

**Components**:
- **`theme_summarizer.py`**: Summarizes each theme using LLM
- **`pulse_assembler.py`**: Assembles final pulse document (≤250 words)
  - Selects top 3 themes
  - Extracts 3 representative quotes
  - Generates 3 action items
- **`weekly_pulse_generator.py`**: Orchestrates pulse generation workflow
- **`generate_pulse.py`**: Main entry point

**Output**: Week-level pulse files in `data/pulses/pulse_YYYY-MM-DD.json`

**Pulse Structure**:
- **Title**: One-line summary
- **Overview**: Brief context (2-3 sentences)
- **Top 3 Themes**: Bulleted list with summaries
- **3 Quotes**: Representative user quotes
- **3 Action Items**: Actionable recommendations

**Key Features**:
- Word count limit (250 words)
- LLM-based summarization
- Quote extraction from reviews
- Action item generation
- Retry logic for LLM calls

### Layer 4: Distribution (`layer_4_distribution/`)

**Purpose**: Generate and send weekly email reports to stakeholders.

**Components**:
- **`email_drafter.py`**: Drafts email body from pulse using LLM
  - Converts pulse to email format (≤350 words)
  - Generates subject line
- **`pii_checker.py`**: Checks and removes PII from email content
- **`email_sender.py`**: Sends emails via SMTP (Gmail-ready)
- **`generate_email.py`**: Main entry point orchestrating email workflow

**Output**: Email templates in `data/emails/email_YYYY-MM-DD.json`

**Key Features**:
- Email template caching (reuse without regeneration)
- PII detection and masking
- SMTP email sending (Gmail App Password support)
- Preview mode (safe testing without sending)
- Regeneration flag for forced updates

---

## Data Flow

### Complete Workflow

```
1. SCHEDULER/TRIGGER
   ↓
2. Layer 1: Import Reviews
   ├─ Fetch from App Store (Playwright)
   ├─ Fetch from Play Store (Playwright)
   ├─ Validate (language, length, PII, emojis)
   ├─ Deduplicate
   └─ Store by week → data/reviews/reviews_YYYY-MM-DD.json
   ↓
3. Layer 2: Theme Extraction
   ├─ Load week reviews
   ├─ Batch reviews (30 per batch)
   ├─ Classify with LLM (Gemini)
   ├─ Group by theme
   └─ Store themes → data/themes/themes_YYYY-MM-DD.json
   ↓
4. Layer 3: Content Generation
   ├─ Load theme data
   ├─ Summarize themes (LLM)
   ├─ Assemble pulse (LLM)
   └─ Store pulse → data/pulses/pulse_YYYY-MM-DD.json
   ↓
5. Layer 4: Distribution
   ├─ Load pulse data
   ├─ Draft email (LLM)
   ├─ Check PII
   ├─ Send email (SMTP)
   └─ Store template → data/emails/email_YYYY-MM-DD.json
```

### Data Formats

**Review** (`models/review.py`):
```python
{
    "review_id": str,
    "title": str,
    "text": str,  # Cleaned, PII-free
    "date": datetime,
    "platform": "app_store" | "play_store"
}
```

**Theme Data** (`data/themes/themes_YYYY-MM-DD.json`):
```json
{
    "week_key": "2025-11-24",
    "week_start_date": "2025-11-24",
    "week_end_date": "2025-11-30",
    "themes": {
        "Feature Requests": [
            {"review_id": "...", "text": "...", ...}
        ],
        ...
    },
    "theme_counts": {...},
    "total_reviews": 150
}
```

**Pulse Data** (`data/pulses/pulse_YYYY-MM-DD.json`):
```json
{
    "week_key": "2025-11-24",
    "week_start_date": "2025-11-24",
    "week_end_date": "2025-11-30",
    "pulse": {
        "title": "...",
        "overview": "...",
        "themes": [...],
        "quotes": [...],
        "actions": [...]
    },
    "word_count": 245
}
```

**Email Template** (`data/emails/email_YYYY-MM-DD.json`):
```json
{
    "week_key": "2025-11-24",
    "subject": "...",
    "email_body": "...",
    "word_count": 320,
    "pii_detected": [],
    "generated_at": "..."
}
```

---

## Key Components

### Core Utilities (`utils/`)

**`llm_client.py`**:
- Wraps Google Gemini API
- Handles text generation, clustering, and labeling
- Includes retry logic and rate limiting
- Supports batch processing

**`embeddings_client.py`**:
- Generates embeddings using Gemini embedding model
- Handles batching and retries
- Used for similarity calculations and clustering

**`logger.py`**:
- Centralized logging configuration
- File and console logging
- Configurable log levels

### Configuration (`config/`)

**`settings.py`**:
- Centralized configuration management
- Environment variable loading (`.env`)
- Default values for all settings
- Directory management

**Key Settings**:
- App Store/Play Store URLs and IDs
- Review import date ranges
- Gemini API configuration
- LLM batching and rate limiting
- Clustering parameters (HDBSCAN)
- Email/SMTP configuration
- Scheduler settings

### Data Models (`models/`)

**`review.py`**:
- Review data class
- Week date calculation
- Serialization/deserialization
- Minimal storage schema

### Scheduler (`scheduler.py`)

- Weekly scheduled execution
- Configurable day/time (default: Monday 9 AM IST)
- Runs Layer 1 import automatically
- Can be extended to run full pipeline

---

## Technology Stack

### Core Technologies
- **Python 3.13+**: Main language
- **Playwright**: Web scraping for App Store and Play Store
- **Google Gemini API**: LLM for classification and content generation
  - `gemini-1.5-flash`: Main model for text generation
  - `models/gemini-embedding-001`: Embeddings model
- **ChromaDB**: Vector database for embeddings storage
- **HDBSCAN**: Clustering algorithm (optional, falls back to DBSCAN)

### Key Libraries
- `google-generativeai`: Gemini API client
- `chromadb`: Vector database
- `hdbscan`: Density-based clustering
- `playwright`: Browser automation
- `python-dotenv`: Environment variable management
- `schedule`: Task scheduling

### Data Processing
- JSON for data storage (week-level files)
- Batch processing for efficiency
- Retry logic with exponential backoff
- Rate limiting handling

---

## Data Storage

### Directory Structure

```
data/
├── reviews/
│   ├── raw/                    # Raw reviews before processing
│   │   └── raw_reviews_YYYY-MM-DD.json
│   └── reviews_YYYY-MM-DD.json  # Processed reviews by week
├── themes/
│   └── themes_YYYY-MM-DD.json   # Classified themes by week
├── pulses/
│   └── pulse_YYYY-MM-DD.json     # Generated pulses by week
├── emails/
│   └── email_YYYY-MM-DD.json     # Email templates by week
└── cache/
    ├── chroma/                   # ChromaDB vector database
    │   └── chroma.sqlite3
    └── processed_reviews.json    # Deduplication cache
```

### Storage Strategy

- **Week-level files**: All data organized by week (Monday-Sunday)
- **JSON format**: Human-readable, easy to debug
- **Raw data preservation**: Original reviews stored separately
- **Template caching**: Email templates cached for reuse
- **Vector database**: ChromaDB for embeddings and similarity search

---

## Configuration

### Environment Variables (`.env`)

**App Store Configuration**:
```env
APP_STORE_URL=https://apps.apple.com/...
PLAY_STORE_URL=https://play.google.com/...
ANDROID_APP_ID=com.nextbillion.groww
APPLE_APP_ID=1404871703
```

**Review Import**:
```env
WEEKS_TO_FETCH=12
DAYS_BACK_START=84
DAYS_BACK_END=7
```

**Gemini API**:
```env
GEMINI_API_KEY=your_api_key
GEMINI_MODEL=gemini-1.5-flash
GEMINI_EMBEDDING_MODEL=models/gemini-embedding-001
```

**LLM Batching & Rate Limiting**:
```env
LLM_BATCH_SIZE=100
LLM_MAX_TOKENS_PER_BATCH=800000
LLM_RETRY_ATTEMPTS=5
LLM_RETRY_DELAY_BASE=2.0
LLM_RATE_LIMIT_DELAY=15.0
```

**Clustering**:
```env
HDBSCAN_MIN_CLUSTER_SIZE=5
HDBSCAN_MIN_SAMPLES=2
MAX_THEME_CLUSTERS=5
```

**Email/SMTP**:
```env
PRODUCT_NAME=Groww
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=your.email@gmail.com
SMTP_PASSWORD=your_app_password
FROM_EMAIL=your.email@gmail.com
TO_EMAIL=recipient@example.com
SMTP_USE_TLS=true
```

**Scheduler**:
```env
SCHEDULE_DAY=monday
SCHEDULE_HOUR=9
SCHEDULE_MINUTE=0
```

---

## Testing

### Test Structure (`tests/`)

- **`test_data_import.py`**: Layer 1 tests (scraping, validation, deduplication)
- **`test_theme_extraction.py`**: Layer 2 tests (classification, theme grouping)
- **`test_content_generation.py`**: Layer 3 tests (pulse generation)
- **`test_email_distribution.py`**: Layer 4 tests (email drafting, PII checking, sending)
- **`test_scraper.py`**: Scraper-specific tests
- **`test_scraper_auto.py`**: Automated scraper tests

### Running Tests

```bash
# Run all tests
python tests/test_email_distribution.py

# Run specific test file
python tests/test_data_import.py
```

### Test Coverage

- Unit tests for each layer
- Integration tests for workflows
- Mocked LLM calls for speed
- Error handling validation
- Edge case testing

---

## Deployment & Scheduling

### Manual Execution

**Full Pipeline**:
```bash
python main.py
```

**Individual Layers**:
```bash
# Layer 1: Import reviews
python layer_1_data_import/import_reviews.py

# Layer 2: Classify themes
python layer_2_theme_extraction/classify_reviews.py

# Layer 3: Generate pulses
python layer_3_content_generation/generate_pulse.py

# Layer 4: Generate emails (preview)
python layer_4_distribution/generate_email.py

# Layer 4: Send emails
python layer_4_distribution/generate_email.py --send
```

### Scheduled Execution

**Start Scheduler**:
```bash
python scheduler.py
```

The scheduler runs weekly imports automatically. To run the full pipeline on schedule, extend `scheduler.py` to call all layers.

### Production Considerations

1. **API Rate Limiting**: Built-in retry logic and rate limit handling
2. **Error Handling**: Comprehensive logging and error recovery
3. **Data Persistence**: All data stored in JSON files (consider database for scale)
4. **Email Safety**: Preview mode by default, explicit `--send` flag required
5. **PII Protection**: Automatic detection and removal of PII
6. **Monitoring**: Log files in `logs/app.log`

---

## Design Principles

1. **Layer Separation**: Each layer is independent and can run separately
2. **Week-based Processing**: All data organized by week for consistency
3. **Idempotency**: Re-running layers is safe (uses cached data when available)
4. **Error Resilience**: Retry logic, fallbacks, and comprehensive error handling
5. **Observability**: Extensive logging at each step
6. **Configuration-driven**: All settings via environment variables
7. **Template Caching**: Email templates cached to avoid regeneration
8. **PII Safety**: Multiple layers of PII detection and removal

---

## Future Enhancements

1. **Database Integration**: Replace JSON files with database (PostgreSQL/MongoDB)
2. **Real-time Processing**: Stream processing for new reviews
3. **Multi-app Support**: Support multiple apps/products
4. **Advanced Analytics**: Trend analysis, sentiment over time
5. **Web Dashboard**: UI for viewing insights
6. **API Endpoints**: REST API for programmatic access
7. **Enhanced Clustering**: Better theme discovery with unsupervised learning
8. **Multi-language Support**: Process reviews in multiple languages

---

## Maintenance

### Logs
- Location: `logs/app.log`
- Level: Configurable via `LOG_LEVEL` env var
- Rotation: Consider log rotation for production

### Data Cleanup
- Old reviews: Consider archival strategy
- Cache cleanup: ChromaDB can grow large
- Email templates: Can be regenerated if needed

### Monitoring
- Review import success rate
- LLM API usage and costs
- Email delivery status
- Processing time per week

---

## License

MIT

