import os, re, json, math
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, quote

BASE = Path(__file__).resolve().parent
UPLOADS = BASE / "uploads"
DATA = BASE / "data"
KNOWLEDGE = DATA / "knowledge.json"
META = DATA / "metadata.json"
INDEX = json.loads(KNOWLEDGE.read_text(encoding="utf-8")) if KNOWLEDGE.exists() else []
SOURCE_CACHE = {}
META_DATA = json.loads(META.read_text(encoding="utf-8")) if META.exists() else {}

def get_subjects():
    vals=[]
    for x in INDEX:
        v=x.get("subject") or x.get("course")
        if v and v not in vals: vals.append(v)
    preferred=["Behaviour in Organizations","Financial Reporting and Management Accounting","Business Statistics for Managers","Digital Transformation","Operations Management","Action Lab: Systems Thinking for Problem Solving","Artificial Intelligence for Business","Managerial Economics and Macroeconomic Environment","Marketing Management–I: Marketing Management Using AI","Supply Chain Management"]
    return [x for x in preferred if x in vals]+[x for x in vals if x not in preferred]

def norm(s): return re.sub(r"\s+", " ", str(s or "")).strip()
def tokens(s): return set(re.findall(r"[a-zA-Z0-9][a-zA-Z0-9'/-]{1,}", str(s).lower()))
CONCEPTS={
 "fixed cost":["fixed cost","fixed costs","relevant range","variable cost","contribution","break-even"],
 "variable cost":["variable cost","variable costs","fixed cost","contribution","break-even"],
 "contribution":["contribution","contribution margin","selling price","variable cost","fixed cost","break-even"],
 "break-even":["break-even","break even","contribution","fixed cost","variable cost"],
 "vrio":["VRIO","valuable","rare","inimitable","organization","competitive advantage"],
 "five forces":["five forces","Porter","rivalry","buyers","suppliers","substitutes","new entrants"],
 "confidence interval":["confidence interval","confidence intervals","sample","population","margin of error"],
 "hypothesis testing":["hypothesis testing","null hypothesis","alternative hypothesis","p-value","type I","type II"],
 "clt":["central limit theorem","CLT","sampling distribution","sample mean"],
 "forecasting":["forecast","forecasting","moving average","exponential smoothing","demand"],
 "inventory":["inventory","EOQ","safety stock","reorder point","holding cost"],
 "capacity":["capacity","bottleneck","utilization","process capacity"]}
STOP=set("the and for with that this from into about what how why are was were can could would should have has had not your their our they them you of to in on at by an is be as a or if it its we i a this these those which who where when than then also using used use more most very".split())
def detect_concept(q):
 l=q.lower()
 for k,v in CONCEPTS.items():
  if k in l or (k=='break-even' and 'break even' in l): return k,v
 ts=[x for x in re.findall(r"[a-zA-Z0-9][a-zA-Z0-9'-]+",l) if x not in STOP]
 return (ts[0] if ts else '',ts[:8])
def score(q,text):
 qt=set(re.findall(r"[a-zA-Z0-9][a-zA-Z0-9'-]+",q.lower()))-STOP; tl=text.lower(); tt=set(re.findall(r"[a-zA-Z0-9][a-zA-Z0-9'-]+",tl))-STOP
 concept,terms=detect_concept(q); overlap=len(qt&tt); hits=sum(1 for x in terms if x.lower() in tl)
 val=overlap*1.5+hits*3+(8 if concept and concept in tl else 0)
 if any(x in tl for x in ['total assets','total liabilities',"owners' equity",'balance sheet']) and not any(x in q.lower() for x in ['balance sheet','assets','liabilities','equity']): val-=10
 if any(x in tl for x in ['net income','cash flow statement']) and not any(x in q.lower() for x in ['net income','cash flow']): val-=5
 return val

