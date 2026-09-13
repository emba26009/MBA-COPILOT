import os,re
import psycopg2
from psycopg2.extras import RealDictCursor

SCHEMA='''
CREATE EXTENSION IF NOT EXISTS vector;
CREATE TABLE IF NOT EXISTS documents (id BIGSERIAL PRIMARY KEY, filename TEXT NOT NULL, subject TEXT NOT NULL, file_type TEXT, created_at TIMESTAMPTZ DEFAULT NOW());
CREATE TABLE IF NOT EXISTS passages (id BIGSERIAL PRIMARY KEY, document_id BIGINT REFERENCES documents(id) ON DELETE CASCADE, locator TEXT, text TEXT NOT NULL, embedding vector(1536), created_at TIMESTAMPTZ DEFAULT NOW());
CREATE INDEX IF NOT EXISTS passages_document_idx ON passages(document_id);
CREATE INDEX IF NOT EXISTS documents_subject_idx ON documents(subject);
'''
def enabled(): return bool(os.getenv('DATABASE_URL'))
def conn(): return psycopg2.connect(os.environ['DATABASE_URL'])
def ensure_schema():
    if not enabled(): return False
    with conn() as c:
        with c.cursor() as cur: cur.execute(SCHEMA)
    return True
def normalize_subject(s):
    s=re.sub(r'\s+',' ',str(s or '')).strip().casefold()
    return s.replace('–','-').replace('—','-')
def subject_aliases(subject):
    s=normalize_subject(subject)
    aliases={s}
    groups=[
      (['financial reporting and management accounting','frma','financial reporting & management accounting'],),
      (['business statistics for managers','business statistics','statistics for managers'],),
      (['behaviour in organizations','behavior in organizations','organizational behaviour','organizational behavior'],),
      (['digital transformation','dt'],),
      (['operations management','om'],),
      (['artificial intelligence for business','ai for business','aib'],),
      (['action lab: systems thinking for problem solving','systems thinking for problem solving'],),
      (['managerial economics and macroeconomic environment','managerial economics','macroeconomics'],),
      (['marketing management–i: marketing management using ai','marketing management-i: marketing management using ai','marketing management using ai','marketing management'],),
      (['supply chain management','scm'],)
    ]
    for g in groups:
        vals={normalize_subject(x) for x in g[0]}
        if s in vals: return sorted(vals)
    return sorted(aliases)
def subjects():
    if not enabled(): return []
    with conn() as c:
        with c.cursor() as cur:
            cur.execute('SELECT DISTINCT subject FROM documents WHERE subject IS NOT NULL AND TRIM(subject)<>\'\' ORDER BY subject'); return [r[0] for r in cur.fetchall()]
def count_passages():
    if not enabled(): return 0
    with conn() as c:
        with c.cursor() as cur: cur.execute('SELECT COUNT(*) FROM passages'); return cur.fetchone()[0]
def _subject_clause(subject,params):
    if not subject or normalize_subject(subject) in ('all subjects','all'): return ''
    aliases=subject_aliases(subject);params.append(aliases)
    return " AND LOWER(REPLACE(REPLACE(TRIM(d.subject),'–','-'),'—','-')) = ANY(%s)"
def search_lexical(q,subject=None,limit=14):
    if not enabled(): return []
    words=[w for w in re.findall(r"[a-zA-Z0-9][a-zA-Z0-9'-]+",q.lower()) if len(w)>2]
    if not words:return []
    clauses=[];params=[]
    for w in words[:12]: clauses.append('p.text ILIKE %s');params.append('%'+w+'%')
    subject_sql=_subject_clause(subject,params);params.append(limit)
    sql=f'''SELECT p.id,d.filename AS document,d.subject,p.locator,p.text FROM passages p JOIN documents d ON d.id=p.document_id WHERE ({' OR '.join(clauses)}){subject_sql} ORDER BY p.id DESC LIMIT %s'''
    with conn() as c:
        with c.cursor(cursor_factory=RealDictCursor) as cur: cur.execute(sql,params);return [dict(r) for r in cur.fetchall()]
def add_document(filename,subject,file_type,passages):
    with conn() as c:
        with c.cursor() as cur:
            cur.execute('INSERT INTO documents(filename,subject,file_type) VALUES(%s,%s,%s) RETURNING id',(filename,subject,file_type));did=cur.fetchone()[0]
            for locator,text in passages: cur.execute('INSERT INTO passages(document_id,locator,text) VALUES(%s,%s,%s)',(did,locator,text))
            return did
def store_embeddings(document_id,vectors):
    with conn() as c:
        with c.cursor() as cur:
            for i,v in enumerate(vectors): cur.execute('UPDATE passages SET embedding=%s WHERE document_id=%s AND id=(SELECT id FROM passages WHERE document_id=%s ORDER BY id OFFSET %s LIMIT 1)',(str(v),document_id,document_id,i))
def search_vector(vector,subject=None,limit=10):
    if not enabled(): return []
    params=[str(vector)];filt=_subject_clause(subject,params);params.extend([str(vector),limit])
    sql=f'''SELECT p.id,d.filename AS document,d.subject,p.locator,p.text,1-(p.embedding <=> %s::vector) AS similarity FROM passages p JOIN documents d ON d.id=p.document_id WHERE p.embedding IS NOT NULL{filt} ORDER BY p.embedding <=> %s::vector LIMIT %s'''
    with conn() as c:
        with c.cursor(cursor_factory=RealDictCursor) as cur: cur.execute(sql,params);return [dict(r) for r in cur.fetchall()]
