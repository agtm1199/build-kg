"""Tests for manifest loading and validation."""
import json
from pathlib import Path

import pytest

EXAMPLES_DIR = Path(__file__).resolve().parent.parent / "examples" / "manifests"


class TestManifestFormat:
    @pytest.fixture
    def singapore_manifest(self):
        with open(EXAMPLES_DIR / "singapore-fb.json") as f:
            return json.load(f)

    @pytest.fixture
    def canada_manifest(self):
        with open(EXAMPLES_DIR / "canada-food.json") as f:
            return json.load(f)

    def test_singapore_manifest_has_required_fields(self, singapore_manifest):
        assert "topic" in singapore_manifest
        assert "graph_name" in singapore_manifest
        assert "sources" in singapore_manifest
        assert "defaults" in singapore_manifest

    def test_singapore_manifest_has_sources(self, singapore_manifest):
        assert len(singapore_manifest["sources"]) > 0

    def test_singapore_sources_have_required_fields(self, singapore_manifest):
        required_fields = ["source_name", "url", "title", "authority", "jurisdiction", "doc_type"]
        for source in singapore_manifest["sources"]:
            for field in required_fields:
                assert field in source, f"Source {source.get('source_name', '?')} missing {field}"

    def test_singapore_jurisdictions_are_sg(self, singapore_manifest):
        for source in singapore_manifest["sources"]:
            assert source["jurisdiction"] == "SG"

    def test_canada_manifest_has_required_fields(self, canada_manifest):
        assert "topic" in canada_manifest
        assert "graph_name" in canada_manifest
        assert "sources" in canada_manifest
        assert "defaults" in canada_manifest

    def test_canada_manifest_has_coverage(self, canada_manifest):
        assert "coverage" in canada_manifest
        assert "covered" in canada_manifest["coverage"]
        assert "gaps" in canada_manifest["coverage"]
        assert "coverage_pct" in canada_manifest["coverage"]

    def test_canada_sources_have_priority(self, canada_manifest):
        for source in canada_manifest["sources"]:
            assert "priority" in source
            assert source["priority"] in ("P1", "P2", "P3", "P4")

    def test_doc_types_are_valid(self, singapore_manifest):
        valid_types = {"regulation", "standard", "guidance", "code", "act", "directive", "order"}
        for source in singapore_manifest["sources"]:
            assert source["doc_type"] in valid_types, f"Invalid doc_type: {source['doc_type']}"

    def test_graph_name_format(self, singapore_manifest):
        name = singapore_manifest["graph_name"]
        assert name.startswith("reg_")
        assert name == name.lower()
        assert len(name) <= 20
