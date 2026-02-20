#!/usr/bin/env python3
"""
Apache AGE Setup Script for Knowledge Graph
Creates the graph and initial schema from an ontology definition.
"""
import argparse
import sys
from typing import List, Optional

import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

from build_kg.config import AGE_GRAPH_NAME, DB_CONFIG
from build_kg.domain import OntologyConfig, load_ontology


def setup_age_extension():
    """Install Apache AGE extension if not already installed."""
    conn = None
    try:
        # Connect with autocommit for extension installation
        conn = psycopg2.connect(**DB_CONFIG)
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        cursor = conn.cursor()

        print("Checking for Apache AGE extension...")

        # Check if AGE is installed
        cursor.execute("SELECT extname FROM pg_extension WHERE extname = 'age';")
        if cursor.fetchone():
            print("✓ Apache AGE extension already installed")
        else:
            print("Installing Apache AGE extension...")
            try:
                cursor.execute("CREATE EXTENSION age;")
                print("✓ Apache AGE extension installed successfully")
            except psycopg2.Error as e:
                print(f"✗ Failed to install AGE extension: {e}")
                print("\nNote: You may need superuser privileges to install extensions.")
                print("Ask your DBA to run: CREATE EXTENSION age;")
                return False

        # Load AGE into search path
        cursor.execute("LOAD 'age';")
        cursor.execute("SET search_path = ag_catalog, '$user', public;")
        print("✓ AGE loaded into search path")

        cursor.close()
        conn.close()
        return True

    except psycopg2.Error as e:
        print(f"✗ Database error: {e}")
        return False
    except Exception as e:
        print(f"✗ Unexpected error: {e}")
        return False

def create_graph():
    """Create the knowledge graph."""
    conn = None
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        cursor = conn.cursor()

        # Load AGE
        cursor.execute("LOAD 'age';")
        cursor.execute("SET search_path = ag_catalog, '$user', public;")

        print(f"\nChecking for graph '{AGE_GRAPH_NAME}'...")

        # Check if graph already exists
        cursor.execute(
            "SELECT name FROM ag_catalog.ag_graph WHERE name = %s;",
            (AGE_GRAPH_NAME,)
        )

        if cursor.fetchone():
            print(f"✓ Graph '{AGE_GRAPH_NAME}' already exists")
        else:
            print(f"Creating graph '{AGE_GRAPH_NAME}'...")
            cursor.execute(f"SELECT create_graph('{AGE_GRAPH_NAME}');")
            print(f"✓ Graph '{AGE_GRAPH_NAME}' created successfully")

        cursor.close()
        conn.close()
        return True

    except psycopg2.Error as e:
        print(f"✗ Database error: {e}")
        if conn:
            conn.close()
        return False
    except Exception as e:
        print(f"✗ Unexpected error: {e}")
        if conn:
            conn.close()
        return False

def _get_node_labels(ontology: Optional[OntologyConfig]) -> List[str]:
    """Get vertex labels from ontology or use legacy defaults."""
    if ontology and ontology.nodes:
        return [node.label for node in ontology.nodes]
    return ['RegulatorySource', 'Provision', 'Requirement', 'Constraint']


def create_graph_schema(ontology: Optional[OntologyConfig] = None):
    """Create initial graph schema (vertex and edge labels)."""
    conn = None
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        cursor = conn.cursor()

        # Load AGE
        cursor.execute("LOAD 'age';")
        cursor.execute("SET search_path = ag_catalog, '$user', public;")

        print("\nCreating graph schema...")

        labels = _get_node_labels(ontology)

        # Create sample vertices to establish labels
        # Note: AGE creates labels automatically when first used
        for label in labels:
            query = f"""
            SELECT * FROM cypher('{AGE_GRAPH_NAME}', $$
                MERGE (n:{label} {{id: '_schema_init'}})
                RETURN n
            $$) as (v agtype);
            """
            cursor.execute(query)

        # Clean up schema init nodes
        cursor.execute(f"""
            SELECT * FROM cypher('{AGE_GRAPH_NAME}', $$
                MATCH (n {{id: '_schema_init'}})
                DELETE n
            $$) as (v agtype);
        """)

        print("✓ Graph schema initialized")
        print("\nVertex labels created:")
        for label in labels:
            print(f"  • {label}")

        cursor.close()
        conn.close()
        return True

    except psycopg2.Error as e:
        print(f"✗ Database error: {e}")
        if conn:
            conn.close()
        return False
    except Exception as e:
        print(f"✗ Unexpected error: {e}")
        if conn:
            conn.close()
        return False

def main():
    """Main setup routine."""
    parser = argparse.ArgumentParser(description='Setup Apache AGE graph')
    parser.add_argument(
        '--ontology',
        help='Path to ontology YAML file for custom node labels'
    )
    args = parser.parse_args()

    ontology = None
    if args.ontology:
        ontology = load_ontology(args.ontology)
        print(f"Using ontology: {ontology.description or args.ontology}")

    print("=" * 70)
    print("Apache AGE Setup for Knowledge Graph")
    print("=" * 70)

    # Step 1: Install AGE extension
    if not setup_age_extension():
        print("\n✗ Setup failed at extension installation")
        sys.exit(1)

    # Step 2: Create graph
    if not create_graph():
        print("\n✗ Setup failed at graph creation")
        sys.exit(1)

    # Step 3: Create schema
    if not create_graph_schema(ontology):
        print("\n✗ Setup failed at schema creation")
        sys.exit(1)

    print("\n" + "=" * 70)
    print("✓ Setup completed successfully!")
    print(f"Graph '{AGE_GRAPH_NAME}' is ready for use")
    print("=" * 70)

if __name__ == "__main__":
    main()
