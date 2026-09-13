import os,re,json,tempfile,email,secrets,http.cookies,time,base64
from pathlib import Path
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from urllib.parse import urlparse
import db
BASE=Path(__file__).resolve().parent; DATA=BASE/'data'; KNOWLEDGE=DATA/'knowledge.json'
INDEX=json.loads(KNOWLEDGE.read_text(encoding='utf-8')) if KNOWLEDGE.exists() else []
SOURCE_CACHE={}; ADMIN_SESSIONS={}; SESSION_TTL=8*60*60
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
 definition_markers={'fixed cost':['does not change','remain constant','constant regardless','within the relevant range','fixed costs are','fixed cost is'],'variable cost':['changes with','varies with','variable costs are','variable cost is','proportion to activity'],'contribution':['selling price minus','sales minus','variable cost','contribution margin'],'break-even':['break-even point','break even point','fixed costs','contribution per unit']}
 if concept in definition_markers:
  v+=sum(18 for m in definition_markers[concept] if m in tl)
  if any(x in tl for x in ['exhibit','bill of materials','source: casewriters']) and not any(m in tl for m in definition_markers[concept]):v-=16
 if concept in ('fixed cost','variable cost','contribution','break-even') and any(x in tl for x in ['total assets','total liabilities',"owners' equity",'balance sheet']):v-=22
 if any(x in tl for x in ['income statement','net income','sales revenue']) and concept in ('fixed cost','variable cost','contribution','break-even'):v-=10
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
  if score<2:continue
  key=(it.get('document') or it.get('filename'),it.get('locator'))
  if key in seen:continue
  seen.add(key);out.append(it)
  if len(out)>=limit:break
 return out
def retrieve(q,subject=None,limit=8):
 items=[]
 if db.enabled() and os.getenv('OPENAI_API_KEY'):
  try:
   from openai import OpenAI;v=OpenAI(api_key=os.environ['OPENAI_API_KEY']).embeddings.create(model='text-embedding-3-small',input=q).data[0].embedding;items=db.search_vector(v,subject,limit*4)
  except Exception:items=[]
 if not items and db.enabled():
  try:items=db.search_lexical(q,subject,limit*6)
  except Exception:items=[]
 if not items and is_all_subjects(subject) and db.enabled():
  try:items=db.search_lexical(q,None,limit*8)
  except Exception:items=[]
 if not items:items=INDEX
 return _rank(q,_filter_items(items,subject),limit)
def subjects():
 vals=db.subjects() if db.enabled() else []
 if not vals:vals=list(dict.fromkeys((x.get('subject') or x.get('course')) for x in INDEX if x.get('subject') or x.get('course')))
 vals=[x for x in vals if x];bykey={subject_key(x):x for x in vals};ordered=[]
 for p in PREFERRED:
  if subject_key(p) in bykey:ordered.append(bykey[subject_key(p)])
 ordered.extend(x for x in vals if subject_key(x) not in {subject_key(y) for y in ordered});return ordered
def ref(item,n):
 doc=item.get('document') or item.get('source') or item.get('filename') or 'Course material';loc=item.get('locator') or item.get('page') or item.get('slide') or item.get('sheet') or ''
 return {'ref':f'src_{n}','document':doc,'locator':loc,'text':norm(item.get('text') or item.get('content') or item.get('passage')),'type':'spreadsheet' if str(doc).lower().endswith(('.xls','.xlsx')) else 'document'}
def gpt_client():
 key=os.getenv('OPENAI_API_KEY')
 if not key:return None
 from openai import OpenAI
 return OpenAI(api_key=key)
def ask_gpt(q,subject=None):
 c=gpt_client()
 if not c:return None,'OpenAI API key is not configured on this server.'
 try:
  r=c.responses.create(model=os.getenv('MBA_COPILOT_MODEL','gpt-5.6-luna'),input=f'You are a general GPT assistant, not course-grounded. Subject: {subject or "MBA"}. Answer clearly. Question: {q}')
  return r.output_text,None
 except Exception as e:return None,gpt_error(e)
def gpt_error(e):
 msg=str(e)
 if any(x in msg for x in ('insufficient_quota','credit_balance_exhausted','429')):return 'OpenAI API credits/rate limits are exhausted. Ask GPT requires available OpenAI API capacity.'
 return f'GPT request failed: {msg}'
