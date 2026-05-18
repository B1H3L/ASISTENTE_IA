from db import get_connection
conn = get_connection()
cur = conn.cursor()

cur.execute("SELECT column_name, data_type FROM information_schema.columns WHERE table_name='alumno' ORDER BY ordinal_position")
print('=== alumno ===')
for r in cur.fetchall(): print(r)

cur.execute("SELECT column_name, data_type FROM information_schema.columns WHERE table_name='persona' ORDER BY ordinal_position")
print('=== persona ===')
for r in cur.fetchall(): print(r)

cur.execute("SELECT kcu.table_name, kcu.column_name, ccu.table_name, ccu.column_name FROM information_schema.key_column_usage kcu JOIN information_schema.referential_constraints rc ON kcu.constraint_name=rc.constraint_name JOIN information_schema.constraint_column_usage ccu ON rc.unique_constraint_name=ccu.constraint_name WHERE kcu.table_name IN ('alumno','persona')")
print('=== FKs ===')
for r in cur.fetchall(): print(r)

cur.close()
conn.close()
