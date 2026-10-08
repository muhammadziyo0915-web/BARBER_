@echo off
cd /d %~dp0
if not exist .venv\Scripts\python.exe (
  echo [X] .venv topilmadi. Avval Python virtual muhitini yarating.
  pause
  exit /b 1
)
call .venv\Scripts\activate
py manage.py migrate
py manage.py backup_db
start "BARBER AURA SERVER" cmd /k "call .venv\Scripts\activate && py manage.py runserver"
start "BARBER AURA TELEGRAM BOT" cmd /k "call .venv\Scripts\activate && py bot.py"
