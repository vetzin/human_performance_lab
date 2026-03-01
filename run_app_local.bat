@echo off
cd /d "%~dp0"

echo Syncing from Notion...
python scripts/sync_notion.py
if errorlevel 1 (
    echo Sync failed. Set NOTION_API_KEY and NOTION_DATABASE_ID in the environment or in .env.
    echo See README for the manual Excel export flow if you don't use the Notion API.
    pause
    exit /b 1
)

echo.
echo Starting server at http://localhost:8080
echo Press Ctrl+C to stop.
echo.
start http://localhost:8080
python -m http.server 8080 -d docs
