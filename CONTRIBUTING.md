# Contributing to build-kg

Thanks for considering contributing to build-kg! This project turns any topic into a structured knowledge graph on your own PostgreSQL, and there are many ways to help -- from adding domain profiles to improving the pipeline itself.

## Ways to Contribute

| Contribution | Difficulty | Impact |
|-------------|-----------|--------|
| **Add a domain profile** for your industry | Low | High -- unlocks a new domain with pre-built ontology |
| **Add ID extraction patterns** for a jurisdiction | Low | Medium -- improves provision ID quality |
| **Fix a bug** | Varies | High |
| **Improve documentation** | Low | Medium |
| **Add a new jurisdiction** | Low | Medium -- expands country support |
| **Improve chunking or parsing** | Medium-High | High -- better graph quality |
| **Improve ontology generation** | Medium | High -- better auto-generated graph structures |

## Development Setup

```bash
# 1. Fork and clone the repository
git clone https://github.com/YOUR_USERNAME/build-kg.git
cd build-kg

# 2. Create a virtual environment
python3 -m venv venv
source venv/bin/activate

# 3. Install in development mode
pip install -e ".[dev]"

# 4. Install the browser for crawling
crawl4ai-setup

# 5. Start the database
docker compose -f db/docker-compose.yml up -d

# 6. Configure environment
cp .env.example .env
# Edit .env with your settings

# 7. Initialize the graph
python -m build_kg.setup_graph

# 8. Run tests to verify
pytest tests/ -v
```

## Project Structure

```
build-kg/
├── src/build_kg/          # Main package
│   ├── config.py          # Configuration from .env
│   ├── crawl.py           # Web crawler (Crawl4AI)
│   ├── chunk.py           # Document chunker (Unstructured)
│   ├── load.py            # Database loader
│   ├── parse.py           # Sync parser (OpenAI)
│   ├── parse_batch.py     # Batch parser (OpenAI Batch API)
│   ├── setup_graph.py     # AGE graph setup
│   ├── verify.py          # Setup verification
│   ├── id_extractors.py   # Regex-based ID extraction
│   ├── domain.py          # Domain profile system
│   └── domains/           # YAML domain profiles
│       ├── default.yaml
│       ├── food-safety.yaml
│       ├── financial-aml.yaml
│       └── data-privacy.yaml
├── db/                    # Database setup
├── docs/                  # Documentation
├── examples/              # Example manifests and data
├── tests/                 # Test suite
└── .claude/commands/      # Claude Code skill
```

## Code Style

We use [Ruff](https://docs.astral.sh/ruff/) for linting:

```bash
# Check for issues
ruff check src/ tests/

# Auto-fix what's possible
ruff check --fix src/ tests/
```

- Line length: 120 characters
- Rules: E (pycodestyle errors), F (pyflakes), I (isort), W (pycodestyle warnings)

## Running Tests

```bash
# Run all tests
pytest tests/ -v

# Run a specific test file
pytest tests/test_id_extractors.py -v

# Run domain profile tests
pytest tests/test_domain.py -v
```

Tests are designed to run without a database connection. Integration tests that require a running database are skipped automatically if the DB is not available.

## Pull Request Process

1. **Fork** the repository and create a feature branch from `main`
2. **Make your changes** and ensure tests pass
3. **Run the linter**: `ruff check src/ tests/`
4. **Write tests** for new functionality
5. **Submit a PR** with a clear description of what changed and why

## Adding a New Domain Profile

This is one of the highest-impact contributions you can make. Each new profile unlocks build-kg for an entirely new domain with a pre-built ontology.

1. Create `src/build_kg/domains/your-domain.yaml` using `food-safety.yaml` as a template
2. Set `extends: default` to inherit base configuration
3. Define domain-specific configuration:

   **Ontology** -- the graph structure:
   - `ontology.nodes` -- node types with labels, descriptions, and properties
   - `ontology.edges` -- edge types with source/target labels and descriptions
   - `ontology.root_node` -- primary node type that maps 1:1 to source fragments
   - `ontology.json_schema` -- expected LLM output JSON format

   **Parsing** -- what the LLM extracts:
   - `parsing.requirement_types` -- e.g., `[consent, data_processing, breach_notification]` for privacy
   - `parsing.target_signal_examples` -- e.g., `[data.retention_period, consent.mechanism]`
   - `parsing.scope_examples` -- e.g., `[data_controller, data_processor, data_subject]`

   **ID Patterns** -- regex for domain-specific IDs:
   - `id_patterns.patterns` -- e.g., GDPR Article patterns, FATF Recommendation patterns
   - `id_patterns.authority_priorities` -- which patterns to try first for each authority

   **Discovery** -- how the `/build-kg` skill finds sources:
   - `discovery.search_templates` -- search queries for finding sources
   - `discovery.sub_domains` -- checklist of sub-areas to cover

4. Add tests to `tests/test_domain.py` to verify the profile loads correctly
5. Update the profile table in `README.md`
6. Test with `build-kg-parse --domain your-domain --test`

**Example profile ideas:**
- `pharma` -- FDA drug regulations, clinical trial requirements, GMP
- `environmental` -- EPA regulations, emissions standards, waste management
- `telecom` -- FCC rules, spectrum licensing, net neutrality
- `construction` -- building codes, safety standards, permits
- `aviation` -- FAA regulations, airworthiness, pilot licensing
- `maritime` -- IMO conventions, port state control, SOLAS

## Adding a New Jurisdiction

The `jurisdiction` field is a freeform TEXT column in the database, so no schema changes are needed to support a new country. To add support for a new jurisdiction:

1. Add authority-specific regex patterns to `src/build_kg/id_extractors.py` if the jurisdiction uses a unique ID format
2. Update the jurisdiction list in `.claude/commands/build-kg.md`

## Adding ID Extraction Patterns

To add new regex patterns for regulatory ID formats:

1. Edit `src/build_kg/id_extractors.py`
2. Add patterns to `ProvisionIDExtractor.PATTERNS`:
   ```python
   'your_pattern_name': re.compile(r'your_regex_here'),
   ```
3. Add authority mapping to `AUTHORITY_PATTERNS`:
   ```python
   'Authority Name': ['your_pattern_name', 'other_patterns'],
   ```
4. Add format rules to `ProvisionIDValidator.FORMAT_RULES` (optional)
5. Add test cases to `tests/test_id_extractors.py`

## Reporting Issues

When reporting a bug, please include:

- **What happened**: Describe the error or unexpected behavior
- **What you expected**: What should have happened instead
- **How to reproduce**: Step-by-step commands to reproduce the issue
- **Environment**: Python version, OS, Docker version
- **Error output**: Full traceback or error message

## Code of Conduct

We follow the [Contributor Covenant Code of Conduct](https://www.contributor-covenant.org/version/2/1/code_of_conduct/). Be kind, be respectful, be constructive.
