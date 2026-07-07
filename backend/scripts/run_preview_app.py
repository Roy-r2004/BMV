import sys

sys.path.insert(0, '.')
from app.infrastructure.db.session import SessionLocal
from app.infrastructure.ai_providers.factory import get_ai_provider
from app.infrastructure.templating.renderer import get_template_renderer
from app.application.preview_app import generate_preview_app

print('Starting React preview app generation for request #1...')
print('Steps: plan -> architect -> codegen -> build -> fix loop')
print('This takes 10-20 minutes depending on file count and model speed')
print()

db = SessionLocal()
try:
    result = generate_preview_app(db, 1, get_ai_provider(), get_template_renderer())
    app = result.get('preview_app', {})
    print(f'Done! Status: {app.get("status")}')
    print(f'URL: {app.get("url")}')
    print(f'Roles: {len(app.get("roles", []))}')
    print(f'Routes: {len(app.get("routes", []))}')
except Exception as e:
    print(f'ERROR: {e}')
    import traceback
    traceback.print_exc()
finally:
    db.close()
