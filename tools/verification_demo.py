"""Isolated browser demo with a deterministic local LLM fixture, never real AI."""
import os,sys,tempfile,threading
from pathlib import Path
sys.path[:0]=[str(Path(__file__).resolve().parents[1]),str(Path(__file__).resolve().parents[1]/'tests')]
from http.server import ThreadingHTTPServer
from test_platform import Fixture
from test_acceptance import Client
import server,qa
with tempfile.TemporaryDirectory() as directory:
    server.DATA=Path(directory);server.DB=server.DATA/'demo.db';server.init_db()
    fixture=ThreadingHTTPServer(('127.0.0.1',0),Fixture)
    threading.Thread(target=fixture.serve_forever,daemon=True).start()
    qa.config=lambda:{'AI_API_KEY':'fixture-only','AI_MODEL':'fixture-model','AI_BASE_URL':'http://127.0.0.1:'+str(fixture.server_port)+'/v1','AI_RETRIEVAL_MODE':'keyword'}
    os.environ['CAMPUS_EXTERNAL_TOOLS']='[]'
    app=ThreadingHTTPServer(('127.0.0.1',8879),server.Handler)
    threading.Thread(target=app.serve_forever,daemon=True).start()
    client=Client('http://127.0.0.1:8879');client.login('teacher');client.upload('磁铁实验.md','磁铁能吸引铁钉，不能吸引木块。'.encode())
    print('FIXTURE DEMO http://127.0.0.1:8879/chat',flush=True)
    try:threading.Event().wait()
    except KeyboardInterrupt:pass
    finally:app.shutdown();app.server_close();fixture.shutdown();fixture.server_close()
