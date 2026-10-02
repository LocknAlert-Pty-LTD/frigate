"""The plate filters, which decide whether a read is acted on.

Where LPR opens a gate, `format` is a security control: it is what stops a
misread of a passing van from resembling a plate on the allow list. A filter that
silently stopped filtering is therefore the failure that matters, and an invalid
regex used to cause exactly that -- it logged an error once per plate and then
returned True, admitting everything it could read.

Two changes are covered. The pattern is compiled when the config loads, so a typo
stops startup instead of disabling the filter; and if one ever reaches the runtime
path anyway, it rejects rather than accepts.
"""

import unittest

import pydantic

from frigate.config.classification import LicensePlateRecognitionConfig
from frigate.data_processing.common.license_plate.mixin import (
    LicensePlateProcessingMixin,
)


def mixin(**lpr_kwargs) -> LicensePlateProcessingMixin:
    instance = LicensePlateProcessingMixin.__new__(LicensePlateProcessingMixin)
    instance.lpr_config = LicensePlateRecognitionConfig(**lpr_kwargs)
    return instance


def broken_regex_mixin(pattern: str) -> LicensePlateProcessingMixin:
    """Bypasses validation, to reach the runtime branch validation now prevents.

    Defence in depth rather than a reachable path: config is reloadable at
    runtime, and the two guards were added together.
    """
    instance = LicensePlateProcessingMixin.__new__(LicensePlateProcessingMixin)
    instance.lpr_config = LicensePlateRecognitionConfig.model_construct(
        min_plate_length=4, format=pattern
    )
    return instance


class TestConfigRejectsABrokenPattern(unittest.TestCase):
    def test_an_unbalanced_bracket_stops_startup(self) -> None:
        with self.assertRaises(pydantic.ValidationError):
            LicensePlateRecognitionConfig(format="[unclosed")

    def test_a_dangling_quantifier_stops_startup(self) -> None:
        with self.assertRaises(pydantic.ValidationError):
            LicensePlateRecognitionConfig(format="*ABC")

    def test_the_error_names_the_setting(self) -> None:
        """So the cause is obvious from the startup log rather than being hunted."""
        with self.assertRaises(pydantic.ValidationError) as caught:
            LicensePlateRecognitionConfig(format="(unclosed")

        self.assertIn("lpr.format", str(caught.exception))

    def test_a_valid_pattern_is_kept_verbatim(self) -> None:
        pattern = r"^[A-Z]{2}\d{3}[A-Z]{2}$"

        self.assertEqual(pattern, LicensePlateRecognitionConfig(format=pattern).format)

    def test_no_pattern_is_allowed(self) -> None:
        self.assertIsNone(LicensePlateRecognitionConfig().format)


class TestFormatFilter(unittest.TestCase):
    def test_a_matching_plate_passes(self) -> None:
        instance = mixin(format=r"^[A-Z]{2}\d{4}$", min_plate_length=4)

        self.assertTrue(instance._passes_plate_filters("gate", "AB1234"))

    def test_a_non_matching_plate_is_rejected(self) -> None:
        instance = mixin(format=r"^[A-Z]{2}\d{4}$", min_plate_length=4)

        self.assertFalse(instance._passes_plate_filters("gate", "ABCDEF"))

    def test_the_match_must_cover_the_whole_plate(self) -> None:
        """fullmatch, not search. A partial match would let a misread with extra
        characters satisfy a pattern meant to pin the exact shape of a plate."""
        instance = mixin(format=r"[A-Z]{2}\d{4}", min_plate_length=4)

        self.assertFalse(instance._passes_plate_filters("gate", "XXAB1234YY"))

    def test_no_pattern_accepts_any_shape(self) -> None:
        instance = mixin(min_plate_length=4)

        self.assertTrue(instance._passes_plate_filters("gate", "WHATEVER"))


class TestLengthFilter(unittest.TestCase):
    def test_a_short_read_is_rejected(self) -> None:
        """The common OCR failure: part of a plate resolving into a plausible
        shorter string."""
        instance = mixin(min_plate_length=6)

        self.assertFalse(instance._passes_plate_filters("gate", "AB12"))

    def test_exactly_the_minimum_passes(self) -> None:
        instance = mixin(min_plate_length=6)

        self.assertTrue(instance._passes_plate_filters("gate", "AB1234"))

    def test_an_empty_read_is_rejected(self) -> None:
        instance = mixin(min_plate_length=4)

        self.assertFalse(instance._passes_plate_filters("gate", ""))

    def test_length_is_checked_before_the_pattern(self) -> None:
        """Both must hold; order only affects which reason is logged."""
        instance = mixin(format=r".*", min_plate_length=6)

        self.assertFalse(instance._passes_plate_filters("gate", "AB1"))


class TestBrokenPatternFailsClosed(unittest.TestCase):
    def test_a_plate_is_rejected_rather_than_admitted(self) -> None:
        """The fail-open that mattered. This used to return True, so a typo in
        `format` admitted every readable plate while the log filled with errors
        nobody was watching."""
        instance = broken_regex_mixin("[unclosed")

        self.assertFalse(instance._passes_plate_filters("gate", "AB1234"))

    def test_it_rejects_every_plate_not_just_some(self) -> None:
        """Failing closed has to be consistent: a gate that works intermittently
        would be diagnosed as a camera problem rather than a config error."""
        instance = broken_regex_mixin("(unclosed")

        for plate in ("AB1234", "ZZ9999", "TESTPLATE"):
            self.assertFalse(instance._passes_plate_filters("gate", plate), plate)


if __name__ == "__main__":
    unittest.main()
