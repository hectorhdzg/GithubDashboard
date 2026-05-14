# GitHub Dashboard

A Flask web application that provides a centralized view of GitHub issues and pull requests across multiple repositories. Data is fetched from a separate sync service and displayed through an interactive Bootstrap UI.

## Architecture

```
Sync Service (REST API)  →  SyncClient (HTTP)  →  Flask Routes  →  Jinja2 Templates  →  Vanilla JS
```

- **Backend**: Flask 3.0 with Jinja2 server-side rendering
- **Data Source**: External sync service providing repository, issue, and PR data via REST API
- **Frontend**: Bootstrap 4.6, Font Awesome 6, vanilla JavaScript (no framework)
- **Storage**: Browser localStorage for followed items; all repo data comes from sync service

## Features

- **Repository Dashboard** — Browse issues and PRs filtered by repo, state, and type
- **Navbar Grouping** — Repositories organized by language and category with open-item badges
- **Followed Items** — Bookmark any issue/PR to a personal list persisted in localStorage
- **Search, Sort & Pagination** — Client-side table controls for all views
- **Color-Coded Labels** — Deterministic HSL colors for labels and categories
- **Health Check** — `/health` endpoint for load balancers and monitoring

## Setup

### Prerequisites

- Python 3.11+
- Node.js 18+ (for JS tests only)
- A running sync service instance

### Installation

```bash
# Install Python dependencies
pip install -r requirements.txt

# (Optional) Install JS test dependencies
npm install
```

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `SYNC_SERVICE_URL` | `http://localhost:8000` | Base URL of the sync service REST API |
| `PORT` | `8001` | Port the Flask app listens on |

### Running

```bash
# Development
cd src
python app.py

# Production (Azure App Service)
./startup.sh
```

The dashboard will be available at `http://localhost:8001`.

## API Endpoints

| Route | Description |
|-------|-------------|
| `/` | Followed items page |
| `/favorites` | Followed items page (alias) |
| `/dashboard?repo=owner/repo&type=issues&state=open` | Issues/PRs dashboard |
| `/health` | Health check (returns JSON with sync service connectivity status) |

## Testing

```bash
# Python tests (107 tests)
python -m pytest tests/unit/ -v

# JavaScript tests (36 tests)
npx jest --verbose

# Python tests with coverage
python -m pytest tests/unit/ --cov=src --cov-report=term-missing
```

## Project Structure

```
src/
  app.py                 # Flask app factory, routes, helpers
  services/
    sync_client.py       # HTTP wrapper for sync service API
static/
  css/                   # Dashboard and table styles
  js/
    work_items_table.js  # Table behavior (sort, search, pagination, follow)
    followed.js          # Followed items page logic
templates/
  base.html              # Base layout with navbar and CDN assets
  dashboard.html         # Issues/PRs dashboard view
  favorites/index.html   # Followed items view
  components/
    navbar.html          # Navigation bar with repo grouping
    work_items_table.html # Reusable table macro
tests/
  unit/                  # Python unit tests
  js/                    # Jest tests for frontend JS
  integration/           # Integration tests
```
