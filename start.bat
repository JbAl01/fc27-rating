@echo off
rem Rater alle spillerfiler i data\ og åpner rapporten (Windows)
cd /d "%~dp0"
set FILES=
if exist data\ea_players.json (set FILES=data\ea_players.json) else (set FILES=data\eksempel_spillere.json)
if exist data\spesialkort.json set FILES=%FILES% data\spesialkort.json
if exist data\mine_spillere.json set FILES=%FILES% data\mine_spillere.json
py -m fcrating rate %FILES%
start "" output\rapport.html
pause
