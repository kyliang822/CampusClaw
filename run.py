"""Run the local app and populate bundled demo content via its protected API."""
import os
from pathlib import Path
import subprocess
import sys
import time
import urllib.error
import urllib.request
ROOT=Path(__file__).resolve().parent
project_python=ROOT/'.venv'/('Scripts/python.exe' if os.name=='nt' else 'bin/python')
if project_python.exists() and Path(sys.prefix).resolve()!=(ROOT/'.venv').resolve():
    os.execv(str(project_python),[str(project_python),str(Path(__file__).resolve())])
host=os.environ.get('CAMPUS_HOST','127.0.0.1')
port=os.environ.get('CAMPUS_PORT','8765')
base='http://127.0.0.1:'+port
process=subprocess.Popen([sys.executable,str(ROOT/'server.py'),'--host',host,'--port',port],cwd=ROOT)
try:
    ready=False
    for _ in range(40):
        if process.poll() is not None:raise RuntimeError('服务启动失败，请检查端口 8765 是否被占用。')
        try:
            urllib.request.urlopen(base+'/api/me',timeout=.5)
            ready=True
        except urllib.error.HTTPError as e:ready=e.code==401
        except (urllib.error.URLError,TimeoutError):pass
        if ready:break
        time.sleep(.15)
    if not ready:raise RuntimeError('本地服务未就绪。')
    subprocess.run([sys.executable,str(ROOT/'seed_demo.py'),'--url',base],cwd=ROOT,check=True)
    print(f'\n打开 {base}\n教师账号：teacher\n按 Ctrl+C 关闭系统。\n',flush=True)
    process.wait()
except KeyboardInterrupt:
    pass
finally:
    process.terminate()
    try:process.wait(timeout=5)
    except subprocess.TimeoutExpired:process.kill()
