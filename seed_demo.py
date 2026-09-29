"""Upload bundled teaching samples through authenticated APIs; safe to rerun."""
import argparse, base64, http.cookiejar, json, os, urllib.request
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--url',default='http://127.0.0.1:8765');args=p.parse_args()
jar=http.cookiejar.CookieJar();opener=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar));csrf=''
def api(path,data=None):
    req=urllib.request.Request(args.url+path,None if data is None else json.dumps(data).encode(),{'Content-Type':'application/json','X-CSRF-Token':csrf})
    with opener.open(req) as r:return json.load(r)
api('/api/login',{'username':'teacher','password':os.environ.get('CAMPUS_DEMO_PASSWORD','Campus2026!')})
csrf=api('/api/me')['csrf']
existing={m['filename'] for m in api('/api/materials')['materials']}
for file in sorted((Path(__file__).parent/'sample-materials').iterdir()):
    if file.name in existing:continue
    api('/api/materials',{'filename':file.name,'title':file.stem.split('-',1)[1],'content':base64.b64encode(file.read_bytes()).decode()})
    print('Uploaded:',file.name)
api('/api/logout',{})
