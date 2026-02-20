#!/usr/bin/env python3
"""
Chunk-to-Database Loader

Loads chunker JSON output into source_document and source_fragment
PostgreSQL tables, bridging the gap between the chunker and the
knowledge graph parser.

Usage:
    python chunk_to_db.py <chunk_dir> --manifest <crawl_manifest.json>
    python chunk_to_db.py <chunk_dir> --manifest <manifest.json> --dry-run
"""

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional

import psycopg2
from psycopg2.extras import RealDictCursor

from build_kg.config import DB_CONFIG


def load_manifest(manifest_path: str) -> Dict[str, Any]:
    """
    Load crawl manifest for URL/authority mapping.

    Args:
        manifest_path: Path to crawl_manifest.json

    Returns:
        Manifest dictionary with sources and defaults
    """
    with open(manifest_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def match_source(filepath: str, sources: List[Dict]) -> Optional[Dict]:
    """
    Match a chunk file path to its source entry in the manifest.

    The chunker preserves directory structure from crawl_output/<source_name>/,
    so we match by checking if source_name appears in the file path.

    Args:
        filepath: Path to the chunk JSON file
        sources: List of source entries from the manifest

    Returns:
        Matching source dict, or None
    """
    filepath_str = str(filepath)
    for source in sources:
        source_name = source.get('source_name', '')
        if source_name and source_name in filepath_str:
            return source
    return None


def load_chunks(chunk_dir: str) -> Dict[str, List[Dict]]:
    """
    Walk chunk_dir, read each JSON chunk file, and group by source document.

    Groups are keyed by the original source filename from chunk metadata.

    Args:
        chunk_dir: Directory containing JSON chunk files

    Returns:
        Dictionary mapping source_filename -> list of chunk dicts (with filepath added)
    """
    chunks_by_doc = defaultdict(list)

    chunk_path = Path(chunk_dir)
    for json_file in sorted(chunk_path.rglob('*_chunk_*.json')):
        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                chunk_data = json.load(f)

            # Add the file path for source matching
            chunk_data['_filepath'] = str(json_file)

            # Group by original source filename
            metadata = chunk_data.get('metadata', {})
            source_filename = metadata.get('filename', '')
            if not source_filename:
                # Fall back to inferring from file path
                # Chunk files are named <original>_chunk_N.json
                name = json_file.stem
                # Remove _chunk_N suffix
                parts = name.rsplit('_chunk_', 1)
                source_filename = parts[0] if parts else name

            chunks_by_doc[source_filename].append(chunk_data)
        except (json.JSONDecodeError, IOError) as e:
            print(f"  Warning: Could not read {json_file}: {e}")

    # Sort chunks within each document by chunk_index
    for filename in chunks_by_doc:
        chunks_by_doc[filename].sort(
            key=lambda c: c.get('metadata', {}).get('chunk_index', 0)
        )

    return dict(chunks_by_doc)


def insert_document(cursor, doc_data: Dict[str, str]) -> Optional[str]:
    """
    Insert a source_document row.

    Uses ON CONFLICT (filepath) DO UPDATE to return the existing doc_id
    if the document was already loaded.

    Args:
        cursor: psycopg2 cursor
        doc_data: Document metadata dict

    Returns:
        doc_id (UUID string) or None on failure
    """
    query = """
    INSERT INTO source_document (
        jurisdiction, authority, doc_type, title, url, filepath, metadata, retrieved_at
    ) VALUES (
        %(jurisdiction)s, %(authority)s, %(doc_type)s,
        %(title)s, %(url)s, %(filepath)s, %(metadata)s, NOW()
    )
    ON CONFLICT (filepath) DO UPDATE SET updated_at = NOW()
    RETURNING doc_id;
    """

    cursor.execute(query, doc_data)
    result = cursor.fetchone()
    return str(result['doc_id']) if result else None


def insert_fragments(
    cursor,
    doc_id: str,
    chunks: List[Dict],
    doc_data: Dict[str, str]
) -> int:
    """
    Insert source_fragment rows for all chunks of a document.

    Populates context_before and context_after from adjacent chunks.

    Args:
        cursor: psycopg2 cursor
        doc_id: UUID of parent source_document
        chunks: List of chunk dicts sorted by chunk_index
        doc_data: Document metadata for jurisdiction/authority/doc_type

    Returns:
        Number of fragments inserted
    """
    query = """
    INSERT INTO source_fragment (
        doc_id, canonical_locator, excerpt,
        context_before, context_after,
        source_url, jurisdiction, authority, doc_type, metadata
    ) VALUES (
        %(doc_id)s, %(canonical_locator)s, %(excerpt)s,
        %(context_before)s, %(context_after)s,
        %(source_url)s, %(jurisdiction)s, %(authority)s, %(doc_type)s,
        %(metadata)s
    );
    """

    inserted = 0
    for i, chunk in enumerate(chunks):
        text = chunk.get('text', '').strip()
        if not text or len(text) < 10:
            continue

        metadata = chunk.get('metadata', {})

        # Build canonical locator from metadata
        locator = metadata.get('page_name', '')
        if not locator:
            filename = metadata.get('filename', 'unknown')
            chunk_idx = metadata.get('chunk_index', i + 1)
            locator = f"{filename}_chunk_{chunk_idx}"

        # Context from adjacent chunks
        context_before = None
        if i > 0:
            prev_text = chunks[i - 1].get('text', '')
            if prev_text:
                context_before = prev_text[-200:]

        context_after = None
        if i < len(chunks) - 1:
            next_text = chunks[i + 1].get('text', '')
            if next_text:
                context_after = next_text[:200]

        fragment_data = {
            'doc_id': doc_id,
            'canonical_locator': locator[:500],
            'excerpt': text,
            'context_before': context_before,
            'context_after': context_after,
            'source_url': doc_data.get('url', ''),
            'jurisdiction': doc_data.get('jurisdiction'),
            'authority': doc_data.get('authority'),
            'doc_type': doc_data.get('doc_type'),
            'metadata': doc_data.get('metadata'),
        }

        cursor.execute(query, fragment_data)
        inserted += 1

    return inserted


def main():
    parser = argparse.ArgumentParser(
        description='Load chunker JSON output into source_document and source_fragment tables',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python chunk_to_db.py ./chunk_output/ --manifest ./crawl_manifest.json
  python chunk_to_db.py ./chunk_output/ --manifest ./manifest.json --dry-run
        """
    )

    parser.add_argument(
        'chunk_dir',
        help='Directory containing JSON chunk files (output from chunker.py)'
    )
    parser.add_argument(
        '--manifest',
        required=True,
        help='Path to crawl_manifest.json with source metadata'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Preview what would be inserted without committing'
    )

    args = parser.parse_args()

    # Validate inputs
    chunk_dir = Path(args.chunk_dir)
    if not chunk_dir.exists() or not chunk_dir.is_dir():
        print(f"Error: Chunk directory '{chunk_dir}' does not exist")
        sys.exit(1)

    manifest_path = Path(args.manifest)
    if not manifest_path.exists():
        print(f"Error: Manifest file '{manifest_path}' does not exist")
        sys.exit(1)

    # Load manifest
    print("=" * 60)
    print("  Chunk-to-Database Loader")
    print("=" * 60)

    manifest = load_manifest(str(manifest_path))
    sources = manifest.get('sources', [])
    defaults = manifest.get('defaults', {})

    print(f"  Manifest: {manifest_path}")
    print(f"  Sources:  {len(sources)}")
    print(f"  Defaults: jurisdiction={defaults.get('jurisdiction')}, "
          f"authority={defaults.get('authority')}")
    print()

    # Load and group chunks
    print("Scanning chunk files...")
    chunks_by_doc = load_chunks(str(chunk_dir))
    total_chunks = sum(len(chunks) for chunks in chunks_by_doc.values())
    print(f"  Found {total_chunks} chunks across {len(chunks_by_doc)} documents")
    print()

    if not chunks_by_doc:
        print("No chunks found. Nothing to load.")
        sys.exit(0)

    if args.dry_run:
        print("[DRY RUN] Would insert:")
        for doc_name, chunks in chunks_by_doc.items():
            sample_path = chunks[0].get('_filepath', '')
            source = match_source(sample_path, sources)
            authority = source['authority'] if source else defaults.get('authority', 'UNKNOWN')
            jurisdiction = source['jurisdiction'] if source else defaults.get('jurisdiction', 'OTHER')
            valid_chunks = sum(1 for c in chunks if len(c.get('text', '').strip()) >= 10)
            print(f"  Document: {doc_name}")
            print(f"    Authority: {authority}, Jurisdiction: {jurisdiction}")
            print(f"    Fragments: {valid_chunks} (of {len(chunks)} chunks)")
        print(f"\n  Total: {len(chunks_by_doc)} documents, ~{total_chunks} fragments")
        print("\n[DRY RUN] No data was written.")
        sys.exit(0)

    # Connect to database
    print("Connecting to database...")
    conn = psycopg2.connect(**DB_CONFIG)
    cursor = conn.cursor(cursor_factory=RealDictCursor)

    stats = {
        'documents_inserted': 0,
        'documents_skipped': 0,
        'fragments_inserted': 0,
        'fragments_skipped': 0,
        'errors': 0,
    }

    # Process each document group
    for doc_name, chunks in chunks_by_doc.items():
        print(f"\nProcessing: {doc_name} ({len(chunks)} chunks)")

        try:
            # Match to manifest source
            sample_path = chunks[0].get('_filepath', '')
            source = match_source(sample_path, sources)

            if source:
                authority = source.get('authority')
                jurisdiction = source.get('jurisdiction')
                doc_type = source.get('doc_type', defaults.get('doc_type'))
                url = source.get('url', '')
                title = source.get('title', doc_name)
            else:
                authority = defaults.get('authority')
                jurisdiction = defaults.get('jurisdiction')
                doc_type = defaults.get('doc_type')
                url = ''
                title = doc_name
                print("  Warning: No manifest match, using defaults")

            # Build document data
            doc_data = {
                'jurisdiction': jurisdiction or None,
                'authority': authority or None,
                'doc_type': doc_type or None,
                'title': title,
                'url': url,
                'filepath': f"{chunk_dir}/{doc_name}",
                'metadata': json.dumps(manifest.get('metadata')) if manifest.get('metadata') else None,
            }

            # Insert document
            doc_id = insert_document(cursor, doc_data)
            if doc_id:
                stats['documents_inserted'] += 1
                print(f"  Document: {doc_id[:8]}... ({authority}, {jurisdiction})")
            else:
                stats['documents_skipped'] += 1
                print("  Document skipped (already exists)")
                continue

            # Insert fragments
            count = insert_fragments(cursor, doc_id, chunks, doc_data)
            stats['fragments_inserted'] += count
            print(f"  Fragments: {count} inserted")

            # Commit per document for safety
            conn.commit()

        except Exception as e:
            conn.rollback()
            stats['errors'] += 1
            print(f"  Error: {e}")

    cursor.close()
    conn.close()

    # Summary
    print()
    print("=" * 60)
    print("  LOAD COMPLETE")
    print("=" * 60)
    print(f"  Documents inserted:  {stats['documents_inserted']}")
    print(f"  Documents skipped:   {stats['documents_skipped']}")
    print(f"  Fragments inserted:  {stats['fragments_inserted']}")
    print(f"  Errors:              {stats['errors']}")
    print("=" * 60)


if __name__ == '__main__':
    main()
