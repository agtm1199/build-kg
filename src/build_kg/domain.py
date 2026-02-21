"""
Domain Profile System for build-kg.

Loads YAML domain profiles that parameterize the pipeline
for different topics. All parsing is ontology-driven.
"""
import os
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import yaml
from pydantic import BaseModel, Field

# ---- Pydantic Schema Models ----


class ParsingConfig(BaseModel):
    """LLM parsing configuration from domain profile."""
    system_message: str = "You are a knowledge extraction expert. Always respond with valid JSON."
    prompt_template: Optional[str] = None
    # Legacy fields — retained so existing domain YAML files load without error.
    # Not used by the core pipeline (ontology-driven parsing only).
    requirement_types: List[str] = Field(default_factory=list)
    deontic_modalities: List[str] = Field(default_factory=list)
    constraint_logic_types: List[str] = Field(default_factory=list)
    target_signal_examples: List[str] = Field(default_factory=list)
    scope_examples: List[str] = Field(default_factory=list)


class IDPatternConfig(BaseModel):
    """Single regex pattern configuration."""
    regex: str
    flags: str = ""
    confidence: float = 0.80


class IDExtractionConfig(BaseModel):
    """ID extraction patterns from domain profile."""
    patterns: Dict[str, IDPatternConfig] = Field(default_factory=dict)
    authority_priorities: Dict[str, List[str]] = Field(default_factory=dict)
    exclusions: List[str] = Field(default_factory=lambda: [
        r"\b\d{4}\b",
        r"\b\d{1,3}%\b",
        r"\b\d+\s*(mg|g|ml|kg|mcg)\b",
        r"\b\d+\s*ppm\b",
    ])
    format_rules: Dict[str, List[str]] = Field(default_factory=dict)


class SubDomain(BaseModel):
    """A sub-domain or sub-topic within a domain."""
    name: str
    description: str = ""


class PriorityTier(BaseModel):
    """Crawl priority tier configuration."""
    description: str = ""
    depth: int = 2
    max_pages: int = 50
    delay: int = 1500


class DiscoveryConfig(BaseModel):
    """Source discovery configuration for Claude Code skill."""
    search_templates: List[str] = Field(default_factory=list)
    sub_domains: List[SubDomain] = Field(default_factory=list)
    priority_tiers: Dict[str, PriorityTier] = Field(default_factory=dict)
    gap_search_templates: List[str] = Field(default_factory=list)
    supplementary_sources: List[str] = Field(default_factory=list)


class NodeDef(BaseModel):
    """A node type in the knowledge graph ontology."""
    label: str
    description: str = ""
    properties: Dict[str, str] = Field(default_factory=dict)


class EdgeDef(BaseModel):
    """An edge type in the knowledge graph ontology."""
    label: str
    source: str
    target: str
    description: str = ""
    properties: Dict[str, str] = Field(default_factory=dict)


class OntologyConfig(BaseModel):
    """Knowledge graph ontology definition."""
    description: str = ""
    nodes: List[NodeDef] = Field(default_factory=list)
    edges: List[EdgeDef] = Field(default_factory=list)
    root_node: str = ""
    json_schema: Optional[str] = None


class DomainProfile(BaseModel):
    """Complete domain profile."""
    name: str
    description: str = ""
    version: str = "1.0"
    extends: Optional[str] = None

    parsing: ParsingConfig = Field(default_factory=ParsingConfig)
    id_patterns: IDExtractionConfig = Field(default_factory=IDExtractionConfig)
    discovery: DiscoveryConfig = Field(default_factory=DiscoveryConfig)
    ontology: OntologyConfig = Field(default_factory=OntologyConfig)


# ---- Profile Directory ----

DOMAINS_DIR = Path(__file__).parent / "domains"

# ---- Regex Flag Map ----

_FLAG_MAP = {
    'IGNORECASE': re.IGNORECASE,
    'MULTILINE': re.MULTILINE,
    'DOTALL': re.DOTALL,
}


# ---- Loader Functions ----


def _deep_merge(base: dict, override: dict) -> dict:
    """Deep-merge override into base. Override key order takes priority."""
    merged = {}
    # Override keys first (preserves child profile's intended order)
    for key, value in override.items():
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            merged[key] = _deep_merge(base[key], value)
        else:
            merged[key] = value
    # Then base-only keys
    for key, value in base.items():
        if key not in merged:
            merged[key] = value
    return merged


def _load_raw_profile(name: str) -> dict:
    """Load raw YAML dict for a named profile (no validation)."""
    path = DOMAINS_DIR / f"{name}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"Base profile not found: {path}")
    with open(path, 'r') as f:
        return yaml.safe_load(f) or {}


def load_profile(name_or_path: str) -> DomainProfile:
    """
    Load a domain profile by name or file path.

    Resolution:
    1. If name_or_path ends with .yaml/.yml, treat as file path
    2. Otherwise, look for {name}.yaml in the domains/ package directory

    If the profile declares `extends`, load the base and deep-merge.
    """
    path = Path(name_or_path)
    if path.suffix in ('.yaml', '.yml'):
        profile_path = path if path.is_absolute() else Path.cwd() / path
    else:
        profile_path = DOMAINS_DIR / f"{name_or_path}.yaml"

    if not profile_path.exists():
        raise FileNotFoundError(
            f"Domain profile not found: {profile_path}\n"
            f"Available profiles: {list_profiles()}"
        )

    with open(profile_path, 'r') as f:
        raw = yaml.safe_load(f) or {}

    if raw.get('extends'):
        base_raw = _load_raw_profile(raw['extends'])
        raw = _deep_merge(base_raw, raw)

    return DomainProfile(**raw)


