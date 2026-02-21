# Troubleshooting

Common errors and their solutions when running the build-kg pipeline.

## Quick Reference

| Error | Phase | Solution |
|-------|-------|----------|
| Connection refused on port 5432 | Any DB operation | Start the database container |
| relation "source_fragment" does not exist | Load / Parse | Run the init SQL or recreate the container |
| AGE extension not found | Setup / Parse | Run `build-kg-setup` |
| API authentication error 401 | Parse | Check `ANTHROPIC_API_KEY` (or `OPENAI_API_KEY`) in `.env` |
| Chromium not found | Crawl | Run `crawl4ai-setup` |
| No fragments found | Parse | Verify the database load succeeded |
| Batch still in "validating" | Batch Parse | Wait; batches take 1-24 hours |
| UNKNOWN authority on all provisions | Parse | Check metadata and source matching |
| PDF support not installed | Chunk | Install the `[pdf]` extra |
| Ontology file not found | Parse / Setup | Check `--ontology` path is correct |
| Empty entities in LLM output | Parse (ontology) | LLM found nothing extractable; check text quality |

---

## Detailed Solutions

### Connection refused on port 5432

**Symptom:**

```
psycopg2.OperationalError: could not connect to server: Connection refused
    Is the server running on host "localhost" and accepting TCP/IP connections on port 5432?
```

**Cause:** The PostgreSQL + Apache AGE Docker container is not running.

**Fix:**

```bash
# Start the database
docker compose -f db/docker-compose.yml up -d

# Check it is running and healthy
docker compose -f db/docker-compose.yml ps

# If the container exists but is stopped
docker compose -f db/docker-compose.yml start
```

If the container is running but you still cannot connect, check:
- Is another PostgreSQL instance using port 5432? Change `DB_PORT` in `.env`.
- Are you running inside a VM or container? Use the correct host IP instead of `localhost`.

---

### relation "source_fragment" does not exist

**Symptom:**

```
psycopg2.errors.UndefinedTable: relation "source_fragment" does not exist
```

**Cause:** The database tables were not created. This happens if:
- The Docker container was started without the init script running.
- The database volume was reset but the container was not recreated.

**Fix:**

```bash
# Option 1: Reset the database (destroys all data)
make db-reset

# Option 2: Run init.sql manually
docker exec -i build-kg-db psql -U buildkg -d buildkg < db/init.sql
```

Verify:

```bash
docker exec build-kg-db psql -U buildkg -d buildkg -c "\dt"
```

You should see `source_document` and `source_fragment` in the table list.

---

### AGE extension not found

**Symptom:**

```
ERROR: extension "age" is not available
```

or

```
ERROR: could not open extension control file "/usr/share/postgresql/16/extension/age.control": No such file
```

**Cause:** The Apache AGE extension is not installed in the PostgreSQL instance. This usually means you are connecting to a standard PostgreSQL instance instead of the Apache AGE Docker image.

**Fix:**

```bash
# Make sure you are using the Apache AGE Docker image
docker compose -f db/docker-compose.yml up -d

# Then run setup
build-kg-setup
# or
python -m build_kg.setup_graph
```

