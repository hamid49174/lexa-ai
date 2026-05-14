# Performance Guide — Lexa AI

## Backend Performance

### SQLite Optimization
```sql
-- Add indexes on frequently queried columns
CREATE INDEX IF NOT EXISTS idx_notes_category ON notes(category);
CREATE INDEX IF NOT EXISTS idx_memories_importance ON memories(importance);
CREATE INDEX IF NOT EXISTS idx_todos_status ON todos(status);
CREATE INDEX IF NOT EXISTS idx_conversations_updated ON conversations(updated_at DESC);
```

**Rule of thumb:** If a column appears in WHERE or ORDER BY and the table will have >1000 rows, add an index.

### Async Operations
All blocking operations MUST use asyncio.to_thread():
```python
# Bad: blocks event loop
result = subprocess.run(cmd, capture_output=True)

# Good: runs in thread pool
result = await asyncio.to_thread(subprocess.run, cmd, capture_output=True)
```

### Rate Limiting
Per-endpoint limits prevent abuse:
| Endpoint | Limit | Window |
|----------|-------|--------|
| /chat | 30 | 1 minute |
| /companion/execute | 20 | 1 minute |
| /voice/* | 60 | 1 minute |

### FTS5 Full-Text Search
Use FTS5 virtual tables for fast text search:
```sql
CREATE VIRTUAL TABLE notes_fts USING fts5(title, content, content=notes, content_rowid=id);
```
With auto-sync triggers on INSERT/UPDATE/DELETE.

---

## Frontend Performance

### DOM Trimming
Chat messages are capped at 100 in the DOM. Older messages are removed:
```javascript
while (chatMessages.children.length > 100) {
    chatMessages.removeChild(chatMessages.firstChild);
}
```

### Parallel API Calls
Use Promise.allSettled() for independent API calls:
```javascript
const [todosRes, pomoRes, habitsRes, ttRes, focusRes] =
    await Promise.allSettled([
        window.lexa.todos(),
        window.lexa.pomodoroStatus(),
        window.lexa.habits(),
        window.lexa.timeTrackingStatus(),
        window.lexa.focusStatus()
    ]);
```

### Interval Cleanup
Clear intervals when switching views to prevent memory leaks:
```javascript
function switchView(view) {
    if (pomodoroInterval) clearInterval(pomodoroInterval);
    if (dashboardInterval) clearInterval(dashboardInterval);
    // ... switch to new view
}
```

### Debounced Refresh
Avoid rapid consecutive refreshes:
```javascript
let refreshTimeout;
function debouncedRefresh(fn, delay = 300) {
    clearTimeout(refreshTimeout);
    refreshTimeout = setTimeout(fn, delay);
}
```

### fetchWithTimeout
All preload bridge calls use 30s timeout:
```javascript
async function fetchWithTimeout(url, options = {}, timeout = 30000) {
    const controller = new AbortController();
    const id = setTimeout(() => controller.abort(), timeout);
    const response = await fetch(url, { ...options, signal: controller.signal });
    clearTimeout(id);
    return response;
}
```

---

## Quick Wins Checklist
- [ ] All SQLite tables have appropriate indexes
- [ ] All blocking operations use asyncio.to_thread()
- [ ] DOM trimming active for chat messages
- [ ] Parallel API calls in all multi-fetch views
- [ ] Intervals cleaned up on view switch
- [ ] FTS5 used for search (not LIKE '%query%')
- [ ] fetchWithTimeout on all bridge calls
