import hashlib
import os
import sys
import tempfile
import threading
import unittest
import uuid
from pathlib import Path
from unittest.mock import Mock,patch
from urllib.parse import urlencode
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import server
import retrieval
from test_acceptance import Client

class ChunkTests(unittest.TestCase):
    def test_unicode_exact_offsets_and_overlap(self):
        body='一二三🙂ABC\n'*320
        chunks=retrieval.split_chunks(body)
        self.assertGreater(len(chunks),2)
        for i,ch in enumerate(chunks):
            self.assertEqual(ch['body'],body[ch['start_char']:ch['end_char']])
            self.assertLessEqual(len(ch['body']),800)
            if i:self.assertEqual(chunks[i-1]['end_char']-ch['start_char'],100)
        self.assertEqual(chunks[-1]['end_char'],len(body))
    def test_all_split_strategies_keep_exact_text(self):
        body='# 第一章\n'+('甲乙。\n\n'*220)+'\n# 第二章\n丁戊---己庚'
        for strategy in ['line','paragraph','sentence','markdown','custom']:
            chunks=retrieval.split_chunks(body,strategy,'---')
            self.assertEqual(''.join(c['body'] for c in chunks),body)
            self.assertTrue(all(c['body']==body[c['start_char']:c['end_char']] for c in chunks))
    def test_rrf_promotes_dual_hit(self):
        ranked=retrieval.fuse([('one',9),('shared',8)],[('two',.9),('shared',.8)],3)
        self.assertEqual(ranked[0][0],'shared')

class RetrievalHTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory();server.DATA=Path(cls.temp.name);server.DB=server.DATA/'db.sqlite'
        server.init_db()
        with patch.dict(os.environ,{'CAMPUS_VECTOR_MODE':'off'}):server.VECTOR_INDEX=retrieval.VectorIndex(server.connect,server.DATA)
        cls.http=server.ThreadingHTTPServer(('127.0.0.1',0),server.Handler)
        threading.Thread(target=cls.http.serve_forever,daemon=True).start()
        cls.base=f'http://127.0.0.1:{cls.http.server_port}'
    @classmethod
    def tearDownClass(cls):
        cls.http.shutdown();cls.http.server_close();cls.temp.cleanup()
    def setUp(self):
        with server.connect() as c:c.execute('DELETE FROM materials')
        self.teacher=Client(self.base);self.teacher.login('teacher')
        self.student=Client(self.base);self.student.login('student')
        self.other=Client(self.base);self.other.login('teacher2')
        self.body='课堂表达指导\n鼓励学生说明自己的观点，并使用原文细节作为依据。\n小组交流可以帮助学生认真倾听。'
        self.mid=self.teacher.upload('课堂表达.md',self.body.encode())[1]['id']
        self.other.upload('班级保密资料.md','课堂表达：B班密钥ZEBRA890。禁止泄露。'.encode())
    def search(self,client=None,q='课堂表达',mode='keyword',**extra):
        return (client or self.teacher).request('/api/search?'+urlencode({'q':q,'mode':mode,**extra}))
    def test_teacher_and_student_scoped_and_traceable(self):
        for client in [self.teacher,self.student]:
            status,data=self.search(client,class_id=2)
            self.assertEqual(status,200);self.assertEqual(len(data['hits']),1)
            hit=data['hits'][0];self.assertEqual(hit['material_id'],self.mid)
            self.assertNotIn('ZEBRA890',str(data))
            status,source=client.request(hit['source_url']);self.assertEqual(status,200)
            self.assertEqual(hit['excerpt'],source['original_body'][hit['start_char']:hit['end_char']])
            self.assertEqual(hit['body_hash'],hashlib.sha256(hit['excerpt'].encode()).hexdigest())
            self.assertEqual(self.other.request(hit['source_url'])[0],404)
    def test_unauthenticated_and_validation(self):
        self.assertEqual(self.search(Client(self.base))[0],401)
        for args in [{'q':''},{'q':'x'*501},{'mode':'invalid'},{'limit':'abc'},{'limit':100}]:
            self.assertEqual(self.search(**args)[0],400)
    def test_keyword_never_calls_embedding(self):
        with patch.object(server.VECTOR_INDEX,'search',side_effect=AssertionError('Embedding called')):
            self.assertEqual(self.search()[0],200)
    def test_empty_has_no_fabricated_hits(self):
        status,data=self.search(q='量子纠缠与黑洞蒸发')
        self.assertEqual(status,200);self.assertEqual(data['hits'],[])
        self.assertEqual(data['message'],'资料中未找到相关内容')
    def test_vector_failure_not_silent_keyword_fallback(self):
        for mode in ['vector','hybrid']:self.assertEqual(self.search(mode=mode)[0],503)
    def test_final_sql_check_rejects_injected_foreign_vector(self):
        with server.connect() as c:cid=c.execute('SELECT id FROM knowledge_chunks WHERE class_id=2').fetchone()['id']
        with patch.object(server.VECTOR_INDEX,'search',return_value=[(cid,.99)]):
            status,data=self.search(q='B班密钥',mode='hybrid')
            self.assertEqual(status,200);self.assertEqual(data['hits'],[])
    def test_migration_idempotent_and_fts_cleanup(self):
        retrieval.migrate(server.connect);retrieval.migrate(server.connect)
        with server.connect() as c:
            self.assertEqual(c.execute('SELECT count(*) FROM knowledge_chunks').fetchone()[0],2)
            c.execute('DELETE FROM materials WHERE id=?',(self.mid,))
        self.assertEqual(self.search()[1]['hits'],[])
    def test_chunks_transaction_rolls_back(self):
        with server.connect() as c:
            before=c.execute('SELECT count(*) FROM materials').fetchone()[0]
            c.execute("CREATE TRIGGER fail_chunk BEFORE INSERT ON knowledge_chunks BEGIN SELECT RAISE(ABORT,'failure'); END")
        try:
            self.assertEqual(self.teacher.upload()[0],500)
            with server.connect() as c:self.assertEqual(c.execute('SELECT count(*) FROM materials').fetchone()[0],before)
        finally:
            with server.connect() as c:c.execute('DROP TRIGGER fail_chunk')
    def test_long_material_source_exact(self):
        body='海洋探究资料🙂\n'*170+'珊瑚礁需要保护。'
        mid=self.teacher.upload('海洋.md',body.encode(),chunk_strategy='window')[1]['id']
        status,data=self.search(q='珊瑚礁')
        self.assertEqual(status,200);self.assertTrue(data['hits'])
        h=data['hits'][0];self.assertEqual(h['material_id'],mid);self.assertGreater(h['start_char'],0)
        self.assertEqual(h['excerpt'],body[h['start_char']:h['end_char']])
    def test_retry_teacher_only(self):
        self.assertEqual(self.student.request('/api/retrieval/retry',{})[0],403)
        self.assertEqual(self.teacher.request('/api/retrieval/retry',{})[0],202)

