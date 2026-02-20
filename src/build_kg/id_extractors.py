"""
Provision ID Extraction Module
Extracts provision IDs from source text using regex patterns.
Supports domain profiles for customizable patterns.
"""
import re
from dataclasses import dataclass
from typing import Optional, Tuple


@dataclass
class ExtractionResult:
    """Result of ID extraction."""
    provision_id: str
    confidence: float  # 0.0 - 1.0
    method: str  # 'canonical_locator', 'regex', 'llm', 'inference'
    pattern_name: Optional[str] = None


class ProvisionIDExtractor:
    """
    Extract provision IDs using multiple strategies.

    Can be initialized with patterns from a domain profile,
    or falls back to built-in default patterns.

    Priority order:
    1. canonical_locator metadata
    2. Regex patterns (source-specific)
    3. General regex patterns
    4. Fallback to UNKNOWN
    """

    # Built-in default patterns (backward compatibility)
    _DEFAULT_PATTERNS = {
        'cfia_bdot': re.compile(
            r'\b([A-Z]\.\d{2}\.\d{3}(?:\.\d+)?)\b', re.IGNORECASE
        ),
        'cfia_cdot': re.compile(
            r'\b([A-Z]\.\d{2,3})\b', re.IGNORECASE
        ),
        'cfr_full': re.compile(
            r'\b(\d{1,2}\s*CFR\s*\d+(?:\.\d+)*)\b', re.IGNORECASE
        ),
        'cfr_section': re.compile(
            r'\b§\s*(\d+\.\d+)\b', re.IGNORECASE
        ),
        'section_numbered': re.compile(
            r'\bSection\s+(\d+(?:\.\d+)*)\b', re.IGNORECASE
        ),
        'subsection': re.compile(
            r'\b(\d+(?:\.\d+){2,})\b',
        ),
        'chapter': re.compile(
            r'\bChapter\s+([A-Z]?\d+)\b', re.IGNORECASE
        ),
        'article': re.compile(
            r'\bArticle\s+(\d+(?:\.\d+)*)\b', re.IGNORECASE
        ),
        'parenthetical': re.compile(
            r'\(([A-Z]\d+(?:\.\d+)+)\)', re.IGNORECASE
        ),
        'schedule': re.compile(
            r'\bSchedule\s+([IVX]+|[A-Z]|\d+)\b', re.IGNORECASE
        ),
    }

    _DEFAULT_AUTHORITY_PATTERNS = {
        'CFIA': ['cfia_bdot', 'cfia_cdot', 'section_numbered', 'parenthetical'],
        'Health Canada': ['section_numbered', 'cfia_bdot', 'schedule'],
        'Department of Justice': ['chapter', 'section_numbered', 'article'],
        'Canadian General Standards Board': ['section_numbered', 'cfia_cdot'],
        'World Health Organization': ['article', 'section_numbered'],
    }

    _DEFAULT_EXCLUSION_PATTERNS = [
        re.compile(r'\b\d{4}\b'),
        re.compile(r'\b\d{1,3}%\b'),
        re.compile(r'\b\d+\s*(mg|g|ml|kg|mcg)\b', re.IGNORECASE),
        re.compile(r'\b\d+\s*ppm\b', re.IGNORECASE),
    ]

    _FLAG_MAP = {
        'IGNORECASE': re.IGNORECASE,
        'MULTILINE': re.MULTILINE,
        'DOTALL': re.DOTALL,
    }

    def __init__(self, profile=None):
        """
        Initialize extractor.

        Args:
            profile: Optional DomainProfile. If None or profile has no patterns,
                     uses built-in defaults. If provided, compiles patterns from profile.
        """
        if profile is not None and profile.id_patterns.patterns:
            self.PATTERNS = self._compile_patterns(profile.id_patterns.patterns)
            self.AUTHORITY_PATTERNS = dict(profile.id_patterns.authority_priorities)
            self.EXCLUSION_PATTERNS = self._compile_exclusions(profile.id_patterns.exclusions)
        else:
            self.PATTERNS = dict(self._DEFAULT_PATTERNS)
            self.AUTHORITY_PATTERNS = dict(self._DEFAULT_AUTHORITY_PATTERNS)
            self.EXCLUSION_PATTERNS = list(self._DEFAULT_EXCLUSION_PATTERNS)

    def _compile_patterns(self, patterns_config) -> dict:
        """Compile regex patterns from profile config."""
        compiled = {}
        for name, pat_config in patterns_config.items():
            flags = 0
            if pat_config.flags:
                for flag_name in pat_config.flags.split('|'):
                    flag_name = flag_name.strip()
                    if flag_name in self._FLAG_MAP:
                        flags |= self._FLAG_MAP[flag_name]
            compiled[name] = re.compile(pat_config.regex, flags)
        return compiled

    def _compile_exclusions(self, exclusion_strings: list) -> list:
        """Compile exclusion regex patterns."""
        return [re.compile(pattern, re.IGNORECASE) for pattern in exclusion_strings]

    def extract_from_canonical_locator(self, locator: str) -> ExtractionResult:
        """
        Extract ID from canonical_locator metadata.

        Args:
            locator: canonical_locator string from source_fragment

        Returns:
            ExtractionResult with extracted ID or UNKNOWN
        """
        if not locator or locator.strip() == '':
            return ExtractionResult(
                provision_id="UNKNOWN",
                confidence=0.0,
                method='canonical_locator'
            )

        locator = locator.strip()

        # Try each pattern
        for pattern_name, pattern in self.PATTERNS.items():
            match = pattern.search(locator)
            if match:
                extracted_id = match.group(1)

                # Check exclusions
                if not self._is_excluded(extracted_id):
                    return ExtractionResult(
                        provision_id=extracted_id,
                        confidence=0.95,  # High confidence from metadata
                        method='canonical_locator',
                        pattern_name=pattern_name
                    )

        # If no pattern matched, try using locator as-is if it looks like an ID
        if self._looks_like_id(locator):
            return ExtractionResult(
                provision_id=locator,
                confidence=0.80,
                method='canonical_locator',
                pattern_name='direct'
            )

        return ExtractionResult(
            provision_id="UNKNOWN",
            confidence=0.0,
            method='canonical_locator'
        )

    def extract_from_text(
        self,
        text: str,
        authority: str = "UNKNOWN"
    ) -> ExtractionResult:
        """
        Extract ID from source text using regex patterns.

        Args:
            text: Source text excerpt
            authority: Source authority name

        Returns:
            ExtractionResult with extracted ID or UNKNOWN
        """
        if not text:
            return ExtractionResult(
                provision_id="UNKNOWN",
                confidence=0.0,
                method='regex'
            )

        # Get authority-specific pattern priority
        pattern_priority = self.AUTHORITY_PATTERNS.get(authority, [])

        # Try authority-specific patterns first
        for pattern_name in pattern_priority:
            if pattern_name in self.PATTERNS:
                result = self._try_pattern(
                    text,
                    pattern_name,
                    self.PATTERNS[pattern_name],
                    confidence=0.85
                )
                if result.provision_id != "UNKNOWN":
                    return result

        # Try all patterns (fallback)
        for pattern_name, pattern in self.PATTERNS.items():
            if pattern_name not in pattern_priority:  # Skip already tried
                result = self._try_pattern(
                    text,
                    pattern_name,
                    pattern,
                    confidence=0.70
                )
                if result.provision_id != "UNKNOWN":
                    return result

        return ExtractionResult(
            provision_id="UNKNOWN",
            confidence=0.0,
            method='regex'
        )

    def extract(
        self,
        text: str,
        canonical_locator: Optional[str] = None,
        authority: str = "UNKNOWN"
    ) -> ExtractionResult:
        """
        Extract provision ID using all available methods.

        Priority:
        1. canonical_locator metadata
        2. Regex from text

        Args:
            text: Source text excerpt
            canonical_locator: Optional canonical_locator from source_fragment
            authority: Source authority name

        Returns:
            ExtractionResult with best extracted ID
        """
        # Try canonical_locator first (highest confidence)
        if canonical_locator:
            result = self.extract_from_canonical_locator(canonical_locator)
            if result.provision_id != "UNKNOWN" and result.confidence >= 0.80:
                return result

        # Try regex extraction from text
        result = self.extract_from_text(text, authority)
        if result.provision_id != "UNKNOWN":
            return result

        # No ID found
        return ExtractionResult(
            provision_id="UNKNOWN",
            confidence=0.0,
            method='none'
        )

    def _try_pattern(
        self,
        text: str,
        pattern_name: str,
        pattern: re.Pattern,
        confidence: float
    ) -> ExtractionResult:
        """Try a single pattern and return result."""
        # Look for pattern in first 500 chars (IDs usually appear early)
        search_text = text[:500]

        match = pattern.search(search_text)
        if match:
            extracted_id = match.group(1).strip()

            # Validate
            if not self._is_excluded(extracted_id):
                return ExtractionResult(
                    provision_id=extracted_id,
                    confidence=confidence,
                    method='regex',
                    pattern_name=pattern_name
                )

        return ExtractionResult(
            provision_id="UNKNOWN",
            confidence=0.0,
            method='regex',
            pattern_name=pattern_name
        )

    def _is_excluded(self, candidate: str) -> bool:
        """Check if candidate matches exclusion patterns."""
        for exclusion in self.EXCLUSION_PATTERNS:
            if exclusion.fullmatch(candidate):
                return True
        return False

    def _looks_like_id(self, text: str) -> bool:
        """Heuristic check if string looks like a provision ID."""
        # Basic checks
        if len(text) < 2 or len(text) > 30:
            return False

        # Should contain at least one digit
        if not re.search(r'\d', text):
            return False

        # Should contain at least one letter or dot or section keyword
        if not re.search(r'[A-Za-z\.]|Section|Chapter|Article', text, re.IGNORECASE):
            return False

        return True


