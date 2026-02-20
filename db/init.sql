-- build-kg: Database initialization
-- Runs automatically on first docker-compose up

-- 1. Enable AGE extension
CREATE EXTENSION IF NOT EXISTS age;
LOAD 'age';
SET search_path = ag_catalog, "$user", public;

-- 2. Create custom ENUM types
DO $$ BEGIN
    CREATE TYPE market_code AS ENUM (
        'CA', 'US', 'EU', 'UK', 'AU', 'NZ', 'JP',
        'SG', 'MY', 'TH', 'KR', 'CN', 'IN',
        'AE', 'SA', 'BR', 'MX', 'ZA', 'OTHER'
    );
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE TYPE doc_type AS ENUM (
        'regulation', 'standard', 'guidance', 'code',
        'act', 'directive', 'order'
    );
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

-- 3. Source document table
CREATE TABLE IF NOT EXISTS source_document (
    doc_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    jurisdiction market_code,
    authority TEXT,
    publisher TEXT,
    doc_type doc_type,
    title TEXT NOT NULL,
    canonical_citation TEXT,
    url TEXT NOT NULL,
    language TEXT NOT NULL DEFAULT 'en',
    retrieved_at TIMESTAMP WITH TIME ZONE,
    verified_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    display JSONB,
    citation JSONB,
    actions JSONB,
    metadata JSONB,
    filepath TEXT UNIQUE
);

-- 4. Source fragment table
CREATE TABLE IF NOT EXISTS source_fragment (
    fragment_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    doc_id UUID NOT NULL REFERENCES source_document(doc_id) ON DELETE CASCADE,
    canonical_locator TEXT,
    excerpt TEXT NOT NULL,
    context_before TEXT,
    context_after TEXT,
    anchor TEXT,
    source_url TEXT NOT NULL,
    jurisdiction market_code,
    authority TEXT,
    doc_type doc_type,
    verified_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    display JSONB,
    citation JSONB,
    actions JSONB,
    metadata JSONB,
    json_s3_location TEXT
);

-- 5. Indexes
CREATE INDEX IF NOT EXISTS idx_sf_doc_id ON source_fragment(doc_id);
CREATE INDEX IF NOT EXISTS idx_sf_jurisdiction ON source_fragment(jurisdiction);
CREATE INDEX IF NOT EXISTS idx_sf_authority ON source_fragment(authority);
