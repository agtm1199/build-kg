"""Tests for domain profile loading and validation."""
import pytest

from build_kg.domain import (
    DOMAINS_DIR,
    DomainProfile,
    EdgeDef,
    NodeDef,
    OntologyConfig,
    build_prompt,
    get_profile,
    list_profiles,
    load_profile,
    reset_profile,
    set_profile,
)


class TestProfileDiscovery:
    def test_domains_dir_exists(self):
        assert DOMAINS_DIR.exists()
        assert DOMAINS_DIR.is_dir()

    def test_list_profiles_returns_builtin(self):
        profiles = list_profiles()
        assert "default" in profiles
        assert "food-safety" in profiles
        assert "financial-aml" in profiles
        assert "data-privacy" in profiles

    def test_list_profiles_returns_at_least_four(self):
        assert len(list_profiles()) >= 4


class TestProfileLoading:
    def test_load_food_safety(self):
        profile = load_profile("food-safety")
        assert profile.name == "Food Safety & Labeling"
        assert profile.version in ("1.0", "2.0")

    def test_load_default(self):
        profile = load_profile("default")
        assert "Default" in profile.name

    def test_load_financial_aml(self):
        profile = load_profile("financial-aml")
        assert "Financial" in profile.name or "AML" in profile.name

    def test_load_data_privacy(self):
        profile = load_profile("data-privacy")
        assert "Privacy" in profile.name or "Data" in profile.name

    def test_load_nonexistent_raises(self):
        with pytest.raises(FileNotFoundError):
            load_profile("nonexistent-domain")

    def test_load_by_path(self, tmp_path):
        profile_file = tmp_path / "custom.yaml"
        profile_file.write_text(
            'name: "Custom"\ndescription: "test"\nversion: "1.0"\n'
        )
        profile = load_profile(str(profile_file))
        assert profile.name == "Custom"


class TestProfileInheritance:
    def test_food_safety_inherits_deontic_modalities(self):
        profile = load_profile("food-safety")
        assert len(profile.parsing.deontic_modalities) >= 5
        assert "must" in profile.parsing.deontic_modalities

    def test_food_safety_inherits_constraint_logic_types(self):
        profile = load_profile("food-safety")
        assert "threshold" in profile.parsing.constraint_logic_types
        assert "boolean" in profile.parsing.constraint_logic_types

    def test_food_safety_overrides_requirement_types(self):
        profile = load_profile("food-safety")
        assert "labelling" in profile.parsing.requirement_types
        # Should NOT have default's generic types
        assert "obligation" not in profile.parsing.requirement_types

    def test_financial_aml_overrides_requirement_types(self):
        profile = load_profile("financial-aml")
        assert "monitoring" in profile.parsing.requirement_types
        assert "labelling" not in profile.parsing.requirement_types


class TestParsingConfig:
    def test_food_safety_has_food_specific_types(self):
        profile = load_profile("food-safety")
        types = profile.parsing.requirement_types
        assert "labelling" in types
        assert "composition" in types

    def test_financial_aml_has_aml_specific_types(self):
        profile = load_profile("financial-aml")
        types = profile.parsing.requirement_types
        assert "monitoring" in types
        assert "reporting" in types

    def test_data_privacy_has_privacy_specific_types(self):
        profile = load_profile("data-privacy")
        types = profile.parsing.requirement_types
        assert "consent" in types
        assert "breach_notification" in types

    def test_system_message_is_nonempty(self):
        for name in list_profiles():
            profile = load_profile(name)
            assert len(profile.parsing.system_message) > 10


class TestIDPatterns:
    def test_food_safety_has_cfia_patterns(self):
        profile = load_profile("food-safety")
        assert "cfia_bdot" in profile.id_patterns.patterns
        assert "cfia_cdot" in profile.id_patterns.patterns

    def test_food_safety_has_authority_priorities(self):
        profile = load_profile("food-safety")
        assert "CFIA" in profile.id_patterns.authority_priorities

    def test_default_has_empty_patterns(self):
        """Default generic profile has no ID patterns (ontology auto-generated)."""
        profile = load_profile("default")
        assert len(profile.id_patterns.patterns) == 0

    def test_financial_aml_has_fatf_pattern(self):
        profile = load_profile("financial-aml")
        assert "fatf_rec" in profile.id_patterns.patterns

    def test_data_privacy_has_gdpr_patterns(self):
        profile = load_profile("data-privacy")
        assert "gdpr_article" in profile.id_patterns.patterns
        assert "gdpr_recital" in profile.id_patterns.patterns


class TestDiscovery:
    def test_food_safety_has_20_subdomains(self):
        profile = load_profile("food-safety")
        assert len(profile.discovery.sub_domains) == 20

    def test_food_safety_has_search_templates(self):
        profile = load_profile("food-safety")
        assert len(profile.discovery.search_templates) >= 10

    def test_food_safety_has_priority_tiers(self):
        profile = load_profile("food-safety")
        assert "P1" in profile.discovery.priority_tiers
        assert "P4" in profile.discovery.priority_tiers

    def test_default_has_priority_tiers(self):
        profile = load_profile("default")
        assert "P1" in profile.discovery.priority_tiers

    def test_financial_aml_has_subdomains(self):
        profile = load_profile("financial-aml")
        assert len(profile.discovery.sub_domains) >= 10


