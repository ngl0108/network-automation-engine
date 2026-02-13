@echo off
echo Starting NetManager Server...
cd /d "%~dp0"
docker-compose up -d
echo.
echo Server Started!
echo Frontend: http://localhost
echo API Docs: http://localhost:8000/docs
echo.
pause