class ProvisionIDValidator:
    """Validate extracted provision IDs."""

    # Built-in default format rules
    _DEFAULT_FORMAT_RULES = {
        'CFIA': [
            re.compile(r'^[A-Z]\.\d{2}\.\d{3}(?:\.\d+)?$'),
            re.compile(r'^[A-Z]\.\d{2,3}$'),
        ],
        'Health Canada': [
            re.compile(r'^Section\s+\d+(?:\.\d+)*$', re.IGNORECASE),
            re.compile(r'^Schedule\s+[IVX]+$', re.IGNORECASE),
        ],
        'CFR': [
            re.compile(r'^\d{1,2}\s*CFR\s*\d+(?:\.\d+)*$', re.IGNORECASE),
            re.compile(r'^\d+\.\d+(?:\.\d+)*$'),
        ],
    }

    def __init__(self, profile=None):
        """
        Initialize validator.

        Args:
            profile: Optional DomainProfile. If provided and has format_rules,
                     compiles rules from profile. Otherwise uses defaults.
        """
        if profile is not None and profile.id_patterns.format_rules:
            self.FORMAT_RULES = {
                authority: [re.compile(pattern) for pattern in patterns]
                for authority, patterns in profile.id_patterns.format_rules.items()
            }
        else:
            self.FORMAT_RULES = dict(self._DEFAULT_FORMAT_RULES)

    def validate(
        self,
        provision_id: str,
        authority: str = "UNKNOWN"
    ) -> Tuple[bool, str]:
        """
        Validate provision ID format.

        RELAXED: Accepts most patterns to maximize data recovery.

        Args:
            provision_id: Extracted provision ID
            authority: Source authority

        Returns:
            (is_valid, reason)
        """
        if provision_id == "UNKNOWN":
            return True, "UNKNOWN is valid placeholder"

        # Check length
        if len(provision_id) < 1:
            return False, "Empty"
        if len(provision_id) > 50:
            return False, "Too long"

        # RELAXED: Accept numeric-only IDs (e.g., "88", "157")
        # These are common section numbers
        if re.match(r'^\d+$', provision_id):
            if len(provision_id) <= 5:  # Reasonable section number
                return True, "Valid numeric section"
            else:
                return False, "Numeric but too long (likely not an ID)"

        # RELAXED: Accept numeric with dots (e.g., "3.5", "101.61")
        if re.match(r'^\d+(?:\.\d+)+$', provision_id):
            return True, "Valid dotted numeric format"

        # Check for authority-specific format (if available)
        if authority in self.FORMAT_RULES:
            for pattern in self.FORMAT_RULES[authority]:
                if pattern.match(provision_id):
                    return True, f"Matches {authority} format"

        # Generic validation: must contain at least one digit
        if not re.search(r'\d', provision_id):
            return False, "Must contain at least one digit"

        # RELAXED: Accept letter+digit combinations
        if re.search(r'[A-Za-z]', provision_id):
            return True, "Contains letters and digits"

        # Accept anything with dots and digits
        if '.' in provision_id:
            return True, "Contains dot separator"

        # Fallback: if we got here and it has digits, accept it
        return True, "Passes relaxed validation"