def ask_gpt_more(question,filename=None,filedata=None,search=True,ai_mode='hybrid',conversation=None):
 c=gpt_client()
 if not c:return None,'OpenAI API key is not configured on this server.'
 try:
  # The current UI embeds the selected mode instruction in the request. Detect it server-side too,
  # so Generative/Analytical/Hybrid behavior cannot silently fall back to a generic assistant.
  qlower=(question or '').lower()
  if 'generative ai mode' in qlower: ai_mode='generative'
  elif 'analytical ai mode' in qlower: ai_mode='analytical'
  elif 'hybrid mode' in qlower: ai_mode='hybrid'
  content=[]
  if question:content.append({'type':'input_text','text':question})
  uploaded=None
  if filename and filedata:
   ext=Path(filename).suffix.lower()
   if ext in ('.png','.jpg','.jpeg','.webp','.gif'):
    mime={'.png':'image/png','.jpg':'image/jpeg','.jpeg':'image/jpeg','.webp':'image/webp','.gif':'image/gif'}.get(ext,'image/png')
    content.append({'type':'input_image','image_url':f'data:{mime};base64,{base64.b64encode(filedata).decode("ascii")}'} )
   else:
    suffix=ext or '.bin'
    with tempfile.NamedTemporaryFile(suffix=suffix,delete=False) as f:f.write(filedata);tmp=f.name
    try:
     with open(tmp,'rb') as fh: uploaded=c.files.create(file=fh,purpose='user_data')
    finally: os.unlink(tmp)
    content.append({'type':'input_file','file_id':uploaded.id})
  if not content:return None,'Enter a question or upload a file/image.'
  mode_instructions={
   'analytical':'''You are ANALYTICAL AI. Your primary job is rigorous reasoning and analysis. Analyze data, calculate metrics, compare alternatives, identify assumptions, trends, risks, trade-offs and root causes, and finish with evidence-based conclusions and actionable recommendations. When numbers are available, calculate them rather than merely describing them. Show formulas, tables or structured comparisons when useful. Never invent missing data.''',
   'generative':'''You are GENERATIVE AI. Your primary job is to CREATE the requested output. Do not merely explain how to create it. If the user asks for an email, write the complete email. If they ask for a report, produce the report. If they ask for ideas, generate multiple concrete ideas. If they ask for a presentation, provide slide-by-slide content. If they ask to rewrite, return the rewritten version. If they ask for code, provide working code. If they ask for a business plan, strategy, proposal, assignment answer, script, table, framework or action plan, produce the actual finished deliverable. Follow the requested tone, audience, format and length. Be original, useful and specific. Do not respond with a generic explanation when the user is asking you to create something.''',
   'hybrid':'''You are HYBRID ANALYTICAL + GENERATIVE AI. First perform whatever analysis, reasoning, calculations or evidence assessment is needed; then CREATE the requested final output. Do not stop at analysis when the user asks for an artifact, recommendation, plan, draft, strategy, report, table, presentation or other deliverable.'''
  }
  system=mode_instructions.get(ai_mode,mode_instructions['hybrid'])+'''\n\nYou are the general Ask More assistant in MBA Copilot. You are not restricted to MBA course material. If web search is enabled, research current information when useful. If files/images are attached, inspect them carefully. Follow the user's explicit request and produce a useful finished answer.'''
  inp=[{'role':'system','content':system}]
  if conversation:
   for m in conversation[-30:]:
    role='assistant' if m.get('role')=='assistant' else 'user'
    inp.append({'role':role,'content':[{'type':'input_text','text':str(m.get('text',''))}]})
  inp.append({'role':'user','content':content})
  tools=[{'type':'web_search'}] if search else []
  r=c.responses.create(model=os.getenv('MBA_COPILOT_MODEL','gpt-5.6-luna'),input=inp,tools=tools)
  return r.output_text,None
 except Exception as e:return None,gpt_error(e)
