import app
from admin_api import install
install(app.Handler)
if __name__=='__main__':
    try: app.db.ensure_schema()
    except Exception as e: print('Database initialization warning:',e)
    port=int(app.os.getenv('PORT','8000'))
    print('MBA Copilot running on port',port)
    app.ThreadingHTTPServer(('0.0.0.0',port),app.Handler).serve_forever()
