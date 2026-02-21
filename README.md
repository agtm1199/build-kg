# build-kg

[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![CI](https://github.com/agtm1199/build-kg/actions/workflows/ci.yml/badge.svg)](https://github.com/agtm1199/build-kg/actions/workflows/ci.yml)

**One command. Any topic. Knowledge graph in your own PostgreSQL.**

build-kg is a skill for coding agents that turns any topic into a structured knowledge graph stored in Apache AGE (PostgreSQL). Works with [Claude Code](https://docs.anthropic.com/en/docs/claude-code), [OpenAI Codex](https://openai.com/index/codex/), and other agent platforms that support skill files.

```
/build-kg kubernetes networking

Your coding agent autonomously:
  -> Generates an ontology (Component, Concept, Configuration)
  -> Researches authoritative sources (5-round discovery)
  -> Crawls official documentation
  -> Chunks documents by section boundaries
  -> Loads to PostgreSQL
  -> Parses with LLM into your graph
  -> Outputs: queryable knowledge graph in Apache AGE
```

## The Problem

Building knowledge graphs is hard. The #1 pain point? **Ontology design** — figuring out the right node types, relationships, and properties for your domain.

**build-kg solves this.** Your coding agent automatically generates the ontology for your topic, and the graph lives in your own PostgreSQL. Open-source, self-hosted, no vendor lock-in.

## What You Get

```
/build-kg React architecture patterns
/build-kg machine learning optimization algorithms
/build-kg React architecture patterns
/build-kg kubernetes networking
```

For **"kubernetes networking"**, the agent generates:
```
Component              "kube-proxy"
  |                    type: proxy, layer: L4
  |
  +-- USES ----------> Concept: "iptables"
  |                    category: packet filtering
  |
  +-- CONFIGURES ----> Configuration: "service.spec.type"
                       default_value: ClusterIP, scope: service
```

For **"machine learning optimization"**, the agent generates:
```
Algorithm              "Adam optimizer"
  |                    type: gradient-based, family: adaptive
  |
  +-- APPLIES -------> Technique: "momentum"
  |                    category: first-order
  |
  +-- USED_IN -------> Application: "neural network training"
                       domain: deep learning
```

## Features

- **Skill for coding agents** — works with Claude Code, OpenAI Codex, and compatible platforms
- **Full automation** — one skill command runs the entire pipeline end-to-end
- **Automatic ontology generation** — the agent designs the graph structure for your topic
- **Any topic** — technical, scientific, educational, or anything else
- **Self-hosted** — Apache AGE graph in your own PostgreSQL, no external services
- **Batch API support** for 50% cheaper processing of large datasets
- **Domain profiles** — extensible YAML profiles with custom ontologies
- **Open source** — Apache 2.0, no vendor lock-in, no hosting fees

## Quickstart

### Prerequisites

- A coding agent that supports skills ([Claude Code](https://docs.anthropic.com/en/docs/claude-code), [OpenAI Codex](https://openai.com/index/codex/), etc.)
- **Docker** (for PostgreSQL + Apache AGE)
- **Anthropic API key** or **OpenAI API key** (for LLM parsing)

### Install

```bash
git clone https://github.com/agtm1199/build-kg.git
cd build-kg
make setup
```

```bash
# Configure
cp .env.example .env
# Edit .env and set your API key and DB password

# Verify everything works
make verify
```

### Use the skill

The `/build-kg` skill is included in the repository and activates automatically:

| Agent | Skill file | Activation |
|-------|-----------|------------|
| **Claude Code** | `.claude/skills/build-kg/SKILL.md` | Auto-detected. Type `/build-kg <topic>` |
| **OpenAI Codex** | `AGENTS.md` | Auto-detected. Ask "build a knowledge graph about \<topic\>" |
| **Other agents** | Either file | Point your agent at `.claude/skills/build-kg/SKILL.md` or `AGENTS.md` |

```
/build-kg kubernetes networking
/build-kg distributed systems consensus algorithms
/build-kg machine learning optimization algorithms
```

The agent runs all phases autonomously — generating the ontology, researching sources, crawling, chunking, loading, parsing, and reporting.

## Pipeline

```
Phase 0       Phase 0.5      Phase 1        Phase 2        Phase 3        Phase 4        Phase 5
INIT          ONTOLOGY       DISCOVER       CRAWL          CHUNK          LOAD           PARSE
--------      --------       --------       --------       --------       --------       --------
Set graph     Auto-gen       WebSearch      Crawl4AI       Unstructured   PostgreSQL     Claude Haiku 3.5
name, dirs    ontology       WebFetch       async crawl    smart chunks   + AGE          LLM extraction
```

## Domain Profiles

build-kg supports specialized domains through YAML profiles. Each profile configures the ontology, LLM prompt, and source discovery templates.

| Profile | Domain | Description |
|---------|--------|-------------|
| `default` | Generic | Any topic — ontology auto-generated by the agent |

Create custom profiles with your own ontology — see the [documentation](docs/docs.html#domain-profiles) for details.

## Configuration

All configuration is via `.env` file or environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `LLM_PROVIDER` | `anthropic` | LLM provider (`anthropic` or `openai`) |
| `ANTHROPIC_API_KEY` | -- | Anthropic API key |
| `ANTHROPIC_MODEL` | `claude-haiku-4-5-20251001` | Anthropic model for parsing |
| `OPENAI_API_KEY` | -- | OpenAI API key (if using OpenAI) |
| `OPENAI_MODEL` | `gpt-4o-mini` | OpenAI model for parsing |
| `DB_HOST` | `localhost` | PostgreSQL host |
| `DB_PORT` | `5432` | PostgreSQL port |
| `DB_NAME` | `buildkg` | Database name |
| `DB_USER` | `buildkg` | Database user |
| `DB_PASSWORD` | -- | Database password (**required**) |
| `AGE_GRAPH_NAME` | `reg_ca` | Apache AGE graph name |
| `DOMAIN` | `default` | Domain profile name or path |

## Cost

The only cost is LLM API calls during parsing. Everything else runs locally.

| Fragments | Sync | Batch (50% off) |
|-----------|------|-----------------|
| 100 | ~$0.03 | ~$0.015 |
| 1,000 | ~$0.30 | ~$0.15 |
| 5,000 | ~$1.50 | ~$0.75 |

## Documentation

| Doc | Description |
|-----|-------------|
| [Documentation](docs/docs.html) | Complete reference: architecture, configuration, troubleshooting |
| [Tutorial](docs/tutorial.html) | Hands-on guide from setup to querying your first knowledge graph |

## Contributing

We welcome contributions! See [CONTRIBUTING.md](CONTRIBUTING.md) for setup instructions.

- **Add a domain profile** for your area (pharma, environmental, telecom, etc.)
- **Improve the pipeline** with better chunking strategies, parsing prompts, or graph enrichment
- **Report bugs** and suggest features via [GitHub Issues](https://github.com/agtm1199/build-kg/issues)

## License

Apache 2.0 -- see [LICENSE](LICENSE) for details.
