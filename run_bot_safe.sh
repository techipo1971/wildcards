#!/bin/bash

LOCKFILE="/tmp/postbot.lock"
LOGFILE="/var/log/postbot.log"
SCRIPT="/home/tetsuya/scripts/tweet_bot.py"   # ←あなたのbot.pyに書き換え

# すでに実行中なら終了（重複実行を防止）
if [ -e "$LOCKFILE" ]; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Already running" >> $LOGFILE
    exit 1
fi

# ロック作成
touch "$LOCKFILE"

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Start" >> $LOGFILE

# Python スクリプト実行
/home/tetsuya/scripts/venv/bin/python "$SCRIPT" >> $LOGFILE 2>&1

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Finish" >> $LOGFILE

# ロック解除
rm -f "$LOCKFILE"
