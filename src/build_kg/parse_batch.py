#!/usr/bin/env python3
"""
Knowledge Graph Parser - OpenAI Batch API Version
Step 1: Prepare batch requests from source_fragment table
Step 2: Submit batch to OpenAI
Step 3: Monitor batch status
Step 4: Process results and load into AGE graph

This is 50% cheaper than the standard API and designed for large-scale processing.
Supports both domain-specific (Provision/Requirement/Constraint) and generic ontology modes.
"""
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import psycopg2
from openai import OpenAI
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
from psycopg2.extras import RealDictCursor

from build_kg.config import AGE_GRAPH_NAME, DB_CONFIG, OPENAI_API_KEY, OPENAI_MODEL, validate_config
from build_kg.domain import OntologyConfig, build_prompt, load_ontology, load_profile, set_profile


class BatchPreparation:
    """Prepare batch requests from database."""

    def __init__(self):
        """Initialize batch preparation."""
        validate_config()
        self.db_conn = None
        self.output_dir = Path.cwd() / "batch_data"
        self.output_dir.mkdir(exist_ok=True)

    def connect_db(self):
        """Establish database connection."""
        if not self.db_conn or self.db_conn.closed:
            self.db_conn = psycopg2.connect(**DB_CONFIG)

    def disconnect_db(self):
        """Close database connection."""
        if self.db_conn and not self.db_conn.closed:
            self.db_conn.close()

    def fetch_fragments(self, limit: Optional[int] = None, offset: int = 0, jurisdiction: Optional[str] = None) -> List[Dict[str, Any]]:
        """Fetch source fragments from database."""
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

    def create_prompt(self, fragment: Dict[str, Any]) -> tuple:
        """Create parsing prompt for a fragment. Returns (system_message, user_prompt)."""
        return build_prompt(
            excerpt=fragment['excerpt'],
            authority=fragment.get('authority', '') or '',
            jurisdiction=fragment.get('jurisdiction', '') or '',
        )

    def prepare_batch_file(self, fragments: List[Dict[str, Any]], output_file: str) -> str:
        """
        Create JSONL batch file for OpenAI.

        Args:
            fragments: List of fragment dictionaries
            output_file: Output filename

        Returns:
            Path to created file
        """
        output_path = self.output_dir / output_file

        print(f"Creating batch file: {output_path}")
        print(f"Processing {len(fragments)} fragments...")

        with open(output_path, 'w') as f:
            for fragment in fragments:
                system_message, user_prompt = self.create_prompt(fragment)
                # Create batch request
                batch_request = {
                    "custom_id": str(fragment['fragment_id']),
                    "method": "POST",
                    "url": "/v1/chat/completions",
                    "body": {
                        "model": OPENAI_MODEL,
                        "messages": [
                            {
                                "role": "system",
                                "content": system_message
                            },
                            {
                                "role": "user",
                                "content": user_prompt
                            }
                        ],
                        "response_format": {"type": "json_object"},
                        "temperature": 0.1,
                    }
                }

                # Write as JSONL (one JSON per line)
                f.write(json.dumps(batch_request) + '\n')

        # Save metadata for later processing
        metadata = {
            "created_at": datetime.now().isoformat(),
            "fragment_count": len(fragments),
            "fragments": [
                {
                    "fragment_id": str(f['fragment_id']),
                    "doc_id": str(f['doc_id']),
                    "jurisdiction": f.get('jurisdiction', '') or '',
                    "authority": f.get('authority', '') or '',
                }
                for f in fragments
            ]
        }

        metadata_path = self.output_dir / f"{output_file}.metadata.json"
        with open(metadata_path, 'w') as f:
            json.dump(metadata, f, indent=2)

        print(f"✓ Batch file created: {output_path}")
        print(f"✓ Metadata saved: {metadata_path}")

        return str(output_path)

    def run(self, limit: Optional[int] = None, offset: int = 0, output_file: str = "batch_requests.jsonl", jurisdiction: Optional[str] = None):
        """
        Main execution for batch preparation.

        Args:
            limit: Maximum number of fragments to process
            offset: Number of fragments to skip
            output_file: Output JSONL filename
            jurisdiction: Filter by jurisdiction code
        """
        print("=" * 70)
        print("Batch Preparation - Step 1")
        if jurisdiction:
            print(f"Jurisdiction filter: {jurisdiction}")
        print("=" * 70)

        try:
            # Fetch fragments
            print(f"\nFetching fragments (limit={limit}, offset={offset}, jurisdiction={jurisdiction})...")
            fragments = self.fetch_fragments(limit=limit, offset=offset, jurisdiction=jurisdiction)
            print(f"Found {len(fragments)} fragments")

            if not fragments:
                print("No fragments to process!")
                return None

            # Create batch file
            batch_file = self.prepare_batch_file(fragments, output_file)

            print("\n" + "=" * 70)
            print("✓ Batch preparation complete!")
            print(f"Next step: build-kg-parse-batch submit {batch_file}")
            print("=" * 70)

            return batch_file

        finally:
            self.disconnect_db()