def retrieve(q,subject=None,limit=14):
 rows=[]
 for item in INDEX:
  text=norm(item.get('text') or item.get('content') or item.get('passage') or '')
  if not text: continue
  subj=item.get('subject') or item.get('course') or ''
  if subject and subject.lower() not in ('all subjects','all') and subj and subj.lower()!=subject.lower(): continue
  sc=score(q,text)
  if sc>0: rows.append((sc,item))
 rows.sort(key=lambda x:x[0],reverse=True); out=[]; seen=set()
 for sc,it in rows:
  key=(it.get('document'),it.get('locator'))
  if key in seen: continue
  seen.add(key); out.append(it)
  if len(out)>=limit: break
 return out

def source_ref(item,n=0):
 doc=item.get('document') or item.get('source') or item.get('filename') or 'Course material'; loc=item.get('locator') or item.get('page') or item.get('slide') or item.get('sheet') or ''
 return {'ref':f'src_{n}','document':doc,'locator':loc,'text':norm(item.get('text') or item.get('content') or item.get('passage') or ''),'type':'spreadsheet' if str(doc).lower().endswith(('.xls','.xlsx')) else 'document'}

def ask_gpt_direct(q,subject=None):
 key=os.getenv('OPENAI_API_KEY')
 if not key: return None,'OpenAI API key is not configured on this server. Add OPENAI_API_KEY to the hosting platform environment variables.'
 try:
  from openai import OpenAI
  client=OpenAI(api_key=key)
  prompt=f"You are a helpful general-purpose GPT assistant. Answer the user's question clearly. This is NOT a course-grounded answer. Subject context: {subject or 'MBA'}. Question: {q}"
  r=client.responses.create(model=os.getenv('MBA_COPILOT_MODEL','gpt-4.1-mini'),input=prompt)
  return r.output_text,None
 except Exception as e: return None,f'GPT request failed: {e}'

def answer(q,subject=None):
 concept,_=detect_concept(q); items=retrieve(q,subject)
 refs=[source_ref(x,i) for i,x in enumerate(items[:8])]
 if not items: return {'answer':'I could not find sufficiently relevant evidence in the selected MBA material. Please upload the relevant course material or broaden the question.','sources':[],'concept':concept,'grounded':False}
 key=os.getenv('OPENAI_API_KEY')
 if key:
  try:
   from openai import OpenAI
   client=OpenAI(api_key=key)
   evidence='\n'.join([f"[SOURCE {i+1}] {r['document']} | {r['locator']} | {r['text']}" for i,r in enumerate(refs)])
   prompt=f"""You are MBA Copilot, a course-material-grounded MBA tutor. Question: {q}. Subject: {subject or 'All Subjects'}. Use ONLY relevant supplied evidence for course claims. Treat evidence as raw evidence, not the answer. Ignore irrelevant fragments, unrelated financial statements, tables, case background and numbers. Give: simple meaning; course explanation; one relevant course example; formula/calculation only if supported; Must Know/High Priority/Understand; exam priority; 4-6 likely exam questions; real business use clearly labelled as general application when not course-derived; common confusion; 30-second revision; sources. Insert clickable source markers exactly like [[SOURCE 1]] when a claim relies on evidence. If not established, say 'Not established in the supplied course material.' Evidence:\n{evidence}"""
   r=client.responses.create(model=os.getenv('MBA_COPILOT_MODEL','gpt-4.1-mini'),input=prompt)
   return {'answer':r.output_text,'sources':refs,'concept':concept,'grounded':True}
  except Exception: pass
 # Conservative fallback
 core={'fixed cost':'A fixed cost is a cost that does not change with the level of activity within the relevant range.','variable cost':'A variable cost changes with the level of activity.','contribution':'Contribution is selling price minus variable cost per unit.','break-even':'Break-even is the activity level where contribution covers fixed costs and profit is zero.'}.get(concept,f"The supplied material contains evidence related to '{concept}'.")
 return {'answer':f"## 📖 Simple Meaning\n{core}\n\n## 📚 Course Example\n{refs[0]['text'][:900]}\n\n## 🧠 Memorize\n**Must Know:** {core}\n**High Priority:** Know how this concept connects to its closest related concepts.\n\n## 🎯 Exam Questions\n1. Define {concept} and explain it with an example.\n2. Differentiate it from the closest related concept.\n3. Apply it to a business case.\n\n## 🏢 Real Business Use\nGeneral business application: use the concept to support relevant managerial decisions.\n\n## ⚡ Quick Revision\n{core}\n\n[[SOURCE 1]]",'sources':refs,'concept':concept,'grounded':True}

