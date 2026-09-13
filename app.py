import os, re, json
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, unquote
import db

BASE=Path(__file__).resolve().parent
UPLOADS=BASE/'uploads'; DATA=BASE/'data'; KNOWLEDGE=DATA/'knowledge.json'
INDEX=json.loads(KNOWLEDGE.read_text(encoding='utf-8')) if KNOWLEDGE.exists() else []
SOURCE_CACHE={}

PREFERRED=["Behaviour in Organizations","Financial Reporting and Management Accounting","Business Statistics for Managers","Digital Transformation","Operations Management","Action Lab: Systems Thinking for Problem Solving","Artificial Intelligence for Business","Managerial Economics and Macroeconomic Environment","Marketing Management–I: Marketing Management Using AI","Supply Chain Management"]
CONCEPTS={
 'fixed cost':['fixed cost','fixed costs','relevant range','variable cost','contribution','break-even'],
 'variable cost':['variable cost','variable costs','fixed cost','contribution','break-even'],
 'contribution':['contribution','contribution margin','selling price','variable cost','fixed cost','break-even'],
 'break-even':['break-even','break even','contribution','fixed cost','variable cost'],
 'vrio':['vrio','valuable','rare','inimitable','organization','competitive advantage'],
 'five forces':['five forces','porter','rivalry','buyers','suppliers','substitutes','new entrants'],
 'confidence interval':['confidence interval','confidence intervals','sample','population','margin of error'],
 'hypothesis testing':['hypothesis testing','null hypothesis','alternative hypothesis','p-value','type i','type ii'],
 'clt':['central limit theorem','clt','sampling distribution','sample mean'],
 'forecasting':['forecast','forecasting','moving average','exponential smoothing','demand'],
 'inventory':['inventory','eoq','safety stock','reorder point','holding cost'],
 'capacity':['capacity','bottleneck','utilization','process capacity']}
STOP=set('the and for with that this from into about what how why are was were can could would should have has had not your their our they them you of to in on at by an is be as a or if it its we i a this these those which who where when than then also using used use more most very'.split())

def norm(s): return re.sub(r'\s+',' ',str(s or '')).strip()
def detect_concept(q):
 l=q.lower()
 for k,terms in CONCEPTS.items():
  if k in l or (k=='break-even' and 'break even' in l): return k,terms
 ts=[x for x in re.findall(r"[a-zA-Z0-9][a-zA-Z0-9'-]+",l) if x not in STOP]
 return (ts[0] if ts else ''),ts[:8]
def score(q,text):
 ql=q.lower(); tl=text.lower(); concept,terms=detect_concept(q)
 qt=set(re.findall(r"[a-zA-Z0-9][a-zA-Z0-9'-]+",ql))-STOP
 tt=set(re.findall(r"[a-zA-Z0-9][a-zA-Z0-9'-]+",tl))-STOP
 val=len(qt&tt)*1.5+sum(1 for x in terms if x.lower() in tl)*3+(8 if concept and concept in tl else 0)
 if any(x in tl for x in ['total assets','total liabilities',"owners' equity",'balance sheet']) and not any(x in ql for x in ['balance sheet','assets','liabilities','equity']): val-=10
 if any(x in tl for x in ['net income','cash flow statement']) and not any(x in ql for x in ['net income','cash flow']): val-=5
 return val

def retrieve(q,subject=None,limit=14):
 items=db.search_lexical(q,subject,limit*2) if db.enabled() else []
 if not items: items=INDEX
 rows=[]
 for it in items:
  text=norm(it.get('text') or it.get('content') or it.get('passage'))
  if not text: continue
  subj=it.get('subject') or it.get('course') or ''
  if subject and subject.lower() not in ('all subjects','all') and subj and subj.lower()!=subject.lower(): continue
  rows.append((score(q,text),it))
 rows=[x for x in rows if x[0]>0]; rows.sort(key=lambda x:x[0],reverse=True)
 out=[]; seen=set()
 for _,it in rows:
  key=(it.get('document'),it.get('locator'))
  if key in seen: continue
  seen.add(key); out.append(it)
  if len(out)>=limit: break
 return out

def subjects():
 vals=db.subjects() if db.enabled() else []
 if not vals:
  vals=list(dict.fromkeys((x.get('subject') or x.get('course')) for x in INDEX if x.get('subject') or x.get('course')))
 return [x for x in PREFERRED if x in vals]+[x for x in vals if x not in PREFERRED]

def ref(item,n):
 doc=item.get('document') or item.get('source') or item.get('filename') or 'Course material'; loc=item.get('locator') or item.get('page') or item.get('slide') or item.get('sheet') or ''
 return {'ref':f'src_{n}','document':doc,'locator':loc,'text':norm(item.get('text') or item.get('content') or item.get('passage')),'type':'spreadsheet' if str(doc).lower().endswith(('.xls','.xlsx')) else 'document'}

def ask_gpt(q,subject=None):
 key=os.getenv('OPENAI_API_KEY')
 if not key:return None,'OpenAI API key is not configured on this server.'
 try:
  from openai import OpenAI
  r=OpenAI(api_key=key).responses.create(model=os.getenv('MBA_COPILOT_MODEL','gpt-4.1-mini'),input=f'You are a general GPT assistant. This is NOT course-grounded. Answer clearly. Subject: {subject or "MBA"}. Question: {q}')
  return r.output_text,None
 except Exception as e:return None,f'GPT request failed: {e}'

