import os, json, zlib, base64
import db

FILENAME = "Uber - Applying Machine Learning to Improve the Customer Experience.pdf"
SUBJECT = "Digital Transformation"
_DATA = """REPLACE_ME"""

def seed_uber_case():
    if not db.enabled():
        return False, "DATABASE_URL not configured"
    db.ensure_schema()
    with db.conn() as c:
        with c.cursor() as cur:
            cur.execute("SELECT id FROM documents WHERE filename=%s AND subject=%s LIMIT 1", (FILENAME, SUBJECT))
            if cur.fetchone():
                return True, "Uber case already indexed"
    passages = json.loads(zlib.decompress(base64.b64decode(_DATA)).decode())
    did = db.add_document(FILENAME, SUBJECT, ".pdf", [(x[0], x[1]) for x in passages])
    embedded = 0
    if os.getenv("OPENAI_API_KEY"):
        try:
            from openai import OpenAI
            client=OpenAI(api_key=os.environ["OPENAI_API_KEY"]); vecs=[]
            for start in range(0,len(passages),64):
                r=client.embeddings.create(model="text-embedding-3-small", input=[x[1] for x in passages[start:start+64]])
                vecs.extend(x.embedding for x in r.data)
            db.store_embeddings(did, vecs); embedded=len(vecs)
        except Exception as e: print("Uber embedding warning:", e)
    return True, f"Indexed Uber case: {len(passages)} passages, {embedded} embeddings"
