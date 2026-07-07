import json

from app.infrastructure.db.session import SessionLocal
from app.domain.models.request import Request

db = SessionLocal()
req = db.query(Request).filter(Request.id == 1).first()
pages = json.loads(req.generated_pages)
# Save each page to a file to inspect
for role in pages['roles']:
    for page in role['pages']:
        fname = f"page_{page['id']}.html"
        with open(fname, "w", encoding="utf-8") as f:
            f.write(page['html'])
        print(f"Saved {fname} ({len(page['html'])} chars)")
db.close()
