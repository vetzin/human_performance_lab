@echo off
cd /d "%~dp0"

echo Syncing from Notion...
python scripts/sync_notion.py
if errorlevel 1 (
    echo Sync failed. Check NOTION_API_KEY and NOTION_DATABASE_ID in .env
    pause
    exit /b 1
)

echo.
echo Staging docs/data.json...
git add docs/data.json

git diff --staged --quiet docs/data.json
if errorlevel 1 (
    echo Committing and pushing...
    git commit -m "Update data from Notion"
    git push
    if errorlevel 1 (
        echo Push failed. Check your Git remote and credentials.
        pause
        exit /b 1
    )
    echo Done. Dashboard data pushed to GitHub.
) else (
    echo No changes to docs/data.json. Nothing to commit.
)

echo.
pause
