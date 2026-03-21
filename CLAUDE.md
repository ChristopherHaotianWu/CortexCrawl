# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

CortexCrawl is a data collection pipeline that monitors crowdfunding and product discovery platforms, syncing results to Feishu (Lark) multi-dimensional tables with bot notifications. It contains two parallel workflows with nearly identical architecture:
- **kickstarter-workflow**: Monitors Kickstarter projects with ≥$500K funding, launched after 2026-01-01
- **producthunt-workflow**: Monitors Product Hunt products with ≥100 votes in the last 30 days

## Commands

Each workflow is self-contained. Run from within the workflow directory:

```bash
# Setup
cd kickstarter-workflow  # or producthunt-workflow
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # then fill in real credentials

# Run workflow
python src/main.py                          # full run
python src/main.py --data-path /custom/path/to/raw.json
python src/main.py --test                   # test mode (no Feishu writes)

# Trigger OpenClaw skill manually (on server)
curl -X POST http://47.254.73.23:8080/api/kickstarter/trigger \
  -H "Authorization: Bearer $OPENCLAW_TOKEN"
```

## Architecture

### Data Flow
```
GraphQL APIs (Kickstarter / Product Hunt)
    → OpenClaw Skill (JS) — daily schedule or webhook trigger
    → Raw JSON file (/data/*/raw_*.json on server)
    → Python workflow (src/main.py)
    → Feishu Bitable (multi-dimensional table) + Webhook notification
```

### Component Roles

**`openclaw/`** — Node.js scripts run inside OpenClaw server
- `skill-config.yaml`: defines trigger schedule, pipeline steps, output destinations
- `fetch-*.js`: queries GraphQL APIs, filters data, writes raw JSON to disk, then POSTs to Python webhook

**`src/config.py`** — Dataclasses for all config: `FeishuConfig`, `OpenClawConfig`, workflow-specific config (thresholds, field mappings). `TABLE_FIELDS` dict maps raw data field names to Feishu column names.

**`src/data_processor.py`** — Core dedup logic: loads raw JSON, compares against existing Feishu records matched by URL, classifies each item as new/updated/unchanged. Only numeric fields (funding amount, backers, votes, comments) are updated; manual fields (履历, 融资历史) are preserved.

**`src/feishu_client.py`** — Feishu API wrapper with 2-hour token caching (refreshed 5 min early). Key methods: `list_records()`, `create_records()` (batch), `update_records()` (batch), `send_webhook_card()`.

**`src/main.py`** — Orchestrates 5 steps: load raw data → fetch Feishu records → process (dedup+update) → write to Feishu → send notification card. Outputs JSON result summary to stdout.

### Deduplication Logic
Records are matched by `project_url` / `product_url` as the dedup key. When a URL already exists in Feishu, only changed numeric fields are updated; manual research fields are left untouched. Missing items in new data are kept (archive behavior, no deletes).

## Environment Variables

Both workflows use the same structure (see `.env.example` in each):
- `OPENCLAW_TOKEN` + `OPENCLAW_BASE_URL`: OpenClaw server auth
- `FEISHU_APP_ID` + `FEISHU_APP_SECRET`: Feishu app credentials
- `FEISHU_BASE_ID` + `FEISHU_TABLE_ID`: Target Bitable table
- `FEISHU_WEBHOOK_URL`: Bot notification endpoint
- Workflow-specific thresholds: `MIN_FUNDING_AMOUNT`, `MIN_LAUNCH_DATE` (Kickstarter) or `PRODUCT_HUNT_API_TOKEN` (Product Hunt)

## Deployment

- Server: Alibaba Cloud ECS at `47.254.73.23`
- OpenClaw runs on port 8080, Python services on port 8000
- Kickstarter skill triggers at UTC 00:00; Product Hunt at UTC 08:00
- Raw data files land at `/data/kickstarter/raw_projects.json` and `/data/producthunt/raw_products.json`
- Cron can also call `python src/main.py` independently if the raw file was already written
