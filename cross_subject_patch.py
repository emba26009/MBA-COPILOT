from pathlib import Path
import re
p = Path('app.py')
s = p.read_text(encoding='utf-8')

# Replace the retrieval function without depending on one exact generated line.
pat = re.compile(r"def retrieve\(q,subject=None,limit=8\):.*?(?=\ndef subjects\(\):)", re.S)
new_retrieve = '''def retrieve(q,subject=None,limit=8):
 # Cross-subject retrieval: the selected subject is context, never a hard boundary.
 items=[]
 if db.enabled() and os.getenv('OPENAI_API_KEY'):
  try:
   from openai import OpenAI;v=OpenAI(api_key=os.environ['OPENAI_API_KEY']).embeddings.create(model='text-embedding-3-small',input=q).data[0].embedding;items=db.search_vector(v,None,limit*6)
  except Exception:items=[]
 if not items and db.enabled():
  try:items=db.search_lexical(q,None,limit*10)
  except Exception:items=[]
 if not items:items=INDEX
 return _rank(q,_filter_items(items,None),limit)
'''
s,n = pat.subn(new_retrieve,s,count=1)
if n != 1:
    raise SystemExit('retrieve function not found')

# Add subject to each displayed source reference.
s = s.replace("return {'ref':f'src_{n}','document':doc,'locator':loc,'text':norm(item.get('text') or item.get('content') or item.get('passage')),'type':'spreadsheet' if str(doc).lower().endswith(('.xls','.xlsx')) else 'document'}", "return {'ref':f'src_{n}','document':doc,'subject':item.get('subject') or item.get('course') or 'Unassigned','locator':loc,'text':norm(item.get('text') or item.get('content') or item.get('passage')),'type':'spreadsheet' if str(doc).lower().endswith(('.xls','.xlsx')) else 'document'}")

# Make the grounded prompt explicitly use the entire MBA knowledge base.
s = s.replace('Answer ONLY from the supplied MBA course evidence.', 'Answer ONLY from the supplied MBA course evidence across ALL supplied MBA subjects. The selected subject is context, not a retrieval restriction.')
s = s.replace('If the supplied passages do not directly establish the answer, say "Not established in the supplied course material." Never invent course facts. Do not combine unrelated passages to manufacture an answer.', 'If the exact term is not explicitly defined but the supplied material contains clearly related concepts, explain the term using those related course concepts and explicitly say that the exact term is not directly defined. Do not pretend related evidence is a direct definition. Use evidence from any subject when the relationship is meaningful. If there is neither direct nor meaningful related evidence anywhere in the supplied MBA material, say "Not established in the supplied course material." Never invent course facts. Do not combine unrelated passages to manufacture an answer.')
s = s.replace("evidence='\\n'.join(f\"[SOURCE {i+1}] {r['document']} | {r['locator']} | {r['text']}\" for i,r in enumerate(refs))", "evidence='\\n'.join(f\"[SOURCE {i+1}] Subject: {r.get('subject','Unassigned')} | {r['document']} | {r['locator']} | {r['text']}\" for i,r in enumerate(refs))")
s = s.replace('I could not find sufficiently relevant evidence in the selected MBA material. No answer was generated from another subject. Try selecting the subject containing the topic or upload/index the relevant class material.', 'I could not find sufficiently relevant evidence in the MBA knowledge base across the supplied subjects. Try another wording or upload/index the relevant class material.')

p.write_text(s,encoding='utf-8')
print('cross-subject patch applied')