def list_profiles() -> List[str]:
    """List available built-in profile names."""
    if not DOMAINS_DIR.exists():
        return []
    return sorted(p.stem for p in DOMAINS_DIR.glob("*.yaml"))


def get_default_profile_name() -> str:
    """Get the profile name from env var or default."""
    return os.getenv('DOMAIN', 'default')


# ---- Module-level Singleton ----

_active_profile: Optional[DomainProfile] = None


def get_profile() -> DomainProfile:
    """Get the active domain profile (lazy-loaded singleton)."""
    global _active_profile
    if _active_profile is None:
        _active_profile = load_profile(get_default_profile_name())
    return _active_profile


def set_profile(profile: DomainProfile) -> None:
    """Override the active domain profile."""
    global _active_profile
    _active_profile = profile


def reset_profile() -> None:
    """Reset the active profile (forces reload on next get_profile())."""
    global _active_profile
    _active_profile = None


# ---- Pattern Compilation Helpers ----


def compile_patterns(id_config: IDExtractionConfig) -> Dict[str, 're.Pattern']:
    """Compile regex patterns from profile config."""
    compiled = {}
    for name, pat_config in id_config.patterns.items():
        flags = 0
        if pat_config.flags:
            for flag_name in pat_config.flags.split('|'):
                flag_name = flag_name.strip()
                if flag_name in _FLAG_MAP:
                    flags |= _FLAG_MAP[flag_name]
        compiled[name] = re.compile(pat_config.regex, flags)
    return compiled


def compile_exclusions(exclusion_strings: List[str]) -> List['re.Pattern']:
    """Compile exclusion regex patterns."""
    return [re.compile(pattern, re.IGNORECASE) for pattern in exclusion_strings]


# ---- Shared Prompt Builder ----


def build_prompt(
    excerpt: str,
    authority: str = "",
    jurisdiction: str = "",
    profile: Optional[DomainProfile] = None,
    ontology: Optional[OntologyConfig] = None,
) -> Tuple[str, str]:
    """
    Build LLM prompt for ontology-driven knowledge extraction.

    Args:
        excerpt: Text to extract knowledge from.
        authority: Publishing organization (optional).
        jurisdiction: Geographic/topical scope (optional).
        profile: Domain profile (uses active profile if None).
        ontology: Explicit ontology (takes priority over profile ontology).

    Returns:
        (system_message, user_prompt)

    Raises:
        ValueError: If no ontology with nodes and json_schema is available.
    """
    if profile is None:
        profile = get_profile()

    effective_ontology = ontology or profile.ontology

    if not effective_ontology.nodes or not effective_ontology.json_schema:
        raise ValueError(
            "Ontology with nodes and json_schema is required. "
            "Pass --ontology <file> or use a domain profile with an ontology section."
        )

    return _build_ontology_prompt(excerpt, effective_ontology, profile.parsing, authority, jurisdiction)


def _build_ontology_prompt(
    excerpt: str,
    ontology: OntologyConfig,
    parsing: ParsingConfig,
    authority: str,
    jurisdiction: str,
) -> Tuple[str, str]:
    """Build prompt driven by an explicit ontology definition."""
    node_descriptions = "\n".join(
        f"- **{n.label}**: {n.description}" + (
            " (Properties: " + ", ".join(f"`{k}` [{v}]" for k, v in n.properties.items()) + ")"
            if n.properties else ""
        )
        for n in ontology.nodes
    )
    edge_descriptions = "\n".join(
        f"- **{e.label}**: {e.source} → {e.target} ({e.description})"
        for e in ontology.edges
    )

    source_context = ""
    if authority and jurisdiction:
        source_context = f"\n\nSource: {authority} ({jurisdiction})"
    elif authority:
        source_context = f"\n\nSource: {authority}"

    user_prompt = f"""Extract structured knowledge from the text below according to this ontology.

**Node types:**
{node_descriptions}

**Relationships:**
{edge_descriptions}
{source_context}

Text:
\"\"\"
{excerpt}
\"\"\"

Respond with valid JSON in this exact format:
{ontology.json_schema}

If no meaningful entities are found, return minimal valid JSON with empty arrays."""

    return parsing.system_message, user_prompt


def load_ontology(path: str) -> OntologyConfig:
    """Load an ontology definition from a YAML file."""
    ontology_path = Path(path)
    if not ontology_path.exists():
        raise FileNotFoundError(f"Ontology file not found: {ontology_path}")
    with open(ontology_path, 'r') as f:
        raw = yaml.safe_load(f) or {}
    return OntologyConfig(**raw)


# ---- CLI Entry Point ----


def _cli_list_profiles():
    """List available domain profiles."""
    profiles = list_profiles()
    print("Available domain profiles:\n")
    for name in profiles:
        try:
            p = load_profile(name)
            print(f"  {name:20s}  {p.description}")
        except Exception:
            print(f"  {name:20s}  (error loading)")
    print(f"\nProfile directory: {DOMAINS_DIR}")
    print("\nUsage: DOMAIN=<name> build-kg-parse ...")
    print("   or: build-kg-parse --domain <name>")
