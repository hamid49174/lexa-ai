# Database Guide — Lexa AI (SQLite)

## Database Location
`lexa-ai/lexa_memory.db`

## Schema Overview

### Core Tables
- **notes** — User notes (title, content, category, timestamps)
- **memories** — AI memories (content, category, importance, timestamps)
- **conversations** — Chat sessions (title, messages JSON, timestamps)
- **session_state** — Key-value session persistence
- **clipboard_entries** — Clipboard history

### Productivity Tables
- **todos** — Tasks (title, description, priority, status, category, due_date)
- **pomodoro_sessions** — Pomodoro history (task, duration, completed_at)
- **habits** — Habit definitions (name, description, frequency, target)
- **habit_logs** — Habit tracking entries
- **time_entries** — Time tracking records

### Search Tables (FTS5)
- **notes_fts** — Full-text search index for notes
- **memories_fts** — Full-text search index for memories

### System Tables
- **timers** — Scheduled timers (fire_at, message, acknowledged)

## Best Practices

### 1. Always Use Parameterized Queries
```python
# Bad: SQL injection risk
cursor.execute(f"SELECT * FROM notes WHERE id = {note_id}")

# Good: parameterized
cursor.execute("SELECT * FROM notes WHERE id = ?", (note_id,))
```

### 2. Add Indexes on Queried Columns
```python
cursor.execute("CREATE INDEX IF NOT EXISTS idx_todos_status ON todos(status)")
cursor.execute("CREATE INDEX IF NOT EXISTS idx_notes_category ON notes(category)")
```

### 3. Use Transactions for Multi-Step Operations
```python
conn = sqlite3.connect("lexa_memory.db")
try:
    conn.execute("BEGIN")
    conn.execute("INSERT INTO ...", (...))
    conn.execute("UPDATE ...", (...))
    conn.commit()
except Exception:
    conn.rollback()
    raise
```

### 4. Limit List Queries
```python
# Always limit results
cursor.execute("SELECT * FROM notes ORDER BY created_at DESC LIMIT 50")
```

### 5. FTS5 Search
```python
# Fast full-text search
cursor.execute(
    "SELECT rowid, title, content FROM notes_fts WHERE notes_fts MATCH ?",
    (query,)
)
```

## Backup & Restore

### Create Backup
```python
import sqlite3
src = sqlite3.connect("lexa_memory.db")
dst = sqlite3.connect("backup_2026-03-12.db")
src.backup(dst)
```

### Restore from Backup
```python
src = sqlite3.connect("backup_2026-03-12.db")
dst = sqlite3.connect("lexa_memory.db")
src.backup(dst)
```

### API Endpoints
- `POST /backup/create` — Create timestamped backup
- `GET /backup/list` — List available backups
- `POST /backup/restore-db` — Restore from backup file

## Maintenance

### Cleanup Old Data
```python
# Remove memories older than 90 days with low importance
cursor.execute("""
    DELETE FROM memories
    WHERE importance < 4
    AND created_at < datetime('now', '-90 days')
""")
```

### Vacuum
```sql
-- Reclaim disk space after large deletions
VACUUM;
```

### Integrity Check
```sql
PRAGMA integrity_check;
```
