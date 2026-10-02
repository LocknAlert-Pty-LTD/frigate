"""Scoring for face recognition, which here gates physical access.

The three behaviours under test replaced a single averaged embedding per
person plus a plain argmax:

* keep_inlier_embeddings keeps every enrolled sample instead of averaging.
  One centroid cannot represent someone photographed with and without
  glasses -- the mean lands between the modes, matching neither well while
  drifting toward other people.
* score_classes ranks a person by their top-k most similar enrolled images.
* apply_margin declines when the runner-up is too close. Absolute score says
  nothing about whether two people were told apart, and confusing siblings is
  the failure that actually opens a door for the wrong person.
"""

import unittest

import numpy as np

from frigate.data_processing.common.face.recognizer import (
    apply_margin,
    keep_inlier_embeddings,
    score_classes,
)


def unit(*values) -> np.ndarray:
    vec = np.array(values, dtype=np.float64)
    return vec / np.linalg.norm(vec)


class TestKeepInlierEmbeddings(unittest.TestCase):
    def test_keeps_every_sample_rather_than_averaging(self) -> None:
        embs = [unit(1, 0, 0), unit(0.9, 0.1, 0), unit(0.8, 0.2, 0)]

        kept = keep_inlier_embeddings(embs)

        self.assertEqual(3, len(kept), "samples must survive, not collapse to a mean")

    def test_output_is_l2_normalised(self) -> None:
        kept = keep_inlier_embeddings([np.array([3.0, 4.0, 0.0])])

        np.testing.assert_allclose(1.0, np.linalg.norm(kept[0]), rtol=1e-6)

    def test_small_collections_bypass_outlier_rejection(self) -> None:
        """Under five samples there is no way to tell an outlier from natural
        variation, so nothing is dropped."""
        embs = [unit(1, 0, 0), unit(-1, 0, 0)]

        self.assertEqual(2, len(keep_inlier_embeddings(embs)))

    def test_drops_a_wrong_face_from_a_large_enough_collection(self) -> None:
        embs = [unit(1, 0.05 * i, 0) for i in range(8)] + [unit(-1, 0, 0)]

        kept = keep_inlier_embeddings(embs)

        self.assertLess(len(kept), len(embs), "the opposing vector should be dropped")
        self.assertTrue(all(vec @ unit(1, 0, 0) > 0 for vec in kept))


class TestScoreClasses(unittest.TestCase):
    def setUp(self) -> None:
        # alice enrolled twice, in two genuinely different looks
        self.classes = {
            "alice": keep_inlier_embeddings([unit(1, 0, 0), unit(0, 1, 0)]),
            "bob": keep_inlier_embeddings([unit(0, 0, 1)]),
        }

    def test_matches_the_closest_enrolled_look_not_an_average(self) -> None:
        """The regression that motivated this.

        Averaging alice's two looks gives a centroid at 45 degrees to both, so
        a probe matching one of them exactly scores only ~0.71 against her.
        Scoring against the samples returns the full 1.0.
        """
        scored = score_classes(unit(1, 0, 0), self.classes, top_k=1)

        self.assertEqual("alice", scored[0][0])
        self.assertAlmostEqual(1.0, scored[0][1], places=6)

    def test_ranks_best_first(self) -> None:
        scored = score_classes(unit(0, 0, 1), self.classes, top_k=1)

        self.assertEqual(["bob", "alice"], [name for name, _ in scored])

    def test_top_k_is_capped_at_the_enrolment_count(self) -> None:
        """Asking for more neighbours than exist must not error or pad."""
        scored = score_classes(unit(0, 0, 1), self.classes, top_k=50)

        self.assertEqual("bob", scored[0][0])
        self.assertAlmostEqual(1.0, scored[0][1], places=6)

    def test_top_k_averages_rather_than_taking_the_luckiest_frame(self) -> None:
        classes = {"carol": keep_inlier_embeddings([unit(1, 0, 0), unit(0, 1, 0)])}

        best_only = score_classes(unit(1, 0, 0), classes, top_k=1)[0][1]
        averaged = score_classes(unit(1, 0, 0), classes, top_k=2)[0][1]

        self.assertGreater(best_only, averaged)

    def test_a_person_with_no_embeddings_is_skipped(self) -> None:
        scored = score_classes(
            unit(1, 0, 0), {"empty": np.empty((0, 3)), **self.classes}, top_k=1
        )

        self.assertNotIn("empty", [name for name, _ in scored])


class TestApplyMargin(unittest.TestCase):
    def test_accepts_a_clear_winner(self) -> None:
        name, sim, ambiguous = apply_margin([("alice", 0.9), ("bob", 0.4)], 0.05)

        self.assertEqual("alice", name)
        self.assertFalse(ambiguous)
        self.assertAlmostEqual(0.9, sim)

    def test_rejects_a_near_tie_however_high_the_score(self) -> None:
        """0.91 vs 0.90 is not an identification. This is the look-alike case
        that would otherwise unlock a door for the wrong person."""
        name, _, ambiguous = apply_margin([("alice", 0.91), ("bob", 0.90)], 0.05)

        self.assertIsNone(name)
        self.assertTrue(ambiguous, "must be reported as ambiguous, not as no-match")

    def test_a_single_enrolled_person_has_no_runner_up(self) -> None:
        name, _, ambiguous = apply_margin([("alice", 0.8)], 0.05)

        self.assertEqual("alice", name)
        self.assertFalse(ambiguous)

    def test_margin_of_zero_disables_the_check(self) -> None:
        name, _, ambiguous = apply_margin([("alice", 0.91), ("bob", 0.90)], 0.0)

        self.assertEqual("alice", name)
        self.assertFalse(ambiguous)

    def test_nobody_enrolled(self) -> None:
        name, sim, ambiguous = apply_margin([], 0.05)

        self.assertIsNone(name)
        self.assertEqual(0.0, sim)
        self.assertFalse(ambiguous, "no enrolments is not ambiguity")


if __name__ == "__main__":
    unittest.main()
