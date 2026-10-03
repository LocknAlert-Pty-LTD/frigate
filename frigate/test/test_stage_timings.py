"""Per-stage timings, and the contract that puts them on the health dashboard.

A pipeline reported as one number tells you it is slow and nothing about where.
"Plate Recognition 72.59ms" covers four models plus a good deal of NumPy, and
staring at that figure does not say which to attack.

Two things are pinned here. One is the **additivity**: a stage is summed across a
whole pass before being averaged, so the cards add up to the total beside them. A
first version averaged each model call instead, which looks equivalent and is
not -- recognition runs once per batch of text crops, so on a plate with two
batches it reported the cost of one call while contributing two to the total, and
the parts came to less than the whole. On a real dashboard the stages summed to
84.9ms against a 72.59ms total.

The other is the **stats key shape**: the dashboard builds a card for every
`{base}_speed` key it finds, so breaking the suffix or the shared dictionary
would silently empty the dashboard rather than fail anything.
"""

import time
import unittest

from frigate.util.builtin import StageTimings


class StageTimingsTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.published: dict[str, float] = {}
        self.timings = StageTimings(self.published, prefix="plate_")

    def one_pass(self, **stages: float) -> None:
        """A complete pass containing the given stages."""
        self.timings.start_pass()

        for stage, seconds in stages.items():
            self.timings.add(stage, seconds)

        self.timings.flush()


class TestPublishing(StageTimingsTestCase):
    def test_a_stage_is_published_under_its_prefixed_name(self) -> None:
        self.one_pass(ocr=0.05)

        self.assertEqual({"plate_ocr": 0.05}, self.published)

    def test_nothing_is_published_until_the_pass_ends(self) -> None:
        """A half-finished pass would publish a stage total that is still
        growing, which on the dashboard reads as a stage that got faster."""
        self.timings.start_pass()
        self.timings.add("ocr", 0.05)

        self.assertEqual({}, self.published)

        self.timings.flush()

        self.assertEqual({"plate_ocr": 0.05}, self.published)

    def test_an_empty_prefix_is_allowed(self) -> None:
        timings = StageTimings(self.published)
        timings.start_pass()
        timings.add("something", 0.01)
        timings.flush()

        self.assertIn("something", self.published)

    def test_a_stage_that_did_not_run_is_not_updated(self) -> None:
        """Feeding it a zero would drag its average toward nothing and hide a
        real cost. Orientation only runs on some plates."""
        self.one_pass(ocr=0.05, orientation=0.02)
        self.one_pass(ocr=0.05)

        self.assertAlmostEqual(0.02, self.published["plate_orientation"])


class TestAdditivity(StageTimingsTestCase):
    """The property that lets the cards be read as a breakdown of the total."""

    def test_repeated_stages_sum_within_a_pass(self) -> None:
        """Recognition runs once per batch of text crops. Both batches are part
        of the one pass and both belong in its total."""
        self.one_pass()
        self.timings.start_pass()
        self.timings.add("ocr", 0.02)
        self.timings.add("ocr", 0.03)
        self.timings.flush()

        self.assertAlmostEqual(0.05, self.published["plate_ocr"])

    def test_stages_sum_to_the_pass_total(self) -> None:
        self.timings.start_pass()
        self.timings.add("text_detection", 0.06)
        self.timings.add("ocr", 0.019)
        self.timings.add("ocr", 0.004)

        self.assertAlmostEqual(0.083, self.timings.pass_seconds)

    def test_the_published_stages_sum_to_the_published_total(self) -> None:
        """What somebody does when they look at the dashboard: add the parts up
        and check them against the whole."""
        for _ in range(50):
            self.timings.start_pass()
            self.timings.add("text_detection", 0.061)
            self.timings.add("ocr", 0.010)
            self.timings.add("ocr", 0.009)
            total = 0.085
            self.timings.add(
                "cpu_overhead", max(0.0, total - self.timings.pass_seconds)
            )
            self.timings.flush()

        parts = sum(
            self.published[f"plate_{stage}"]
            for stage in ("text_detection", "ocr", "cpu_overhead")
        )

        self.assertAlmostEqual(0.085, parts, places=6)

    def test_start_pass_clears_the_previous_one(self) -> None:
        """Without this every pass would look slower than the last and the CPU
        share would go negative."""
        self.one_pass(ocr=0.02)

        self.timings.start_pass()
        self.timings.add("ocr", 0.03)

        self.assertAlmostEqual(0.03, self.timings.pass_seconds)

    def test_the_cpu_share_is_what_was_not_in_a_model(self) -> None:
        self.timings.start_pass()
        self.timings.add("text_detection", 0.01)
        self.timings.add("ocr", 0.02)
        self.timings.add("cpu_overhead", max(0.0, 0.05 - self.timings.pass_seconds))
        self.timings.flush()

        self.assertAlmostEqual(0.02, self.published["plate_cpu_overhead"])


