#!/bin/zsh
cd -- "${0:A:h}"
python3 scripts/manage.py
print '\n服务已停止。按回车关闭窗口。'
read
