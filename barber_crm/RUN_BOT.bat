@echo off
cd /d %~dp0
call .venv\Scripts\activate
py manage.py migrate
py bot.py
pause