class TestSmoothing(StageTimingsTestCase):
    def test_the_first_pass_is_taken_as_is(self) -> None:
        """Smoothing from a zero start would understate the first readings, and
        the first readings are what somebody watches after a change."""
        self.one_pass(ocr=0.2)

        self.assertAlmostEqual(0.2, self.published["plate_ocr"])

    def test_later_passes_are_smoothed_nine_to_one(self) -> None:
        """The same weighting InferenceSpeed uses, so a stage reads on the same
        footing as the pipeline total beside it."""
        self.one_pass(ocr=0.1)
        self.one_pass(ocr=0.2)

        self.assertAlmostEqual((0.1 * 9 + 0.2) / 10, self.published["plate_ocr"])

    def test_it_converges_on_a_steady_value(self) -> None:
        for _ in range(200):
            self.one_pass(ocr=0.04)

        self.assertAlmostEqual(0.04, self.published["plate_ocr"], places=4)

    def test_stages_are_smoothed_independently(self) -> None:
        """A shared accumulator would blend the stages and the breakdown would be
        worthless."""
        self.one_pass(ocr=0.1, text_detection=0.9)

        self.assertAlmostEqual(0.1, self.published["plate_ocr"])
        self.assertAlmostEqual(0.9, self.published["plate_text_detection"])


class TestMeasureContext(StageTimingsTestCase):
    def test_it_times_the_block(self) -> None:
        self.timings.start_pass()
        with self.timings.measure("ocr"):
            time.sleep(0.02)
        self.timings.flush()

        self.assertGreaterEqual(self.published["plate_ocr"], 0.015)

    def test_a_raising_block_is_still_counted(self) -> None:
        """Model calls sit inside try/except. If a failure recorded nothing, a
        stage that was failing slowly would look like a stage that was fast."""
        self.timings.start_pass()

        with self.assertRaises(RuntimeError):
            with self.timings.measure("ocr"):
                time.sleep(0.01)
                raise RuntimeError("inference failed")

        self.timings.flush()

        self.assertGreater(self.published["plate_ocr"], 0)


class TestRegisteredAtStartup(unittest.TestCase):
    """The breakdown cards exist before the first plate, not only after it.

    Without this, every restart left Plate Recognition on the dashboard with its
    total and nothing under it until a car came past."""

    def test_named_stages_are_published_immediately(self) -> None:
        published: dict[str, float] = {}

        StageTimings(published, prefix="plate_", stages=("ocr", "cpu_overhead"))

        self.assertEqual({"plate_ocr": 0.0, "plate_cpu_overhead": 0.0}, published)

    def test_the_placeholder_is_not_averaged_into_the_first_pass(self) -> None:
        published: dict[str, float] = {}
        timings = StageTimings(published, prefix="plate_", stages=("ocr",))

        timings.start_pass()
        timings.add("ocr", 0.004)
        timings.flush()

        self.assertAlmostEqual(0.004, published["plate_ocr"])

    def test_an_existing_value_is_not_reset(self) -> None:
        """Registering must not wipe a figure another instance already shows."""
        published = {"plate_ocr": 0.004}

        StageTimings(published, prefix="plate_", stages=("ocr",))

        self.assertEqual(0.004, published["plate_ocr"])

    def test_the_plate_pipeline_registers_the_stages_that_always_run(self) -> None:
        from frigate.data_processing.common.license_plate.mixin import PLATE_STAGES

        self.assertEqual({"text_detection", "ocr", "cpu_overhead"}, set(PLATE_STAGES))

    def test_it_works_on_the_shared_dict_the_stats_read(self) -> None:
        """Production publishes into a multiprocessing DictProxy, not a dict."""
        import multiprocessing

        with multiprocessing.Manager() as manager:
            published = manager.dict()

            StageTimings(published, prefix="plate_", stages=("ocr",))

            self.assertEqual({"plate_ocr": 0.0}, dict(published))


class TestStatsContract(unittest.TestCase):
    """What the health dashboard needs in order to render these at all."""

    def test_published_stages_become_speed_keys(self) -> None:
        """The UI strips the _speed suffix and looks the remainder up as a
        display name. A bare stage name would render an untitled card; a
        different suffix would render none."""
        published = {"plate_ocr": 0.0421, "plate_cpu_overhead": 0.0183}

        stats = {
            f"{stage}_speed": round(seconds * 1000, 2)
            for stage, seconds in published.items()
        }

        self.assertEqual(
            {"plate_ocr_speed": 42.1, "plate_cpu_overhead_speed": 18.3}, stats
        )

    def test_every_published_stage_has_a_display_name(self) -> None:
        """A missing name renders the raw i18n key on the dashboard."""
        import json
        import pathlib

        locale = pathlib.Path("/opt/frigate/web/public/locales/en/views/system.json")

        if not locale.is_file():
            self.skipTest("web assets are not present in this image")

        names = json.loads(locale.read_text(encoding="utf-8"))["enrichments"][
            "embeddings"
        ]

        for stage in ("text_detection", "orientation", "ocr", "cpu_overhead"):
            self.assertIn(f"plate_{stage}", names, stage)
            self.assertIn(f"plate_{stage}_speed", names, stage)


if __name__ == "__main__":
    unittest.main()
