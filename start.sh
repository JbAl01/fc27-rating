#!/bin/sh
# Rater alle spillerfiler i data/ og åpner rapporten (Mac/Linux)
cd "$(dirname "$0")"
if [ -f data/ea_players.json ]; then FILES="data/ea_players.json"; else FILES="data/eksempel_spillere.json"; fi
[ -f data/spesialkort.json ] && FILES="$FILES data/spesialkort.json"
[ -f data/mine_spillere.json ] && FILES="$FILES data/mine_spillere.json"
python3 -m fcrating rate $FILES
(open output/rapport.html 2>/dev/null || xdg-open output/rapport.html 2>/dev/null) &