def find_source_file(doc):
 for p in UPLOADS.rglob('*'):
  if p.is_file() and p.name==doc: return p
 return None

def source_payload(item):
 r=source_ref(item); return r
class Handler(BaseHTTPRequestHandler):
 def send_json(self,obj,status=200):
  b=json.dumps(obj,ensure_ascii=False).encode(); self.send_response(status); self.send_header('Content-Type','application/json; charset=utf-8'); self.send_header('Content-Length',str(len(b))); self.end_headers(); self.wfile.write(b)
 def do_GET(self):
  path=urlparse(self.path).path
  if path=='/api/meta': self.send_json({'subjects':get_subjects(),'chunks':len(INDEX),'ai_configured':bool(os.getenv('OPENAI_API_KEY'))}); return
  if path.startswith('/api/source/'):
   ref=path.rsplit('/',1)[-1]; item=SOURCE_CACHE.get(ref)
   if not item: self.send_json({'error':'Reference expired. Ask the question again.'},404); return
   self.send_json(source_payload(item)); return
  if path.startswith('/api/original/'):
   from urllib.parse import unquote
   doc=unquote(path.split('/api/original/',1)[1]); fp=find_source_file(doc)
   if not fp: self.send_json({'error':'Original file is not present on this server.'},404); return
   raw=fp.read_bytes(); ext=fp.suffix.lower(); ctype={'.pdf':'application/pdf','.txt':'text/plain','.html':'text/html','.htm':'text/html'}.get(ext,'application/octet-stream')
   self.send_response(200); self.send_header('Content-Type',ctype); self.send_header('Content-Length',str(len(raw))); self.send_header('Content-Disposition','inline; filename="'+fp.name.replace('"','')+'"'); self.end_headers(); self.wfile.write(raw); return
  if path in ('/','/index.html'):
   data=(BASE/'index.html').read_bytes(); self.send_response(200); self.send_header('Content-Type','text/html; charset=utf-8'); self.send_header('Content-Length',str(len(data))); self.end_headers(); self.wfile.write(data); return
  self.send_response(404); self.end_headers()
 def do_POST(self):
  path=urlparse(self.path).path; n=int(self.headers.get('Content-Length',0)); body=json.loads(self.rfile.read(n) or b'{}'); q=body.get('question','').strip(); subject=body.get('subject')
  if not q: self.send_json({'error':'Question is required.'},400); return
  if path=='/api/chat':
   result=answer(q,subject); SOURCE_CACHE.clear();
   for i,s in enumerate(result['sources']): SOURCE_CACHE[s['ref']]=next((x for x in INDEX if x.get('document')==s['document'] and x.get('locator')==s['locator']),{})
   self.send_json(result); return
  if path=='/api/ask-gpt':
   text,err=ask_gpt_direct(q,subject)
   if err: self.send_json({'error':err,'configured':bool(os.getenv('OPENAI_API_KEY'))},400); return
   self.send_json({'answer':text,'ai':True,'mode':'Ask GPT','grounded':False}); return
  self.send_response(404); self.end_headers()
if __name__=='__main__':
 port=int(os.getenv('PORT','8000')); print(f'MBA Copilot running on port {port}'); ThreadingHTTPServer(('0.0.0.0',port),Handler).serve_forever()
