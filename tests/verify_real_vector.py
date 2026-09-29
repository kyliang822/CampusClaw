"""Explicit integration verification with real ONNX embeddings, isolated SQL and Qdrant.
Run: CAMPUS_MODEL_CACHE=/path/to/cache .venv/bin/python tests/verify_real_vector.py
"""
import json, os, sys, tempfile, threading, time
from pathlib import Path
from urllib.parse import urlencode
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from test_acceptance import Client
import server, retrieval
with tempfile.TemporaryDirectory() as temp:
    server.DATA=Path(temp);server.DB=server.DATA/'integration.db';server.init_db()
    server.VECTOR_INDEX=retrieval.VectorIndex(server.connect,server.DATA)
    assert server.VECTOR_INDEX.enabled,'Vector dependencies required'
    http=server.ThreadingHTTPServer(('127.0.0.1',0),server.Handler)
    threading.Thread(target=http.serve_forever,daemon=True).start()
    base=f'http://127.0.0.1:{http.server_port}'
    report={}
    try:
        teacher=Client(base);teacher.login('teacher')
        student=Client(base);student.login('student')
        other=Client(base);other.login('teacher2')
        text='课堂交流时，可以先安排同桌讨论，再邀请学生分享。教师给予积极回应，逐步帮助内向的同学增强发言的信心。'
        _,created=teacher.upload('表达指导.md',text.encode())
        other.upload('B班实验记录.md','B班独有记录：量子纠缠与黑洞蒸发，暗号ZEBRA890。'.encode())
        server.VECTOR_INDEX.start()
        for _ in range(180):
            states=[server.VECTOR_INDEX.status(i) for i in (1,2)]
            if all(s['ready'] and s['pending_chunks']==0 for s in states):break
            time.sleep(1)
        else:raise AssertionError('Real embedding indexing timeout')
        q='怎样鼓励害羞的孩子说出自己的想法？'
        for mode in ('keyword','vector','hybrid'):
            code,data=student.request('/api/search?'+urlencode({'q':q,'mode':mode,'class_id':2}))
            assert code==200,(code,data)
            if mode!='keyword':assert data['hits'],'Paraphrase must find evidence'
            assert all(h['material_id']==created['id'] for h in data['hits'])
            for h in data['hits']:
                code,source=student.request(h['source_url']);assert code==200
                assert h['excerpt']==source['original_body'][h['start_char']:h['end_char']]
                assert other.request(h['source_url'])[0]==404
            report[mode]={'hits':len(data['hits']),'scores':[h['vector_score'] for h in data['hits']]}
        for mode in ('keyword','vector','hybrid'):
            code,data=teacher.request('/api/search?'+urlencode({'q':'量子纠缠与黑洞蒸发','mode':mode,'class_id':2}))
            assert code==200 and data['hits']==[],(mode,data)
        points,_=server.VECTOR_INDEX.client.scroll(server.VECTOR_INDEX.collection,limit=100,with_payload=True)
        assert all(set(p.payload)=={'class_id','material_id','body_hash'} for p in points)
        report.update({'cross_class_denied':True,'unrelated_hits_empty_all_modes':True,'source_offsets_exact':True,'payload_has_no_text':True,'points':len(points)})
        print(json.dumps(report,ensure_ascii=False,indent=2))
    finally:
        http.shutdown();http.server_close();server.VECTOR_INDEX.close()
