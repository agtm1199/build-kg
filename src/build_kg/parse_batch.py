#!/usr/bin/env python3
"""
Knowledge Graph Parser - Batch API Version
Step 1: Prepare batch requests from source_fragment table
Step 2: Submit batch to LLM provider
Step 3: Monitor batch status
Step 4: Process results and load into AGE graph

This is 50% cheaper than the standard API and designed for large-scale processing.
Ontology-driven: requires an OntologyConfig defining node types, edge types, and JSON schema.
"""
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
from psycopg2.extras import RealDictCursor

from build_kg.config import AGE_GRAPH_NAME, DB_CONFIG, validate_config
from build_kg.domain import OntologyConfig, build_prompt, load_ontology, load_profile, set_profile
from build_kg.llm import build_batch_request, create_client, extract_batch_response_text, get_provider_config


class BatchPreparation:
    """Prepare batch requests from database."""

    def __init__(self, ontology: OntologyConfig):
        """Initialize batch preparation.

        Args:
            ontology: Ontology defining node types, edge types, and JSON schema.
        """
        validate_config()
        self.provider, _, self.model = get_provider_config()
        self.db_conn = None
        self.output_dir = Path.cwd() / "batch_data"
        self.output_dir.mkdir(exist_ok=True)
        self.ontology = ontology

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
            ontology=self.ontology,
        )

    def prepare_batch_file(self, fragments: List[Dict[str, Any]], output_file: str) -> str:
        """
        Create JSONL batch file for the configured LLM provider.

        Args:
            fragments: List of fragment dictionaries
            output_file: Output filename

        Returns:
            Path to created file
        """
        output_path = self.output_dir / output_file

        print(f"Creating batch file: {output_path}")
        print(f"Provider: {self.provider}, Model: {self.model}")
        print(f"Processing {len(fragments)} fragments...")

        with open(output_path, 'w') as f:
            for fragment in fragments:
                system_message, user_prompt = self.create_prompt(fragment)
                batch_request = build_batch_request(
                    self.provider, self.model,
                    str(fragment['fragment_id']),
                    system_message, user_prompt,
                )

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
    """Submit batch to LLM provider."""

    def __init__(self):
        """Initialize batch submission."""
        validate_config()
        self.provider, api_key, self.model = get_provider_config()
        self.client = create_client(self.provider, api_key)
        self.output_dir = Path.cwd() / "batch_data"

    def submit_batch(self, batch_file: str) -> str:
        """
        Submit batch file to LLM provider.

        Args:
            batch_file: Path to JSONL batch file

        Returns:
            Batch ID
        """
        print("=" * 70)
        print("Batch Submission - Step 2")
        print(f"Provider: {self.provider}")
        print("=" * 70)
        print(f"\nProcessing file: {batch_file}")

        if self.provider == 'anthropic':
            return self._submit_anthropic(batch_file)
        else:
            return self._submit_openai(batch_file)

    def _submit_anthropic(self, batch_file: str) -> str:
        """Submit batch via Anthropic Message Batches API."""
        requests = []
        with open(batch_file, 'r') as f:
            for line in f:
                requests.append(json.loads(line))

        print(f"Submitting {len(requests)} requests...")

        batch = self.client.messages.batches.create(requests=requests)

        print(f"✓ Batch created: {batch.id}")
        print(f"  Status: {batch.processing_status}")

        # Save batch info
        batch_info = {
            "batch_id": batch.id,
            "provider": self.provider,
            "status": batch.processing_status,
            "created_at": datetime.now().isoformat(),
            "batch_file": batch_file,
            "request_count": len(requests),
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

    def _submit_openai(self, batch_file: str) -> str:
        """Submit batch via OpenAI Batch API."""
        print(f"Uploading file: {batch_file}")

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
            "provider": self.provider,
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
        self.provider, api_key, _ = get_provider_config()
        self.client = create_client(self.provider, api_key)

    def check_status(self, batch_id: str, watch: bool = False):
        """
        Check batch status.

        Args:
            batch_id: Batch ID
            watch: If True, poll until complete
        """
        print("=" * 70)
        print("Batch Status - Step 3")
        print(f"Provider: {self.provider}")
        print("=" * 70)

        if self.provider == 'anthropic':
            self._check_anthropic(batch_id, watch)
        else:
            self._check_openai(batch_id, watch)

        print("=" * 70)

    def _check_anthropic(self, batch_id: str, watch: bool):
        """Check batch status via Anthropic API."""
        while True:
            batch = self.client.messages.batches.retrieve(batch_id)

            print(f"\nBatch ID: {batch.id}")
            print(f"Status: {batch.processing_status}")

            if batch.request_counts:
                print("\nRequest Counts:")
                print(f"  Processing: {batch.request_counts.processing}")
                print(f"  Succeeded: {batch.request_counts.succeeded}")
                print(f"  Errored: {batch.request_counts.errored}")
                print(f"  Canceled: {batch.request_counts.canceled}")
                print(f"  Expired: {batch.request_counts.expired}")

            if batch.processing_status == "ended":
                print("\n✓ Batch completed!")
                print(f"\nNext step: build-kg-parse-batch process {batch_id}")
                break

            elif watch:
                print("\nStill processing... (will check again in 60 seconds)")
                time.sleep(60)
            else:
                break

    def _check_openai(self, batch_id: str, watch: bool):
        """Check batch status via OpenAI API."""
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


class BatchProcessor:
    """Process batch results and load into AGE graph."""

    def __init__(self, ontology: OntologyConfig):
        """Initialize batch processor.

        Args:
            ontology: Ontology defining node types, edge types, and JSON schema.
        """
        validate_config()
        self.provider, api_key, self.model = get_provider_config()
        self.client = create_client(self.provider, api_key)
        self.db_conn = None
        self.graph_name = AGE_GRAPH_NAME
        self.output_dir = Path.cwd() / "batch_data"
        self.ontology = ontology

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

        if self.provider == 'anthropic':
            return self._download_anthropic(batch_id)
        else:
            return self._download_openai(batch_id)

    def _download_anthropic(self, batch_id: str) -> str:
        """Download results from Anthropic batch."""
        batch = self.client.messages.batches.retrieve(batch_id)

        if batch.processing_status != "ended":
            print(f"✗ Batch not completed yet (status: {batch.processing_status})")
            return None

        output_path = self.output_dir / f"batch_{batch_id}_results.jsonl"

        with open(output_path, 'w') as f:
            for result in self.client.messages.batches.results(batch_id):
                f.write(json.dumps(result.model_dump()) + '\n')

        print(f"✓ Results downloaded: {output_path}")
        return str(output_path)

    def _download_openai(self, batch_id: str) -> str:
        """Download results from OpenAI batch."""
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

    def _escape_cypher(self, value: str) -> str:
        """Escape a string for Cypher embedding."""
        if not isinstance(value, str):
            return str(value)
        return value.replace('\\', '\\\\').replace("'", "\\'").replace('"', '\\"').replace('\n', ' ')

    def load_to_graph(self, fragment_id: str, doc_id: str, parsed_data: Dict[str, Any]) -> bool:
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

                # Check for errors (provider-specific)
                if self.provider == 'anthropic':
                    result_type = result.get('result', {}).get('type', '')
                    if result_type != 'succeeded':
                        print(f"  ✗ Error for {fragment_id}: {result_type}")
                        stats['failed'] += 1
                        continue
                else:
                    if result.get('error'):
                        print(f"  ✗ Error for {fragment_id}: {result['error']}")
                        stats['failed'] += 1
                        continue

                # Extract response text
                try:
                    content = extract_batch_response_text(self.provider, result)
                except (KeyError, IndexError, TypeError) as e:
                    print(f"  ⊘ No response for {fragment_id}: {e}")
                    stats['skipped'] += 1
                    continue

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

                if not parsed_data.get('entities'):
                    stats['skipped'] += 1
                    continue
                if self.load_to_graph(fragment_id, doc_id, parsed_data):
                    stats['success'] += 1
                    if stats['success'] % 100 == 0:
                        print(f"  Processed {stats['success']} entities...")
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
        description='Parse data into knowledge graph using Batch API',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Step 1: Prepare batch (test with 100 fragments)
  build-kg-parse-batch prepare --ontology ontology.yaml --limit 100

  # Step 2: Submit batch
  build-kg-parse-batch submit batch_data/batch_requests.jsonl

  # Step 3: Check status
  build-kg-parse-batch status batch_xyz123

  # Step 3b: Watch status until complete
  build-kg-parse-batch status batch_xyz123 --watch

  # Step 4: Process results
  build-kg-parse-batch process batch_xyz123 --ontology ontology.yaml
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
    prepare_parser.add_argument('--ontology', type=str, required=True, help='Path to ontology YAML file (required)')

    # Submit command
    submit_parser = subparsers.add_parser('submit', help='Submit batch to LLM provider')
    submit_parser.add_argument('batch_file', help='Path to batch JSONL file')

    # Status command
    status_parser = subparsers.add_parser('status', help='Check batch status')
    status_parser.add_argument('batch_id', help='Batch ID')
    status_parser.add_argument('--watch', action='store_true', help='Watch until complete')

    # Process command
    process_parser = subparsers.add_parser('process', help='Process batch results')
    process_parser.add_argument('batch_id', help='Batch ID')
    process_parser.add_argument('--ontology', type=str, required=True, help='Path to ontology YAML file (required)')

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    if hasattr(args, 'domain') and args.domain:
        set_profile(load_profile(args.domain))

    if args.command == 'prepare':
        ontology = load_ontology(args.ontology)
        prep = BatchPreparation(ontology=ontology)
        prep.run(limit=args.limit, offset=args.offset, output_file=args.output, jurisdiction=getattr(args, 'jurisdiction', None))

    elif args.command == 'submit':
        sub = BatchSubmission()
        sub.submit_batch(args.batch_file)

    elif args.command == 'status':
        mon = BatchMonitor()
        mon.check_status(args.batch_id, watch=args.watch)

    elif args.command == 'process':
        ontology = load_ontology(args.ontology)
        proc = BatchProcessor(ontology=ontology)
        proc.process_results(args.batch_id)


if __name__ == "__main__":
    main()
