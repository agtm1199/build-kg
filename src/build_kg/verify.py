#!/usr/bin/env python3
"""
Setup Verification Script
Verifies database connection, AGE installation, and OpenAI API access.
"""
import sys

from build_kg.config import AGE_GRAPH_NAME, DB_CONFIG, OPENAI_API_KEY


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

def verify_openai():
    """Verify OpenAI API access."""
    print("\n4. Verifying OpenAI API access...")

    if not OPENAI_API_KEY or OPENAI_API_KEY == 'your_openai_api_key_here':
        print("   ✗ OpenAI API key not configured")
        print("     Set OPENAI_API_KEY in .env file")
        return False

    try:
        from openai import OpenAI
        client = OpenAI(api_key=OPENAI_API_KEY)

        # Test with minimal request
        client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": "Hello"}],
            max_tokens=5
        )

        print("   ✓ OpenAI API connection successful")
        print("     Model: gpt-4o-mini")
        return True

    except Exception as e:
        print(f"   ✗ OpenAI API verification failed: {e}")
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
        verify_openai(),
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