def answer(q,subject=None,mode='Teach Me'):
 concept,_=detect_concept(q); items=retrieve(q,subject)
 refs=[ref(x,i) for i,x in enumerate(items[:8])]
 if not refs:return {'answer':'I could not find sufficiently relevant evidence in the selected MBA material.','sources':[],'concept':concept,'grounded':False}
 key=os.getenv('OPENAI_API_KEY')
 if key:
  try:
   from openai import OpenAI
   evidence='\n'.join(f"[SOURCE {i+1}] {r['document']} | {r['locator']} | {r['text']}" for i,r in enumerate(refs))
   prompt=f'''You are MBA Copilot, a course-material-grounded MBA tutor. Question: {q}. Subject: {subject or 'All Subjects'}. Mode: {mode}. Treat retrieved text only as evidence. Do NOT dump or quote irrelevant passages. Filter out unrelated tables, financial statements, case background and numbers. Answer with: 📖 Simple Meaning; 📚 Course Material; 💡 Relevant Example; 🧮 How It Works/Formula if relevant; 🧠 Memorize on Priority (Must Know/High Priority/Understand); 🎯 Exam Priority; ❓ 4-6 likely exam questions; 🏢 Real Business Use (label as general application if not course-derived); ⚠️ Common Confusion; ⚡ 30-Second Revision. Insert source markers exactly [[SOURCE 1]] etc. Only cite a source when it supports the claim. If unsupported, say "Not established in the supplied course material." Evidence:\n{evidence}'''
   r=OpenAI(api_key=key).responses.create(model=os.getenv('MBA_COPILOT_MODEL','gpt-4.1-mini'),input=prompt)
   return {'answer':r.output_text,'sources':refs,'concept':concept,'grounded':True}
  except Exception:
   pass
 core={'fixed cost':'A fixed cost is a cost that does not change with the level of activity within the relevant range.','variable cost':'A variable cost changes with the level of activity.','contribution':'Contribution is selling price minus variable cost per unit.','break-even':'Break-even is the activity level where contribution covers fixed costs and profit is zero.'}.get(concept,f"The supplied material contains evidence related to '{concept}'.")
 return {'answer':f'## 📖 Simple Meaning\n{core}\n\n## 📚 Course Example\n{refs[0]["text"][:900]}\n\n## 🧠 Memorize\n**Must Know:** {core}\n**High Priority:** Know the closest related concepts.\n\n## 🎯 Exam Questions\n1. Define {concept}.\n2. Differentiate it from its closest related concept.\n3. Apply it to a business case.\n\n## 🏢 Real Business Use\nGeneral business application.\n\n## ⚡ Quick Revision\n{core}\n\n[[SOURCE 1]]','sources':refs,'concept':concept,'grounded':True}

class Handler(BaseHTTPRequestHandler):
 def send_json(self,obj,status=200):
  b=json.dumps(obj,ensure_ascii=False).encode(); self.send_response(status); self.send_header('Content-Type','application/json; charset=utf-8'); self.send_header('Content-Length',str(len(b))); self.end_headers(); self.wfile.write(b)
 def do_GET(self):
  path=urlparse(self.path).path
  if path=='/health': self.send_json({'ok':True,'database':db.enabled(),'chunks':db.count_passages() if db.enabled() else len(INDEX)}); return
  if path=='/api/meta': self.send_json({'subjects':subjects(),'chunks':db.count_passages() if db.enabled() else len(INDEX),'ai_configured':bool(os.getenv('OPENAI_API_KEY')),'database_configured':db.enabled()}); return
  if path.startswith('/api/source/'):
   item=SOURCE_CACHE.get(path.rsplit('/',1)[-1]);
   if not item:self.send_json({'error':'Reference expired. Ask the question again.'},404)
   else:self.send_json(ref(item))
   return
  if path in ('/','/index.html'):
   data=(BASE/'index.html').read_bytes(); self.send_response(200); self.send_header('Content-Type','text/html; charset=utf-8'); self.send_header('Content-Length',str(len(data))); self.end_headers(); self.wfile.write(data); return
  self.send_response(404); self.end_headers()
 def do_POST(self):
  path=urlparse(self.path).path; n=int(self.headers.get('Content-Length',0)); body=json.loads(self.rfile.read(n) or b'{}'); q=body.get('question','').strip(); subject=body.get('subject'); mode=body.get('mode','Teach Me')
  if not q:self.send_json({'error':'Question is required.'},400);return
  if path=='/api/chat':
   result=answer(q,subject,mode); SOURCE_CACHE.clear()
   for s in result['sources']:
    SOURCE_CACHE[s['ref']]=next((x for x in (db.search_lexical(q,subject,20) if db.enabled() else INDEX) if (x.get('document') or x.get('filename'))==s['document'] and (x.get('locator') or '')==s['locator']),{})
   self.send_json(result);return
  if path=='/api/ask-gpt':
   text,err=ask_gpt(q,subject)
   if err:self.send_json({'error':err},400)
   else:self.send_json({'answer':text,'ai':True,'mode':'Ask GPT','grounded':False})
   return
  self.send_json({'error':'Not found'},404)

if __name__=='__main__':
 try: db.ensure_schema()
 except Exception as e: print('Database initialization warning:',e)
 port=int(os.getenv('PORT','8000')); print('MBA Copilot running on port',port); ThreadingHTTPServer(('0.0.0.0',port),Handler).serve_forever()
