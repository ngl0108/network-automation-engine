@echo off
echo Restarting NetManager Server...
cd /d "%~dp0"
docker-compose down
echo.
docker-compose up -d
echo.
echo Server Restarted!
echo Frontend: http://localhost
echo API Docs: http://localhost:8000/docs
echo.
pause
