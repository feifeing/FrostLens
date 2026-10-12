"""Scientific and safety invariants for the standalone StateLens engine."""

import copy
import importlib.util
import json
import math
from pathlib import Path
import random
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "skills" / "compare-experiments" / "scripts" / "engine.py"
SPEC = importlib.util.spec_from_file_location("statelens_engine_test", SCRIPT)
engine = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(engine)


def dataset(a=(1, 2, 3, 4, 5), b=(3, 4, 5, 6, 7), design="paired"):
    def state(sid, values):
        return {"id": sid, "label": sid, "context": {"instrument": "same", "treatment": sid},
                "observations": [{"replicate": str(i), "values": {"score": value}} for i, value in enumerate(values)]}
    return {"schema_version": "1.0", "title": "Synthetic invariant", "synthetic": True,
            "studies": [{"id": "study", "label": "Study", "domain": "test", "question": "Which state improves score?",
                         "baseline": "a", "design": design, "context_keys": ["instrument", "treatment"],
                         "varying": ["treatment"],
                         "metrics": [{"id": "score", "label": "Score", "unit": "1", "direction": "higher", "margin": 0.5}],
                         "states": [state("a", a), state("b", b)]}]}


def compare(data, **kwargs):
    return engine.compare_dataset(data, draws=200, **kwargs)


def result(data, **kwargs):
    return compare(data, **kwargs)["studies"][0]["comparisons"][0]["metrics"][0]


