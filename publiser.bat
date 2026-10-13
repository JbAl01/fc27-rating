@echo off
rem Reserve hvis GitHub ikke får hentet kortene: henter, rater og laster opp siden fra denne PC-en.
rem Trenger Node.js (nodejs.org) og at du har kjort "npx wrangler login" en gang.
rem Kjor automatisk med Oppgaveplanlegging: publiser.bat auto
cd /d "%~dp0"
py -m fcrating watch --once --publiser --deploy
if /i not "%~1"=="auto" pause