The `apache/age` Docker image includes the AGE extension pre-installed. If you are using a different PostgreSQL instance, you need to install AGE manually following the [Apache AGE installation guide](https://age.apache.org/age-manual/master/intro/setup.html).

---

### API Authentication Error 401

**Symptom (Anthropic):**

```
anthropic.AuthenticationError: Error code: 401 - {'error': {'message': 'Invalid API key', 'type': 'authentication_error'}}
```

**Symptom (OpenAI):**

```
openai.AuthenticationError: Error code: 401 - {'error': {'message': 'Incorrect API key provided: sk-...', 'type': 'invalid_request_error'}}
```

**Cause:** The API key is missing, incorrect, or expired.

**Fix:**

1. Check your `.env` file for the correct provider key:

```bash
# If using Anthropic (default)
grep ANTHROPIC_API_KEY .env

# If using OpenAI
grep OPENAI_API_KEY .env
```

2. Make sure the key is set and is not the placeholder value:

```
# Anthropic (default)
ANTHROPIC_API_KEY=sk-ant-your-actual-key-here

# OpenAI (alternative)
OPENAI_API_KEY=sk-your-actual-key-here
```

3. Verify the key works:

```bash
build-kg-verify
```

4. If the key is correct but still fails, check your account for billing issues or key revocation at [console.anthropic.com](https://console.anthropic.com) (Anthropic) or [platform.openai.com/api-keys](https://platform.openai.com/api-keys) (OpenAI).

---

### Chromium not found

**Symptom:**

```
playwright._impl._errors.Error: Executable doesn't exist at /home/user/.cache/ms-playwright/chromium-xxx/chrome-linux/chrome
```

or

```
crawl4ai: Browser not found. Please run crawl4ai-setup first.
```

**Cause:** The Crawl4AI Chromium browser was not installed.

**Fix:**

```bash
# Make sure the virtual environment is active
source venv/bin/activate

# Install Chromium
crawl4ai-setup
```

If `crawl4ai-setup` fails:
- Check disk space (Chromium requires ~400MB).
- On some Linux distributions, you may need additional libraries: `sudo apt install libnss3 libatk-bridge2.0-0 libdrm2 libxcomposite1 libxdamage1 libxrandr2 libgbm1 libpango-1.0-0 libcairo2 libasound2`

---

### No fragments found

**Symptom:**

```
Fetching fragments (limit=None, offset=0, jurisdiction=None)...
Found 0 fragments to process
No fragments to process!
```

**Cause:** The `source_fragment` table is empty. Either `build-kg-load` was not run, or it failed silently.

**Fix:**

1. Check the fragment count:

```bash
python3 -c "
import psycopg2
from build_kg.config import DB_CONFIG
conn = psycopg2.connect(**DB_CONFIG)
cur = conn.cursor()
cur.execute('SELECT COUNT(*) FROM source_fragment')
print(f'Fragments: {cur.fetchone()[0]}')
cur.execute('SELECT COUNT(*) FROM source_document')
print(f'Documents: {cur.fetchone()[0]}')
conn.close()
"
```

2. If both are 0, re-run the loader:

```bash
build-kg-load ./chunk_output/ --manifest ./crawl_manifest.json
```

3. If the loader reports 0 chunks found, check that the chunk directory contains `*_chunk_*.json` files:

```bash
find ./chunk_output/ -name "*_chunk_*.json" | wc -l
```

4. If you filtered by jurisdiction (e.g., `--jurisdiction SG`), make sure the loaded fragments have that jurisdiction. Check:

```sql
SELECT jurisdiction, COUNT(*) FROM source_fragment GROUP BY jurisdiction;
```

---

### Batch still in "validating"

**Symptom:**

```
Batch ID: batch_abc123def456
Status: validating
```

**Cause:** The provider is still validating the batch input file. This is normal behavior.

**Fix:** Wait. Batches can take 1-24 hours to complete. Validation itself usually takes a few minutes but can be longer during high-demand periods.

Monitor with:

```bash
build-kg-parse-batch status batch_abc123def456 --watch
```

If the batch stays in "validating" for more than 1 hour, check:
- The JSONL file for formatting errors (each line must be valid JSON)
- Your provider account for any rate limit or quota issues

---

### UNKNOWN authority on all provisions

**Symptom:** All or most provisions in the graph have `authority: "UNKNOWN"` or the authority does not match expectations.

**Cause:** The loader could not match chunk file paths to sources in the manifest, so it used the defaults. This happens when:
- The `source_name` in the manifest does not match the directory structure of the chunks.
- The chunks were reorganized after crawling.

**Fix:**

1. Check the manifest `source_name` values match the crawl output directory names:

```bash
# Manifest source names
python3 -c "
import json
manifest = json.load(open('crawl_manifest.json'))
for s in manifest['sources']:
    print(s['source_name'])
"

# Chunk directory names
ls chunk_output/
```

2. Ensure each `source_name` appears as a directory name in `chunk_output/`.

3. If you need to re-load, reset the relevant data and re-run:

```bash
# Reset all fragments and documents (careful -- this deletes all loaded data)
docker exec build-kg-db psql -U buildkg -d buildkg -c "TRUNCATE source_fragment CASCADE; TRUNCATE source_document CASCADE;"

# Re-run the loader
build-kg-load ./chunk_output/ --manifest ./crawl_manifest.json
```

---

### PDF support not installed

**Symptom:**

```
ERROR: PDF support not installed (missing unstructured[pdf])
```

**Cause:** The `unstructured[pdf]` extra is not installed.

**Fix:**

```bash
make setup
```

For OCR-based PDF extraction, you also need system packages:

```bash
# Ubuntu/Debian
sudo apt install poppler-utils tesseract-ocr

# macOS
brew install poppler tesseract

# Fedora/RHEL
sudo dnf install poppler-utils tesseract
```

---

### Graph loading failed: syntax error

**Symptom:**

```
Graph loading failed: syntax error at or near "'"
```

**Cause:** The regulatory text contains unescaped single quotes or special characters that break the Cypher query.

**Fix:** This is usually handled by the parser's escape function, but extremely unusual text (e.g., nested quotes, backslashes in regex patterns) can still cause issues. The parser will skip the fragment and continue. Check the failure count in the summary.

If this affects many fragments, it may indicate a systematic issue with the source text. Check the crawled markdown for encoding problems.

---

### DB_PASSWORD is required

**Symptom:**

```
ValueError: Configuration errors: DB_PASSWORD is required
```

**Cause:** The `.env` file is missing or the `DB_PASSWORD` variable is not set.

**Fix:**

```bash
# Copy the example
cp .env.example .env

# The default password matches the Docker container
# DB_PASSWORD=buildkg_dev
```

Make sure your `.env` file is in the project root directory (same level as `pyproject.toml`) or in your current working directory.

---

### Ontology file not found

**Symptom:**

```
FileNotFoundError: Ontology file not found: ./ontology.yaml
```

**Cause:** The `--ontology` flag points to a file that does not exist.

**Fix:**

If you are using the Claude Code `/build-kg` skill, the ontology file is auto-generated during Phase 0.5. If running manually, create an ontology YAML file or use a domain profile that has a built-in ontology (e.g., `--domain food-safety`).

---

### Empty entities in LLM output (ontology mode)

**Symptom:** The parser reports many fragments as "skipped" with 0 entities extracted.

**Cause:** The LLM could not extract meaningful entities from the text. This can happen when:
- The text is too short or generic (e.g., navigation text, boilerplate)
- The ontology node types don't match the content well
- The chunking produced fragments that are too small to contain useful information

**Fix:**

1. Check that your ontology node types are appropriate for the source content.
2. Try increasing `--max-chars` during chunking to produce larger, more informative fragments.
3. Review the auto-generated ontology and adjust node/edge definitions if needed.

---

## Getting Help

If your issue is not listed here:

1. Run `build-kg-verify` to check the overall system health.
2. Check the Docker container logs: `docker compose -f db/docker-compose.yml logs`
3. Open an issue at [github.com/agtm1199/build-kg/issues](https://github.com/agtm1199/build-kg/issues) with:
   - The exact error message
   - The command you ran
   - Your Python version (`python3 --version`)
   - Your OS (`uname -a`)