class StateLensEngineTests(unittest.TestCase):
    def test_paired_alignment_is_by_id_not_row_position(self):
        data = dataset()
        data["studies"][0]["states"][1]["observations"].reverse()
        value = result(data)
        self.assertEqual(value["interval"], [2.0, 2.0])
        self.assertEqual(value["decision"], "better")
        self.assertEqual(value["n_pairs"], 5)

    def test_incomplete_pairs_suppress_inference_and_pareto(self):
        data = dataset()
        data["studies"][0]["states"][1]["observations"][0]["replicate"] = "unmatched"
        report = compare(data)["studies"][0]
        value = report["comparisons"][0]["metrics"][0]
        self.assertEqual(value["n_pairs"], 4)
        self.assertIsNone(value["interval"])
        self.assertEqual(value["decision"], "insufficient")
        self.assertNotIn("b", report["pareto"]["eligible_ids"])
        self.assertTrue(any("仅基线有效" in warning for warning in value["warnings"]))

    def test_missing_values_are_not_zero_and_incomplete_pairs_are_flagged(self):
        data = dataset()
        data["studies"][0]["states"][1]["observations"][0]["values"]["score"] = None
        value = result(data)
        self.assertEqual(value["n_state"], 4)
        self.assertEqual(value["state_mean"], 5.5)
        self.assertEqual(value["decision"], "insufficient")
        self.assertIsNone(value["interval"])

    def test_absent_metric_is_missing_and_all_missing_is_insufficient(self):
        data = dataset(design="independent")
        for item in data["studies"][0]["states"][1]["observations"]:
            item["values"] = {}
        value = result(data)
        self.assertEqual(value["n_state"], 0)
        self.assertIsNone(value["state_mean"])
        self.assertIsNone(value["delta"])
        self.assertEqual(value["decision"], "insufficient")

    def test_small_samples_do_not_receive_confident_label(self):
        for n in (1, 2, 4):
            with self.subTest(n=n):
                value = result(dataset([1] * n, [10] * n))
                self.assertEqual(value["decision"], "insufficient")
                self.assertEqual(value["interval"], None if n == 1 else [9.0, 9.0])
                self.assertIsNone(value["sensitivity"]["positive_margin_max"])

    def test_unit_conversion_precedes_statistics(self):
        data = dataset([1000, 2000, 3000, 4000, 5000], [2, 3, 4, 5, 6])
        study = data["studies"][0]
        study["metrics"][0]["unit"] = "s"
        for obs in study["states"][0]["observations"]:
            obs["units"] = {"score": "ms"}
        value = result(data)
        self.assertEqual(value["baseline_mean"], 3.0)
        self.assertEqual(value["delta"], 1.0)
        self.assertEqual(value["interval"], [1.0, 1.0])

    def test_affine_temperature_conversion_and_no_percent(self):
        data = dataset([0] * 5, [283.15] * 5)
        study = data["studies"][0]
        study["metrics"][0]["unit"] = "K"
        for obs in study["states"][0]["observations"]:
            obs["units"] = {"score": "degC"}
        value = result(data)
        self.assertAlmostEqual(value["delta"], 10.0)
        self.assertAlmostEqual(value["baseline_mean"], 273.15)
        self.assertIsNone(value["percent_delta"])

    def test_fraction_percent_conversion(self):
        data = dataset([0.5] * 5, [60] * 5)
        study = data["studies"][0]
        study["metrics"][0]["unit"] = "%"
        for obs in study["states"][0]["observations"]:
            obs["units"] = {"score": "fraction"}
        value = result(data)
        self.assertEqual(value["delta"], 10.0)
        self.assertEqual(value["percent_delta"], 20.0)

    def test_dimensionless_ratio_converts_to_percent(self):
        data = dataset([0.5] * 5, [60] * 5)
        study = data["studies"][0]
        study["metrics"][0]["unit"] = "%"
        for obs in study["states"][0]["observations"]:
            obs["units"] = {"score": "1"}
        self.assertEqual(result(data)["baseline_mean"], 50.0)

    def test_incompatible_units_rejected_even_for_missing_values(self):
        data = dataset()
        data["studies"][0]["metrics"][0]["unit"] = "s"
        obs = data["studies"][0]["states"][0]["observations"][0]
        obs["values"]["score"] = None
        obs["units"] = {"score": "kg"}
        with self.assertRaisesRegex(engine.ValidationError, "incompatible units"):
            compare(data)

    def test_unknown_identical_units_warn_but_never_infer_conversion(self):
        data = dataset()
        data["studies"][0]["metrics"][0]["unit"] = "arbitrary intensity"
        self.assertTrue(any("单位未登记" in w for w in result(data)["warnings"]))
        data["studies"][0]["states"][0]["observations"][0]["units"] = {"score": "a.u."}
        with self.assertRaisesRegex(engine.ValidationError, "cannot convert unknown unit"):
            compare(data)

    def test_confounded_context_blocks_preference_but_retains_difference(self):
        data = dataset()
        data["studies"][0]["states"][1]["context"]["instrument"] = "different"
        study = compare(data)["studies"][0]
        comparison = study["comparisons"][0]
        self.assertEqual(comparison["gate"], "blocked")
        self.assertEqual(comparison["metrics"][0]["decision"], "blocked")
        self.assertEqual(comparison["metrics"][0]["delta"], 2.0)
        self.assertIsNone(comparison["metrics"][0]["interval"])
        self.assertNotIn("b", study["pareto"]["eligible_ids"])

    def test_missing_required_context_blocks_even_when_varying(self):
        data = dataset()
        del data["studies"][0]["states"][1]["context"]["treatment"]
        self.assertEqual(result(data)["decision"], "blocked")

    def test_unknown_required_controls_block_both_states_and_pareto(self):
        for unknown in (None, "", "   "):
            data = dataset()
            for state in data["studies"][0]["states"]:
                state["context"]["instrument"] = unknown
            with self.subTest(unknown=unknown):
                study = compare(data)["studies"][0]
                self.assertEqual(study["comparisons"][0]["metrics"][0]["decision"], "blocked")
                self.assertEqual(study["pareto"]["eligible_ids"], [])

    def test_changed_extra_context_also_blocks(self):
        data = dataset()
        data["studies"][0]["states"][1]["context"]["operator"] = "new"
        self.assertEqual(result(data)["decision"], "blocked")

    def test_true_and_one_are_different_context_values(self):
        data = dataset()
        states = data["studies"][0]["states"]
        states[0]["context"]["instrument"] = True
        states[1]["context"]["instrument"] = 1
        self.assertEqual(result(data)["decision"], "blocked")

    def test_no_controls_is_descriptive_and_unranked(self):
        data = dataset()
        data["studies"][0]["context_keys"] = []
        study = compare(data)["studies"][0]
        self.assertEqual(study["comparisons"][0]["metrics"][0]["decision"], "descriptive")
        self.assertIsNone(study["comparisons"][0]["metrics"][0]["interval"])
        self.assertEqual(study["pareto"]["state_ids"], [])

    def test_observe_has_no_benefit_interval_or_ranking(self):
        data = dataset()
        data["studies"][0]["metrics"][0]["direction"] = "observe"
        study = compare(data)["studies"][0]
        value = study["comparisons"][0]["metrics"][0]
        self.assertEqual(value["decision"], "descriptive")
        self.assertIsNone(value["benefit"])
        self.assertIsNone(value["interval"])
        self.assertEqual(study["pareto"]["state_ids"], [])

    def test_descriptive_design_does_not_bootstrap(self):
        value = result(dataset(design="descriptive"))
        self.assertEqual(value["decision"], "descriptive")
        self.assertIsNone(value["interval"])

    def test_lower_direction_reverses_benefit_but_not_delta(self):
        data = dataset()
        data["studies"][0]["metrics"][0]["direction"] = "lower"
        value = result(data)
        self.assertEqual(value["delta"], 2.0)
        self.assertEqual(value["benefit"], -2.0)
        self.assertEqual(value["interval"], [-2.0, -2.0])
        self.assertEqual(value["decision"], "worse")

    def test_target_benefit_is_distance_of_means_not_signed_delta(self):
        data = dataset([4, 5, 6, 7, 8], [8, 9, 10, 11, 12])
        metric = data["studies"][0]["metrics"][0]
        metric.update(direction="target", target=10)
        value = result(data)
        self.assertEqual(value["benefit"], 4.0)
        # Bootstrap samples which cross the target are recomputed nonlinearly.
        self.assertLess(value["interval"][0], 4.0)
        self.assertAlmostEqual(value["interval"][1], 4.0)
        self.assertEqual(compare(data)["studies"][0]["pareto"]["state_ids"], ["b"])

    def test_target_is_distance_of_group_mean_not_mean_trial_distance(self):
        data = dataset([2] * 6, [-10, 10] * 3)
        data["studies"][0]["metrics"][0].update(direction="target", target=0)
        self.assertEqual(result(data)["benefit"], 2.0)

    def test_paired_linear_differences_avoid_cancellation_at_large_offsets(self):
        a = [1e16 + 2 * i for i in range(6)]
        value = result(dataset(a, [v + 2 for v in a]))
        self.assertEqual(value["delta"], 2.0)
        self.assertEqual(value["benefit"], 2.0)
        self.assertEqual(value["interval"], [2.0, 2.0])

    def test_margin_boundaries_are_strict_and_sensitivity_exclusive(self):
        data = dataset()
        data["studies"][0]["metrics"][0]["margin"] = 2.0
        value = result(data)
        self.assertEqual(value["decision"], "uncertain")
        self.assertEqual(value["sensitivity"]["positive_margin_max"], 2.0)
        data["studies"][0]["metrics"][0]["margin"] = 2.1
        self.assertEqual(result(data)["decision"], "within_margin")

    def test_negative_and_zero_baseline_percent_suppressed(self):
        for baseline in (0, -2):
            with self.subTest(baseline=baseline):
                self.assertIsNone(result(dataset([baseline] * 5, [1] * 5))["percent_delta"])

    def test_tiny_baseline_percent_overflow_does_not_break_report(self):
        value = result(dataset([5e-324] * 5, [1e90] * 5))
        self.assertIsNone(value["percent_delta"])
        self.assertTrue(math.isclose(value["delta"], 1e90, rel_tol=1e-15))

    def test_deterministic_without_global_random_mutation(self):
        data = dataset(design="independent")
        state = random.getstate()
        first = compare(data)
        self.assertEqual(first, compare(data))
        self.assertEqual(state, random.getstate())
        self.assertNotEqual(result(data, seed=1)["interval"], result(data, seed=2)["interval"])

    def test_independent_interval_has_variation_unlike_exact_paired_shift(self):
        paired = result(dataset())
        independent = result(dataset(design="independent"))
        self.assertEqual(paired["interval"], [2.0, 2.0])
        self.assertLess(independent["interval"][0], 2.0)
        self.assertGreater(independent["interval"][1], 2.0)
        self.assertIsNone(independent["n_pairs"])

    def test_independent_bootstrap_resamples_each_group_at_its_own_size(self):
        data = dataset([1] * 5, [7] * 9, design="independent")
        value = result(data)
        self.assertEqual((value["n_baseline"], value["n_state"]), (5, 9))
        self.assertEqual(value["interval"], [6.0, 6.0])

    def test_interval_stable_when_observation_order_changes(self):
        data = dataset(design="independent")
        expected = result(data)["interval"]
        for state in data["studies"][0]["states"]:
            state["observations"].reverse()
        self.assertEqual(result(data)["interval"], expected)

    def test_paired_shared_missing_values_use_complete_cases_with_warning(self):
        data = dataset(range(7), range(2, 9))
        for state in data["studies"][0]["states"]:
            state["observations"][0]["values"]["score"] = None
        study = compare(data)["studies"][0]
        value = study["comparisons"][0]["metrics"][0]
        self.assertEqual(value["n_pairs"], 6)
        self.assertEqual(value["interval"], [2.0, 2.0])
        self.assertTrue(value["warnings"])
        self.assertEqual(study["pareto"]["eligible_ids"], [])

    def test_input_untouched_and_hash_covers_provenance(self):
        data = dataset()
        data["sources"] = [{"id": "src", "file": "synthetic.csv", "verified": False}]
        data["notes"] = "Unverified extraction"
        before = copy.deepcopy(data)
        first = compare(data)
        self.assertEqual(data, before)
        self.assertEqual(first["provenance"]["sources"], data["sources"])
        self.assertTrue(first["provenance"]["synthetic"])
        data["sources"][0]["verified"] = True
        self.assertNotEqual(first["provenance"]["sha256"], compare(data)["provenance"]["sha256"])
        json.dumps(first, allow_nan=False)

    def test_non_json_and_nonfinite_values_rejected(self):
        for bad in (True, "5", float("nan"), float("inf"), 10**1000):
            with self.subTest(value=type(bad).__name__):
                data = dataset()
                data["studies"][0]["states"][0]["observations"][0]["values"]["score"] = bad
                with self.assertRaises(engine.ValidationError):
                    compare(data)
        data = dataset()
        data["sources"] = [{"unrecognized": float("nan")}]
        with self.assertRaises(engine.ValidationError):
            compare(data)

    def test_duplicate_ids_replicates_and_unknown_metrics_rejected(self):
        mutations = [
            lambda d: d["studies"].append(copy.deepcopy(d["studies"][0])),
            lambda d: d["studies"][0]["metrics"].append(copy.deepcopy(d["studies"][0]["metrics"][0])),
            lambda d: d["studies"][0]["states"].append(copy.deepcopy(d["studies"][0]["states"][0])),
            lambda d: d["studies"][0]["states"][0]["observations"].append(copy.deepcopy(d["studies"][0]["states"][0]["observations"][0])),
            lambda d: d["studies"][0]["states"][0]["observations"][0]["values"].update(typo=5),
        ]
        for mutation in mutations:
            data = dataset()
            mutation(data)
            with self.subTest(mutation=mutation), self.assertRaises(engine.ValidationError):
                compare(data)

    def test_invalid_design_target_margin_and_bounds_rejected(self):
        for field, value in (("design", "random"), ("baseline", "missing")):
            data = dataset()
            data["studies"][0][field] = value
            with self.assertRaises(engine.ValidationError):
                compare(data)
        for edit in ({"margin": -1}, {"direction": "target"}, {"margin": True}):
            data = dataset()
            data["studies"][0]["metrics"][0].update(edit)
            with self.assertRaises(engine.ValidationError):
                compare(data)
        for draws in (False, 0, 99, 10001, 200.5):
            with self.assertRaises(engine.ValidationError):
                engine.compare_dataset(dataset(), draws=draws)

    def test_multiobjective_tradeoff_keeps_both_nondominated_states(self):
        data = dataset()
        study = data["studies"][0]
        study["metrics"].append({"id": "cost", "unit": "1", "direction": "lower", "margin": 0})
        for state in study["states"]:
            for obs in state["observations"]:
                obs["values"]["cost"] = 1 if state["id"] == "a" else 2
        self.assertEqual(compare(data)["studies"][0]["pareto"]["state_ids"], ["a", "b"])

    def test_work_budget_is_explicit_and_never_fabricates_interval(self):
        previous = engine.MAX_BOOTSTRAP_WORK
        try:
            engine.MAX_BOOTSTRAP_WORK = 1
            value = result(dataset())
            self.assertEqual(value["decision"], "insufficient")
            self.assertIsNone(value["interval"])
            self.assertTrue(any("计算量上限" in w for w in value["warnings"]))
        finally:
            engine.MAX_BOOTSTRAP_WORK = previous


if __name__ == "__main__":
    unittest.main()
