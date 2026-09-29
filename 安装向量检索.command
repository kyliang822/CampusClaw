#!/bin/sh
cd "$(dirname "$0")" || exit 1
python3 setup_vector.py
printf '\n按回车关闭窗口。'
read answer
