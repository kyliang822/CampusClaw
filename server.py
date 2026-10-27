"""CampusClaw local teaching edition. Python 3.9+, no third-party dependencies."""
import argparse
import hashlib
import hmac
import json
import os
import secrets
import signal
import sqlite3
import time
import retrieval
import qa
import platform_runtime
from datetime import datetime
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, urlsplit

ROOT = Path(__file__).resolve().parent
DATA = Path(os.environ.get('CAMPUS_DATA_DIR', str(ROOT / 'data')))
DB = DATA / 'campus.db'
MAX_FILE = 2 * 1024 * 1024
TTL = 8 * 3600
VECTOR_INDEX = None


def connect():
    c = sqlite3.connect(DB, timeout=10)
    c.row_factory = sqlite3.Row
    c.execute('PRAGMA foreign_keys=ON')
    return c


def password_hash(password, salt):
    return hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(salt), 260000).hex()


def init_db():
    DATA.mkdir(parents=True, exist_ok=True)
    with connect() as c:
        c.executescript('''
        CREATE TABLE IF NOT EXISTS classes(id INTEGER PRIMARY KEY, name TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, username TEXT UNIQUE NOT NULL,
          display_name TEXT NOT NULL, role TEXT NOT NULL CHECK(role IN ('teacher','student')),
          class_id INTEGER NOT NULL REFERENCES classes(id), salt TEXT NOT NULL, password_hash TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS sessions(token_hash TEXT PRIMARY KEY, user_id INTEGER REFERENCES users(id),
          csrf TEXT NOT NULL, expires REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS materials(id TEXT PRIMARY KEY, class_id INTEGER REFERENCES classes(id),
          title TEXT NOT NULL, filename TEXT NOT NULL, size INTEGER NOT NULL, content BLOB NOT NULL,
          created_by INTEGER REFERENCES users(id), created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS knowledge_entries(id INTEGER PRIMARY KEY, material_id TEXT UNIQUE NOT NULL
          REFERENCES materials(id) ON DELETE CASCADE, class_id INTEGER NOT NULL REFERENCES classes(id), body TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS materials_class ON materials(class_id);
        CREATE INDEX IF NOT EXISTS knowledge_class ON knowledge_entries(class_id);
        CREATE TABLE IF NOT EXISTS login_attempts(key TEXT PRIMARY KEY, count INTEGER NOT NULL, reset_at REAL NOT NULL);
        ''')
        c.executemany('INSERT OR IGNORE INTO classes VALUES(?,?)', [(1,'A班'),(2,'B班')])
        for name, display, role, class_id in [('teacher','梁老师','teacher',1),('student','李同学','student',1),('teacher2','王老师','teacher',2),('student2','陈同学','student',2)]:
            if not c.execute('SELECT 1 FROM users WHERE username=?',(name,)).fetchone():
                salt = secrets.token_hex(16)
                pwd = os.environ.get('CAMPUS_DEMO_PASSWORD','Campus2026!')
                c.execute('INSERT INTO users(username,display_name,role,class_id,salt,password_hash) VALUES(?,?,?,?,?,?)',
                    (name,display,role,class_id,salt,password_hash(pwd,salt)))

    retrieval.migrate(connect)
    qa.migrate(connect)
    platform_runtime.migrate(connect)