def heuristic_answer(q,refs,concept):
 core={'fixed cost':'A fixed cost does not change with activity within the relevant range.','variable cost':'A variable cost changes with the level of activity.','contribution':'Contribution equals selling price minus variable cost per unit.','break-even':'Break-even is the activity level where contribution covers fixed costs and profit is zero.'}.get(concept,f"The supplied material contains evidence related to '{concept}'.")
 evidence=refs[0]['text'][:1200] if refs else 'Not established in the supplied course material.'
 return f'''## 📖 Simple Meaning\n{core}\n\n## 📚 Course Evidence\n{evidence}\n\n## 🧠 Memorize on Priority\n**Must Know:** {core}\n**High Priority:** Understand the distinction from related cost/concept terms.\n**Understand:** Be able to apply it to a business case.\n\n## 🎯 Exam Priority\nFocus first on the definition, distinction, formula where applicable, and worked case examples in the cited material.\n\n## ❓ Likely Exam Questions\n1. Define {concept}.\n2. Differentiate {concept} from a related concept.\n3. Apply {concept} to a business case.\n4. Explain or calculate the relevant metric using supplied case data.\n\n## 🏢 Real Business Use\nGeneral business application; this section is not claimed as a direct quote from the course material.\n\n## ⚠️ Common Confusion\nDo not treat every number in a retrieved case as evidence about the concept. Use only the figures and statements directly connected to the question.\n\n## ⚡ 30-Second Revision\n{core}\n\n[[SOURCE 1]]'''
def answer(q,subject=None,mode='Teach Me'):
 concept,_=detect_concept(q);items=retrieve(q,subject);refs=[ref(x,i) for i,x in enumerate(items)]
 if not refs:return {'answer':'I could not find sufficiently relevant evidence in the selected MBA material. No answer was generated from another subject. Try selecting the subject containing the topic or upload/index the relevant class material.','sources':[],'concept':concept,'grounded':False}
 key=os.getenv('OPENAI_API_KEY')
 if key:
  try:
   from openai import OpenAI;evidence='\n'.join(f"[SOURCE {i+1}] {r['document']} | {r['locator']} | {r['text']}" for i,r in enumerate(refs));prompt=f'''You are MBA Copilot. Answer ONLY from the supplied MBA course evidence. Question: {q}. Subject: {subject or 'All Subjects'}. Mode: {mode}. Relevance is the highest priority. For a definition question such as "what is X", use the clearest definitional/explanatory source first. Do NOT use a case table, financial statement, exhibit, bill of materials, or isolated number merely because it contains the words X. If the supplied passages do not directly establish the answer, say "Not established in the supplied course material." Never invent course facts. Do not combine unrelated passages to manufacture an answer. Structure: 📖 Simple Meaning; 📚 Course Material; 💡 Relevant Example; 🧮 How It Works/Formula if relevant; 🧠 Memorize on Priority with Must Know/High Priority/Understand; 🎯 Exam Priority; ❓ 4-6 likely exam questions; 🏢 Real Business Use (label general application if not course-derived); ⚠️ Common Confusion; ⚡ 30-Second Revision. Insert [[SOURCE N]] only when that source directly supports the sentence. Evidence:\n{evidence}''';r=OpenAI(api_key=os.getenv('OPENAI_API_KEY')).responses.create(model=os.getenv('MBA_COPILOT_MODEL','gpt-5.6-luna'),input=prompt);return {'answer':r.output_text,'sources':refs,'concept':concept,'grounded':True}
  except Exception:pass
 return {'answer':heuristic_answer(q,refs,concept),'sources':refs,'concept':concept,'grounded':True,'ai_synthesis':False}
def admin_users():
 raw=os.getenv('ADMIN_USERS','')
 try:
  data=json.loads(raw) if raw else {};return {str(k).strip().casefold():str(v) for k,v in data.items() if k and v}
 except Exception:return {}
def admin_login(email_addr,access_code):
 users=admin_users();e=norm(email_addr).casefold()
 if not e or e not in users or not secrets.compare_digest(str(access_code or ''),users[e]):return None
 token=secrets.token_urlsafe(32);ADMIN_SESSIONS[token]={'email':e,'expires':time.time()+SESSION_TTL};return token
def admin_session(headers):
 try:c=http.cookies.SimpleCookie();c.load(headers.get('Cookie',''));token=c.get('mba_admin_session').value if c.get('mba_admin_session') else ''
 except Exception:token=''
 s=ADMIN_SESSIONS.get(token)
 if not s:return None
 if s['expires']<time.time():ADMIN_SESSIONS.pop(token,None);return None
 s['expires']=time.time()+SESSION_TTL;return s