class BatchSubmission:
    """Submit batch to OpenAI."""

    def __init__(self):
        """Initialize batch submission."""
        validate_config()
        self.client = OpenAI(api_key=OPENAI_API_KEY)
        self.output_dir = Path.cwd() / "batch_data"

    def submit_batch(self, batch_file: str) -> str:
        """
        Submit batch file to OpenAI.

        Args:
            batch_file: Path to JSONL batch file

        Returns:
            Batch ID
        """
        print("=" * 70)
        print("Batch Submission - Step 2")
        print("=" * 70)
        print(f"\nUploading file: {batch_file}")

        # Upload file
        with open(batch_file, 'rb') as f:
            batch_input_file = self.client.files.create(
                file=f,
                purpose="batch"
            )

        print(f"✓ File uploaded: {batch_input_file.id}")
        print("\nCreating batch job...")

        # Create batch
        batch = self.client.batches.create(
            input_file_id=batch_input_file.id,
            endpoint="/v1/chat/completions",
            completion_window="24h",
            metadata={
                "description": "Knowledge graph data parsing"
            }
        )

        print(f"✓ Batch created: {batch.id}")
        print(f"  Status: {batch.status}")
        print(f"  Total requests: {batch.request_counts.total}")

        # Save batch info
        batch_info = {
            "batch_id": batch.id,
            "input_file_id": batch_input_file.id,
            "status": batch.status,
            "created_at": datetime.now().isoformat(),
            "batch_file": batch_file,
        }

        info_path = self.output_dir / f"batch_{batch.id}.info.json"
        with open(info_path, 'w') as f:
            json.dump(batch_info, f, indent=2)

        print(f"✓ Batch info saved: {info_path}")

        print("\n" + "=" * 70)
        print("✓ Batch submitted successfully!")
        print(f"Batch ID: {batch.id}")
        print(f"\nMonitor progress: build-kg-parse-batch status {batch.id}")
        print("=" * 70)

        return batch.id


class BatchMonitor:
    """Monitor batch status."""

    def __init__(self):
        """Initialize batch monitor."""
        validate_config()
        self.client = OpenAI(api_key=OPENAI_API_KEY)

    def check_status(self, batch_id: str, watch: bool = False):
        """
        Check batch status.

        Args:
            batch_id: OpenAI batch ID
            watch: If True, poll until complete
        """
        print("=" * 70)
        print("Batch Status - Step 3")
        print("=" * 70)

        while True:
            batch = self.client.batches.retrieve(batch_id)

            print(f"\nBatch ID: {batch.id}")
            print(f"Status: {batch.status}")
            print(f"Created: {datetime.fromtimestamp(batch.created_at)}")

            if batch.request_counts:
                print("\nRequest Counts:")
                print(f"  Total: {batch.request_counts.total}")
                print(f"  Completed: {batch.request_counts.completed}")
                print(f"  Failed: {batch.request_counts.failed}")

            if batch.status == "completed":
                print("\n✓ Batch completed!")
                print(f"Output file ID: {batch.output_file_id}")
                if batch.error_file_id:
                    print(f"Error file ID: {batch.error_file_id}")

                print(f"\nNext step: build-kg-parse-batch process {batch_id}")
                break

            elif batch.status == "failed":
                print("\n✗ Batch failed!")
                if batch.errors:
                    print(f"Errors: {batch.errors}")
                break

            elif batch.status in ["expired", "cancelled"]:
                print(f"\n✗ Batch {batch.status}")
                break

            elif watch:
                print("\nStill processing... (will check again in 60 seconds)")
                time.sleep(60)
            else:
                break

        print("=" * 70)


