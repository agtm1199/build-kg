-- build-kg: Database initialization
-- Runs automatically on first docker-compose up
--
-- Generic schema for any knowledge graph domain.
-- Columns like jurisdiction, authority, and doc_type are optional TEXT fields
-- that domain profiles can use as needed (e.g., regulatory profiles populate
-- jurisdiction with country codes; a generic topic leaves them NULL).

-- 1. Enable AGE extension
CREATE EXTENSION IF NOT EXISTS age;
LOAD 'age';
SET search_path = ag_catalog, "$user", public;

-- 2. Source document table
CREATE TABLE IF NOT EXISTS source_document (
    doc_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title TEXT NOT NULL,
    url TEXT NOT NULL,
    jurisdiction TEXT,           -- optional: country/region code, topic area, etc.
    authority TEXT,              -- optional: publishing organization
    publisher TEXT,
    doc_type TEXT,               -- optional: freeform document type
    canonical_citation TEXT,
    language TEXT NOT NULL DEFAULT 'en',
    retrieved_at TIMESTAMP WITH TIME ZONE,
    verified_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    display JSONB,
    citation JSONB,
    actions JSONB,
    metadata JSONB,             -- arbitrary key-value metadata
    filepath TEXT UNIQUE
);

-- 3. Source fragment table
CREATE TABLE IF NOT EXISTS source_fragment (
    fragment_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    doc_id UUID NOT NULL REFERENCES source_document(doc_id) ON DELETE CASCADE,
    canonical_locator TEXT,
    excerpt TEXT NOT NULL,
    context_before TEXT,
    context_after TEXT,
    anchor TEXT,
    source_url TEXT NOT NULL,
    jurisdiction TEXT,           -- inherited from parent document
    authority TEXT,              -- inherited from parent document
    doc_type TEXT,               -- inherited from parent document
    verified_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    display JSONB,
    citation JSONB,
    actions JSONB,
    metadata JSONB,             -- arbitrary key-value metadata
    json_s3_location TEXT
);

-- 4. Indexes
CREATE INDEX IF NOT EXISTS idx_sf_doc_id ON source_fragment(doc_id);
CREATE INDEX IF NOT EXISTS idx_sf_jurisdiction ON source_fragment(jurisdiction);
CREATE INDEX IF NOT EXISTS idx_sf_authority ON source_fragment(authority);
