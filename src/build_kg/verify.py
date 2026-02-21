#!/usr/bin/env python3
"""
Setup Verification Script
Verifies database connection, AGE installation, and LLM API access.
"""
import sys

from build_kg.config import AGE_GRAPH_NAME, DB_CONFIG
from build_kg.llm import create_client, get_provider_config


def verify_database():
    """Verify database connection."""
    print("1. Verifying database connection...")
    try:
        import psycopg2
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()
        cursor.execute("SELECT version();")
        version = cursor.fetchone()[0]
        print("   ✓ Connected to PostgreSQL")
        print(f"     Version: {version.split(',')[0]}")
        cursor.close()
        conn.close()
        return True
    except Exception as e:
        print(f"   ✗ Database connection failed: {e}")
        return False

def verify_age():
    """Verify AGE extension."""
    print("\n2. Verifying Apache AGE extension...")
    try:
        import psycopg2
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()

        # Check extension
        cursor.execute("SELECT extname, extversion FROM pg_extension WHERE extname = 'age';")
        result = cursor.fetchone()

        if not result:
            print("   ✗ AGE extension not installed")
            print("     Run: build-kg-setup")
            cursor.close()
            conn.close()
            return False

        print(f"   ✓ AGE extension installed (version {result[1]})")

        # Check graph
        cursor.execute("LOAD 'age';")
        cursor.execute("SET search_path = ag_catalog, '$user', public;")
        cursor.execute(f"SELECT name FROM ag_catalog.ag_graph WHERE name = '{AGE_GRAPH_NAME}';")

        if cursor.fetchone():
            print(f"   ✓ Graph '{AGE_GRAPH_NAME}' exists")
        else:
            print(f"   ✗ Graph '{AGE_GRAPH_NAME}' not found")
            print("     Run: build-kg-setup")
            cursor.close()
            conn.close()
            return False

        cursor.close()
        conn.close()
        return True

    except Exception as e:
        print(f"   ✗ AGE verification failed: {e}")
        return False

def verify_source_data():
    """Verify source data tables."""
    print("\n3. Verifying source data...")
    try:
        import psycopg2
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()

        # Check source_fragment table
        cursor.execute("SELECT COUNT(*) FROM source_fragment WHERE excerpt IS NOT NULL;")
        fragment_count = cursor.fetchone()[0]

        print(f"   ✓ Found {fragment_count:,} fragments with excerpts")

        # Check source_document table
        cursor.execute("SELECT COUNT(*) FROM source_document;")
        doc_count = cursor.fetchone()[0]

        print(f"   ✓ Found {doc_count:,} source documents")

        cursor.close()
        conn.close()
        return True

    except Exception as e:
        print(f"   ✗ Source data verification failed: {e}")
        return False

def verify_llm():
    """Verify LLM API access for the configured provider."""
    provider, api_key, model = get_provider_config()
    print(f"\n4. Verifying LLM API access ({provider})...")

    if not api_key:
        key_name = 'ANTHROPIC_API_KEY' if provider == 'anthropic' else 'OPENAI_API_KEY'
        print(f"   ✗ {key_name} not configured")
        print(f"     Set {key_name} in .env file")
        return False

    try:
        client = create_client(provider, api_key)

        if provider == 'anthropic':
            client.messages.create(
                model=model,
                max_tokens=5,
                messages=[{"role": "user", "content": "Hello"}],
            )
        else:
            client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": "Hello"}],
                max_tokens=5,
            )

        print(f"   ✓ {provider.title()} API connection successful")
        print(f"     Model: {model}")
        return True

    except Exception as e:
        print(f"   ✗ {provider.title()} API verification failed: {e}")
        print("     Check your API key in .env file")
        return False

def main():
    """Run all verification checks."""
    print("=" * 70)
    print("Setup Verification")
    print("=" * 70)

    checks = [
        verify_database(),
        verify_age(),
        verify_source_data(),
        verify_llm(),
    ]

    print("\n" + "=" * 70)

    if all(checks):
        print("✓ All checks passed! System is ready.")
        print("\nYou can now run:")
        print("  build-kg-parse --test")
        print("=" * 70)
        sys.exit(0)
    else:
        print("✗ Some checks failed. Please fix the issues above.")
        print("=" * 70)
        sys.exit(1)

if __name__ == "__main__":
    main()
