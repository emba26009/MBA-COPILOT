import os,re
import psycopg2
from psycopg2.extras import RealDictCursor
SCHEMA='''CREATE EXTENSION IF NOT EXISTS vector; CREATE TABLE IF NOT EXISTS documents (id BIGSERIAL PRIMARY KEY, filename TEXT NOT NULL, subject TEXT NOT NULL, file_type TEXT, created_at TIMESTAMPTZ DEFAULT NOW()); CREATE TABLE IF NOT EXISTS passages (id BIGSERIAL PRIMARY KEY, document_id BIGINT REFERENCES documents(id) ON DELETE CASCADE, locator TEXT, text TEXT NOT NULL, embedding vector(1536), created_at TIMESTAMPTZ DEFAULT NOW()); CREATE INDEX IF NOT EXISTS passages_document_idx ON passages(document_id); CREATE INDEX IF NOT EXISTS documents_subject_idx ON documents(subject);'''
def enabled(): return bool(os.getenv('DATABASE_URL'))
def conn(): return psycopg2.connect(os.environ['DATABASE_URL'])
def ensure_schema():
    if not enabled(): return False
    with conn() as c:
        with c.cursor() as cur: cur.execute(SCHEMA)
    return True
def normalize_subject(s): return re.sub(r'\s+',' ',str(s or '')).strip().casefold().replace('–','-').replace('—','-')
def subject_aliases(subject):
    s=normalize_subject(subject);groups=[['financial reporting and management accounting','frma','financial reporting & management accounting'],['business statistics for managers','business statistics','statistics for managers'],['behaviour in organizations','behavior in organizations','organizational behaviour','organizational behavior'],['digital transformation','dt'],['operations management','om'],['artificial intelligence for business','ai for business','aib'],['action lab: systems thinking for problem solving','systems thinking for problem solving'],['managerial economics and macroeconomic environment','managerial economics','macroeconomics'],['marketing management-i: marketing management using ai','marketing management using ai','marketing management'],['supply chain management','scm']]
    for g in groups:
        vals={normalize_subject(x) for x in g}
        if s in vals:return sorted(vals)
    return [s]
def subjects():
    if not enabled():return []
    with conn() as c:
        with c.cursor() as cur:cur.execute("SELECT DISTINCT subject FROM documents WHERE TRIM(subject)<>'' ORDER BY subject");return [r[0] for r in cur.fetchall()]
def count_passages():
    if not enabled():return 0
    with conn() as c:
        with c.cursor() as cur:cur.execute('SELECT COUNT(*) FROM passages');return cur.fetchone()[0]
def subject_counts():
    if not enabled():return []
    with conn() as c:
        with c.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute('SELECT d.subject,COUNT(DISTINCT d.id) documents,COUNT(p.id) passages,COUNT(p.embedding) embeddings FROM documents d LEFT JOIN passages p ON p.document_id=d.id GROUP BY d.subject ORDER BY d.subject');return [dict(r) for r in cur.fetchall()]
def _subject_clause(subject,params):
    if not subject or normalize_subject(subject) in ('all subjects','all'):return ''
    params.append(subject_aliases(subject));return " AND LOWER(REPLACE(REPLACE(TRIM(d.subject),'–','-'),'—','-')) = ANY(%s)"
