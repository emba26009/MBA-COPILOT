import os,re,json,tempfile,email
from pathlib import Path
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from urllib.parse import urlparse
import db
BASE=Path(__file__).resolve().parent; DATA=BASE/'data'; KNOWLEDGE=DATA/'knowledge.json'
INDEX=json.loads(KNOWLEDGE.read_text(encoding='utf-8')) if KNOWLEDGE.exists() else []
SOURCE_CACHE={}
PREFERRED=["Behaviour in Organizations","Financial Reporting and Management Accounting","Business Statistics for Managers","Digital Transformation","Operations Management","Action Lab: Systems Thinking for Problem Solving","Artificial Intelligence for Business","Managerial Economics and Macroeconomic Environment","Marketing Management–I: Marketing Management Using AI","Supply Chain Management"]
CONCEPTS={'fixed cost':['fixed cost','fixed costs','relevant range','variable cost','contribution','break-even'],'variable cost':['variable cost','variable costs','fixed cost','contribution','break-even'],'contribution':['contribution','contribution margin','selling price','variable cost','fixed cost','break-even'],'break-even':['break-even','break even','contribution','fixed cost','variable cost'],'vrio':['vrio','valuable','rare','inimitable','organization','competitive advantage'],'five forces':['five forces','porter','rivalry','buyers','suppliers','substitutes','new entrants'],'confidence interval':['confidence interval','confidence intervals','sample','population','margin of error'],'hypothesis testing':['hypothesis testing','null hypothesis','alternative hypothesis','p-value','type i','type ii'],'clt':['central limit theorem','clt','sampling distribution','sample mean'],'forecasting':['forecast','forecasting','moving average','exponential smoothing','demand'],'inventory':['inventory','eoq','safety stock','reorder point','holding cost'],'capacity':['capacity','bottleneck','utilization','process capacity']}
STOP=set('the and for with that this from into about what how why are was were can could would should have has had not your their our they them you of to in on at by an is be as a or if it its we i a this these those which who where when than then also using used use more most very'.split())
def norm(s):return re.sub(r'\s+',' ',str(s or '')).strip()
def subject_key(s):return norm(s).casefold().replace('–','-').replace('—','-')
def is_all_subjects(s):return not s or subject_key(s) in ('all subjects','all')
def detect_concept(q):
 l=q.lower()
 for k,terms in CONCEPTS.items():
  if k in l or (k=='break-even' and 'break even' in l):return k,terms
 ts=[x for x in re.findall(r"[a-zA-Z0-9][a-zA-Z0-9'-]+",l) if x not in STOP];return (ts[0] if ts else ''),ts[:8]
def local_score(q,text):
 concept,terms=detect_concept(q);ql=q.lower();tl=text.lower();qt=set(re.findall(r"[a-zA-Z0-9][a-zA-Z0-9'-]+",ql))-STOP;tt=set(re.findall(r"[a-zA-Z0-9][a-zA-Z0-9'-]+",tl))-STOP
 v=len(qt&tt)*1.5+sum(3 for x in terms if x in tl)+(8 if concept and concept in tl else 0)
 if any(x in tl for x in ['total assets','total liabilities',"owners' equity",'balance sheet']) and not any(x in ql for x in ['balance sheet','assets','liabilities','equity']):v-=18
 if any(x in tl for x in ['income statement','net income','sales revenue']) and concept in ('fixed cost','variable cost','contribution','break-even'):v-=8
 return v
def _filter_items(items,subject):
 out=[];wanted=subject_key(subject)
 for it in items or []:
  text=norm(it.get('text') or it.get('content') or it.get('passage'));subj=it.get('subject') or it.get('course') or ''
  if not text:continue
  if not is_all_subjects(subject) and subject_key(subj)!=wanted:continue
  out.append(it)
 return out
def _rank(q,items,limit):
 rows=[(local_score(q,norm(it.get('text') or it.get('content') or it.get('passage'))),it) for it in items];rows.sort(key=lambda x:x[0],reverse=True);out=[];seen=set()
 for score,it in rows:
  if score<1:continue
  key=(it.get('document') or it.get('filename'),it.get('locator'))
  if key in seen:continue
  seen.add(key);out.append(it)
  if len(out)>=limit:break
 return out
def retrieve(q,subject=None,limit=10):
 items=[]
 if db.enabled() and os.getenv('OPENAI_API_KEY'):
  try:
   from openai import OpenAI;v=OpenAI(api_key=os.environ['OPENAI_API_KEY']).embeddings.create(model='text-embedding-3-small',input=q).data[0].embedding;items=db.search_vector(v,subject,limit*3)
  except Exception:items=[]
 if not items and db.enabled():
  try:items=db.search_lexical(q,subject,limit*4)
  except Exception:items=[]
 if not items and is_all_subjects(subject) and db.enabled():
  try:items=db.search_lexical(q,None,limit*6)
  except Exception:items=[]
 if not items:items=INDEX
 # IMPORTANT: the selected subject is a hard boundary. We never fall back to
 # another subject merely because it has a better lexical match.
 filtered=_filter_items(items,subject)
 return _rank(q,filtered,limit)
