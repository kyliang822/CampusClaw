#!/bin/sh
cd "$(dirname "$0")" || exit 1
if command -v python3 >/dev/null 2>&1; then
  python3 run.py
else
  echo '需要安装 Python 3.9 或更新版本。'
fi
printf '\n按回车关闭窗口。'
read answer