def demo():
    """Demonstrate ID extraction."""
    extractor = ProvisionIDExtractor()
    validator = ProvisionIDValidator()

    test_cases = [
        {
            'text': 'B.01.008.2 The product must contain...',
            'locator': 'B.01.008.2',
            'authority': 'CFIA'
        },
        {
            'text': 'Section 101.61 requires that sodium content...',
            'locator': '',
            'authority': 'Health Canada'
        },
        {
            'text': '21 CFR 101.61 specifies labeling requirements...',
            'locator': '21 CFR 101.61',
            'authority': 'CFR'
        },
        {
            'text': 'Chapter 27 of the regulations states...',
            'locator': 'Chapter 27',
            'authority': 'Department of Justice'
        },
    ]

    print("=" * 80)
    print("PROVISION ID EXTRACTOR - DEMO")
    print("=" * 80)

    for i, test in enumerate(test_cases, 1):
        print(f"\n[{i}] Test Case:")
        print(f"    Authority: {test['authority']}")
        print(f"    Locator: '{test['locator']}'")
        print(f"    Text: {test['text'][:80]}...")

        result = extractor.extract(
            text=test['text'],
            canonical_locator=test['locator'],
            authority=test['authority']
        )

        print("\n    Result:")
        print(f"      provision_id: {result.provision_id}")
        print(f"      confidence: {result.confidence:.2f}")
        print(f"      method: {result.method}")
        print(f"      pattern: {result.pattern_name}")

        # Validate
        is_valid, reason = validator.validate(result.provision_id, test['authority'])
        print("\n    Validation:")
        print(f"      valid: {is_valid}")
        print(f"      reason: {reason}")

        print("-" * 80)


if __name__ == "__main__":
    demo()
