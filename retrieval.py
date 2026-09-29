"""Class-scoped, traceable retrieval. SQLite owns text; Qdrant owns vectors only."""
import hashlib
import importlib.util
import json
import logging
import math
import os
import re
import threading
import time
import uuid
from collections import Counter
from pathlib import Path

log = logging.getLogger('campus.retrieval')
WINDOW, OVERLAP, THRESHOLD, RRF_K = 800, 100, 0.35, 60
MODEL = 'sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2'
STOPWORDS = set('的 了 和 是 在 有 与 或 及 为 对 将 中 从 我 我们 请 如何 怎么 什么 哪些 是否 一个 一些 可以 能够 进行 以及 通过 学生 老师'.split())

class RetrievalError(Exception):
    def __init__(self, message, status=503):
        self.status = status
        super().__init__(message)


def tokenize(text):
    """CJK bigrams + ASCII words: deterministic, offline full-text index terms."""
    terms = []
    for span in re.findall(r'[\u3400-\u9fff]+|[a-zA-Z0-9_]+', text.lower()):
        if re.fullmatch(r'[a-z0-9_]+', span):
            if len(span) > 1 and span not in {'the','is','of','a','how','what','to','and','in'}: terms.append(span)
        elif len(span) == 1:
            if span not in STOPWORDS: terms.append(span)
        else:
            terms.extend(span[i:i+2] for i in range(len(span)-1) if span[i:i+2] not in STOPWORDS)
    return list(dict.fromkeys(terms))


def split_chunks(body, strategy='window', separator=''):
    if strategy not in {'window','line','paragraph','sentence','markdown','custom'}:
        raise ValueError('不支持的切分策略。')
    if strategy == 'custom' and (not isinstance(separator,str) or not 1 <= len(separator) <= 20):
        raise ValueError('自定义分隔符须为 1–20 个字符。')
    boundaries = []
    if strategy == 'window':
        start = 0
        while start < len(body):
            end = min(start+WINDOW, len(body))
            boundaries.append((start,end))
            if end == len(body): break
            start = end-OVERLAP
    else:
        pattern = {'line':r'\n','paragraph':r'\n\s*\n','sentence':r'[。！？.!?](?:\s|$)?',
                   'markdown':r'(?m)^#{1,6}\s+', 'custom':re.escape(separator)}[strategy]
        points = ([m.start() for m in re.finditer(pattern, body)] if strategy == 'markdown'
                  else [m.end() for m in re.finditer(pattern, body)])
        points = sorted(set([0]+points+[len(body)]))
        for start,end in zip(points,points[1:]):
            # Short units are combined up to WINDOW; explicit Markdown sections stay separate.
            if strategy != 'markdown' and boundaries and end-boundaries[-1][0] <= WINDOW:
                boundaries[-1]=(boundaries[-1][0],end)
            else:
                while start < end:
                    stop=min(start+WINDOW,end);boundaries.append((start,stop));start=stop
    return [{'chunk_index':i+1,'start_char':a,'end_char':b,'body':body[a:b]}
            for i,(a,b) in enumerate((a,b) for a,b in boundaries if body[a:b].strip())]


def add_chunks(c, material_id, class_id, body, strategy='window', separator=''):
    chunks=split_chunks(body,strategy,separator)
    for chunk in chunks:
        digest=hashlib.sha256(chunk['body'].encode()).hexdigest()
        cid=str(uuid.uuid5(uuid.NAMESPACE_URL,f'campusclaw:{material_id}:{chunk["start_char"]}:{digest}'))
        c.execute('''INSERT INTO knowledge_chunks(id,material_id,class_id,chunk_index,start_char,end_char,
                     body,body_hash,strategy) VALUES(?,?,?,?,?,?,?,?,?)''',
                  (cid,material_id,class_id,chunk['chunk_index'],chunk['start_char'],chunk['end_char'],chunk['body'],digest,strategy))
        c.execute('INSERT INTO chunks_fts(chunk_id,terms) VALUES(?,?)',(cid,' '.join(tokenize(chunk['body']))))
    return len(chunks)


