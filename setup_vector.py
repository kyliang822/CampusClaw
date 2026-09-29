"""Install vector dependencies into this project only; Python 3.10+ required."""
from pathlib import Path
import os, subprocess, sys
ROOT=Path(__file__).resolve().parent
if sys.version_info < (3,10):
    bundled=Path.home()/'.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3'
    if bundled.exists():os.execv(str(bundled),[str(bundled),str(Path(__file__).resolve())])
    raise SystemExit('语义检索需要 Python 3.10+。请安装后运行 python3 setup_vector.py。')
subprocess.run([sys.executable,'-m','venv',str(ROOT/'.venv')],check=True)
python=ROOT/'.venv'/('Scripts/python.exe' if os.name=='nt' else 'bin/python')
subprocess.run([str(python),'-m','pip','install','-r',str(ROOT/'requirements-vector.txt')],check=True)
print('向量依赖已安装到项目 .venv。现在可运行 python3 run.py 或双击启动系统.command。')
