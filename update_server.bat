@echo off
echo Updating NetManager Server (Rebuilding Images)...
cd /d "%~dp0"
docker-compose down
echo.
echo Rebuilding... (This may take a few minutes)
docker-compose up -d --build
echo.
echo Server Updated and Restarted!
echo Frontend: http://localhost
echo API Docs: http://localhost:8000/docs
echo.
pause
