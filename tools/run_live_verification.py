import sys,os,json,secrets,threading
from pathlib import Path
root=Path(__file__).resolve().parents[1];sys.path[:0]=[str(root),str(root/'tools')]
import server,retrieval,mcp_school_demo
os.environ['CAMPUS_DEMO_TOOL_TOKEN']=secrets.token_urlsafe(32)
os.environ['CAMPUS_EXTERNAL_TOOLS']=json.dumps([{'id':'school','kind':'mcp','url':'http://127.0.0.1:8891/mcp','allowed_tools':['lookup'],'token_env':'CAMPUS_DEMO_TOOL_TOKEN'},{'id':'topic_http','kind':'http','url':'http://127.0.0.1:8891/http-topic','description':'查询教学主题资源说明','token_env':'CAMPUS_DEMO_TOOL_TOKEN','inputSchema':{'type':'object','properties':{'topic':{'type':'string'}},'required':['topic'],'additionalProperties':False}}])
os.environ['AI_RETRIEVAL_MODE']='keyword'
server.DATA=root/'data'/'verification';server.DB=server.DATA/'campus.db';server.init_db();server.VECTOR_INDEX=retrieval.VectorIndex(server.connect,server.DATA)
mcp=server.ThreadingHTTPServer(('127.0.0.1',8891),mcp_school_demo.Handler);threading.Thread(target=mcp.serve_forever,daemon=True).start()
app=server.ThreadingHTTPServer(('127.0.0.1',8890),server.Handler)
print('Actual gateway + authenticated MCP verification: http://127.0.0.1:8890/chat',flush=True)
try:app.serve_forever()
finally:app.server_close();mcp.shutdown();mcp.server_close()