def upload(body,ctype,admin):
 if not admin:return {'error':'Admin authentication required.'},401
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
 return {'ok':True,'subject':subject,'uploaded_by':admin['email'],'results':results},200
class Handler(BaseHTTPRequestHandler):
 def send_json(self,obj,status=200,cookies=None):
  b=json.dumps(obj,ensure_ascii=False).encode();self.send_response(status);self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Content-Length',str(len(b)));self.send_header('Cache-Control','no-store')
  if cookies:
   for c in cookies:self.send_header('Set-Cookie',c)
  self.end_headers();self.wfile.write(b)
 def do_GET(self):
  path=urlparse(self.path).path
  if path=='/health':self.send_json({'ok':True,'database':db.enabled(),'chunks':db.count_passages() if db.enabled() else len(INDEX)});return
  if path=='/api/meta':self.send_json({'subjects':subjects(),'chunks':db.count_passages() if db.enabled() else len(INDEX),'ai_configured':bool(os.getenv('OPENAI_API_KEY')),'database_configured':db.enabled(),'admin_auth_configured':bool(admin_users())});return
  if path=='/api/admin/me':
   s=admin_session(self.headers);self.send_json({'authenticated':bool(s),'email':s.get('email') if s else None});return
  if path.startswith('/api/source/'):
   item=SOURCE_CACHE.get(path.rsplit('/',1)[-1]);self.send_json(ref(item) if item else {'error':'Reference expired. Ask the question again.'},200 if item else 404);return
  if path in ('/','/index.html'):
   data=(BASE/'index.html').read_bytes();self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8');self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data);return
  self.send_response(404);self.end_headers()
 def do_POST(self):
  path=urlparse(self.path).path;n=int(self.headers.get('Content-Length',0));raw=self.rfile.read(n)
  if path=='/api/admin/login':
   try:b=json.loads(raw or b'{}');token=admin_login(b.get('email',''),b.get('access_code',''))
   except Exception:token=None
   if not token:self.send_json({'error':'Invalid admin credentials or account not authorized.'},401);return
   cookie=f'mba_admin_session={token}; Path=/; HttpOnly; SameSite=Strict; Max-Age={SESSION_TTL}';self.send_json({'ok':True,'message':'Admin access granted.'},200,[cookie]);return
  if path=='/api/admin/logout':
   try:c=http.cookies.SimpleCookie();c.load(self.headers.get('Cookie',''));token=c.get('mba_admin_session').value if c.get('mba_admin_session') else '';ADMIN_SESSIONS.pop(token,None)
   except Exception:pass
   self.send_json({'ok':True},200,['mba_admin_session=; Path=/; HttpOnly; Max-Age=0']);return
  if path=='/api/upload':out,status=upload(raw,self.headers.get('Content-Type',''),admin_session(self.headers));self.send_json(out,status);return
  if path=='/api/ask-gpt-more':
   ctype=self.headers.get('Content-Type','');fields={};b={}
   if ctype.lower().startswith('multipart/form-data'):
    msg=email.message_from_bytes(b'Content-Type: '+ctype.encode()+b'\r\n\r\n'+raw);filedata=None;filename=None
    for part in msg.walk():
     cd=part.get('Content-Disposition','')
     if 'form-data' not in cd:continue
     name=part.get_param('name',header='content-disposition');fn=part.get_filename();data=part.get_payload(decode=True) or b''
     if fn and not filename:filename=fn;filedata=data
     elif not fn:fields[name]=data.decode('utf-8','ignore')
    try:conversation=json.loads(fields.get('conversation','[]'))
    except Exception:conversation=[]
    text,err=ask_gpt_more(fields.get('question','').strip(),filename,filedata,fields.get('search','true').lower()!='false',fields.get('ai_mode','hybrid'),conversation)
    selected_mode=fields.get('ai_mode','hybrid')
   else:
    try:b=json.loads(raw or b'{}')
    except Exception:self.send_json({'error':'Invalid JSON.'},400);return
    text,err=ask_gpt_more(str(b.get('question','')).strip(),None,None,bool(b.get('search',True)),str(b.get('ai_mode','hybrid')),b.get('conversation') or [])
    selected_mode=str(b.get('ai_mode','hybrid'))
   if err:self.send_json({'error':err},400)
   else:self.send_json({'answer':text,'ai':True,'mode':selected_mode,'grounded':False,'web_search':True})
   return
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