def _lexical_once(q,subject,limit,exact_phrases=None):
    words=[w for w in re.findall(r"[a-zA-Z0-9][a-zA-Z0-9'-]+",q.lower()) if len(w)>2]
    phrases=[normalize_subject(q)] if len(words)>=2 else []
    phrases += [normalize_subject(x) for x in (exact_phrases or []) if normalize_subject(x)]
    phrases=list(dict.fromkeys(phrases))
    if not words and not phrases:return []
    clauses=[];params=[]
    for ph in phrases: clauses.append('p.text ILIKE %s');params.append('%'+ph+'%')
    clauses += ['p.text ILIKE %s']*len(words[:16]);params += ['%'+w+'%' for w in words[:16]]
    filt=_subject_clause(subject,params)
    order='CASE '+''.join(f" WHEN p.text ILIKE %s THEN {i} " for i,_ in enumerate(phrases))+' ELSE 99 END, p.id DESC'
    params += ['%'+ph+'%' for ph in phrases]
    params.append(limit)
    sql=f"SELECT p.id,d.filename AS document,d.subject,p.locator,p.text FROM passages p JOIN documents d ON d.id=p.document_id WHERE ({' OR '.join(clauses)}){filt} ORDER BY {order} LIMIT %s"
    with conn() as c:
        with c.cursor(cursor_factory=RealDictCursor) as cur:cur.execute(sql,params);return [dict(r) for r in cur.fetchall()]

def search_lexical(q,subject=None,limit=14):
    if not enabled():return []
    l=q.casefold();exact=[]
    if 'fixed cost' in l or 'fixed costs' in l:exact=['fixed cost','fixed costs','relevant range','shut down costs','fixed costs cannot be avoided']
    elif 'variable cost' in l or 'variable costs' in l:exact=['variable cost','variable costs']
    elif 'contribution' in l:exact=['contribution margin','contribution','selling price','variable cost']
    elif 'break-even' in l or 'break even' in l:exact=['break-even','break even','contribution','fixed cost']
    elif 'vrio' in l:exact=['VRIO','valuable','rare','inimitable']
    elif 'social psychology' in l:exact=['social psychology','social behavior','social behaviour','group behavior','group behaviour','social influence','interpersonal','group dynamics','perception','attitudes']
    elif 'group behavior' in l or 'group behaviour' in l:exact=['group behavior','group behaviour','group dynamics','roles','norms','cohesiveness','social loafing']
    elif 'personality' in l:exact=['personality','individual differences','traits','situation','behavior']
    elif 'perception' in l:exact=['perception','selective perception','halo effect','stereotyping','projection','attribution']
    elif 'attitude' in l or 'attitudes' in l:exact=['attitude','attitudes','job satisfaction','organizational commitment','perceived organizational support']
    if exact:
        rows=_lexical_once(' '.join(exact[:2]),subject,limit,exact_phrases=exact)
        if rows:return rows
        rows=_lexical_once(q,subject,limit,exact_phrases=exact)
        if rows:return rows
    return _lexical_once(q,subject,limit,exact_phrases=exact)
def add_document(filename,subject,file_type,passages):
    with conn() as c:
        with c.cursor() as cur:
            cur.execute('INSERT INTO documents(filename,subject,file_type) VALUES(%s,%s,%s) RETURNING id',(filename,subject,file_type));did=cur.fetchone()[0]
            for locator,text in passages:cur.execute('INSERT INTO passages(document_id,locator,text) VALUES(%s,%s,%s)',(did,locator,text))
            return did
def store_embeddings(document_id,vectors):
    with conn() as c:
        with c.cursor() as cur:
            cur.execute('SELECT id FROM passages WHERE document_id=%s ORDER BY id',(document_id,));ids=[r[0] for r in cur.fetchall()]
            for pid,v in zip(ids,vectors):cur.execute('UPDATE passages SET embedding=%s WHERE id=%s',(str(v),pid))
def search_vector(vector,subject=None,limit=10):
    if not enabled():return []
    params=[str(vector)];filt=_subject_clause(subject,params);params.extend([str(vector),limit])
    sql=f'''SELECT p.id,d.filename AS document,d.subject,p.locator,p.text,1-(p.embedding <=> %s::vector) AS similarity FROM passages p JOIN documents d ON d.id=p.document_id WHERE p.embedding IS NOT NULL{filt} ORDER BY p.embedding <=> %s::vector LIMIT %s'''
    with conn() as c:
        with c.cursor(cursor_factory=RealDictCursor) as cur:cur.execute(sql,params);return [dict(r) for r in cur.fetchall()]
