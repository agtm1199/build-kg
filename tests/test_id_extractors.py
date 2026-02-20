"""Tests for provision ID extraction."""
import pytest

from build_kg.id_extractors import ProvisionIDExtractor, ProvisionIDValidator


@pytest.fixture
def extractor():
    return ProvisionIDExtractor()


@pytest.fixture
def validator():
    return ProvisionIDValidator()


class TestProvisionIDExtractor:
    def test_cfia_id_from_locator(self, extractor):
        result = extractor.extract(
            text="B.01.008.2 The product must contain...",
            canonical_locator="B.01.008.2",
            authority="CFIA",
        )
        assert result.provision_id == "B.01.008.2"
        assert result.confidence >= 0.80
        assert result.method == "canonical_locator"

    def test_section_from_text(self, extractor):
        result = extractor.extract(
            text="Section 101.61 requires that sodium content...",
            canonical_locator="",
            authority="Health Canada",
        )
        assert result.provision_id == "101.61"
        assert result.method == "regex"

    def test_cfr_from_locator(self, extractor):
        result = extractor.extract(
            text="21 CFR 101.61 specifies labeling requirements...",
            canonical_locator="21 CFR 101.61",
            authority="CFR",
        )
        assert result.provision_id == "21 CFR 101.61"
        assert result.confidence >= 0.80

    def test_chapter_from_text(self, extractor):
        result = extractor.extract(
            text="Chapter 27 of the regulations states...",
            canonical_locator="Chapter 27",
            authority="Department of Justice",
        )
        assert result.provision_id == "27"
        assert result.confidence >= 0.80

    def test_unknown_when_no_id(self, extractor):
        result = extractor.extract(
            text="This is a general paragraph without any regulatory reference.",
            canonical_locator="",
            authority="UNKNOWN",
        )
        assert result.provision_id == "UNKNOWN"
        assert result.confidence == 0.0

    def test_excludes_years(self, extractor):
        """Years like 2020 should not be extracted as IDs."""
        result = extractor.extract(
            text="The regulation was enacted in 2020 and updated in 2023.",
            canonical_locator="",
            authority="UNKNOWN",
        )
        # Should not extract a year as a provision ID
        if result.provision_id != "UNKNOWN":
            assert not result.provision_id.isdigit() or int(result.provision_id) < 1900


class TestProvisionIDValidator:
    def test_valid_cfia_format(self, validator):
        is_valid, _ = validator.validate("B.01.008.2", "CFIA")
        assert is_valid

    def test_valid_unknown_placeholder(self, validator):
        is_valid, _ = validator.validate("UNKNOWN")
        assert is_valid

    def test_valid_dotted_numeric(self, validator):
        is_valid, _ = validator.validate("101.61")
        assert is_valid

    def test_rejects_empty(self, validator):
        is_valid, _ = validator.validate("")
        assert not is_valid

    def test_rejects_too_long(self, validator):
        is_valid, _ = validator.validate("x" * 51)
        assert not is_valid


class TestProfileBasedExtractor:
    """Test extractors initialized with domain profiles."""

    def test_extractor_with_food_safety_profile(self):
        from build_kg.domain import load_profile
        profile = load_profile("food-safety")
        extractor = ProvisionIDExtractor(profile=profile)
        result = extractor.extract(
            text="B.01.008.2 The product must contain...",
            canonical_locator="B.01.008.2",
            authority="CFIA",
        )
        assert result.provision_id == "B.01.008.2"

    def test_extractor_with_default_profile(self):
        from build_kg.domain import load_profile
        profile = load_profile("default")
        extractor = ProvisionIDExtractor(profile=profile)
        result = extractor.extract(
            text="Section 101.61 requires...",
            canonical_locator="",
            authority="UNKNOWN",
        )
        assert result.provision_id == "101.61"

    def test_extractor_without_profile_uses_defaults(self):
        """Backward compatibility: no profile = same as current behavior."""
        extractor = ProvisionIDExtractor()
        result = extractor.extract(
            text="B.01.008.2 The product must contain...",
            canonical_locator="B.01.008.2",
            authority="CFIA",
        )
        assert result.provision_id == "B.01.008.2"

    def test_validator_with_food_safety_profile(self):
        from build_kg.domain import load_profile
        profile = load_profile("food-safety")
        validator = ProvisionIDValidator(profile=profile)
        is_valid, _ = validator.validate("B.01.008.2", "CFIA")
        assert is_valid