class Handler(BaseHTTPRequestHandler):
    server_version = 'CampusClaw/1.0'

    def log_message(self, fmt, *args):
        # Do not log request bodies, credentials or session cookies.
        super().log_message(fmt, *args)

    def reply(self, status, data, headers=None):
        raw = json.dumps(data, ensure_ascii=False).encode()
        self.raw(status, raw, 'application/json; charset=utf-8', headers)

    def raw(self, status, body, kind, headers=None):
        self.send_response(status)
        self.send_header('Content-Type', kind)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Referrer-Policy','same-origin')
        self.send_header('Cache-Control','no-store')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
        for k,v in (headers or {}).items(): self.send_header(k,v)
        self.end_headers()
        self.wfile.write(body)

    def cookie(self, value, max_age=TTL):
        secure = '; Secure' if os.environ.get('CAMPUS_SECURE_COOKIE') == '1' else ''
        return f'campus_session={value}; HttpOnly; SameSite=Strict; Path=/; Max-Age={max_age}{secure}'

    def session(self):
        try:
            scheme,token=self.headers.get('Authorization','').split(' ',1)
            if scheme.lower()!='bearer' or not token or ' ' in token: return None
        except Exception:
            return None
        digest=hashlib.sha256(token.encode()).hexdigest()
        with connect() as c:
            row=c.execute('''SELECT u.id,u.username,u.display_name,u.role,u.class_id,c.name class_name,
                 s.csrf,s.token_hash FROM sessions s JOIN users u ON s.user_id=u.id
                 JOIN classes c ON c.id=u.class_id WHERE s.token_hash=? AND s.expires>?''',(digest,time.time())).fetchone()
        return dict(row) if row else None

    def require_user(self, write=False):
        user=self.session()
        if not user:
            self.reply(401, {'error':'请先登录后再访问。'}, {'WWW-Authenticate':'Bearer'})
            return None
        if write and not hmac.compare_digest(self.headers.get('X-CSRF-Token',''),user['csrf']):
            self.reply(403, {'error':'请求校验失败，请刷新页面后重试。'})
            return None
        return user

    def read_json(self, maximum=3*1024*1024):
        try: length=int(self.headers.get('Content-Length','0'))
        except ValueError:
            self.reply(400,{'error':'无效请求。'}); return None
        if length > maximum or length < 0:
            self.close_connection=True
            self.reply(413,{'error':'文件大小不能超过 2 MB。'}); return None
        try:
            data=json.loads(self.rfile.read(length))
            if not isinstance(data,dict): raise ValueError()
            return data
        except (ValueError, UnicodeDecodeError):
            self.reply(400,{'error':'请求格式错误。'}); return None

    def do_GET(self):
        url=urlsplit(self.path)
        path=url.path
        if path in ('/','/login','/materials','/knowledge','/chat'):
            return self.raw(200,(ROOT/'web/index.html').read_bytes(),'text/html; charset=utf-8')
        assets={'/platform-ui.js':'text/javascript; charset=utf-8','/chat-ui.js':'text/javascript; charset=utf-8','/retrieval-ui.js':'text/javascript; charset=utf-8','/app.css':'text/css; charset=utf-8','/app.js':'text/javascript; charset=utf-8','/marked.js':'text/javascript; charset=utf-8','/favicon.svg':'image/svg+xml'}
        if path in assets:
            return self.raw(200,(ROOT/'web'/path[1:]).read_bytes(),assets[path])
        if not path.startswith('/api/'):
            return self.reply(404,{'error':'页面不存在。'})
        user=self.require_user()
        if not user: return
        if path=='/api/platform' or path.startswith('/api/traces/'):
            return platform_runtime.get(self,connect,user,path)
        if path=='/api/ai/settings' or path=='/api/conversations' or path.startswith('/api/conversations/'):
            return qa.get(self,connect,user,path,parse_qs(url.query),VECTOR_INDEX)
        if path=='/api/me':
            return self.reply(200,{k:v for k,v in user.items() if k!='token_hash'})
        if path=='/api/retrieval/status':
            return self.reply(200,VECTOR_INDEX.status(user['class_id']))
        if path=='/api/search':
            params=parse_qs(url.query)
            try:
                limit=int(params.get('limit',['5'])[0])
                result=retrieval.retrieve(connect,VECTOR_INDEX,user['class_id'],params.get('q',[''])[0],params.get('mode',['hybrid'])[0],limit)
            except ValueError:
                return self.reply(400,{'error':'结果条数须为 1–20。'})
            except retrieval.RetrievalError as e:
                return self.reply(e.status,{'error':str(e)})
            return self.reply(200,result)
        if path.startswith('/api/chunks/'):
            chunk_id=path.removeprefix('/api/chunks/')
            with connect() as c:
                row=c.execute('''SELECT ch.*,m.title,m.filename,k.body original_body
                    FROM knowledge_chunks ch JOIN materials m ON m.id=ch.material_id AND m.class_id=ch.class_id
                    JOIN knowledge_entries k ON k.material_id=m.id AND k.class_id=m.class_id
                    WHERE ch.id=? AND ch.class_id=?''',(chunk_id,user['class_id'])).fetchone()
            if not row:return self.reply(404,{'error':'材料不存在。'})
            return self.reply(200,{k:row[k] for k in ['id','material_id','title','filename','chunk_index','start_char','end_char','body','body_hash','original_body']})
        if path=='/api/materials':
            q=parse_qs(url.query).get('q',[''])[0].strip()[:100]
            with connect() as c:
                rows=c.execute('''SELECT m.id,m.title,m.filename,m.size,m.created_at,u.display_name author,
                    length(k.body) characters FROM materials m JOIN users u ON u.id=m.created_by
                    JOIN knowledge_entries k ON k.material_id=m.id AND k.class_id=m.class_id
                    WHERE m.class_id=? AND (instr(m.title,?)>0 OR instr(m.filename,?)>0)
                    ORDER BY m.created_at DESC,m.rowid DESC''',(user['class_id'],q,q)).fetchall()
                stats=c.execute('SELECT count(*) total,coalesce(sum(size),0) bytes FROM materials WHERE class_id=?',(user['class_id'],)).fetchone()
                entries=c.execute('SELECT count(*) n FROM knowledge_entries WHERE class_id=?',(user['class_id'],)).fetchone()['n']
            return self.reply(200,{'materials':[dict(r) for r in rows],'stats':{**dict(stats),'entries':entries}})
        parts=path.strip('/').split('/')
        if len(parts) in (3,4) and parts[:2]==['api','materials'] and (len(parts)==3 or parts[3]=='download'):
            with connect() as c:
                m=c.execute('''SELECT m.*,k.body,u.display_name author FROM materials m
                    JOIN knowledge_entries k ON k.material_id=m.id AND k.class_id=m.class_id
                    JOIN users u ON u.id=m.created_by WHERE m.id=? AND m.class_id=?''',(parts[2],user['class_id'])).fetchone()
            if not m: return self.reply(404,{'error':'材料不存在。'})
            if len(parts)==4:
                return self.raw(200,m['content'],'application/octet-stream',{'Content-Disposition':"attachment; filename*=UTF-8''"+quote(m['filename'])})
            result=dict(m); result.pop('content')
            return self.reply(200,result)
        self.reply(404,{'error':'接口不存在。'})

    def do_POST(self):
        path=urlsplit(self.path).path
        origin=self.headers.get('Origin')
        if origin and urlsplit(origin).netloc!=self.headers.get('Host'):
            return self.reply(403,{'error':'请求来源不受信任。'})
        if path=='/api/login':
            data=self.read_json(8192)
            if data is None: return
            username=data.get('username',''); password=data.get('password','')
            if not isinstance(username,str) or not isinstance(password,str):
                return self.reply(401,{'error':'账号或密码错误。'})
            key=self.client_address[0]
            with connect() as c:
                now=time.time()
                c.execute('DELETE FROM login_attempts WHERE reset_at<?',(now,))
                attempt=c.execute('SELECT count FROM login_attempts WHERE key=?',(key,)).fetchone()
                if attempt and attempt['count']>=10:
                    return self.reply(429,{'error':'尝试次数过多，请 5 分钟后重试。'})
                user=c.execute('SELECT * FROM users WHERE username=?',(username,)).fetchone()
                hashed=password_hash(password,user['salt'] if user else '00'*16)
                if not user or not hmac.compare_digest(hashed,user['password_hash']):
                    c.execute('INSERT INTO login_attempts VALUES(?,1,?) ON CONFLICT(key) DO UPDATE SET count=count+1',(key,now+300))
                    return self.reply(401,{'error':'账号或密码错误。'})
                c.execute('DELETE FROM login_attempts WHERE key=?',(key,))
                c.execute('DELETE FROM sessions WHERE expires<?',(now,))
                previous=self.session()
                if previous: c.execute('DELETE FROM sessions WHERE token_hash=?',(previous['token_hash'],))
                token=secrets.token_urlsafe(32); csrf=secrets.token_urlsafe(32)
                c.execute('INSERT INTO sessions VALUES(?,?,?,?)',(hashlib.sha256(token.encode()).hexdigest(),user['id'],csrf,now+TTL))
            return self.reply(200,{'ok':True,'access_token':token,'token_type':'Bearer','expires_in':TTL},{'Set-Cookie':self.cookie('',0)})
        user=self.require_user(write=True)
        if not user: return
        if path in ('/api/platform/skills','/api/platform/templates','/api/platform/apps'):
            data=self.read_json(100000)
            if data is not None:return platform_runtime.save_asset(self,connect,user,path,data)
            return
        if path in ('/api/ai/settings','/api/chat'):
            return qa.post(self,connect,user,path,VECTOR_INDEX)
        if path=='/api/retrieval/retry':
            if user['role']!='teacher':return self.reply(403,{'error':'只有教师可以重试索引。'})
            VECTOR_INDEX.retry()
            return self.reply(202,{'message':'已安排索引重试。'})
        if path=='/api/logout':
            with connect() as c: c.execute('DELETE FROM sessions WHERE token_hash=?',(user['token_hash'],))
            return self.reply(200,{'ok':True},{'Set-Cookie':self.cookie('',0)})
        if path=='/api/materials':
            if user['role']!='teacher':
                return self.reply(403,{'error':'只有教师可以上传材料。'})
            data=self.read_json()
            if data is None: return
            filename=data.get('filename',''); encoded=data.get('content',''); title=data.get('title','')
            if not all(isinstance(v,str) for v in [filename,encoded,title]) or not filename or len(filename)>180 or any(ch in filename for ch in '/\\\r\n\x00'):
                return self.reply(400,{'error':'文件名不合法。'})
            if Path(filename).suffix.lower() not in ('.txt','.md'):
                return self.reply(415,{'error':'仅支持 .txt 和 .md 文件。'})
            import base64
            try: content=base64.b64decode(encoded,validate=True)
            except ValueError: return self.reply(422,{'error':'文件内容编码无效。'})
            if len(content)>MAX_FILE: return self.reply(413,{'error':'文件大小不能超过 2 MB。'})
            try:
                body=content.decode('utf-8-sig')
                if not body.strip() or any(ord(ch)<32 and ch not in '\t\r\n' for ch in body): raise ValueError()
            except (UnicodeDecodeError,ValueError):
                return self.reply(422,{'error':'请上传非空的 UTF-8 文本文件。'})
            title=title.strip() or Path(filename).stem
            if len(title)>120: return self.reply(400,{'error':'材料标题不能超过 120 个字符。'})
            strategy=data.get('chunk_strategy','window');separator=data.get('chunk_separator','')
            if not isinstance(strategy,str) or not isinstance(separator,str):
                return self.reply(400,{'error':'切分参数不合法。'})
            try:retrieval.split_chunks(body,strategy,separator)
            except ValueError as e:return self.reply(400,{'error':str(e)})
            material_id=secrets.token_hex(12)
            try:
                with connect() as c:
                    c.execute('INSERT INTO materials VALUES(?,?,?,?,?,?,?,?)',(material_id,user['class_id'],title,filename,len(content),content,user['id'],datetime.now().astimezone().isoformat(timespec='seconds')))
                    c.execute('INSERT INTO knowledge_entries(material_id,class_id,body) VALUES(?,?,?)',(material_id,user['class_id'],body))
                    chunk_count=retrieval.add_chunks(c,material_id,user['class_id'],body,strategy,separator)
            except sqlite3.Error:
                return self.reply(500,{'error':'入库失败，请重试。'})
            if VECTOR_INDEX:VECTOR_INDEX.retry()
            return self.reply(201,{'id':material_id,'chunk_count':chunk_count,'vector_state':'pending','message':'上传成功，正文已切片入库。'})
        self.reply(404,{'error':'接口不存在。'})


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--host',default='127.0.0.1')
    parser.add_argument('--port',type=int,default=8765)
    args=parser.parse_args()
    def stop_server(signum,frame):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM,stop_server)
    init_db()
    VECTOR_INDEX=retrieval.VectorIndex(connect,DATA)
    VECTOR_INDEX.start()
    server=ThreadingHTTPServer((args.host,args.port),Handler)
    print(f'CampusClaw: http://{args.host}:{args.port}',flush=True)
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally:
        server.server_close()
        VECTOR_INDEX.close()