class BatchProcessor:
    """Process batch results and load into AGE graph."""

    def __init__(self, ontology: Optional[OntologyConfig] = None):
        """Initialize batch processor."""
        validate_config()
        self.client = OpenAI(api_key=OPENAI_API_KEY)
        self.db_conn = None
        self.graph_name = AGE_GRAPH_NAME
        self.output_dir = Path.cwd() / "batch_data"
        self.ontology = ontology
        self._use_ontology_mode = bool(ontology and ontology.nodes and ontology.json_schema)

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

    def download_results(self, batch_id: str) -> str:
        """Download batch results."""
        print(f"Downloading results for batch {batch_id}...")

        batch = self.client.batches.retrieve(batch_id)

        if batch.status != "completed":
            print(f"✗ Batch not completed yet (status: {batch.status})")
            return None

        # Download output file
        output_content = self.client.files.content(batch.output_file_id)
        output_path = self.output_dir / f"batch_{batch_id}_results.jsonl"

        with open(output_path, 'wb') as f:
            f.write(output_content.content)

        print(f"✓ Results downloaded: {output_path}")

        # Download error file if exists
        if batch.error_file_id:
            error_content = self.client.files.content(batch.error_file_id)
            error_path = self.output_dir / f"batch_{batch_id}_errors.jsonl"

            with open(error_path, 'wb') as f:
                f.write(error_content.content)

            print(f"✓ Errors downloaded: {error_path}")

        return str(output_path)

    def load_to_graph(self, fragment_id: str, doc_id: str, jurisdiction: str,
                      authority: str, parsed_data: Dict[str, Any]) -> bool:
        """Load parsed provision into AGE graph."""
        self.connect_db()
        cursor = self.db_conn.cursor()

        try:
            provision_id = parsed_data.get('provision_id', 'UNKNOWN')
            provision_text = parsed_data.get('provision_text', '')[:500]
            requirements = parsed_data.get('requirements', [])

            # Create unique provision ID
            prov_id = f"{authority}_{provision_id}_{fragment_id[:8]}"

            # Escape strings for Cypher
            def escape(s):
                if isinstance(s, str):
                    # Escape backslashes first (important for regex patterns)
                    s = s.replace('\\', '\\\\')
                    # Then escape quotes and newlines
                    s = s.replace("'", "\\'").replace('"', '\\"').replace('\n', ' ')
                    return s
                return s

            # Create provision node
            provision_cypher = f"""
            SELECT * FROM cypher('{self.graph_name}', $$
                CREATE (p:Provision {{
                    id: '{escape(prov_id)}',
                    provision_id: '{escape(provision_id)}',
                    text: '{escape(provision_text)}',
                    jurisdiction: '{escape(jurisdiction)}',
                    authority: '{escape(authority)}',
                    fragment_id: '{fragment_id}',
                    doc_id: '{doc_id}',
                    created_at: '{datetime.now().isoformat()}'
                }})
                RETURN id(p)
            $$) as (provision_id agtype);
            """

            cursor.execute(provision_cypher)

            # Process requirements
            for idx, req in enumerate(requirements):
                req_id = f"{prov_id}_req_{idx}"
                req_type = escape(req.get('requirement_type', 'unknown'))
                deontic = escape(req.get('deontic_modality', 'must'))
                description = escape(req.get('description', '')[:500])
                scope = escape(req.get('applies_to_scope', 'unknown'))

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
                    MATCH (p:Provision {{id: '{escape(prov_id)}'}}),
                          (r:Requirement {{id: '{req_id}'}})
                    CREATE (r)-[:DERIVED_FROM]->(p)
                $$) as (result agtype);
                """

                cursor.execute(link_cypher)

                # Process constraints
                for c_idx, constraint in enumerate(req.get('constraints', [])):
                    const_id = f"{req_id}_const_{c_idx}"
                    logic_type = escape(constraint.get('logic_type', 'unknown'))
                    target_signal = escape(constraint.get('target_signal', ''))
                    operator = escape(constraint.get('operator', ''))
                    threshold = constraint.get('threshold')
                    unit = escape(constraint.get('unit', ''))
                    pattern = escape(constraint.get('pattern', ''))

                    const_props = [
                        f"id: '{const_id}'",
                        f"logic_type: '{logic_type}'",
                        f"target_signal: '{target_signal}'",
                    ]

                    if operator:
                        const_props.append(f"operator: '{operator}'")
                    if threshold is not None and isinstance(threshold, (int, float)):
                        # Only add numeric thresholds, skip string values like "current_date"
                        const_props.append(f"threshold: {threshold}")
                    if unit:
                        const_props.append(f"unit: '{unit}'")
                    if pattern:
                        const_props.append(f"pattern: '{pattern}'")

                    const_props_str = ", ".join(const_props)

                    const_cypher = f"""
                    SELECT * FROM cypher('{self.graph_name}', $$
                        CREATE (c:Constraint {{{const_props_str}}})
                        RETURN id(c)
                    $$) as (const_id agtype);
                    """

                    cursor.execute(const_cypher)

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
            print(f"  ✗ Graph loading failed for {fragment_id}: {e}")
            cursor.close()
            return False

    def _escape_cypher(self, value: str) -> str:
        """Escape a string for Cypher embedding."""
        if not isinstance(value, str):
            return str(value)
        return value.replace('\\', '\\\\').replace("'", "\\'").replace('"', '\\"').replace('\n', ' ')

    def load_to_graph_generic(self, fragment_id: str, doc_id: str, parsed_data: Dict[str, Any]) -> bool:
        """Load ontology-driven LLM output into AGE graph."""
        self.connect_db()
        cursor = self.db_conn.cursor()

        try:
            entities = parsed_data.get('entities', [])
            relationships = parsed_data.get('relationships', [])

            if not entities:
                return False

            entity_ids = []
            for idx, entity in enumerate(entities):
                label = entity.get('_label', self.ontology.root_node or 'Entity')
                entity_id = f"{label}_{fragment_id[:8]}_{idx}"

                props_parts = [f"id: '{self._escape_cypher(entity_id)}'",
                               f"fragment_id: '{fragment_id}'",
                               f"doc_id: '{doc_id}'"]
                for key, value in entity.items():
                    if key.startswith('_') or value is None:
                        continue
                    if isinstance(value, (int, float)) and not isinstance(value, bool):
                        props_parts.append(f"{key}: {value}")
                    else:
                        props_parts.append(f"{key}: '{self._escape_cypher(str(value)[:500])}'")

                props_str = ", ".join(props_parts)
                cypher = f"""
                SELECT * FROM cypher('{self.graph_name}', $$
                    CREATE (n:{label} {{{props_str}}})
                    RETURN id(n)
                $$) as (node_id agtype);
                """
                cursor.execute(cypher)
                entity_ids.append((entity_id, label))

            for rel in relationships:
                edge_label = rel.get('_label', 'RELATES_TO')
                from_idx = rel.get('_from_index', 0)
                to_idx = rel.get('_to_index', 0)

                if from_idx < len(entity_ids) and to_idx < len(entity_ids):
                    from_id, from_label = entity_ids[from_idx]
                    to_id, to_label = entity_ids[to_idx]
                    edge_cypher = f"""
                    SELECT * FROM cypher('{self.graph_name}', $$
                        MATCH (a:{from_label} {{id: '{self._escape_cypher(from_id)}'}}),
                              (b:{to_label} {{id: '{self._escape_cypher(to_id)}'}})
                        CREATE (a)-[:{edge_label}]->(b)
                    $$) as (result agtype);
                    """
                    cursor.execute(edge_cypher)

            cursor.close()
            return True

        except Exception as e:
            print(f"  ✗ Graph loading failed for {fragment_id}: {e}")
            cursor.close()
            return False

    def process_results(self, batch_id: str):
        """Process batch results and load into graph."""
        print("=" * 70)
        print("Batch Processing - Step 4")
        print("=" * 70)

        # Download results
        results_file = self.download_results(batch_id)
        if not results_file:
            return

        # Load metadata - try to find the matching batch info to get the original batch file
        metadata_file = None

        # First, try to find batch info which links to the original batch file
        batch_info_path = self.output_dir / f"batch_{batch_id}.info.json"
        if batch_info_path.exists():
            with open(batch_info_path, 'r') as f:
                batch_info = json.load(f)
            original_batch_file = batch_info.get('batch_file', '')
            candidate = Path(original_batch_file + ".metadata.json")
            if candidate.exists():
                metadata_file = candidate

        # Fallback: try most recent metadata file
        if not metadata_file:
            metadata_files = sorted(self.output_dir.glob("*.metadata.json"), key=lambda p: p.stat().st_mtime, reverse=True)
            if not metadata_files:
                print("✗ Metadata file not found!")
                return
            metadata_file = metadata_files[0]

        print(f"Using metadata: {metadata_file.name}")

        with open(metadata_file, 'r') as f:
            metadata = json.load(f)

        # Create fragment lookup
        fragment_lookup = {
            f['fragment_id']: f
            for f in metadata['fragments']
        }

        print(f"\nProcessing results from: {results_file}")

        stats = {'success': 0, 'failed': 0, 'skipped': 0}

        # Process each result
        with open(results_file, 'r') as f:
            for line in f:
                result = json.loads(line)
                custom_id = result['custom_id']
                fragment_id = custom_id

                if result.get('error'):
                    print(f"  ✗ Error for {fragment_id}: {result['error']}")
                    stats['failed'] += 1
                    continue

                # Extract parsed data
                response = result['response']
                body = response['body']
                choices = body['choices']

                if not choices:
                    print(f"  ⊘ No response for {fragment_id}")
                    stats['skipped'] += 1
                    continue

                content = choices[0]['message']['content']

                # Try to parse JSON, skip if malformed
                try:
                    parsed_data = json.loads(content)
                except json.JSONDecodeError as e:
                    print(f"  ✗ JSON parse error for {fragment_id}: {e}")
                    stats['failed'] += 1
                    continue

                # Get fragment metadata
                fragment_meta = fragment_lookup.get(fragment_id, {})
                doc_id = fragment_meta.get('doc_id', 'UNKNOWN')

                if self._use_ontology_mode:
                    # Generic ontology mode
                    if not parsed_data.get('entities'):
                        stats['skipped'] += 1
                        continue
                    if self.load_to_graph_generic(fragment_id, doc_id, parsed_data):
                        stats['success'] += 1
                        if stats['success'] % 100 == 0:
                            print(f"  Processed {stats['success']} entities...")
                    else:
                        stats['failed'] += 1
                else:
                    # Domain-specific mode (Provision/Requirement/Constraint)
                    if not parsed_data.get('requirements'):
                        stats['skipped'] += 1
                        continue
                    jurisdiction = fragment_meta.get('jurisdiction', 'UNKNOWN')
                    authority = fragment_meta.get('authority', 'UNKNOWN')
                    if self.load_to_graph(fragment_id, doc_id, jurisdiction, authority, parsed_data):
                        stats['success'] += 1
                        if stats['success'] % 100 == 0:
                            print(f"  Processed {stats['success']} provisions...")
                    else:
                        stats['failed'] += 1

        print("\n" + "=" * 70)
        print("SUMMARY")
        print("=" * 70)
        print(f"✓ Success:  {stats['success']}")
        print(f"✗ Failed:   {stats['failed']}")
        print(f"⊘ Skipped:  {stats['skipped']}")
        print("=" * 70)

        self.disconnect_db()


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description='Parse data into knowledge graph using OpenAI Batch API',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Step 1: Prepare batch (test with 100 fragments)
  build-kg-parse-batch prepare --limit 100

  # Step 2: Submit batch
  build-kg-parse-batch submit batch_data/batch_requests.jsonl

  # Step 3: Check status
  build-kg-parse-batch status batch_xyz123

  # Step 3b: Watch status until complete
  build-kg-parse-batch status batch_xyz123 --watch

  # Step 4: Process results
  build-kg-parse-batch process batch_xyz123
        """
    )

    subparsers = parser.add_subparsers(dest='command', help='Command to execute')

    # Prepare command
    prepare_parser = subparsers.add_parser('prepare', help='Prepare batch file')
    prepare_parser.add_argument('--limit', type=int, help='Limit number of fragments')
    prepare_parser.add_argument('--offset', type=int, default=0, help='Offset for fragments')
    prepare_parser.add_argument('--jurisdiction', type=str, help='Filter by jurisdiction code (e.g., SG, CA)')
    prepare_parser.add_argument('--output', default='batch_requests.jsonl', help='Output filename')
    prepare_parser.add_argument('--domain', type=str, help='Domain profile name or path')

    # Submit command
    submit_parser = subparsers.add_parser('submit', help='Submit batch to OpenAI')
    submit_parser.add_argument('batch_file', help='Path to batch JSONL file')

    # Status command
    status_parser = subparsers.add_parser('status', help='Check batch status')
    status_parser.add_argument('batch_id', help='OpenAI batch ID')
    status_parser.add_argument('--watch', action='store_true', help='Watch until complete')

    # Process command
    process_parser = subparsers.add_parser('process', help='Process batch results')
    process_parser.add_argument('batch_id', help='OpenAI batch ID')
    process_parser.add_argument('--ontology', type=str, help='Path to ontology YAML file for generic mode')

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    if hasattr(args, 'domain') and args.domain:
        set_profile(load_profile(args.domain))

    if args.command == 'prepare':
        prep = BatchPreparation()
        prep.run(limit=args.limit, offset=args.offset, output_file=args.output, jurisdiction=getattr(args, 'jurisdiction', None))

    elif args.command == 'submit':
        sub = BatchSubmission()
        sub.submit_batch(args.batch_file)

    elif args.command == 'status':
        mon = BatchMonitor()
        mon.check_status(args.batch_id, watch=args.watch)

    elif args.command == 'process':
        ontology = None
        if hasattr(args, 'ontology') and args.ontology:
            ontology = load_ontology(args.ontology)
        proc = BatchProcessor(ontology=ontology)
        proc.process_results(args.batch_id)


if __name__ == "__main__":
    main()
