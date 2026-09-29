"""Run isolated HTTP acceptance tests: python3 -m unittest discover -s tests -v"""
import base64
import http.cookiejar
import json
import os
import sqlite3
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import server

class Client:
    def __init__(self,base):
        self.base=base; self.csrf=''
        self.jar=http.cookiejar.CookieJar()
        self.opener=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar))
    def request(self,path,data=None,csrf=True):
        headers={'Content-Type':'application/json'}
        if csrf:headers['X-CSRF-Token']=self.csrf
        req=urllib.request.Request(self.base+path, None if data is None else json.dumps(data).encode(),headers)
        try: response=self.opener.open(req)
        except urllib.error.HTTPError as e: response=e
        body=response.read()
        if response.headers.get('Content-Type','').startswith('application/json'): body=json.loads(body)
        return response.status,body
    def login(self,name):
        status,_=self.request('/api/login',{'username':name,'password':'Campus2026!'})
        assert status==200
        status,me=self.request('/api/me');self.csrf=me['csrf'];return me
    def upload(self,name='课程.md',body=b'# Teaching notes',**extra):
        return self.request('/api/materials',{'filename':name,'content':base64.b64encode(body).decode(),**extra})

class Acceptance(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory()
        server.DATA=Path(cls.temp.name);server.DB=server.DATA/'test.db';server.init_db()
        cls.http=server.ThreadingHTTPServer(('127.0.0.1',0),server.Handler)
        cls.thread=threading.Thread(target=cls.http.serve_forever,daemon=True);cls.thread.start()
        cls.base=f'http://127.0.0.1:{cls.http.server_port}'
    @classmethod
    def tearDownClass(cls):
        cls.http.shutdown();cls.http.server_close();cls.temp.cleanup()
    def setUp(self):
        with server.connect() as c:
            c.execute('DELETE FROM knowledge_entries');c.execute('DELETE FROM materials')
        self.teacher=Client(self.base);self.teacher.login('teacher')
    def test_01_unauthenticated_no_data(self):
        c=Client(self.base)
        for path in ['/api/me','/api/materials','/api/materials/notfound','/api/materials/notfound/download']:
            status,body=c.request(path);self.assertEqual(status,401);self.assertEqual(set(body),{'error'})
    def test_02_password_failure_uniform(self):
        c=Client(self.base)
        a=c.request('/api/login',{'username':'teacher','password':'wrong'})
        b=c.request('/api/login',{'username':'unknown','password':'wrong'})
        self.assertEqual(a,b);self.assertEqual(a[0],401)
    def test_03_upload_persistence_and_same_class_student(self):
        content='# 教学目标\n\n- 理解概念\n- 完成练习\n'.encode()
        status,m=self.teacher.upload(body=content);self.assertEqual(status,201)
        student=Client(self.base);student.login('student')
        _,listing=student.request('/api/materials');self.assertEqual(len(listing['materials']),1)
        _,detail=student.request('/api/materials/'+m['id']);self.assertEqual(detail['body'],content.decode())
        _,download=student.request('/api/materials/'+m['id']+'/download');self.assertEqual(download,content)
        with server.connect() as c:
            self.assertEqual(c.execute('SELECT count(*) FROM knowledge_entries').fetchone()[0],1)
    def test_04_student_cannot_upload_or_spoof_role(self):
        student=Client(self.base);student.login('student')
        self.assertEqual(student.upload(role='teacher',class_id=1)[0],403)
    def test_05_cross_class_hidden_and_not_found(self):
        _,m=self.teacher.upload()
        other=Client(self.base);other.login('teacher2')
        _,listing=other.request('/api/materials?class_id=1');self.assertEqual(listing['materials'],[])
        for suffix in ['', '/download']:
            self.assertEqual(other.request('/api/materials/'+m['id']+suffix)[0],404)
        self.assertEqual(self.teacher.request('/uploads/'+m['id'])[0],404)
    def test_06_upload_validation_has_no_residue(self):
        self.assertEqual(self.teacher.upload('evil.exe')[0],415)
        self.assertEqual(self.teacher.upload(body=b'\xff\xfe')[0],422)
        self.assertEqual(self.teacher.upload(body=b'  ')[0],422)
        self.assertEqual(self.teacher.upload(body=b'a'*(2*1024*1024+1))[0],413)
        with server.connect() as c:
            self.assertEqual(c.execute('SELECT count(*) FROM materials').fetchone()[0],0)
            self.assertEqual(c.execute('SELECT count(*) FROM knowledge_entries').fetchone()[0],0)
    def test_07_csrf_and_logout(self):
        self.assertEqual(self.teacher.request('/api/materials',{},csrf=False)[0],403)
        self.assertEqual(self.teacher.request('/api/logout',{})[0],200)
        self.assertEqual(self.teacher.request('/api/me')[0],401)
    def test_08_class_from_session_only(self):
        _,m=self.teacher.upload(class_id=2)
        status,body=self.teacher.request('/api/materials/'+m['id']);self.assertEqual(status,200);self.assertEqual(body['class_id'],1)
    def test_09_database_failure_rolls_back_both_tables(self):
        with server.connect() as c:
            c.execute("CREATE TRIGGER fail_knowledge BEFORE INSERT ON knowledge_entries BEGIN SELECT RAISE(ABORT,'test'); END")
        try:
            self.assertEqual(self.teacher.upload()[0],500)
            with server.connect() as c:
                self.assertEqual(c.execute('SELECT count(*) FROM materials').fetchone()[0],0)
        finally:
            with server.connect() as c:c.execute('DROP TRIGGER fail_knowledge')
    def test_10_session_expiry(self):
        with server.connect() as c:c.execute('UPDATE sessions SET expires=0')
        self.assertEqual(self.teacher.request('/api/me')[0],401)

if __name__=='__main__': unittest.main()
