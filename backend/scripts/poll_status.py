import sqlite3, time

for i in range(60):
    try:
        conn = sqlite3.connect('buildmyversion.db', timeout=3)
        rows = conn.execute(
            'SELECT id, concept_name, mvp_blueprint IS NOT NULL, visual_demo_json IS NOT NULL, generated_pages IS NOT NULL FROM requests'
        ).fetchall()
        conn.close()
        if rows:
            r = rows[0]
            blueprint = bool(r[2])
            demo = bool(r[3])
            pages = bool(r[4])
            concept = r[1] or '...'
            elapsed = i * 20
            print(f'[{elapsed}s] concept={concept} | blueprint={blueprint} | demo={demo} | pages={pages}', flush=True)
            if pages:
                print('PAGES READY - open http://localhost:5175/result/1', flush=True)
                break
        else:
            print(f'[{i*20}s] waiting for request to be created...', flush=True)
    except Exception as e:
        print(f'[{i*20}s] DB busy: {e}', flush=True)
    time.sleep(20)