def migrate(connect):
    with connect() as c:
        c.executescript('''
        CREATE TABLE IF NOT EXISTS knowledge_chunks(
          id TEXT PRIMARY KEY, material_id TEXT NOT NULL REFERENCES materials(id) ON DELETE CASCADE,
          class_id INTEGER NOT NULL REFERENCES classes(id), chunk_index INTEGER NOT NULL,
          start_char INTEGER NOT NULL, end_char INTEGER NOT NULL, body TEXT NOT NULL, body_hash TEXT NOT NULL,
          strategy TEXT NOT NULL, vector_state TEXT NOT NULL DEFAULT 'pending', indexed_collection TEXT,
          UNIQUE(material_id,chunk_index));
        CREATE INDEX IF NOT EXISTS chunks_class ON knowledge_chunks(class_id,material_id);
        CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(chunk_id UNINDEXED,terms,tokenize='unicode61');
        CREATE TRIGGER IF NOT EXISTS chunks_delete AFTER DELETE ON knowledge_chunks BEGIN
          DELETE FROM chunks_fts WHERE chunk_id=old.id;
        END;
        ''')
        c.execute('CREATE TABLE IF NOT EXISTS retrieval_schema(version TEXT PRIMARY KEY)')
        if not c.execute("SELECT 1 FROM retrieval_schema WHERE version='fts-full-v1'").fetchone():
            c.execute('DELETE FROM chunks_fts')
            for old in c.execute('SELECT id,body FROM knowledge_chunks').fetchall():
                c.execute('INSERT INTO chunks_fts(chunk_id,terms) VALUES(?,?)',(old['id'],' '.join(tokenize(old['body']))))
            c.execute("INSERT INTO retrieval_schema VALUES('fts-full-v1')")
        for row in c.execute('''SELECT k.material_id,k.class_id,k.body FROM knowledge_entries k
            JOIN materials m ON m.id=k.material_id AND m.class_id=k.class_id
            WHERE NOT EXISTS(SELECT 1 FROM knowledge_chunks ch WHERE ch.material_id=k.material_id)''').fetchall():
            add_chunks(c,row['material_id'],row['class_id'],row['body'])


def keyword_search(c,class_id,query,limit=40):
    terms=tokenize(query)
    if not terms:return []
    expression=' OR '.join('"'+t.replace('"','""')+'"' for t in terms)
    # class scope is enforced before ranking/LIMIT. No global text or title returned.
    rows=c.execute('''SELECT ch.id,ch.body FROM chunks_fts f
        JOIN knowledge_chunks ch ON ch.id=f.chunk_id
        JOIN materials m ON m.id=ch.material_id AND m.class_id=ch.class_id
        WHERE chunks_fts MATCH ? AND ch.class_id=? ORDER BY ch.id''',(expression,class_id)).fetchall()
    scored=[]
    for r in rows:
        present=set(tokenize(r['body']))
        matched=[t for t in terms if t in present]
        # A lone generic CJK bigram in a long question isn't reliable evidence.
        required=1 if len(terms)<=3 else 2
        if len(matched)<required:continue
        score=sum(1+math.log1p(r['body'].lower().count(t)) for t in matched)/len(terms)
        scored.append((r['id'],score))
    return sorted(scored,key=lambda x:(-x[1],x[0]))[:limit]


def fuse(keyword,vector,limit):
    scores={}
    for route in (keyword,vector):
        for rank,(cid,_) in enumerate(route,1):scores[cid]=scores.get(cid,0)+1/(RRF_K+rank)
    return sorted(scores.items(),key=lambda x:(-x[1],x[0]))[:limit]