class QdrantBoundaryTests(unittest.TestCase):
    def test_qdrant_filter_threshold_and_sql_recheck(self):
        try:from qdrant_client import QdrantClient,models
        except ImportError:self.skipTest('Install vector dependencies to test Qdrant')
        import sqlite3
        with tempfile.TemporaryDirectory() as directory:
            db=Path(directory)/'q.sqlite'
            def connect():
                c=sqlite3.connect(db);c.row_factory=sqlite3.Row;return c
            with connect() as c:
                c.executescript('CREATE TABLE materials(id TEXT PRIMARY KEY,class_id INTEGER); CREATE TABLE knowledge_chunks(id TEXT,material_id TEXT,class_id INTEGER,body_hash TEXT,vector_state TEXT,indexed_collection TEXT);')
                ids=[str(uuid.uuid4()) for _ in range(4)]
                for i,cid in enumerate(ids):
                    cls=2 if i==1 else 1
                    c.execute('INSERT INTO materials VALUES(?,?)',(cid,cls))
                    c.execute('INSERT INTO knowledge_chunks VALUES(?,?,?,?,?,?)',(cid,cid,cls,'correct','ready','test'))
            with patch.dict(os.environ,{'CAMPUS_VECTOR_MODE':'local'}):index=retrieval.VectorIndex(connect,directory)
            index.collection='test';index.ready=True;index.embed=lambda _: [[1.,0.]]
            index.client=QdrantClient(':memory:')
            index.client.create_collection('test',vectors_config=models.VectorParams(size=2,distance=models.Distance.COSINE))
            index.client.upsert('test',points=[
                models.PointStruct(id=ids[0],vector=[1.,0.],payload={'class_id':1,'body_hash':'correct'}),
                models.PointStruct(id=ids[1],vector=[1.,0.],payload={'class_id':2,'body_hash':'correct'}),
                models.PointStruct(id=ids[2],vector=[0.,1.],payload={'class_id':1,'body_hash':'correct'}),
                models.PointStruct(id=ids[3],vector=[1.,0.],payload={'class_id':1,'body_hash':'stale'})])
            hits=index.search(1,'test');self.assertEqual([h[0] for h in hits],[ids[0]])
            # Even a corrupted Qdrant class label cannot bypass SQL authorization.
            index.client.set_payload('test',payload={'class_id':1},points=[ids[1]])
            self.assertEqual([h[0] for h in index.search(1,'test')],[ids[0]])
            index.close()
