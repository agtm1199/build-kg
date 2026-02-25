# 🧠🔗 Build-KG: Open-source Knowledge Graph Builder for AI Agents

[![GitHub Stars](https://img.shields.io/github/stars/agtm1199/build-kg?style=social)](https://github.com/agtm1199/build-kg/stargazers)
[![GitHub Forks](https://img.shields.io/github/forks/agtm1199/build-kg?style=social)](https://github.com/agtm1199/build-kg/network/members)
[![PyPI version](https://img.shields.io/badge/version-0.3.0-green.svg)](release-notes/v0.3.0.md)
[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![CI](https://github.com/agtm1199/build-kg/actions/workflows/ci.yml/badge.svg)](https://github.com/agtm1199/build-kg/actions/workflows/ci.yml)

<!-- [![Discord](https://img.shields.io/discord/YOUR_DISCORD_ID?label=Discord&logo=discord)](https://discord.gg/YOUR_INVITE) -->
<!-- [![Twitter](https://img.shields.io/twitter/follow/buildkg?style=social)](https://twitter.com/buildkg) -->

[Docs](https://agtm1199.github.io/build-kg/docs.html) | [Tutorial](https://agtm1199.github.io/build-kg/tutorial.html) | [Release Notes](release-notes/v0.3.0.md) <!-- | [Discord](https://discord.gg/YOUR_INVITE) -->

> **build-kg** turns any topic into a structured knowledge graph — stored in your own PostgreSQL. One command. Fully automated. Open-source.

## 🆕 What's New

**v0.3.0** — Generalized knowledge graph builder
- Any-topic support with automatic ontology generation
- Generic profiles with LLM-designed graph structures
- Nullable regulatory fields for non-regulatory domains
- [Full release notes →](release-notes/v0.3.0.md)

## ⚡ Quick Start

Three steps. That's it.

```bash
# 1. Clone and setup
git clone https://github.com/agtm1199/build-kg.git && cd build-kg && make setup

# 2. Configure your API key
cp .env.example .env  # edit .env → set API key + DB password

# 3. Build a knowledge graph
/build-kg kubernetes networking
```

Your coding agent handles everything autonomously:

```
  → Generates an ontology (Component, Concept, Configuration)
  → Researches authoritative sources
  → Crawls official documentation
  → Chunks documents by section boundaries
  → Loads to PostgreSQL
  → Parses with LLM into your graph
  → Outputs: queryable knowledge graph in Apache AGE
```

---

## 🤔 Why build-kg?

Building knowledge graphs is hard. The #1 pain point? **Ontology design** — figuring out the right node types, relationships, and properties for your domain.

Most tools hand you an empty graph database and say "good luck." You spend weeks modeling your domain before you can even start loading data.

**build-kg takes the opposite approach.** Tell your coding agent what you want a graph about. It designs the ontology, finds the sources, and builds the graph — all in one command. The graph lives in your own PostgreSQL. Open-source, self-hosted, no vendor lock-in.

---

## 🎯 See It In Action

```bash
/build-kg kubernetes networking
/build-kg machine learning optimization algorithms
/build-kg React architecture patterns
/build-kg distributed systems consensus algorithms
```

<details>
<summary><b>Example: "kubernetes networking"</b></summary>

The agent auto-generates this graph structure:

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

</details>

<details>
<summary><b>Example: "machine learning optimization"</b></summary>

Different topic, different ontology — auto-generated:

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

</details>

---

## ✨ Features

<details>
<summary><b>🤖 Works with 8 Coding Agent Platforms</b></summary>

build-kg is a **skill file**, not a CLI tool. It runs inside your coding agent — with native support for 8 platforms:

| Agent | Skill File | Activation |
|-------|-----------|------------|
| **Claude Code** | `.claude/skills/build-kg/SKILL.md` | Auto-detected. Type `/build-kg <topic>` |
| **Amazon Kiro** | `.claude/skills/build-kg/SKILL.md` | Auto-detected (Agent Skills standard). Type `/build-kg <topic>` |
| **Qoder** | `.claude/skills/build-kg/SKILL.md` | Auto-detected (Agent Skills standard). Type `/build-kg <topic>` |
| **Antigravity** | `.claude/skills/build-kg/SKILL.md` | Auto-detected (Agent Skills standard). Type `/build-kg <topic>` |
| **OpenAI Codex** | `AGENTS.md` | Auto-detected. Ask "build a knowledge graph about \<topic\>" |
| **GitHub Copilot** | `.github/copilot-instructions.md` | Auto-detected. Ask "build a knowledge graph about \<topic\>" |
| **Cursor** | `.cursor/rules/build-kg.mdc` | Auto-detected. Ask "build a knowledge graph about \<topic\>" |
| **Windsurf** | `.windsurf/rules/build-kg.md` | Auto-detected. Ask "build a knowledge graph about \<topic\>" |

All skill files ship with the repo — cloning is all it takes.

</details>

<details>
<summary><b>🧬 Automatic Ontology Generation</b></summary>

No more weeks of domain modeling. The agent analyzes your topic and generates:
- Node types with meaningful properties
- Relationship types that capture real connections
- A JSON schema the parser uses for structured extraction

</details>

<details>
<summary><b>🔄 6-Phase Automated Pipeline</b></summary>

```
Phase 0       Phase 0.5      Phase 1        Phase 2        Phase 3        Phase 4        Phase 5
INIT          ONTOLOGY       DISCOVER       CRAWL          CHUNK          LOAD           PARSE
--------      --------       --------       --------       --------       --------       --------
Set graph     Auto-gen       WebSearch      Crawl4AI       Unstructured   PostgreSQL     Claude Haiku 3.5
name, dirs    ontology       WebFetch       async crawl    smart chunks   + AGE          LLM extraction
```

Each phase is independently runnable and resumable.

</details>

<details>
<summary><b>🗄️ Self-Hosted PostgreSQL + Apache AGE</b></summary>

- Graph stored in your own PostgreSQL via Apache AGE extension
- Query with Cypher or SQL — no proprietary query language
- No cloud dependency, no data leaves your machine
- Docker Compose included for zero-config setup

</details>

<details>
<summary><b>📦 Domain Profiles</b></summary>

Extensible YAML profiles with custom ontologies, prompts, and source templates:

| Profile | Domain | Description |
|---------|--------|-------------|
| `default` | Generic | Any topic — ontology auto-generated by the agent |

Create custom profiles for your domain (pharma, legal, telecom, etc.) — see the [docs](https://agtm1199.github.io/build-kg/docs.html#domain-profiles).

</details>

<details>
<summary><b>💰 Minimal Cost</b></summary>

The only cost is LLM API calls during parsing. Everything else runs locally.

| Fragments | Sync | Batch (50% off) |
|-----------|------|-----------------|
| 100 | ~$0.03 | ~$0.015 |
| 1,000 | ~$0.30 | ~$0.15 |
| 5,000 | ~$1.50 | ~$0.75 |

</details>

---

## 🛠️ Installation

<details>
<summary><b>Standard Install</b></summary>

```bash
git clone https://github.com/agtm1199/build-kg.git
cd build-kg
make setup
```

```bash
cp .env.example .env
# Edit .env → set your API key and DB password
make verify
```

</details>

<details>
<summary><b>Prerequisites</b></summary>

- A coding agent: [Claude Code](https://docs.anthropic.com/en/docs/claude-code), [OpenAI Codex](https://openai.com/index/codex/), [GitHub Copilot](https://github.com/features/copilot), [Cursor](https://cursor.com), [Windsurf](https://windsurf.com), [Amazon Kiro](https://kiro.dev), [Qoder](https://qoder.com), or [Antigravity](https://idx.google.com)
- **Docker** (for PostgreSQL + Apache AGE)
- **Anthropic API key** or **OpenAI API key** (for LLM parsing)

</details>

---

## ⚙️ Configuration

All configuration is via `.env` file or environment variables:

<details>
<summary><b>View all configuration options</b></summary>

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
| `AGE_GRAPH_NAME` | `knowledge_graph` | Apache AGE graph name |
| `DOMAIN` | `default` | Domain profile name or path |

</details>

---

## 📖 Documentation

| | |
|---|---|
| [**Documentation**](https://agtm1199.github.io/build-kg/docs.html) | Complete reference — architecture, configuration, troubleshooting |
| [**Tutorial**](https://agtm1199.github.io/build-kg/tutorial.html) | Hands-on guide from setup to querying your first knowledge graph |
| [**Release Notes**](release-notes/v0.3.0.md) | What's new in v0.3.0 |

---

## 🗺️ Roadmap

- [ ] PyPI package (`pip install build-kg`)
- [ ] Web UI for graph exploration
- [ ] Multi-source graphs (combine topics into one graph)
- [ ] Incremental updates (add to existing graphs)
- [ ] More domain profiles (pharma, legal, finance, telecom)
- [ ] Graph enrichment passes (entity resolution, link prediction)

Have an idea? [Open an issue](https://github.com/agtm1199/build-kg/issues) or start a [discussion](https://github.com/agtm1199/build-kg/discussions).

---

## 🤝 Contributing

We welcome contributions of all kinds! See [CONTRIBUTING.md](CONTRIBUTING.md) for setup instructions.

**Ways to contribute:**
- **Add a domain profile** for your area (pharma, environmental, telecom, etc.)
- **Improve the pipeline** — better chunking, parsing prompts, or graph enrichment
- **Build integrations** — new agent platforms, visualization tools, export formats
- **Report bugs** and suggest features via [GitHub Issues](https://github.com/agtm1199/build-kg/issues)

---

## 📜 License

This project is licensed under the Apache License 2.0 — see the [LICENSE](LICENSE) file for details.

---

## 🏷️ Attribution

If you use build-kg in your project, consider adding a badge:

[![Built with build-kg](https://img.shields.io/badge/Built%20with-build--kg-blue)](https://github.com/agtm1199/build-kg)

```markdown
[![Built with build-kg](https://img.shields.io/badge/Built%20with-build--kg-blue)](https://github.com/agtm1199/build-kg)
```

---

## 📄 Citation

If you use build-kg in academic work:

```bibtex
@software{build-kg,
  title={build-kg: Open-source Knowledge Graph Builder for AI Agents},
  url={https://github.com/agtm1199/build-kg},
  license={Apache-2.0},
  year={2025}
}
```

---

## ⭐ Star History

If you find build-kg useful, give it a star! It helps others discover the project.

[![Star History Chart](https://api.star-history.com/svg?repos=agtm1199/build-kg&type=Date)](https://star-history.com/#agtm1199/build-kg&Date)

---

<p align="center">
  <b>build-kg</b> — turn any topic into a knowledge graph. <br/>
  Built with ❤️ for the open-source AI community.
</p>
