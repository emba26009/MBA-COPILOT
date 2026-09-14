import os,re
import db

CASES={'uber':{'aliases':['uber','applying machine learning to improve the customer experience','uber applying machine learning','customer experience at uber'],'terms':['uber','machine learning','customer experience','customer','digital transformation']},'bigbasket':{'aliases':['bigbasket','customer analytics at bigbasket','product recommendations','bigbasket product recommendations'],'terms':['bigbasket','customer analytics','product recommendations','personalization','machine learning']},'el ordeno':{'aliases':['el ordeno','implementing blockchain','el ordeno implementing blockchain'],'terms':['el ordeno','blockchain','supply chain','trust']},'tata steel':{'aliases':['tata steel','digital transformation at tata steel'],'terms':['tata steel','digital transformation','industry 4.0','operations']},'peoplefirst':{'aliases':['peoplefirst','peoplefirst inc','a star employee but a terrible manager'],'terms':['peoplefirst','star employee','terrible manager','leadership','management']},'l.l. bean':{'aliases':['l.l. bean','ll bean','l.l. bean inc','item forecasting and inventory management'],'terms':['l.l. bean','forecasting','inventory management','demand forecasting']},'kristen cookie':{'aliases':["kristen's cookie","kristen’s cookie","kristen cookie","kristen_s cookie"],'terms':['kristen','cookie','process analysis','capacity','bottleneck']},'freemark abbey':{'aliases':['freemark abbey','freemark abbey winery'],'terms':['freemark abbey','winery','process analysis','capacity','bottleneck']},'akshaya patra':{'aliases':['akshaya patra','resource planning at akshaya patra'],'terms':['akshaya patra','resource planning','capacity planning','scheduling']},'abc shipyard':{'aliases':['abc shipyard','facility layout'],'terms':['abc shipyard','facility layout','process layout','capacity','flow']},'bill french':{'aliases':['bill french','bill french accountant'],'terms':['bill french','cost behavior','fixed costs','variable costs','contribution','break-even']},'seligram':{'aliases':['seligram'],'terms':['seligram','cost allocation','activity-based costing','overhead']},'classic pen':{'aliases':['classic pen','classic pen co','classic pen co developing an abc model'],'terms':['classic pen','activity-based costing','cost drivers','overhead allocation']},'revenue recognition hbp':{'aliases':['revenue recognition at hbp','hbp','revenue recognition'],'terms':['hbp','revenue recognition','accrual accounting','financial reporting']},'infosys':{'aliases':['infosys','infosys assessing earnings quality'],'terms':['infosys','earnings quality','financial statement analysis','accounting judgement']},'chemalite':{'aliases':['chemalite','chemalite inc'],'terms':['chemalite','cash flow','working capital','operating cash flow','investing cash flow','financing cash flow']},'marion boats':{'aliases':['marion boats','marion boats inc'],'terms':['marion boats','journal entries','balance sheet','income statement','cash flow statement']},'danshui':{'aliases':['danshui','danshui plant'],'terms':['danshui','cost behavior','fixed costs','variable costs','cost allocation']},'pitcher perfect':{'aliases':['pitcher perfect','visualizing interactive beer profiles'],'terms':['pitcher perfect','beer profiles','descriptive statistics','data visualization']},'how reliable is reliable':{'aliases':['how reliable is reliable'],'terms':['confidence intervals','statistical inference','sampling']},'agony of attrition':{'aliases':['agony of attrition'],'terms':['attrition','descriptive statistics','data analysis']},'crop residue management':{'aliases':['crop residue management','alternatives to crop residue burning in india'],'terms':['crop residue','hypothesis testing','data storytelling','data visualization']},'andalusian tempranillo':{'aliases':['andalusian tempranillo','tempranillo redwine'],'terms':['tempranillo','descriptive statistics','data visualization','analysis']},'dynamic capabilities':{'aliases':['dynamic capabilities'],'terms':['dynamic capabilities','competitive advantage','strategy']},'platr':{'aliases':["platr's eu expansion","platr’s eu expansion","platr"],'terms':['platr','digital business model','international expansion','platform strategy']},'social commerce':{'aliases':['social commerce','pinduoduo','instagram challenge alibaba'],'terms':['social commerce','platform strategy','network effects','digital business models']}}
QUESTION_WORDS=set('explain what how why describe discuss analyse analyze tell me give overview summarize summary case about of the a an is are was were can could would should please'.split())
CONCEPT_ALIASES={'machine learning':['machine learning','ml'],'customer experience':['customer experience','cx'],'digital transformation':['digital transformation','digital technologies'],'blockchain':['blockchain'],'forecasting':['forecast','forecasting','demand forecasting'],'inventory':['inventory','inventory management','eoq','safety stock','reorder point'],'capacity':['capacity','bottleneck','utilization','process capacity'],'fixed cost':['fixed cost','fixed costs'],'variable cost':['variable cost','variable costs'],'contribution':['contribution','contribution margin'],'break-even':['break-even','break even'],'activity-based costing':['activity-based costing','abc costing'],'revenue recognition':['revenue recognition'],'earnings quality':['earnings quality'],'cash flow':['cash flow','cash flows'],'working capital':['working capital'],'confidence interval':['confidence interval','confidence intervals'],'hypothesis testing':['hypothesis testing','null hypothesis','p-value'],'data visualization':['data visualization','visualization'],'data storytelling':['data storytelling'],'vrio':['vrio'],'five forces':['five forces','porter'],'competitive advantage':['competitive advantage'],'group decision making':['group decision making','group decision-making'],'personality':['personality'],'leadership':['leadership'],'negotiation':['negotiation']}
def norm(s):return re.sub(r'\s+',' ',str(s or '')).strip()
def detect_case(q):
 l=norm(q).casefold();matches=[]
 for name,meta in CASES.items():
  for alias in meta['aliases']:
   if alias.casefold() in l:matches.append((len(alias),name,meta))
 if not matches:return None
 matches.sort(reverse=True);return matches[0][1],matches[0][2]
