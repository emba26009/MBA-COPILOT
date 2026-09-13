import os,json,email
from pathlib import Path

def _admin(h):
    import app
    return app.admin_session(h.headers)
def _conn():
    import db
    return db.conn()
def _ensure():
    try:
        with _conn() as c:
            with c.cursor() as x:
                x.execute("ALTER TABLE documents ADD COLUMN IF NOT EXISTS uploaded_by TEXT")
                x.execute("ALTER TABLE documents ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW()")
    except Exception as e: print('Admin schema warning:',e)
def _docs():
    with _conn() as c:
        with c.cursor() as x:
            x.execute("""SELECT d.id,d.filename,d.subject,d.file_type,d.created_at,d.updated_at,d.uploaded_by,COUNT(p.id) passages
                        FROM documents d LEFT JOIN passages p ON p.document_id=d.id GROUP BY d.id ORDER BY d.created_at DESC""")
            return [dict(r) for r in x.fetchall()]
def _delete(i):
    with _conn() as c:
        with c.cursor() as x:
            x.execute('DELETE FROM documents WHERE id=%s RETURNING filename',(i,));r=x.fetchone();return r[0] if r else None
def _reindex(i):
    if not os.getenv('OPENAI_API_KEY'): return False,'OpenAI API key is not configured.'
    from openai import OpenAI
    with _conn() as c:
        with c.cursor() as x:x.execute('SELECT id,text FROM passages WHERE document_id=%s ORDER BY id',(i,));rows=x.fetchall()
    if not rows:return False,'No passages found for this document.'
    client=OpenAI(api_key=os.environ['OPENAI_API_KEY']);vecs=[]
    for n in range(0,len(rows),64):
        r=client.embeddings.create(model='text-embedding-3-small',input=[z[1] for z in rows[n:n+64]]);vecs.extend(z.embedding for z in r.data)
    with _conn() as c:
        with c.cursor() as x:
            for (pid,_),v in zip(rows,vecs):x.execute('UPDATE passages SET embedding=%s WHERE id=%s',(str(v),pid))
            x.execute('UPDATE documents SET updated_at=NOW() WHERE id=%s',(i,))
    return True,f'Re-indexed {len(rows)} passages.'
def _names(raw,ctype):
    try:
        m=email.message_from_bytes(b'Content-Type: '+ctype.encode()+b'\r\n\r\n'+raw)
        return [Path(p.get_filename()).name for p in m.walk() if p.get_filename()]
    except Exception:return []
def install(H):
    _ensure();oldg=H.do_GET;oldp=H.do_POST
    def get(s):
        p=s.path.split('?',1)[0]
        if p=='/api/admin/documents':
            if not _admin(s):return s.send_json({'error':'Admin authentication required.'},401)
            try:return s.send_json({'documents':_docs()})
            except Exception as e:return s.send_json({'error':str(e)},500)
        if p=='/api/admin/stats':
            if not _admin(s):return s.send_json({'error':'Admin authentication required.'},401)
            try:
                d=_docs();return s.send_json({'documents':len(d),'passages':sum(int(x['passages']) for x in d)})
            except Exception as e:return s.send_json({'error':str(e)},500)
        if p in ('/','/index.html'):
            try:
                h=(Path(__file__).parent/'index.html').read_text(encoding='utf-8');u=Path(__file__).parent/'admin_ui.js'
                if u.exists():h=h.replace('</body>','<script>'+u.read_text(encoding='utf-8')+'</script></body>')
                b=h.encode();s.send_response(200);s.send_header('Content-Type','text/html; charset=utf-8');s.send_header('Content-Length',str(len(b)));s.send_header('Cache-Control','no-store');s.end_headers();s.wfile.write(b);return
            except Exception:pass
        return oldg(s)
    def post(s):
        p=s.path.split('?',1)[0]
        if p=='/api/admin/documents/delete':
            if not _admin(s):return s.send_json({'error':'Admin authentication required.'},401)
            n=int(s.headers.get('Content-Length',0));b=json.loads(s.rfile.read(n) or b'{}');
            try:
                f=_delete(int(b['id']));return s.send_json({'ok':bool(f),'filename':f},200 if f else 404)
            except Exception as e:return s.send_json({'error':str(e)},500)
        if p=='/api/admin/documents/reindex':
            if not _admin(s):return s.send_json({'error':'Admin authentication required.'},401)
            n=int(s.headers.get('Content-Length',0));b=json.loads(s.rfile.read(n) or b'{}')
            try:
                ok,msg=_reindex(int(b['id']));return s.send_json({'ok':ok,'message':msg},200 if ok else 400)
            except Exception as e:return s.send_json({'error':str(e)},500)
        if p=='/api/upload':
            a=_admin(s)
            if not a:return s.send_json({'error':'Admin authentication required.'},401)
            n=int(s.headers.get('Content-Length',0));raw=s.rfile.read(n);ct=s.headers.get('Content-Type','');names=_names(raw,ct);sub=''
            try:
                m=email.message_from_bytes(b'Content-Type: '+ct.encode()+b'\r\n\r\n'+raw)
                for z in m.walk():
                    if z.get_param('name',header='content-disposition')=='subject' and not z.get_filename():sub=(z.get_payload(decode=True) or b'').decode()
                if sub and names:
                    with _conn() as c:
                        with c.cursor() as x:
                            for fn in names:x.execute('DELETE FROM documents WHERE filename=%s AND subject=%s',(fn,sub))
            except Exception:pass
            import app
            out,status=app.upload(raw,ct,a); 
            if status==200:
                try:
                    with _conn() as c:
                        with c.cursor() as x:
                            for fn in [z.get('filename') for z in out.get('results',[]) if z.get('filename')]:x.execute('UPDATE documents SET uploaded_by=%s,updated_at=NOW() WHERE filename=%s AND subject=%s',(a['email'],fn,sub))
                except Exception:pass
            return s.send_json(out,status)
        return oldp(s)
    H.do_GET=get;H.do_POST=post;return H