def subjects():
 vals=db.subjects() if db.enabled() else []
 if not vals:vals=list(dict.fromkeys((x.get('subject') or x.get('course')) for x in INDEX if x.get('subject') or x.get('course')))
 vals=[x for x in vals if x]
 # Preserve the canonical display names while matching case/dash variants.
 bykey={subject_key(x):x for x in vals};ordered=[]
 for p in PREFERRED:
  if subject_key(p) in bykey:ordered.append(bykey[subject_key(p)])
 ordered.extend(x for x in vals if subject_key(x) not in {subject_key(y) for y in ordered})
 return ordered
def ref(item,n):
 doc=item.get('document') or item.get('source') or item.get('filename') or 'Course material';loc=item.get('locator') or item.get('page') or item.get('slide') or item.get('sheet') or ''
 return {'ref':f'src_{n}','document':doc,'locator':loc,'text':norm(item.get('text') or item.get('content') or item.get('passage')),'type':'spreadsheet' if str(doc).lower().endswith(('.xls','.xlsx')) else 'document'}
def ask_gpt(q,subject=None):
 key=os.getenv('OPENAI_API_KEY')
 if not key:return None,'OpenAI API key is not configured on this server.'
 try:
  from openai import OpenAI;r=OpenAI(api_key=key).responses.create(model=os.getenv('MBA_COPILOT_MODEL','gpt-4.1-mini'),input=f'You are a general GPT assistant, not course-grounded. Subject: {subject or "MBA"}. Answer clearly. Question: {q}');return r.output_text,None
 except Exception as e:
  msg=str(e)
  if 'insufficient_quota' in msg or 'credit_balance_exhausted' in msg or '429' in msg:return None,'OpenAI API credits are exhausted. The course-grounded MBA Copilot can still work using indexed MBA material, but Ask GPT and AI synthesis require available API credits.'
  return None,f'GPT request failed: {msg}'
def heuristic_answer(q,refs,concept):
 core={'fixed cost':'A fixed cost does not change with activity within the relevant range.','variable cost':'A variable cost changes with the level of activity.','contribution':'Contribution equals selling price minus variable cost per unit.','break-even':'Break-even is the activity level where contribution covers fixed costs and profit is zero.'}.get(concept,f"The supplied material contains evidence related to '{concept}'.")
 return f'''## 📖 Simple Meaning\n{core}\n\n## 📚 Course Evidence\n{refs[0]["text"][:900]}\n\n## 🧠 Memorize on Priority\n**Must Know:** {core}\n**High Priority:** Understand the distinction from related cost/concept terms.\n**Understand:** Be able to apply it to a business case.\n\n## 🎯 Exam Priority\nFocus first on the definition, distinction, formula where applicable, and worked case examples in the cited material.\n\n## ❓ Likely Exam Questions\n1. Define {concept}.\n2. Differentiate {concept} from a related concept.\n3. Apply {concept} to a business case.\n4. Explain or calculate the relevant metric using supplied case data.\n\n## 🏢 Real Business Use\nGeneral business application; this section is not claimed as a direct quote from the course material.\n\n## ⚠️ Common Confusion\nDo not treat every number in a retrieved case as evidence about the concept. Use only the figures and statements directly connected to the question.\n\n## ⚡ 30-Second Revision\n{core}\n\n[[SOURCE 1]]'''
def answer(q,subject=None,mode='Teach Me'):
 concept,_=detect_concept(q);items=retrieve(q,subject);refs=[ref(x,i) for i,x in enumerate(items)]
 if not refs:return {'answer':'I could not find sufficiently relevant evidence in the selected MBA material. No answer was generated from another subject. Try selecting the subject containing the topic or upload/index the relevant class material.','sources':[],'concept':concept,'grounded':False}
 key=os.getenv('OPENAI_API_KEY')
 if key:
  try:
   from openai import OpenAI;evidence='\n'.join(f"[SOURCE {i+1}] {r['document']} | {r['locator']} | {r['text']}" for i,r in enumerate(refs));prompt=f'''You are MBA Copilot. Answer ONLY from the supplied evidence and clearly distinguish general business application. Question: {q}. Subject: {subject or 'All Subjects'}. Mode: {mode}. Relevance is critical: use only sources that directly support the concept. Ignore unrelated case fragments, financial statements, tables and numbers. If evidence is insufficient say: "Not established in the supplied course material." Never invent course facts. Structure: 📖 Simple Meaning; 📚 Course Material; 💡 Relevant Example; 🧮 How It Works/Formula if relevant; 🧠 Memorize on Priority with Must Know/High Priority/Understand; 🎯 Exam Priority; ❓ 4-6 likely exam questions; 🏢 Real Business Use (label general application if not course-derived); ⚠️ Common Confusion; ⚡ 30-Second Revision. Insert [[SOURCE N]] only when that source directly supports the sentence. Evidence:\n{evidence}''';r=OpenAI(api_key=key).responses.create(model=os.getenv('MBA_COPILOT_MODEL','gpt-4.1-mini'),input=prompt);return {'answer':r.output_text,'sources':refs,'concept':concept,'grounded':True}
  except Exception as e:
   if not any(x in str(e) for x in ('insufficient_quota','credit_balance_exhausted','429')):pass
 return {'answer':heuristic_answer(q,refs,concept),'sources':refs,'concept':concept,'grounded':True,'ai_synthesis':False}
