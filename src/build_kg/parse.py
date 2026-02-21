#!/usr/bin/env python3
"""
Knowledge Graph Parser
Reads text from PostgreSQL source_fragment table,
uses LLM (Anthropic or OpenAI) to extract structured ontology,
and loads into Apache AGE graph database.

Ontology-driven: requires an OntologyConfig defining node types,
edge types, and the expected JSON schema.
"""
import json
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
from psycopg2.extras import RealDictCursor

from build_kg.config import (
    AGE_GRAPH_NAME,
    BATCH_SIZE,
    DB_CONFIG,
    RATE_LIMIT_DELAY,
    validate_config,
)
from build_kg.domain import (
    OntologyConfig,
    build_prompt,
    load_ontology,
    load_profile,
    set_profile,
)
from build_kg.llm import chat_parse, create_client, get_provider_config


class KGParser:
    """Ontology-driven parser for knowledge graph data."""

    def __init__(self, ontology: OntologyConfig):
        """Initialize parser.

        Args:
            ontology: Ontology defining node types, edge types, and JSON schema.
        """
        validate_config()
        self.provider, api_key, self.model = get_provider_config()
        self.client = create_client(self.provider, api_key)
        self.db_conn = None
        self.graph_name = AGE_GRAPH_NAME
        self.ontology = ontology

        self.stats = {
            'processed': 0,
            'success': 0,
            'failed': 0,
            'skipped': 0,
            'start_time': None,
            'end_time': None,
        }

    def connect_db(self):
        """Establish database connection."""
        if not self.db_conn or self.db_conn.closed:
            self.db_conn = psycopg2.connect(**DB_CONFIG)
            self.db_conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
            cursor = self.db_conn.cursor()
            cursor.execute("LOAD 'age';")
            cursor.execute("SET search_path = ag_catalog, '$user', public;")
            cursor.close()

    def disconnect_db(self):
        """Close database connection."""
        if self.db_conn and not self.db_conn.closed:
            self.db_conn.close()

    def fetch_fragments(self, limit: Optional[int] = None, offset: int = 0, jurisdiction: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Fetch source fragments from database.

        Args:
            limit: Maximum number of fragments to fetch
            offset: Number of rows to skip
            jurisdiction: Filter by jurisdiction code (e.g., 'SG', 'CA')

        Returns:
            List of fragment dictionaries
        """
        self.connect_db()
        cursor = self.db_conn.cursor(cursor_factory=RealDictCursor)

        query = """
        SELECT
            sf.fragment_id,
            sf.doc_id,
            sf.canonical_locator,
            sf.excerpt,
            sf.jurisdiction,
            sf.authority,
            sf.doc_type,
            sd.title as doc_title,
            sd.canonical_citation
        FROM source_fragment sf
        JOIN source_document sd ON sf.doc_id = sd.doc_id
        WHERE sf.excerpt IS NOT NULL
            AND LENGTH(sf.excerpt) > 50
        """
        params = []
        if jurisdiction:
            query += " AND sf.jurisdiction = %s"
            params.append(jurisdiction)

        query += " ORDER BY sf.created_at"

        if limit:
            query += f" LIMIT {limit} OFFSET {offset}"

        cursor.execute(query, params if params else None)
        fragments = cursor.fetchall()
        cursor.close()

        return [dict(row) for row in fragments]

    def parse_fragment(self, fragment: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Use LLM to extract entities/relationships using ontology-driven prompt.

        Args:
            fragment: Fragment data from database

        Returns:
            Parsed JSON dict or None if parsing fails
        """
        excerpt = fragment['excerpt']
        authority = fragment.get('authority', '')
        jurisdiction = fragment.get('jurisdiction', '')

        system_message, prompt = build_prompt(
            excerpt=excerpt,
            authority=authority,
            jurisdiction=jurisdiction,
            ontology=self.ontology,
        )

        try:
            response_text = chat_parse(self.client, self.provider, self.model, system_message, prompt)
            result = json.loads(response_text)
            result['_fragment_id'] = str(fragment['fragment_id'])
            result['_doc_id'] = str(fragment['doc_id'])
            return result

        except Exception as e:
            print(f"  ✗ LLM parsing failed: {e}")
            return None

    def _escape_cypher(self, value: str) -> str:
        """Escape a string value for safe Cypher embedding."""
        if not isinstance(value, str):
            return str(value)
        return value.replace("\\", "\\\\").replace("'", "\\'").replace('"', '\\"')

    def _create_vertex(self, cursor, label: str, properties: Dict[str, Any]) -> bool:
        """Create a vertex with the given label and properties."""
        props_parts = []
        for key, value in properties.items():
            if value is None:
                continue
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                props_parts.append(f"{key}: {value}")
            elif isinstance(value, bool):
                props_parts.append(f"{key}: {str(value).lower()}")
            elif isinstance(value, list):
                escaped = self._escape_cypher(json.dumps(value))
                props_parts.append(f"{key}: '{escaped}'")
            else:
                escaped = self._escape_cypher(str(value))
                props_parts.append(f"{key}: '{escaped}'")

        props_str = ", ".join(props_parts)
        cypher = f"""
        SELECT * FROM cypher('{self.graph_name}', $$
            CREATE (n:{label} {{{props_str}}})
            RETURN id(n)
        $$) as (node_id agtype);
        """
        cursor.execute(cypher)
        return True

    def _create_edge(self, cursor, from_label: str, from_id: str, to_label: str, to_id: str, edge_label: str) -> bool:
        """Create an edge between two vertices."""
        from_id_escaped = self._escape_cypher(from_id)
        to_id_escaped = self._escape_cypher(to_id)
        cypher = f"""
        SELECT * FROM cypher('{self.graph_name}', $$
            MATCH (a:{from_label} {{id: '{from_id_escaped}'}}),
                  (b:{to_label} {{id: '{to_id_escaped}'}})
            CREATE (a)-[:{edge_label}]->(b)
        $$) as (result agtype);
        """
        cursor.execute(cypher)
        return True

    def load_to_graph(self, result: Dict[str, Any]) -> bool:
        """
        Load ontology-driven LLM output into AGE graph.

        Expects JSON with 'entities' and 'relationships' arrays:
        {
            "entities": [{"_label": "NodeType", "name": "...", ...}],
            "relationships": [{"_label": "EDGE_TYPE", "_from_index": 0, "_to_index": 1}]
        }
        """
        self.connect_db()
        cursor = self.db_conn.cursor()

        try:
            entities = result.get('entities', [])
            relationships = result.get('relationships', [])
            fragment_id = result.get('_fragment_id', '')
            doc_id = result.get('_doc_id', '')

            if not entities:
                return False

            # Create vertices and track their IDs
            entity_ids = []
            for idx, entity in enumerate(entities):
                label = entity.get('_label', self.ontology.root_node or 'Entity')
                # Generate a stable ID
                entity_id = f"{label}_{fragment_id[:8]}_{idx}"

                props = {'id': entity_id, 'fragment_id': fragment_id, 'doc_id': doc_id}
                for key, value in entity.items():
                    if key.startswith('_'):
                        continue
                    if isinstance(value, str):
                        props[key] = value[:500]
                    else:
                        props[key] = value

                self._create_vertex(cursor, label, props)
                entity_ids.append((entity_id, label))

            # Create edges
            for rel in relationships:
                edge_label = rel.get('_label', 'RELATES_TO')
                from_idx = rel.get('_from_index', 0)
                to_idx = rel.get('_to_index', 0)

                if from_idx < len(entity_ids) and to_idx < len(entity_ids):
                    from_id, from_label = entity_ids[from_idx]
                    to_id, to_label = entity_ids[to_idx]
                    self._create_edge(cursor, from_label, from_id, to_label, to_id, edge_label)

            cursor.close()
            return True

        except Exception as e:
            print(f"  ✗ Graph loading failed: {e}")
            cursor.close()
            return False

    def process_batch(self, fragments: List[Dict[str, Any]]) -> Dict[str, int]:
        """Process a batch of fragments through the ontology-driven pipeline."""
        batch_stats = {'success': 0, 'failed': 0, 'skipped': 0}

        for fragment in fragments:
            fragment_id = fragment['fragment_id']
            print(f"\nProcessing fragment {fragment_id}...")

            result = self.parse_fragment(fragment)
            if not result:
                batch_stats['failed'] += 1
                continue

            entities = result.get('entities', [])
            if not entities:
                print("  ⊘ No entities found, skipping")
                batch_stats['skipped'] += 1
                continue

            print(f"  ✓ Extracted {len(entities)} entities")

            if self.load_to_graph(result):
                print("  ✓ Loaded to graph")
                batch_stats['success'] += 1
            else:
                batch_stats['failed'] += 1

            time.sleep(RATE_LIMIT_DELAY)

        return batch_stats

    def run(self, limit: Optional[int] = None, offset: int = 0, jurisdiction: Optional[str] = None):
        """
        Main execution routine.

        Args:
            limit: Maximum number of fragments to process
            offset: Number of fragments to skip
            jurisdiction: Filter by jurisdiction code
        """
        print("=" * 70)
        print("Knowledge Graph Parser")
        print("=" * 70)
        print(f"Graph: {self.graph_name}")
        print(f"Provider: {self.provider}")
        print(f"Model: {self.model}")
        print(f"Batch size: {BATCH_SIZE}")
        if jurisdiction:
            print(f"Jurisdiction: {jurisdiction}")
        print("=" * 70)

        self.stats['start_time'] = datetime.now()

        try:
            # Fetch fragments
            print(f"\nFetching fragments (limit={limit}, offset={offset}, jurisdiction={jurisdiction})...")
            fragments = self.fetch_fragments(limit=limit, offset=offset, jurisdiction=jurisdiction)
            print(f"Found {len(fragments)} fragments to process")

            if not fragments:
                print("No fragments to process!")
                return

            # Process in batches
            total_fragments = len(fragments)
            for i in range(0, total_fragments, BATCH_SIZE):
                batch = fragments[i:i + BATCH_SIZE]
                batch_num = (i // BATCH_SIZE) + 1
                total_batches = (total_fragments + BATCH_SIZE - 1) // BATCH_SIZE

                print(f"\n{'='*70}")
                print(f"Batch {batch_num}/{total_batches}")
                print(f"{'='*70}")

                batch_stats = self.process_batch(batch)

                self.stats['processed'] += len(batch)
                self.stats['success'] += batch_stats['success']
                self.stats['failed'] += batch_stats['failed']
                self.stats['skipped'] += batch_stats['skipped']

                print(f"\nBatch complete: {batch_stats['success']} success, {batch_stats['failed']} failed, {batch_stats['skipped']} skipped")

        except KeyboardInterrupt:
            print("\n\n⚠ Interrupted by user")

        except Exception as e:
            print(f"\n\n✗ Fatal error: {e}")
            import traceback
            traceback.print_exc()

        finally:
            self.stats['end_time'] = datetime.now()
            self.disconnect_db()
            self.print_summary()

    def print_summary(self):
        """Print execution summary."""
        duration = (self.stats['end_time'] - self.stats['start_time']).total_seconds()

        print("\n" + "=" * 70)
        print("SUMMARY")
        print("=" * 70)
        print(f"Total processed:  {self.stats['processed']}")
        print(f"  ✓ Success:      {self.stats['success']}")
        print(f"  ✗ Failed:       {self.stats['failed']}")
        print(f"  ⊘ Skipped:      {self.stats['skipped']}")
        print(f"\nDuration:        {duration:.1f} seconds")
        if self.stats['processed'] > 0:
            print(f"Avg per fragment: {duration / self.stats['processed']:.2f} seconds")
        print("=" * 70)


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description='Parse data into AGE knowledge graph')
    parser.add_argument('--limit', type=int, help='Limit number of fragments to process')
    parser.add_argument('--offset', type=int, default=0, help='Number of fragments to skip')
    parser.add_argument('--jurisdiction', type=str, help='Filter by jurisdiction code (e.g., SG, CA)')
    parser.add_argument('--test', action='store_true', help='Test mode (process only 5 fragments)')
    parser.add_argument('--domain', type=str, help='Domain profile name or path (default: from DOMAIN env var)')
    parser.add_argument('--ontology', type=str, required=True, help='Path to ontology YAML file (required)')

    args = parser.parse_args()

    if args.domain:
        profile = load_profile(args.domain)
        set_profile(profile)

    ontology = load_ontology(args.ontology)
    print(f"Using ontology: {ontology.description or args.ontology}")

    if args.test:
        args.limit = 5
        print("TEST MODE: Processing only 5 fragments\n")

    parser_instance = KGParser(ontology=ontology)
    parser_instance.run(limit=args.limit, offset=args.offset, jurisdiction=args.jurisdiction)


if __name__ == "__main__":
    main()