def detect_concepts(q):
 l=norm(q).casefold();return [name for name,terms in CONCEPT_ALIASES.items() if any(t in l for t in terms)]
def detect_concept(q):
 concepts=detect_concepts(q)
 if concepts:return concepts[0],CONCEPT_ALIASES[concepts[0]]
 tokens=[x for x in re.findall(r"[a-zA-Z0-9][a-zA-Z0-9'-]+",q.casefold()) if x not in QUESTION_WORDS]
 return '',tokens[:8]
def _text(it):return norm(it.get('text') or it.get('content') or it.get('passage'))
def _doc(it):return norm(it.get('document') or it.get('filename') or it.get('source') or '')
def case_concept_score(q,it):
 text=_text(it).casefold();doc=_doc(it).casefold();score=0;case=detect_case(q);concepts=detect_concepts(q)
 if case:
  name,meta=case;aliases=[a.casefold() for a in meta['aliases']]
  if any(a in doc for a in aliases):score+=1000
  if name.casefold() in text:score+=150
  score+=sum(25 for t in meta['terms'] if t.casefold() in text)
  score+=sum(15 for a in aliases if a in text)
 for c in concepts:score+=sum(12 for t in CONCEPT_ALIASES[c] if t.casefold() in text)
 qtokens=set(re.findall(r"[a-zA-Z0-9][a-zA-Z0-9'-]+",q.casefold()))-QUESTION_WORDS;ttokens=set(re.findall(r"[a-zA-Z0-9][a-zA-Z0-9'-]+",text));score+=2*len(qtokens&ttokens)
 return score
def retrieve(q,subject=None,limit=8):
 case=detect_case(q);items=[]
 if db.enabled() and os.getenv('OPENAI_API_KEY'):
  try:
   from openai import OpenAI
   v=OpenAI(api_key=os.getenv('OPENAI_API_KEY')).embeddings.create(model='text-embedding-3-small',input=q).data[0].embedding;items=db.search_vector(v,None,limit*20)
  except Exception:items=[]
 if db.enabled():
  try:items=(items or [])+db.search_lexical(q,None,limit*30)
  except Exception:pass
 seen=set();candidates=[]
 for it in items:
  key=(_doc(it),it.get('locator'),_text(it)[:80])
  if key not in seen and _text(it):seen.add(key);candidates.append(it)
 if case:
  name,meta=case;aliases=[a.casefold() for a in meta['aliases']]
  exact=[x for x in candidates if any(a in _doc(x).casefold() for a in aliases)]
  # Never substitute an unrelated case. If the requested case is not indexed,
  # return no evidence rather than silently returning another case.
  if not exact:return []
  candidates=exact
 ranked=sorted(candidates,key=lambda x:case_concept_score(q,x),reverse=True)
 return [x for x in ranked[:limit] if case_concept_score(q,x)>0]
def heuristic_answer(q,refs,concept):
 case=detect_case(q);name=case[0] if case else '';title=name.title() if name else (concept or 'the requested topic')
 evidence='\n\n'.join(f"**{i+1}. {r.get('document','Course material')} — {r.get('locator','')}**\n{r.get('text','')[:1200]}" for i,r in enumerate(refs[:5])) or 'Not established in the supplied course material.'
 if case:
  return f'''## 📖 Case Overview\nThe question is about the **{title}** case. The answer below is grounded in the retrieved MBA course material.\n\n## 📚 Course Evidence\n{evidence}\n\n## 🧠 What to Remember\nFocus on the business problem, the approach used in the case, the relevant MBA concepts, and the evidence supporting the case conclusions.\n\n## 🎯 Exam Priority\nBe able to explain the case, connect it to the relevant course concept(s), and use the cited material to support your answer.\n\n## ⚠️ Grounding Note\nOnly the retrieved course evidence is treated as a course fact. General interpretation should be clearly separated from the source material.'''
 core={'fixed cost':'A fixed cost does not change with activity within the relevant range.','variable cost':'A variable cost changes with the level of activity.','contribution':'Contribution equals selling price minus variable cost per unit.','break-even':'Break-even is the activity level where contribution covers fixed costs and profit is zero.'}.get(concept,'The supplied material contains relevant evidence for this question.')
 return f'''## 📖 Simple Meaning\n{core}\n\n## 📚 Course Evidence\n{evidence}\n\n## 🧠 Memorize on Priority\n**Must Know:** {core}\n**High Priority:** Connect the concept to the cited MBA case or class material.\n**Understand:** Be able to apply it to a business case.\n\n## 🎯 Exam Priority\nFocus first on the definition, distinction, formula where applicable, and worked case examples in the cited material.\n\n## ⚡ 30-Second Revision\n{core}'''
