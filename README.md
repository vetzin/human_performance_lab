# human_performance_lab
Human Performance Lab is the place where you can measure your progress in everhting in regards to health and fitness

## Run the dashboard locally

By default, the run script **only starts the local server** and does not fetch data from Notion. Use the `sync` parameter when you want to refresh data from Notion first.

- **Windows:** Double-click `run_app_local.bat`, or run:
  - `run_app_local.bat` — start the server only (uses existing `docs/data.json`).
  - `run_app_local.bat sync` — sync from Notion, then start the server.

1. Open **http://localhost:8080** in your browser.

### Optional: sync from Notion before running

1. **Set up Notion API access** (one-time):
   - Create an [integration](https://www.notion.so/my-integrations) in Notion and copy the "Internal Integration Secret" → set as `NOTION_API_KEY` (or `NOTION_TOKEN`).
   - Open your exercise-log database in Notion → "…" → **Add connections** → select the integration.
   - Copy the database ID from the URL (32-character string, with or without hyphens) → set as `NOTION_DATABASE_ID`.
   - Optionally copy `.env.example` to `.env` and fill in the values so you don’t need to set them in the shell.

2. **Sync then serve** (when you want fresh data):
   ```bash
   run_app_local.bat sync
   ```
   Or from the repo root:
   ```bash
   python scripts/sync_notion.py
   python -m http.server 8080 -d docs
   ```
   If the sync fails, set `NOTION_API_KEY` and `NOTION_DATABASE_ID` in the environment or in `.env`.

### Manual (Excel export)

If you prefer to export from Notion by hand:

1. Export the database from Notion to Excel and save as `data/notion_export.xlsx`.
2. Clean and export:
   ```bash
   python clean_notion_export.py
   python scripts/export_data.py
   ```
3. Serve the site:
   ```bash
   python -m http.server 8080 -d docs
   ```
4. Open **http://localhost:8080** in your browser.

## Update the live site (sync and push to GitHub)

To refresh the dashboard data from Notion and push it to GitHub (so the hosted page updates):

- **Windows:** Double-click `sync_and_push.bat`, or run it from a terminal. It runs the Notion sync, then commits and pushes `docs/data.json` if it changed.
- Ensure Git is configured (remote, branch, credentials). If nothing changed, the script will report "Nothing to commit."
