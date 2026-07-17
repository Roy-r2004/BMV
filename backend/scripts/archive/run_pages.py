import sys
sys.path.insert(0, '.')
from app.infrastructure.db.session import SessionLocal
from app.infrastructure.ai_providers.factory import get_ai_provider
from app.infrastructure.templating.renderer import get_template_renderer
from app.application.pipelines.role_pages import generate_role_pages

print('Starting plan-driven UI generation for request #1...')
print('Step 1: Planner reads MVP blueprint and decides all roles + pages')
print('Step 2: Brand manifest for consistency')
print('Step 3: Builder + QA agents generate each page from the plan')
print('This takes 10-20 minutes depending on page count and model speed')
print()

db = SessionLocal()
try:
    result = generate_role_pages(db, 1, get_ai_provider(), get_template_renderer())
    roles = result.get('roles', [])
    total_pages = sum(len(r.get('pages', [])) for r in roles)
    print(f'Done! Generated {len(roles)} roles, {total_pages} pages total')
    for r in roles:
        pages = r.get('pages', [])
        print(f'  Role: {r.get("label")} -> {len(pages)} pages')
        for p in pages:
            html_len = len(p.get('html', ''))
            print(f'    - {p.get("title")}: {html_len:,} chars of HTML')
except Exception as e:
    print(f'ERROR: {e}')
    import traceback
    traceback.print_exc()
finally:
    db.close()