class VectorIndex:
    def __init__(self,connect,data_dir):
        self.connect=connect; self.data_dir=Path(data_dir)
        available=all(importlib.util.find_spec(m) for m in ('qdrant_client','fastembed'))
        self.mode=os.environ.get('CAMPUS_VECTOR_MODE','local' if available else 'off')
        if self.mode not in ('off','local','remote'):raise ValueError('CAMPUS_VECTOR_MODE must be off/local/remote')
        self.model_name=os.environ.get('CAMPUS_EMBED_MODEL',MODEL)
        fingerprint=hashlib.sha256((self.model_name+':mean-subwindows120-v1').encode()).hexdigest()[:12]
        self.collection='campus_chunks_'+fingerprint
        self.enabled=self.mode!='off';self.ready=False;self.error='';self.client=None;self.model=None
        self.lock=threading.RLock();self.wake=threading.Event();self.stop=threading.Event();self.thread=None

    def start(self):
        if not self.enabled:return
        self.thread=threading.Thread(target=self._worker,daemon=True,name='campus-vector-index')
        self.thread.start()

    def _initialize(self):
        cache=os.environ.get('CAMPUS_MODEL_CACHE',str(self.data_dir/'models'))
        os.environ.setdefault('HF_HOME',str(Path(cache)/'huggingface'))
        os.environ.setdefault('HF_XET_CACHE',str(Path(cache)/'xet'))
        os.environ.setdefault('HF_HUB_DISABLE_XET','1')
        os.environ.setdefault('HF_HUB_DISABLE_TELEMETRY','1')
        from fastembed import TextEmbedding
        from qdrant_client import QdrantClient,models
        cache=os.environ.get('CAMPUS_MODEL_CACHE',str(self.data_dir/'models'))
        marker=Path(cache)/('ready-'+hashlib.sha256(self.model_name.encode()).hexdigest()[:12])
        self.model=TextEmbedding(model_name=self.model_name,cache_dir=cache,threads=2,local_files_only=marker.exists())
        marker.parent.mkdir(parents=True,exist_ok=True)
        marker.touch()
        # Increase supported tokenizer limit; subwindowing still covers long original chunks.
        self.model.model.tokenizer.enable_truncation(max_length=512)
        if self.mode=='remote':
            url=os.environ.get('QDRANT_URL','http://qdrant:6333')
            self.client=QdrantClient(url=url,api_key=os.environ.get('QDRANT_API_KEY') or None,timeout=15)
        else:
            self.client=QdrantClient(path=str(self.data_dir/'qdrant'),force_disable_check_same_thread=True)
        dimension=len(self.embed(['初始化向量检索'])[0])
        if not self.client.collection_exists(self.collection):
            self.client.create_collection(self.collection,vectors_config=models.VectorParams(size=dimension,distance=models.Distance.COSINE))
        if self.mode=='remote':
            self.client.create_payload_index(self.collection,field_name='class_id',field_schema=models.PayloadSchemaType.INTEGER)
        # Re-upsert on each process start: safe after Qdrant volume loss/restoration.
        with self.connect() as c:
            c.execute("UPDATE knowledge_chunks SET vector_state='pending' WHERE indexed_collection=?",(self.collection,))
        self.ready=True;self.error=''

    def embed(self,texts):
        import numpy as np
        vectors=[]
        for text in texts:
            parts=[text[i:i+120] for i in range(0,len(text),120)] or [' ']
            matrix=list(self.model.embed(parts,batch_size=16))
            vector=np.mean(matrix,axis=0);norm=float(np.linalg.norm(vector))
            if not math.isfinite(norm) or norm<=0:raise RuntimeError('Invalid embedding')
            vectors.append((vector/norm).tolist())
        return vectors

    def _worker(self):
        while not self.stop.is_set():
            try:
                with self.lock:
                    if not self.ready:self._initialize()
                while not self.stop.is_set():
                    with self.connect() as c:
                        rows=c.execute('''SELECT * FROM knowledge_chunks WHERE vector_state!='ready'
                            OR indexed_collection IS NULL OR indexed_collection!=? LIMIT 16''',(self.collection,)).fetchall()
                    if not rows:break
                    from qdrant_client import models
                    with self.lock:
                        vectors=self.embed([r['body'] for r in rows])
                        points=[models.PointStruct(id=r['id'],vector=v,payload={'class_id':r['class_id'],
                            'material_id':r['material_id'],'body_hash':r['body_hash']}) for r,v in zip(rows,vectors)]
                        self.client.upsert(self.collection,points=points,wait=True)
                    with self.connect() as c:
                        c.executemany("UPDATE knowledge_chunks SET vector_state='ready',indexed_collection=? WHERE id=? AND body_hash=?",
                                      [(self.collection,r['id'],r['body_hash']) for r in rows])
                    self.error=''
            except Exception as e:
                if not self.ready and self.client is not None:
                    try:self.client.close()
                    except Exception:pass
                    self.client=None
                self.error='向量索引暂不可用，请检查模型或向量库后重试。'
                log.warning('Vector indexing failed (%s): %s',type(e).__name__,str(e)[:250])
            self.wake.wait(15);self.wake.clear()

    def retry(self):self.wake.set()

    def status(self,class_id):
        with self.connect() as c:
            row=c.execute('''SELECT count(*) total,coalesce(sum(CASE WHEN vector_state='ready'
                AND indexed_collection=? THEN 1 ELSE 0 END),0) indexed_count FROM knowledge_chunks WHERE class_id=?''',
                (self.collection,class_id)).fetchone()
        return {'enabled':self.enabled,'ready':self.ready and not self.error,'total_chunks':row['total'],
                'indexed_chunks':row['indexed_count'] if self.enabled else 0,'pending_chunks':row['total']-(row['indexed_count'] if self.enabled else 0),
                'model':self.model_name if self.enabled else None,'backend':'qdrant-'+self.mode if self.enabled else 'disabled',
                'message':self.error or ('' if self.enabled else '未启用向量服务，可使用关键词检索。')}

    def search(self,class_id,query,limit=40):
        state=self.status(class_id)
        if not self.enabled:raise RetrievalError('未启用向量服务，请选择关键词模式或安装向量依赖。')
        if not state['ready'] or state['pending_chunks']:
            raise RetrievalError('本班向量索引尚未就绪，请稍后重试，或切换关键词模式。')
        if not state['total_chunks']:return []
        from qdrant_client import models
        try:
            with self.lock:
                vec=self.embed([query])[0]
                result=self.client.query_points(collection_name=self.collection,query=vec,
                    query_filter=models.Filter(must=[models.FieldCondition(key='class_id',match=models.MatchValue(value=class_id))]),
                    score_threshold=THRESHOLD,limit=limit,with_payload=True,with_vectors=False)
        except Exception as e:
            log.warning('Vector query failed (%s)',type(e).__name__)
            raise RetrievalError('向量检索服务暂不可用，请稍后重试。') from e
        # Never trust a vector database payload for text or authorization.
        verified=[]
        with self.connect() as c:
            for hit in result.points:
                row=c.execute('''SELECT ch.body_hash FROM knowledge_chunks ch JOIN materials m
                    ON m.id=ch.material_id AND m.class_id=ch.class_id WHERE ch.id=? AND ch.class_id=?''',
                    (str(hit.id),class_id)).fetchone()
                if row and (hit.payload or {}).get('body_hash')==row['body_hash'] and float(hit.score)>=THRESHOLD:
                    verified.append((str(hit.id),float(hit.score)))
        return verified

    def close(self):
        self.stop.set();self.wake.set()
        if self.thread:self.thread.join(timeout=10)
        if self.client and (not self.thread or not self.thread.is_alive()):self.client.close()


