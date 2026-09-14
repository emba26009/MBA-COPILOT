import html
import app
import case_retrieval
from admin_api import install

# Replace the legacy generic-word retrieval with case-aware + concept-aware retrieval.
app.detect_concept = case_retrieval.detect_concept
app.retrieve = case_retrieval.retrieve
app.heuristic_answer = case_retrieval.heuristic_answer

install(app.Handler)

# The original index.html renders source rows as plain text. Inject a small UI patch
# at serve time so every source becomes an Open Source button without rewriting the
# existing single-line HTML file.
_original_do_get = app.Handler.do_GET

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
        # Let the original handler produce the page, but intercept its bytes so we can
        # inject the source-button behavior immediately before </body>.
        original_write = self.wfile.write
        captured = []
        def capture(data):
            captured.append(data)
        self.wfile.write = capture
        try:
            _original_do_get(self)
        finally:
            self.wfile.write = original_write
        if captured:
            data = b''.join(captured)
            patch = b'''<style>.source-btn{border:0;background:#2563eb;color:#fff;border-radius:8px;padding:7px 10px;cursor:pointer;font-weight:700}.src{display:flex;justify-content:space-between;align-items:center;gap:10px}</style><script>(function(){const oldFetch=window.fetch;const oldInner=Object.getOwnPropertyDescriptor(HTMLElement.prototype,'innerHTML').set;let refs=[];function patchSources(){const box=document.getElementById('sources');if(!box||!box.children.length)return;[...box.children].forEach((el,i)=>{if(el.querySelector('.source-btn'))return;const s=refs[i];if(!s)return;const b=document.createElement('button');b.className='source-btn';b.textContent='📄 Open Source';b.onclick=()=>window.open('/source/'+encodeURIComponent(s.ref),'_blank');el.appendChild(b)})}window.fetch=function(...args){return oldFetch(...args).then(r=>{if(String(args[0]).includes('/api/chat')){const c=r.clone();c.json().then(d=>{refs=d.sources||[];setTimeout(patchSources,0)}).catch(()=>{})}return r})};new MutationObserver(patchSources).observe(document.documentElement,{subtree:true,childList:true})})();</script>'''
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
