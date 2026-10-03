"""Decoding a plate using only the characters a plate can contain.

The recogniser knows 6625 characters. Gate plates use 36. On 1,483 real gate
frames, run through the real pipeline at the default recognition threshold,
reads matching a known plate exactly went from 101 to 206 with
lpr.allowed_characters set, and to 263 with CLAHE as well. Nearly all of the
gain is reads that were right apart from a dash, hash or dot the model put in
somewhere, which made the raw string match nothing.
"""

import types
import unittest

import numpy as np

from frigate.config.classification import LicensePlateRecognitionConfig
from frigate.data_processing.common.license_plate.mixin import (
    CTCDecoder,
    LicensePlateProcessingMixin,
)

ALNUM = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"


class DecoderCase(unittest.TestCase):
    def setUp(self) -> None:
        self.decoder = CTCDecoder()  # the built-in English table
        self.index = {c: i for i, c in self.decoder.char_map.items() if i}

    def output(self, steps: list[dict[str, float]]) -> np.ndarray:
        """One row per time step; unlisted probability goes to blank."""
        classes = len(self.decoder.characters)
        out = np.zeros((len(steps), classes), dtype=np.float32)

        for t, probabilities in enumerate(steps):
            for char, p in probabilities.items():
                out[t, self.index[char]] = p
            out[t, 0] = 1.0 - sum(probabilities.values())

        return out


class TestMasking(DecoderCase):
    def test_a_symbol_gives_way_to_the_best_allowed_character(self) -> None:
        """The case this exists for: the model's second choice is the right one."""
        out = self.output([{"D": 0.9}, {"-": 0.6, "T": 0.35}, {"3": 0.9}])

        unmasked, _ = self.decoder([out])
        masked, _ = self.decoder([out], allowed_characters=ALNUM)

        self.assertEqual(["D-3"], unmasked)
        self.assertEqual(["DT3"], masked)

    def test_blank_still_wins_where_nothing_was_written(self) -> None:
        """A symbol over a mostly blank step must not become a character."""
        out = self.output([{"D": 0.9}, {"-": 0.3, "T": 0.05}, {"3": 0.9}])

        texts, _ = self.decoder([out], allowed_characters=ALNUM)

        self.assertEqual(["D3"], texts)

    def test_lowercase_is_not_allowed_when_not_listed(self) -> None:
        out = self.output([{"d": 0.6, "D": 0.3}])

        texts, _ = self.decoder([out], allowed_characters=ALNUM)

        self.assertEqual(["D"], texts)

    def test_confidence_is_that_of_the_character_chosen(self) -> None:
        """Reported honestly, so recognition_threshold still means something."""
        out = self.output([{"-": 0.6, "T": 0.35}])

        _, confidences = self.decoder([out], allowed_characters=ALNUM)

        self.assertAlmostEqual(0.35, confidences[0][0], places=5)

    def test_unset_changes_nothing(self) -> None:
        rng = np.random.default_rng(0)
        out = rng.dirichlet(np.ones(len(self.decoder.characters)), 40).astype(
            np.float32
        )

        self.assertEqual(self.decoder([out]), self.decoder([out], None))

    def test_the_model_output_is_not_modified(self) -> None:
        out = self.output([{"-": 0.6, "T": 0.35}])
        before = out.copy()

        self.decoder([out], allowed_characters=ALNUM)

        np.testing.assert_array_equal(before, out)

    def test_more_classes_than_the_table_are_masked_out(self) -> None:
        """recognition_v4 emits 6625 classes; ones the table cannot name must not
        be allowed through just because they have no character."""
        out = np.zeros((1, 200), dtype=np.float32)
        out[0, 150] = 0.7
        out[0, self.index["A"]] = 0.2
        out[0, 0] = 0.1

        texts, _ = self.decoder([out], allowed_characters=ALNUM)

        self.assertEqual(["A"], texts)

    def test_the_mask_follows_a_config_change(self) -> None:
        out = self.output([{"1": 0.6, "A": 0.35}])

        self.assertEqual(["1"], self.decoder([out], allowed_characters=ALNUM)[0])
        self.assertEqual(["A"], self.decoder([out], allowed_characters="AB")[0])


class TestConfig(unittest.TestCase):
    def test_unset_by_default(self) -> None:
        self.assertIsNone(LicensePlateRecognitionConfig().allowed_characters)

    def test_an_empty_set_means_unset(self) -> None:
        """Taken literally it would decode every plate to nothing, and clearing
        the field in the settings form submits an empty string."""
        for empty in ("", "   "):
            config = LicensePlateRecognitionConfig(allowed_characters=empty)
            self.assertIsNone(config.allowed_characters)

    def test_a_set_is_kept(self) -> None:
        config = LicensePlateRecognitionConfig(allowed_characters=ALNUM)

        self.assertEqual(ALNUM, config.allowed_characters)


class TestJoiningPieces(unittest.TestCase):
    """A plate the detector cut in two is read as two pieces."""

    def process(self, allowed: str | None) -> list[str]:
        mixin = LicensePlateProcessingMixin.__new__(LicensePlateProcessingMixin)
        mixin.lpr_config = types.SimpleNamespace(
            allowed_characters=allowed,
            recognition_threshold=0.9,
            replace_rules=[],
        )
        mixin.config = types.SimpleNamespace(
            lpr=types.SimpleNamespace(debug_save_plates=False)
        )
        loaded = types.SimpleNamespace(runner=object())
        mixin.model_runner = types.SimpleNamespace(
            detection_model=loaded,
            classification_model=loaded,
            recognition_model=loaded,
        )
        boxes = [
            np.array([[0, 0], [40, 0], [40, 20], [0, 20]]),
            np.array([[44, 0], [84, 0], [84, 20], [44, 20]]),
        ]
        mixin._detect = lambda image, *_: boxes
        mixin._crop_license_plate = lambda image, box: np.zeros((20, 40, 3), np.uint8)
        mixin._merge_nearby_boxes = lambda boxes, **kwargs: boxes
        mixin._recognize = lambda camera, images: (
            ["DT35", "TTGP"],
            [[0.99] * 4, [0.99] * 4],
        )

        plates, _, _ = mixin._process_license_plate(
            "gate", "id", np.zeros((40, 100, 3), np.uint8), 0
        )
        return plates

    def test_without_a_character_set_pieces_keep_their_space(self) -> None:
        self.assertEqual(["DT35 TTGP"], self.process(None))

    def test_with_one_they_join_into_the_plate(self) -> None:
        self.assertEqual(["DT35TTGP"], self.process(ALNUM))

    def test_a_listed_space_is_respected(self) -> None:
        self.assertEqual(["DT35 TTGP"], self.process(ALNUM + " "))


if __name__ == "__main__":
    unittest.main()
