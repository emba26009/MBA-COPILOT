import app
import case_retrieval
from admin_api import install

# Replace the legacy generic-word retrieval with case-aware + concept-aware retrieval.
app.detect_concept = case_retrieval.detect_concept
app.retrieve = case_retrieval.retrieve
app.heuristic_answer = case_retrieval.heuristic_answer

install(app.Handler)
if __name__=='__main__':
    try: app.db.ensure_schema()
    except Exception as e: print('Database initialization warning:',e)
    port=int(app.os.getenv('PORT','8000'))
    print('MBA Copilot running on port',port)
    app.ThreadingHTTPServer(('0.0.0.0',port),app.Handler).serve_forever()
