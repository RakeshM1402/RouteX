import sqlite3
from pathlib import Path

conn = sqlite3.connect(r'C:\Users\Rakesh M\Desktop\SLOT ABCD\Slot A\Capstone\final dataset\routex_olap.db')
cur = conn.cursor()
cur.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name NOT LIKE 'cube_%' ORDER BY name")
out = []
for r in cur.fetchall():
    if r[0]:
        out.append(r[0] + ';\n')
Path(r'C:\Users\Rakesh M\Desktop\SLOT ABCD\Slot A\Capstone\schema_star.sql').write_text('\n'.join(out), encoding='utf-8')
print('done')
conn.close()