def upload(body,ctype,token):
 expected=os.getenv('ADMIN_UPLOAD_TOKEN')
 if not expected or token!=expected:return {'error':'Upload authorization failed. Set ADMIN_UPLOAD_TOKEN on the server.'},403
 msg=email.message_from_bytes(b'Content-Type: '+ctype.encode()+b'\r\n\r\n'+body);fields={};files=[]
 for part in msg.walk():
  cd=part.get('Content-Disposition','')
  if 'form-data' not in cd:continue
  name=part.get_param('name',header='content-disposition');fn=part.get_filename();data=part.get_payload(decode=True) or b''
  if fn:files.append((fn,data))
  else:fields[name]=data.decode('utf-8','ignore')
 if not files:return {'error':'No file supplied.'},400
 subject=fields.get('subject','Unassigned');from ingest import ingest_path;results=[]
 for fn,data in files:
  with tempfile.NamedTemporaryFile(suffix=Path(fn).suffix,delete=False) as f:f.write(data);tmp=f.name
  try:results.extend(ingest_path(tmp,subject))
  finally:os.unlink(tmp)
 return {'ok':True,'subject':subject,'results':results},200
class Handler(BaseHTTPRequestHandler):
 def send_json(self,obj,status=200):
  b=json.dumps(obj,ensure_ascii=False).encode();self.send_response(status);self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Content-Length',str(len(b)));self.end_headers();self.wfile.write(b)
 def do_GET(self):
  path=urlparse(self.path).path
  if path=='/health':self.send_json({'ok':True,'database':db.enabled(),'chunks':db.count_passages() if db.enabled() else len(INDEX)});return
  if path=='/api/meta':self.send_json({'subjects':subjects(),'chunks':db.count_passages() if db.enabled() else len(INDEX),'ai_configured':bool(os.getenv('OPENAI_API_KEY')),'database_configured':db.enabled(),'upload_enabled':bool(os.getenv('ADMIN_UPLOAD_TOKEN'))});return
  if path.startswith('/api/source/'):
   item=SOURCE_CACHE.get(path.rsplit('/',1)[-1]);self.send_json(ref(item) if item else {'error':'Reference expired. Ask the question again.'},200 if item else 404);return
  if path in ('/','/index.html'):
   data=(BASE/'index.html').read_bytes();self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8');self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data);return
  self.send_response(404);self.end_headers()
 def do_POST(self):
  path=urlparse(self.path).path;n=int(self.headers.get('Content-Length',0));raw=self.rfile.read(n)
  if path=='/api/upload':out,status=upload(raw,self.headers.get('Content-Type',''),self.headers.get('X-Admin-Token',''));self.send_json(out,status);return
  try:body=json.loads(raw or b'{}')
  except Exception:self.send_json({'error':'Invalid JSON.'},400);return
  q=str(body.get('question','')).strip();subject=body.get('subject');mode=body.get('mode','Teach Me')
  if not q:self.send_json({'error':'Question is required.'},400);return
  if path=='/api/chat':
   result=answer(q,subject,mode);SOURCE_CACHE.clear()
   for s in result['sources']:SOURCE_CACHE[s['ref']]=s
   self.send_json(result);return
  if path=='/api/ask-gpt':
   text,err=ask_gpt(q,subject);self.send_json({'error':err},400) if err else self.send_json({'answer':text,'ai':True,'mode':'Ask GPT','grounded':False});return
  self.send_json({'error':'Not found'},404)
if __name__=='__main__':
 try:db.ensure_schema()
 except Exception as e:print('Database initialization warning:',e)
 port=int(os.getenv('PORT','8000'));print('MBA Copilot running on port',port);ThreadingHTTPServer(('0.0.0.0',port),Handler).serve_forever()
