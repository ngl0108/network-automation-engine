@echo off
echo Stopping NetManager Server...
cd /d "%~dp0"
docker-compose down
echo.
echo Server Stopped.
pause
