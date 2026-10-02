"""The CTC decoder, which turns model output into the characters on a plate.

Rewritten for speed: a batch of six crops went from 12.26ms to 1.81ms. The old
version took the natural log of the entire output array -- 6625 classes at every
time step -- and then used 80 of those values. Everything here exists to show the
rewrite did not change the answer, because this is the step that decides what a
gate is told the plate says.

The reference implementation below is the old code, kept verbatim so the two can
be compared directly rather than compared against an assumption about what the
old one did.
"""

import unittest

import numpy as np

from frigate.data_processing.common.license_plate.mixin import CTCDecoder


def reference_decode(char_map, outputs):
    """The previous implementation, preserved for comparison."""
    results = []
    confidences = []

    for output in outputs:
        seq_log_probs = np.log(output + 1e-8)
        best_path = np.argmax(seq_log_probs, axis=1)

        merged_path = []
        merged_probs = []
        for t, char_index in enumerate(best_path):
            if char_index != 0 and (t == 0 or char_index != best_path[t - 1]):
                merged_path.append(char_index)
                merged_probs.append(seq_log_probs[t, char_index])

        results.append("".join(char_map.get(idx, "") for idx in merged_path))
        confidences.append(np.exp(merged_probs).tolist())

    return results, confidences


# recognition_v4.onnx emits 6625 classes, from the dictionary the upstream model
# was trained with. Kestrel decodes through a 97 entry English map, so anything
# above that decodes to nothing -- which is the intent for Latin plates, but it
# means a generator picking peaks across all 6625 produces empty text and
# compares two implementations that both returned nothing.
MODEL_CLASSES = 6625
DECODABLE_CLASSES = 97


def peaked_output(rng, steps=60, classes=MODEL_CLASSES, blanks=0.3):
    """Model output as a trained recogniser actually produces it.

    A softmax with one dominant class per step, not a flat spread. The
    distinction matters: the only place the two implementations can disagree is
    on near-exact ties, which a confident model does not produce.
    """
    logits = rng.normal(0, 1, (steps, classes)).astype(np.float32)
    peak = rng.integers(1, DECODABLE_CLASSES, steps)
    peak[rng.random(steps) < blanks] = 0  # blank frames, which CTC drops
    logits[np.arange(steps), peak] += 12.0
    exp = np.exp(logits - logits.max(axis=1, keepdims=True))
    return (exp / exp.sum(axis=1, keepdims=True)).astype(np.float32)


class DecoderTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.decoder = CTCDecoder()
        self.char_map = self.decoder.char_map

    def decode(self, outputs):
        return self.decoder(outputs)


class TestMatchesThePreviousImplementation(DecoderTestCase):
    def test_on_realistic_model_output(self) -> None:
        """The case that matters: output shaped like a confident recogniser."""
        rng = np.random.default_rng(17)
        outputs = [peaked_output(rng) for _ in range(6)]

        texts, confidences = self.decode(outputs)
        ref_texts, ref_confidences = reference_decode(self.char_map, outputs)

        self.assertEqual(ref_texts, texts)
        for mine, theirs in zip(confidences, ref_confidences):
            np.testing.assert_allclose(theirs, mine, rtol=1e-5, atol=1e-7)

    def test_across_many_plates(self) -> None:
        rng = np.random.default_rng(23)

        for trial in range(40):
            outputs = [peaked_output(rng, steps=rng.integers(20, 100))]

            texts, _ = self.decode(outputs)
            ref_texts, _ = reference_decode(self.char_map, outputs)

            self.assertEqual(ref_texts, texts, f"trial {trial}")

    def test_the_text_is_not_empty_for_peaked_input(self) -> None:
        """Guards the comparison itself: two implementations that both returned
        nothing would agree and prove nothing."""
        rng = np.random.default_rng(5)

        texts, _ = self.decode([peaked_output(rng, blanks=0.0)])

        self.assertGreater(len(texts[0]), 0)


class TestCtcCollapse(DecoderTestCase):
    """Blank removal and repeat merging, built explicitly rather than sampled."""

    def output_from(self, path, classes=MODEL_CLASSES):
        """One-hot output that forces a known argmax path."""
        out = np.full((len(path), classes), 1e-6, dtype=np.float32)
        for step, index in enumerate(path):
            out[step, index] = 0.99
        return out

    def test_blanks_are_dropped(self) -> None:
        texts, _ = self.decode([self.output_from([0, 5, 0, 6, 0])])

        self.assertEqual(
            self.char_map.get(5, "") + self.char_map.get(6, ""), texts[0]
        )

    def test_a_repeat_collapses_to_one_character(self) -> None:
        """CTC emits a class on consecutive steps for one character."""
        texts, _ = self.decode([self.output_from([5, 5, 5])])

        self.assertEqual(self.char_map.get(5, ""), texts[0])

    def test_a_blank_between_repeats_keeps_both(self) -> None:
        """A doubled letter in a real plate is separated by a blank. Collapsing
        it would silently turn AA into A."""
        texts, _ = self.decode([self.output_from([5, 0, 5])])

        self.assertEqual(self.char_map.get(5, "") * 2, texts[0])

    def test_the_first_step_is_kept(self) -> None:
        """An off-by-one in the repeat test would drop the leading character."""
        texts, _ = self.decode([self.output_from([5, 6])])

        self.assertEqual(
            self.char_map.get(5, "") + self.char_map.get(6, ""), texts[0]
        )

    def test_an_all_blank_output_decodes_to_nothing(self) -> None:
        texts, confidences = self.decode([self.output_from([0, 0, 0])])

        self.assertEqual("", texts[0])
        self.assertEqual([], confidences[0])


class TestConfidences(DecoderTestCase):
    def test_one_confidence_per_character(self) -> None:
        """The caller zips these with the characters; a mismatch would attach the
        wrong score to the wrong letter."""
        rng = np.random.default_rng(31)
        outputs = [peaked_output(rng) for _ in range(3)]

        texts, confidences = self.decode(outputs)

        for text, scores in zip(texts, confidences):
            self.assertEqual(len(text), len(scores))

    def test_confidences_are_probabilities(self) -> None:
        rng = np.random.default_rng(33)

        _, confidences = self.decode([peaked_output(rng)])

        for score in confidences[0]:
            self.assertGreaterEqual(score, 0.0)
            self.assertLessEqual(score, 1.0 + 1e-6)

    def test_a_confident_prediction_scores_high(self) -> None:
        out = np.full((1, 6625), 1e-9, dtype=np.float32)
        out[0, 5] = 0.995

        _, confidences = self.decode([out])

        self.assertAlmostEqual(0.995, confidences[0][0], places=5)


class TestEdges(DecoderTestCase):
    def test_no_outputs(self) -> None:
        self.assertEqual(([], []), self.decode([]))

    def test_a_single_time_step(self) -> None:
        out = np.full((1, 6625), 1e-6, dtype=np.float32)
        out[0, 7] = 0.9

        texts, confidences = self.decode([out])

        self.assertEqual(self.char_map.get(7, ""), texts[0])
        self.assertEqual(1, len(confidences[0]))

    def test_an_index_outside_the_character_map_is_skipped(self) -> None:
        """char_map is built from a fixed dictionary file. A model emitting an
        index beyond it must not raise in the middle of reading a plate."""
        highest = max(self.char_map) + 50
        out = np.full((1, highest + 1), 1e-6, dtype=np.float32)
        out[0, highest] = 0.9

        texts, _ = self.decode([out])

        self.assertEqual("", texts[0])


if __name__ == "__main__":
    unittest.main()
