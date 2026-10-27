"""Read-only authenticated MCP sample. Genuine JSON-RPC transport, not an LLM mock."""
import json,os,secrets,threading
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
SCHEDULE={'科学':'周三第2节：科学课，主题为磁铁实验，地点为科学实验室。','语文':'周二第1节：语文课，主题为阅读表达。'}
class Handler(BaseHTTPRequestHandler):
    sessions=set()
    guard=threading.Lock()
    audit=[]
    def log_message(self,*args):pass
    def send(self,status,value=None,session=None):
        self.send_response(status);self.send_header('Content-Type','application/json')
        if session:self.send_header('Mcp-Session-Id',session)
        self.end_headers()
        if value is not None:self.wfile.write(json.dumps(value,ensure_ascii=False).encode())
    def do_POST(self):
        token=os.environ.get('CAMPUS_DEMO_TOOL_TOKEN','')
        if not token or self.headers.get('Authorization')!='Bearer '+token:return self.send(401,{'error':'unauthorized'})
        try:
            n=int(self.headers.get('Content-Length','0'))
            if not 0<n<=65536:return self.send(400,{'error':'invalid length'})
            d=json.loads(self.rfile.read(n))
            if self.path=='/http-topic':return self.send(200,{'topic':d.get('topic'),'note':'来自独立 HTTP 教学资源服务的结果'})
            if self.path!='/mcp':return self.send(404)
            method=d.get('method');sid=self.headers.get('Mcp-Session-Id')
            if method!='initialize' and sid not in self.sessions:return self.send(404,{'error':'session missing'})
            if method!='initialize' and self.headers.get('MCP-Protocol-Version')!='2025-06-18':return self.send(400,{'error':'protocol version'})
            self.audit.append({'request':d,'authenticated':True,'session_present':bool(sid)})
            if method=='notifications/initialized':return self.send(202)
            if method=='initialize':
                sid=secrets.token_hex(16)
                with self.guard:self.sessions.add(sid)
                result={'protocolVersion':'2025-06-18','capabilities':{'tools':{}},'serverInfo':{'name':'campus-school-tools','version':'1.0'}}
            elif method=='tools/list':result={'tools':[{'name':'lookup','description':'查询演示课表。topic 为科学或语文。仅查询，不修改数据。','inputSchema':{'type':'object','properties':{'topic':{'type':'string','enum':['科学','语文']}},'required':['topic'],'additionalProperties':False}}]}
            elif method=='tools/call':
                params=d.get('params',{});args=params.get('arguments',{})
                if params.get('name')!='lookup' or set(args)!={'topic'} or args['topic'] not in SCHEDULE:
                    return self.send(200,{'jsonrpc':'2.0','id':d.get('id'),'error':{'code':-32602,'message':'invalid tool arguments'}})
                result={'content':[{'type':'text','text':SCHEDULE[args['topic']]}],'isError':False}
            else:return self.send(200,{'jsonrpc':'2.0','id':d.get('id'),'error':{'code':-32601,'message':'method not found'}})
            self.send(200,{'jsonrpc':'2.0','id':d.get('id'),'result':result},sid)
        except (ValueError,TypeError,KeyError):self.send(400,{'error':'invalid request'})
if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--port',type=int,default=8891);args=p.parse_args()
    if not os.environ.get('CAMPUS_DEMO_TOOL_TOKEN'):raise SystemExit('Set CAMPUS_DEMO_TOOL_TOKEN first')
    ThreadingHTTPServer(('127.0.0.1',args.port),Handler).serve_forever()
