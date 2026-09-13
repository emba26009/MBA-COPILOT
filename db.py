import os
import psycopg2
from psycopg2.extras import RealDictCursor

SCHEMA = '''
CREATE EXTENSION IF NOT EXISTS vector;
CREATE TABLE IF NOT EXISTS documents (
 id BIGSERIAL PRIMARY KEY,
 filename TEXT NOT NULL,
 subject TEXT NOT NULL,
 file_type TEXT,
 created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS passages (
 id BIGSERIAL PRIMARY KEY,
 document_id BIGINT REFERENCES documents(id) ON DELETE CASCADE,
 locator TEXT,
 text TEXT NOT NULL,
 embedding vector(1536),
 created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS passages_document_idx ON passages(document_id);
CREATE INDEX IF NOT EXISTS documents_subject_idx ON documents(subject);
'''

def enabled():
    return bool(os.getenv('DATABASE_URL'))

def conn():
    return psycopg2.connect(os.environ['DATABASE_URL'])

def ensure_schema():
    if not enabled(): return False
    with conn() as c:
        with c.cursor() as cur: cur.execute(SCHEMA)
    return True

def subjects():
    if not enabled(): return []
    ensure_schema()
    with conn() as c:
        with c.cursor() as cur:
            cur.execute('SELECT DISTINCT subject FROM documents ORDER BY subject')
            return [r[0] for r in cur.fetchall()]

def count_passages():
    if not enabled(): return 0
    ensure_schema()
    with conn() as c:
        with c.cursor() as cur:
            cur.execute('SELECT COUNT(*) FROM passages')
            return cur.fetchone()[0]

def search_lexical(q, subject=None, limit=14):
    if not enabled(): return []
    ensure_schema()
    words=[w for w in q.lower().split() if len(w)>2]
    if not words: return []
    clauses=[]; params=[]
    for w in words[:12]:
        clauses.append('p.text ILIKE %s'); params.append('%'+w+'%')
    where=' OR '.join(clauses)
    subject_sql=''
    if subject and subject.lower() not in ('all subjects','all'):
        subject_sql=' AND d.subject = %s'; params.append(subject)
    params.append(limit)
    sql=f'''SELECT p.id,d.filename AS document,d.subject,p.locator,p.text,
            (SELECT COUNT(*) FROM regexp_split_to_table(lower(p.text), E'\\s+') t WHERE t ILIKE ANY(%s)) AS hits
            FROM passages p JOIN documents d ON d.id=p.document_id
            WHERE ({where}) {subject_sql}
            ORDER BY hits DESC, p.id DESC LIMIT %s'''
    # The ANY parameter is a text array; fall back to simpler scoring if driver rejects it.
    try:
        with conn() as c:
            with c.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(sql,[words]+params); return [dict(r) for r in cur.fetchall()]
    except Exception:
        sql=f'''SELECT p.id,d.filename AS document,d.subject,p.locator,p.text
                FROM passages p JOIN documents d ON d.id=p.document_id
                WHERE ({where}) {subject_sql} LIMIT %s'''
        with conn() as c:
            with c.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(sql,params); return [dict(r) for r in cur.fetchall()]

def add_document(filename, subject, file_type, passages):
    ensure_schema()
    with conn() as c:
        with c.cursor() as cur:
            cur.execute('INSERT INTO documents(filename,subject,file_type) VALUES(%s,%s,%s) RETURNING id',(filename,subject,file_type))
            did=cur.fetchone()[0]
            for locator,text in passages:
                cur.execute('INSERT INTO passages(document_id,locator,text) VALUES(%s,%s,%s)',(did,locator,text))
            return did