class TestSingleton:
    def test_get_profile_returns_profile(self):
        reset_profile()
        profile = get_profile()
        assert isinstance(profile, DomainProfile)

    def test_set_profile_overrides(self):
        custom = DomainProfile(name="Test", description="test", version="1.0")
        set_profile(custom)
        assert get_profile().name == "Test"
        reset_profile()  # Clean up

    def test_reset_forces_reload(self):
        reset_profile()
        p1 = get_profile()
        reset_profile()
        p2 = get_profile()
        assert p1.name == p2.name  # Same default


# Helper: minimal ontology for tests that need one
_TEST_ONTOLOGY = OntologyConfig(
    nodes=[
        NodeDef(label="Component", description="A software component", properties={"name": "string"}),
        NodeDef(label="Concept", description="A technical concept", properties={"name": "string"}),
    ],
    edges=[
        EdgeDef(label="USES", source="Component", target="Concept", description="Uses this concept"),
    ],
    root_node="Component",
    json_schema='{"entities": [{"_label": "...", "name": "..."}], "relationships": []}',
)


class TestBuildPrompt:
    def test_returns_tuple(self):
        reset_profile()
        system_msg, user_prompt = build_prompt(
            excerpt="The product must contain less than 5mg sodium.",
            authority="CFIA",
            jurisdiction="CA",
            ontology=_TEST_ONTOLOGY,
        )
        assert isinstance(system_msg, str)
        assert isinstance(user_prompt, str)
        assert "JSON" in system_msg
        assert "sodium" in user_prompt

    def test_uses_profile_ontology(self):
        """Profiles with ontology use ontology-driven prompt (node/edge descriptions)."""
        profile = load_profile("financial-aml")
        _, user_prompt = build_prompt(
            excerpt="The institution must verify customer identity.",
            authority="FinCEN",
            jurisdiction="US",
            profile=profile,
        )
        # Ontology-driven prompt includes node type descriptions
        assert "Provision" in user_prompt
        assert "Requirement" in user_prompt
        assert "DERIVED_FROM" in user_prompt
        assert "FinCEN" in user_prompt

    def test_includes_authority_and_jurisdiction(self):
        _, user_prompt = build_prompt(
            excerpt="Test text.",
            authority="TestAuth",
            jurisdiction="XX",
            ontology=_TEST_ONTOLOGY,
        )
        assert "TestAuth" in user_prompt
        assert "XX" in user_prompt

    def test_build_prompt_with_empty_authority(self):
        """Generic topics may have empty authority/jurisdiction."""
        reset_profile()
        system_msg, user_prompt = build_prompt(
            excerpt="Kubernetes uses iptables for packet filtering.",
            authority="",
            jurisdiction="",
            ontology=_TEST_ONTOLOGY,
        )
        assert isinstance(system_msg, str)
        assert isinstance(user_prompt, str)

    def test_raises_without_ontology(self):
        """build_prompt raises ValueError when no ontology is available."""
        reset_profile()
        # Default profile has no ontology, and no explicit ontology passed
        with pytest.raises(ValueError, match="Ontology with nodes and json_schema is required"):
            build_prompt(
                excerpt="Test text.",
                authority="TestAuth",
                jurisdiction="CA",
            )


class TestOntologyConfig:
    def test_empty_ontology_is_valid(self):
        ontology = OntologyConfig()
        assert ontology.nodes == []
        assert ontology.edges == []
        assert ontology.root_node == ""
        assert ontology.json_schema is None

    def test_ontology_with_nodes_and_edges(self):
        ontology = OntologyConfig(
            description="Test ontology",
            root_node="Concept",
            nodes=[
                NodeDef(label="Concept", description="A key concept", properties={"name": "string"}),
                NodeDef(label="Fact", description="A fact", properties={"text": "string"}),
            ],
            edges=[
                EdgeDef(label="SUPPORTS", source="Fact", target="Concept", description="Fact supports concept"),
            ],
            json_schema='{"entities": [], "relationships": []}',
        )
        assert len(ontology.nodes) == 2
        assert len(ontology.edges) == 1
        assert ontology.root_node == "Concept"
        assert ontology.nodes[0].label == "Concept"
        assert ontology.edges[0].source == "Fact"

    def test_profile_with_ontology(self):
        profile = DomainProfile(
            name="Test",
            ontology=OntologyConfig(
                nodes=[NodeDef(label="Entity", description="test")],
                root_node="Entity",
            ),
        )
        assert len(profile.ontology.nodes) == 1
        assert profile.ontology.root_node == "Entity"

    def test_domain_profiles_have_ontology(self):
        """Domain-specific profiles should have explicit ontology sections."""
        for name in ["food-safety", "financial-aml", "data-privacy"]:
            profile = load_profile(name)
            assert len(profile.ontology.nodes) > 0, f"{name} missing ontology nodes"
            assert profile.ontology.root_node == "Provision", f"{name} wrong root_node"
            assert profile.ontology.json_schema is not None, f"{name} missing json_schema"

    def test_default_profile_has_no_ontology(self):
        """Default generic profile should NOT have an ontology (auto-generated by skill)."""
        profile = load_profile("default")
        assert len(profile.ontology.nodes) == 0

    def test_ontology_driven_prompt(self):
        """When a profile has ontology with json_schema, build_prompt uses it."""
        profile = DomainProfile(
            name="Test Ontology",
            ontology=_TEST_ONTOLOGY,
        )
        system_msg, user_prompt = build_prompt(
            excerpt="kube-proxy uses iptables for packet filtering.",
            profile=profile,
        )
        assert "Component" in user_prompt
        assert "Concept" in user_prompt
        assert "USES" in user_prompt
        assert "entities" in user_prompt
