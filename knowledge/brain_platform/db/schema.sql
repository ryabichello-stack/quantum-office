-- Second Brain v1 store (SQLite). Postgres-compatible column names for later pgvector migration.
-- Security: every row carries tenant_id; search MUST filter in SQL.

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS meta (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS documents (
  id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL,
  title TEXT NOT NULL,
  type TEXT NOT NULL,
  visibility TEXT NOT NULL,
  acl_json TEXT NOT NULL DEFAULT '{}',
  classification_json TEXT NOT NULL DEFAULT '{}',
  publication_json TEXT NOT NULL DEFAULT '{}',
  channels_json TEXT NOT NULL DEFAULT '[]',
  ai_processing_json TEXT NOT NULL DEFAULT '{}',
  status TEXT NOT NULL DEFAULT 'active',
  version INTEGER NOT NULL DEFAULT 1,
  acl_revision INTEGER NOT NULL DEFAULT 1,
  source TEXT,
  project_id TEXT,
  body TEXT NOT NULL DEFAULT '',
  body_hash TEXT NOT NULL DEFAULT '',
  index_zone TEXT NOT NULL DEFAULT 'private', -- public | private | secret
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_documents_tenant ON documents(tenant_id);
CREATE INDEX IF NOT EXISTS idx_documents_zone ON documents(tenant_id, index_zone);
CREATE INDEX IF NOT EXISTS idx_documents_type ON documents(tenant_id, type);
CREATE INDEX IF NOT EXISTS idx_documents_project ON documents(tenant_id, project_id);

CREATE TABLE IF NOT EXISTS chunks (
  chunk_id TEXT PRIMARY KEY,
  document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  tenant_id TEXT NOT NULL,
  visibility TEXT NOT NULL,
  allowed_users_json TEXT NOT NULL DEFAULT '[]',
  allowed_groups_json TEXT NOT NULL DEFAULT '[]',
  allowed_services_json TEXT NOT NULL DEFAULT '[]',
  classification TEXT NOT NULL DEFAULT 'internal',
  acl_revision INTEGER NOT NULL,
  document_status TEXT NOT NULL,
  document_version INTEGER NOT NULL,
  index_zone TEXT NOT NULL DEFAULT 'private',
  channels_json TEXT NOT NULL DEFAULT '[]',
  ordinal INTEGER NOT NULL DEFAULT 0,
  text TEXT NOT NULL,
  embedding_json TEXT NOT NULL DEFAULT '[]'
);

CREATE INDEX IF NOT EXISTS idx_chunks_doc ON chunks(document_id);
CREATE INDEX IF NOT EXISTS idx_chunks_tenant ON chunks(tenant_id, index_zone);

CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
  chunk_id UNINDEXED,
  document_id UNINDEXED,
  tenant_id UNINDEXED,
  text,
  title,
  tokenize = 'unicode61'
);

CREATE TABLE IF NOT EXISTS contacts (
  id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL,
  display_name TEXT NOT NULL,
  emails_json TEXT NOT NULL DEFAULT '[]',
  phones_json TEXT NOT NULL DEFAULT '[]',
  title TEXT,
  company_name TEXT,
  company_entity_id TEXT,
  visibility TEXT NOT NULL DEFAULT 'company',
  acl_json TEXT NOT NULL DEFAULT '{}',
  classification_json TEXT NOT NULL DEFAULT '{"level":"confidential","contains_personal_data":true}',
  project_ids_json TEXT NOT NULL DEFAULT '[]',
  acl_revision INTEGER NOT NULL DEFAULT 1,
  status TEXT NOT NULL DEFAULT 'active',
  source TEXT,
  updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_contacts_tenant ON contacts(tenant_id);
CREATE INDEX IF NOT EXISTS idx_contacts_company ON contacts(tenant_id, company_name);

CREATE TABLE IF NOT EXISTS contact_emails (
  tenant_id TEXT NOT NULL,
  email TEXT NOT NULL,
  contact_id TEXT NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
  PRIMARY KEY (tenant_id, email)
);

CREATE TABLE IF NOT EXISTS threads (
  id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL,
  subject TEXT NOT NULL,
  channel TEXT NOT NULL,
  project_id TEXT,
  participant_ids_json TEXT NOT NULL DEFAULT '[]',
  message_ids_json TEXT NOT NULL DEFAULT '[]',
  last_message_at TEXT,
  visibility TEXT NOT NULL DEFAULT 'restricted',
  acl_json TEXT NOT NULL DEFAULT '{}',
  topics_json TEXT NOT NULL DEFAULT '[]',
  acl_revision INTEGER NOT NULL DEFAULT 1,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS emails (
  id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL,
  message_id TEXT NOT NULL,
  direction TEXT NOT NULL,
  thread_id TEXT NOT NULL,
  subject TEXT NOT NULL,
  from_email TEXT NOT NULL,
  to_emails_json TEXT NOT NULL DEFAULT '[]',
  cc_emails_json TEXT NOT NULL DEFAULT '[]',
  sent_at TEXT,
  project_id TEXT,
  visibility TEXT NOT NULL DEFAULT 'restricted',
  acl_json TEXT NOT NULL DEFAULT '{}',
  classification_json TEXT NOT NULL DEFAULT '{}',
  body_hash TEXT NOT NULL,
  body_text TEXT NOT NULL DEFAULT '',
  attachment_ids_json TEXT NOT NULL DEFAULT '[]',
  acl_revision INTEGER NOT NULL DEFAULT 1,
  status TEXT NOT NULL DEFAULT 'active',
  UNIQUE (tenant_id, message_id)
);

CREATE INDEX IF NOT EXISTS idx_emails_thread ON emails(tenant_id, thread_id);
CREATE INDEX IF NOT EXISTS idx_emails_from ON emails(tenant_id, from_email);

CREATE TABLE IF NOT EXISTS files (
  id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL,
  path TEXT NOT NULL,
  filename TEXT NOT NULL,
  content_hash TEXT NOT NULL,
  source TEXT NOT NULL,
  project_id TEXT,
  visibility TEXT NOT NULL DEFAULT 'company',
  acl_json TEXT NOT NULL DEFAULT '{}',
  classification_json TEXT NOT NULL DEFAULT '{}',
  text_excerpt TEXT NOT NULL DEFAULT '',
  acl_revision INTEGER NOT NULL DEFAULT 1,
  status TEXT NOT NULL DEFAULT 'active',
  updated_at TEXT NOT NULL,
  UNIQUE (tenant_id, path)
);

CREATE TABLE IF NOT EXISTS entities (
  id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL,
  kind TEXT NOT NULL,
  canonical_name TEXT NOT NULL,
  metadata_json TEXT NOT NULL DEFAULT '{}',
  visibility TEXT NOT NULL DEFAULT 'company',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS edges (
  id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL,
  source_entity_id TEXT NOT NULL,
  target_entity_id TEXT NOT NULL,
  relation_type TEXT NOT NULL,
  source_document_id TEXT,
  confidence REAL NOT NULL DEFAULT 1.0,
  review_status TEXT NOT NULL DEFAULT 'accepted',
  visibility TEXT NOT NULL DEFAULT 'company'
);

CREATE INDEX IF NOT EXISTS idx_edges_src ON edges(tenant_id, source_entity_id);
CREATE INDEX IF NOT EXISTS idx_edges_tgt ON edges(tenant_id, target_entity_id);

CREATE TABLE IF NOT EXISTS audit_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  principal_id TEXT NOT NULL,
  tenant_id TEXT NOT NULL,
  query_hash TEXT NOT NULL,
  query_preview_redacted TEXT NOT NULL,
  retrieved_doc_ids_json TEXT NOT NULL DEFAULT '[]',
  denied_doc_count INTEGER NOT NULL DEFAULT 0,
  purpose TEXT NOT NULL,
  request_id TEXT NOT NULL,
  timestamp TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ingest_state (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
