"""
SQLite 表结构定义

参考 clawdbot memory-schema.js
"""

# 创建表的 SQL 语句
SCHEMA_SQL = """
-- 元数据表
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- 文件跟踪表
CREATE TABLE IF NOT EXISTS files (
    path TEXT PRIMARY KEY,
    hash TEXT NOT NULL,
    mtime INTEGER NOT NULL,
    size INTEGER NOT NULL
);

-- 文档分块表
CREATE TABLE IF NOT EXISTS chunks (
    id TEXT PRIMARY KEY,
    path TEXT NOT NULL,
    start_line INTEGER NOT NULL,
    end_line INTEGER NOT NULL,
    hash TEXT NOT NULL,
    model TEXT NOT NULL,
    text TEXT NOT NULL,
    embedding TEXT NOT NULL,
    updated_at INTEGER NOT NULL
);

-- 创建索引
CREATE INDEX IF NOT EXISTS idx_chunks_path ON chunks(path);
CREATE INDEX IF NOT EXISTS idx_chunks_model ON chunks(model);

-- 全文搜索表 (FTS5)
CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
    text,
    id UNINDEXED,
    path UNINDEXED,
    model UNINDEXED,
    start_line UNINDEXED,
    end_line UNINDEXED,
    tokenize='unicode61'
);

-- 嵌入缓存表
CREATE TABLE IF NOT EXISTS embedding_cache (
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    text_hash TEXT NOT NULL,
    embedding TEXT NOT NULL,
    dims INTEGER,
    updated_at INTEGER NOT NULL,
    PRIMARY KEY (provider, model, text_hash)
);
"""

# 插入/更新语句
INSERT_FILE_SQL = """
INSERT OR REPLACE INTO files (path, hash, mtime, size)
VALUES (?, ?, ?, ?)
"""

INSERT_CHUNK_SQL = """
INSERT OR REPLACE INTO chunks (id, path, start_line, end_line, hash, model, text, embedding, updated_at)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
"""

INSERT_FTS_SQL = """
INSERT INTO chunks_fts (text, id, path, model, start_line, end_line)
VALUES (?, ?, ?, ?, ?, ?)
"""

INSERT_EMBEDDING_CACHE_SQL = """
INSERT OR REPLACE INTO embedding_cache (provider, model, text_hash, embedding, dims, updated_at)
VALUES (?, ?, ?, ?, ?, ?)
"""

# 查询语句
SELECT_FILE_SQL = """
SELECT path, hash, mtime, size FROM files WHERE path = ?
"""

SELECT_CHUNKS_BY_PATH_SQL = """
SELECT id, path, start_line, end_line, hash, model, text, embedding, updated_at
FROM chunks WHERE path = ?
"""

SELECT_ALL_CHUNKS_SQL = """
SELECT id, path, start_line, end_line, hash, model, text, embedding, updated_at
FROM chunks WHERE model = ?
"""

SELECT_EMBEDDING_CACHE_SQL = """
SELECT embedding, dims FROM embedding_cache
WHERE provider = ? AND model = ? AND text_hash = ?
"""

# FTS5 搜索
SEARCH_FTS_SQL = """
SELECT id, path, start_line, end_line, text, bm25(chunks_fts) AS rank
FROM chunks_fts
WHERE chunks_fts MATCH ? AND model = ?
ORDER BY rank ASC
LIMIT ?
"""

# 删除语句
DELETE_CHUNKS_BY_PATH_SQL = """
DELETE FROM chunks WHERE path = ?
"""

DELETE_FTS_BY_PATH_SQL = """
DELETE FROM chunks_fts WHERE path = ?
"""

DELETE_FILE_SQL = """
DELETE FROM files WHERE path = ?
"""
