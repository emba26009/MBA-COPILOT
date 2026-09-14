import html
import app
import case_retrieval
from admin_api import install

# Replace the legacy generic-word retrieval with case-aware + concept-aware retrieval.
app.detect_concept = case_retrieval.detect_concept
app.retrieve = case_retrieval.retrieve
app.heuristic_answer = case_retrieval.heuristic_answer

install(app.Handler)
_original_do_get = app.Handler.do_GET

# Serve a readable source-reference page for every result. The original ingestion
# stores passages in the knowledge database, so this opens the exact indexed passage
# and its page/slide locator rather than inventing an external URL.
def _patched_get(self):
    path = app.urlparse(self.path).path
    if path.startswith('/source/'):
        ref_id = path.rsplit('/', 1)[-1]
        item = app.SOURCE_CACHE.get(ref_id)
        if not item:
            body = '<!doctype html><html><body style="font-family:Arial;padding:40px"><h2>Reference expired</h2><p>Ask the question again and open the source from the new result.</p></body></html>'
        else:
            title = html.escape(str(item.get('document','Course material')))
            locator = html.escape(str(item.get('locator','')))
            subject = html.escape(str(item.get('subject','Unassigned')))
            text = html.escape(str(item.get('text','')))
            body = f'''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{title}</title><style>body{{font-family:Inter,Arial,sans-serif;background:#f5f7fb;color:#172033;margin:0}}main{{max-width:900px;margin:40px auto;padding:0 20px}}.card{{background:#fff;border:1px solid #e5e7eb;border-radius:16px;padding:24px}}.meta{{color:#667085;margin:8px 0 18px}}pre{{white-space:pre-wrap;line-height:1.7;font-family:inherit}}</style></head><body><main><div class="card"><h1>📄 {title}</h1><div class="meta">Subject: {subject} · {locator}</div><hr><pre>{text}</pre></div></main></body></html>'''
        data = body.encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type','text/html; charset=utf-8')
        self.send_header('Content-Length',str(len(data)))
        self.end_headers()
        self.wfile.write(data)
        return
    if path in ('/','/index.html'):
        # Serve the existing UI with a tiny runtime patch that turns returned sources
        # into clickable buttons. This avoids modifying the minified index.html.
        data = (app.BASE/'index.html').read_bytes()
        patch = b'''<style>.source-btn{border:0;background:#2563eb;color:#fff;border-radius:8px;padding:7px 10px;cursor:pointer;font-weight:700;white-space:nowrap}</style><script>(function(){const f=window.fetch;let refs=[];function p(){const box=document.getElementById('sources');if(!box)return;[...box.children].forEach((el,i)=>{if(el.querySelector('.source-btn')||!refs[i])return;const b=document.createElement('button');b.className='source-btn';b.textContent='📄 Open Source';b.onclick=()=>window.open('/source/'+encodeURIComponent(refs[i].ref),'_blank');el.appendChild(b)})}window.fetch=function(...a){return f(...a).then(r=>{if(String(a[0]).includes('/api/chat'))r.clone().json().then(d=>{refs=d.sources||[];setTimeout(p,0)}).catch(()=>{});return r})};new MutationObserver(p).observe(document.documentElement,{subtree:true,childList:true})})();</script>'''
        data = data.replace(b'</body>', patch+b'</body>')
        self.send_response(200)
        self.send_header('Content-Type','text/html; charset=utf-8')
        self.send_header('Content-Length',str(len(data)))
        self.end_headers()
        self.wfile.write(data)
        return
    _original_do_get(self)

app.Handler.do_GET = _patched_get

if __name__=='__main__':
    try: app.db.ensure_schema()
    except Exception as e: print('Database initialization warning:',e)
    port=int(app.os.getenv('PORT','8000'))
    print('MBA Copilot running on port',port)
    app.ThreadingHTTPServer(('0.0.0.0',port),app.Handler).serve_forever()
