#!/usr/bin/env python3
"""
Knowledge Graph Parser
Reads text from PostgreSQL source_fragment table,
uses OpenAI to extract structured ontology,
and loads into Apache AGE graph database.

Supports both:
- Domain-specific mode (Provision/Requirement/Constraint) for domain profiles
- Generic ontology-driven mode (any node/edge types) for any topic
"""
import json
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

import psycopg2
from openai import OpenAI
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
from psycopg2.extras import RealDictCursor

from build_kg.config import (
    AGE_GRAPH_NAME,
    BATCH_SIZE,
    DB_CONFIG,
    OPENAI_API_KEY,
    OPENAI_MODEL,
    RATE_LIMIT_DELAY,
    validate_config,
)
from build_kg.domain import (
    OntologyConfig,
    build_prompt,
    get_profile,
    load_ontology,
    load_profile,
    set_profile,
)
from build_kg.id_extractors import ProvisionIDExtractor


@dataclass
class ParsedProvision:
    """Structured data extracted from source text (domain-specific mode)."""
    provision_id: str
    provision_text: str
    requirements: List[Dict[str, Any]]
    source_jurisdiction: str
    source_authority: str
    fragment_id: str
    doc_id: str


class KGParser:
    """Main parser for knowledge graph data. Supports both domain-specific and generic ontologies."""

    def __init__(self, ontology: Optional[OntologyConfig] = None):
        """Initialize parser.

        Args:
            ontology: If provided, use ontology-driven mode. Otherwise, use domain-specific mode.
        """
        validate_config()
        self.client = OpenAI(api_key=OPENAI_API_KEY)
        self.db_conn = None
        self.graph_name = AGE_GRAPH_NAME
        self.ontology = ontology
        self._use_ontology_mode = bool(ontology and ontology.nodes and ontology.json_schema)

        if not self._use_ontology_mode:
            self.id_extractor = ProvisionIDExtractor(profile=get_profile())
        else:
            self.id_extractor = None

        self.stats = {
            'processed': 0,
            'success': 0,
            'failed': 0,
            'skipped': 0,
            'start_time': None,
            'end_time': None,
            'regex_extracted': 0,
            'llm_extracted': 0,
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

    def parse_with_llm(self, fragment: Dict[str, Any]) -> Optional[ParsedProvision]:
        """
        Use OpenAI to parse source text into structured data.

        First tries regex-based ID extraction before calling LLM (domain-specific mode).

        Args:
            fragment: Fragment data from database

        Returns:
            ParsedProvision object or None if parsing fails
        """
        excerpt = fragment['excerpt']
        jurisdiction = fragment.get('jurisdiction', '')
        authority = fragment.get('authority', '')
        canonical_locator = fragment.get('canonical_locator', '')

        # Try regex-based extraction first (domain-specific mode only)
        provision_id_from_regex = "UNKNOWN"
        extraction_result = None
        if self.id_extractor:
            extraction_result = self.id_extractor.extract(
                text=excerpt,
                canonical_locator=canonical_locator,
                authority=authority or "UNKNOWN"
            )
            provision_id_from_regex = extraction_result.provision_id

            if provision_id_from_regex != "UNKNOWN":
                print(f"  ✓ Regex extracted ID: {provision_id_from_regex} (confidence: {extraction_result.confidence:.2f}, method: {extraction_result.method})")
                self.stats['regex_extracted'] += 1

        system_message, prompt = build_prompt(
            excerpt=excerpt,
            authority=authority or "",
            jurisdiction=jurisdiction or "",
        )

        try:
            response = self.client.chat.completions.create(
                model=OPENAI_MODEL,
                messages=[
                    {"role": "system", "content": system_message},
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"},
                temperature=0.1,
            )

            result = json.loads(response.choices[0].message.content)

            # Use regex-extracted ID if available and confident
            llm_provision_id = result.get('provision_id', 'UNKNOWN')

            # Choose best ID source
            if provision_id_from_regex != "UNKNOWN" and extraction_result and extraction_result.confidence >= 0.70:
                final_provision_id = provision_id_from_regex
                print(f"  → Using regex ID: {final_provision_id}")
            elif llm_provision_id != "UNKNOWN":
                final_provision_id = llm_provision_id
                self.stats['llm_extracted'] += 1
                print(f"  → Using LLM ID: {final_provision_id}")
            elif provision_id_from_regex != "UNKNOWN":
                final_provision_id = provision_id_from_regex
                print(f"  → Using low-confidence regex ID: {final_provision_id}")
            else:
                final_provision_id = "UNKNOWN"
                print("  ⚠ No ID extracted from regex or LLM")

            parsed = ParsedProvision(
                provision_id=final_provision_id,
                provision_text=result.get('provision_text', excerpt[:500]),
                requirements=result.get('requirements', []),
                source_jurisdiction=jurisdiction or '',
                source_authority=authority or '',
                fragment_id=str(fragment['fragment_id']),
                doc_id=str(fragment['doc_id']),
            )

            return parsed

        except Exception as e:
            print(f"  ✗ LLM parsing failed: {e}")
            return None

    def parse_generic(self, fragment: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Use OpenAI to extract entities/relationships using ontology-driven prompt.

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
        )

        try:
            response = self.client.chat.completions.create(
                model=OPENAI_MODEL,
                messages=[
                    {"role": "system", "content": system_message},
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"},
                temperature=0.1,
            )

            result = json.loads(response.choices[0].message.content)
            result['_fragment_id'] = str(fragment['fragment_id'])
            result['_doc_id'] = str(fragment['doc_id'])
            return result

        except Exception as e:
            print(f"  ✗ LLM parsing failed: {e}")
            return None

    def load_to_graph(self, parsed: ParsedProvision) -> bool:
        """
        Load parsed provision into AGE graph.

        Args:
            parsed: ParsedProvision object

        Returns:
            True if successful, False otherwise
        """
        self.connect_db()
        cursor = self.db_conn.cursor()

        try:
            # Create Provision vertex
            provision_props = {
                'id': f"{parsed.source_authority}_{parsed.provision_id}_{parsed.fragment_id[:8]}",
                'provision_id': parsed.provision_id,
                'text': parsed.provision_text[:500],
                'jurisdiction': parsed.source_jurisdiction,
                'authority': parsed.source_authority,
                'fragment_id': parsed.fragment_id,
                'doc_id': parsed.doc_id,
                'created_at': datetime.now().isoformat(),
            }

            # Escape single quotes in text
            for key, value in provision_props.items():
                if isinstance(value, str):
                    provision_props[key] = value.replace("'", "\\'").replace('"', '\\"')

            # Create provision node
            provision_cypher = f"""
            SELECT * FROM cypher('{self.graph_name}', $$
                CREATE (p:Provision {{
                    id: '{provision_props['id']}',
                    provision_id: '{provision_props['provision_id']}',
                    text: '{provision_props['text']}',
                    jurisdiction: '{provision_props['jurisdiction']}',
                    authority: '{provision_props['authority']}',
                    fragment_id: '{provision_props['fragment_id']}',
                    doc_id: '{provision_props['doc_id']}',
                    created_at: '{provision_props['created_at']}'
                }})
                RETURN id(p)
            $$) as (provision_id agtype);
            """

            cursor.execute(provision_cypher)
            cursor.fetchone()

            # Process requirements
            for idx, req in enumerate(parsed.requirements):
                req_id = f"{provision_props['id']}_req_{idx}"
                req_type = req.get('requirement_type', 'unknown')
                deontic = req.get('deontic_modality', 'must')
                description = req.get('description', '')[:500].replace("'", "\\'").replace('"', '\\"')
                scope = req.get('applies_to_scope', 'unknown')

                # Create requirement node
                req_cypher = f"""
                SELECT * FROM cypher('{self.graph_name}', $$
                    CREATE (r:Requirement {{
                        id: '{req_id}',
                        requirement_type: '{req_type}',
                        deontic_modality: '{deontic}',
                        description: '{description}',
                        applies_to_scope: '{scope}'
                    }})
                    RETURN id(r)
                $$) as (req_id agtype);
                """

                cursor.execute(req_cypher)

                # Link requirement to provision
                link_cypher = f"""
                SELECT * FROM cypher('{self.graph_name}', $$
                    MATCH (p:Provision {{id: '{provision_props['id']}'}}),
                          (r:Requirement {{id: '{req_id}'}})
                    CREATE (r)-[:DERIVED_FROM]->(p)
                $$) as (result agtype);
                """

                cursor.execute(link_cypher)

                # Process constraints
                for c_idx, constraint in enumerate(req.get('constraints', [])):
                    const_id = f"{req_id}_const_{c_idx}"
                    logic_type = constraint.get('logic_type', 'unknown')
                    target_signal = constraint.get('target_signal', '').replace("'", "\\'")
                    operator = constraint.get('operator', '')
                    threshold = constraint.get('threshold')
                    unit = constraint.get('unit', '')
                    pattern = constraint.get('pattern', '').replace("'", "\\'") if constraint.get('pattern') else ''

                    # Build constraint properties
                    const_props = [
                        f"id: '{const_id}'",
                        f"logic_type: '{logic_type}'",
                        f"target_signal: '{target_signal}'",
                    ]

                    if operator:
                        const_props.append(f"operator: '{operator}'")
                    if threshold is not None:
                        const_props.append(f"threshold: {threshold}")
                    if unit:
                        const_props.append(f"unit: '{unit}'")
                    if pattern:
                        const_props.append(f"pattern: '{pattern}'")

                    const_props_str = ", ".join(const_props)

                    # Create constraint node
                    const_cypher = f"""
                    SELECT * FROM cypher('{self.graph_name}', $$
                        CREATE (c:Constraint {{{const_props_str}}})
                        RETURN id(c)
                    $$) as (const_id agtype);
                    """

                    cursor.execute(const_cypher)

                    # Link constraint to requirement
                    const_link_cypher = f"""
                    SELECT * FROM cypher('{self.graph_name}', $$
                        MATCH (r:Requirement {{id: '{req_id}'}}),
                              (c:Constraint {{id: '{const_id}'}})
                        CREATE (r)-[:HAS_CONSTRAINT]->(c)
                    $$) as (result agtype);
                    """

                    cursor.execute(const_link_cypher)

            cursor.close()
            return True

        except Exception as e:
            print(f"  ✗ Graph loading failed: {e}")
            cursor.close()
            return False

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

    def load_to_graph_generic(self, result: Dict[str, Any]) -> bool:
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
        """
        Process a batch of fragments.

        Routes to ontology-driven or domain-specific path based on config.
        """
        batch_stats = {'success': 0, 'failed': 0, 'skipped': 0}

        for fragment in fragments:
            fragment_id = fragment['fragment_id']
            print(f"\nProcessing fragment {fragment_id}...")

            if self._use_ontology_mode:
                # Generic ontology-driven path
                result = self.parse_generic(fragment)
                if not result:
                    batch_stats['failed'] += 1
                    continue

                entities = result.get('entities', [])
                if not entities:
                    print("  ⊘ No entities found, skipping")
                    batch_stats['skipped'] += 1
                    continue

                print(f"  ✓ Extracted {len(entities)} entities")

                if self.load_to_graph_generic(result):
                    print("  ✓ Loaded to graph")
                    batch_stats['success'] += 1
                else:
                    batch_stats['failed'] += 1
            else:
                # Domain-specific path (Provision/Requirement/Constraint)
                parsed = self.parse_with_llm(fragment)
                if not parsed:
                    batch_stats['failed'] += 1
                    continue

                if not parsed.requirements:
                    print("  ⊘ No requirements found, skipping")
                    batch_stats['skipped'] += 1
                    continue

                print(f"  ✓ Extracted {len(parsed.requirements)} requirements")

                if self.load_to_graph(parsed):
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
        mode = "ontology-driven" if self._use_ontology_mode else "domain-specific"
        print("=" * 70)
        print(f"Knowledge Graph Parser ({mode} mode)")
        print("=" * 70)
        print(f"Graph: {self.graph_name}")
        print(f"Model: {OPENAI_MODEL}")
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
        print("\nID Extraction Methods:")
        print(f"  🔍 Regex:       {self.stats.get('regex_extracted', 0)}")
        print(f"  🤖 LLM:         {self.stats.get('llm_extracted', 0)}")
        total_extracted = self.stats.get('regex_extracted', 0) + self.stats.get('llm_extracted', 0)
        if self.stats['success'] > 0:
            print(f"  📊 Success Rate: {total_extracted / self.stats['success'] * 100:.1f}%")
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
    parser.add_argument('--ontology', type=str, help='Path to ontology YAML file for generic mode')

    args = parser.parse_args()

    if args.domain:
        profile = load_profile(args.domain)
        set_profile(profile)

    ontology = None
    if args.ontology:
        ontology = load_ontology(args.ontology)
        print(f"Using ontology: {ontology.description or args.ontology}")
    elif get_profile().ontology.nodes:
        # Use ontology from profile if present
        ontology = get_profile().ontology

    if args.test:
        args.limit = 5
        print("TEST MODE: Processing only 5 fragments\n")

    parser_instance = KGParser(ontology=ontology)
    parser_instance.run(limit=args.limit, offset=args.offset, jurisdiction=args.jurisdiction)


# Backward compatibility alias
RegulatoryParser = KGParser


if __name__ == "__main__":
    main()