def retrieve(connect,index,class_id,query,mode='hybrid',limit=5):
    if not isinstance(query,str) or not 1<=len(query.strip())<=500:
        raise RetrievalError('检索内容须为 1–500 个字符。',400)
    if mode not in ('keyword','vector','hybrid'):raise RetrievalError('检索模式须为 keyword、vector 或 hybrid。',400)
    if isinstance(limit,bool) or not isinstance(limit,int) or not 1<=limit<=20:raise RetrievalError('结果条数须为 1–20。',400)
    query=query.strip()
    kw=[];vec=[]
    if mode in ('keyword','hybrid'):
        with connect() as c:kw=keyword_search(c,class_id,query)
    if mode in ('vector','hybrid'):vec=index.search(class_id,query)
    ranked=fuse(kw,vec,limit) if mode=='hybrid' else (kw if mode=='keyword' else vec)[:limit]
    kwscores=dict(kw);vscores=dict(vec);hits=[]
    with connect() as c:
        for cid,score in ranked:
            r=c.execute('''SELECT ch.*,m.title,m.filename FROM knowledge_chunks ch JOIN materials m
                ON m.id=ch.material_id AND m.class_id=ch.class_id WHERE ch.id=? AND ch.class_id=?''',(cid,class_id)).fetchone()
            if not r:continue
            # Excerpt is the exact complete chunk, never generated or sourced from Qdrant.
            hits.append({'chunk_id':cid,'material_id':r['material_id'],'title':r['title'],'filename':r['filename'],
                'chunk_index':r['chunk_index'],'start_char':r['start_char'],'end_char':r['end_char'],
                'excerpt':r['body'],'body_hash':r['body_hash'],'score':round(score,6),
                'keyword_score':round(kwscores[cid],6) if cid in kwscores else None,
                'vector_score':round(vscores[cid],6) if cid in vscores else None,
                'matched_by':[p for p,s in [('keyword',kwscores),('vector',vscores)] if cid in s],
                'source_url':'/api/chunks/'+cid,'material_url':'/api/materials/'+r['material_id']})
    return {'query':query,'mode':mode,'scope':'current_class','hits':hits,
            'message':f'找到 {len(hits)} 条相关原文片段。' if hits else '资料中未找到相关内容',
            'offset_convention':'Unicode code points, zero-based [start_char, end_char)',
            'vector_threshold':THRESHOLD,'fusion':'RRF(k=60)' if mode=='hybrid' else None}
