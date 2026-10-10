"""Physical, inferential and experiment-design checks, using actual CoolProp."""
import copy
import json
import unittest
from itertools import product
from types import SimpleNamespace
from unittest.mock import patch

from CoolProp.CoolProp import PropsSI
import numpy as np
from scipy.optimize import least_squares

from frostlens.core import (DEFAULT_BOUNDS, DISPLAY_DELTA_SSE, TRUE_PARAMETERS,
                           _Fit, _solve, analyze, case_rows, validate_rows, virtual_measurement)
from frostlens.model import ENVELOPE, KEYS, LOWER, SCALE, UPPER, point_prediction


class PhysicalModelTests(unittest.TestCase):
    def test_heos_cycle_matches_independent_enthalpy_balance(self):
        point = dict(te_c=-40, tc_c=35, tm_c=-8, load_kw=8)
        eta_l, eta_h, ua, aux = TRUE_PARAMETERS

        def independent_ratio(fluid, te, tc):
            h1 = PropsSI("Hmass", "T", te + 273.15, "Q", 1, fluid)
            s1 = PropsSI("Smass", "T", te + 273.15, "Q", 1, fluid)
            p2 = PropsSI("P", "T", tc + 273.15, "Q", 0, fluid)
            h2 = PropsSI("Hmass", "P", p2, "Smass", s1, fluid)
            h3 = PropsSI("Hmass", "T", tc + 273.15, "Q", 0, fluid)
            return (h2 - h1) / (h1 - h3)

        wl = point["load_kw"] * independent_ratio("CO2", -40, -8) / eta_l
        qc = point["load_kw"] + wl
        nh3_te = point["tm_c"] - qc / ua
        wh = qc * independent_ratio("Ammonia", nh3_te, 35) / eta_h
        total, low = point_prediction(point, TRUE_PARAMETERS)
        self.assertAlmostEqual(low, wl, places=9)
        self.assertAlmostEqual(total, wl + wh + aux, places=9)
        self.assertGreater(nh3_te, -70)
        self.assertLess(nh3_te, point["tm_c"])

    def test_derivatives_match_full_finite_difference(self):
        for point in [dict(te_c=-48, tc_c=44, tm_c=2, load_kw=14),
                      dict(te_c=-28, tc_c=24, tm_c=-15, load_kw=4)]:
            _, _, jt, jl = point_prediction(point, TRUE_PARAMETERS, derivative=True)
            finite_total, finite_low = [], []
            for i in range(4):
                delta = np.zeros(4)
                delta[i] = 1e-5
                above = np.array(point_prediction(point, TRUE_PARAMETERS + delta))
                below = np.array(point_prediction(point, TRUE_PARAMETERS - delta))
                diff = (above - below) / (2e-5)
                finite_total.append(diff[0])
                finite_low.append(diff[1])
            np.testing.assert_allclose(jt, finite_total, rtol=2e-5, atol=1e-6)
            np.testing.assert_allclose(jl, finite_low, rtol=2e-5, atol=1e-6)

    def test_parameter_and_operating_corners_are_physically_computable(self):
        for temperatures in product(*ENVELOPE.values()):
            point = dict(zip(ENVELOPE, temperatures))
            if point["tm_c"] - point["te_c"] < 8 or point["tc_c"] - point["tm_c"] < 12:
                continue
            for parameters in product(*zip(LOWER, UPPER)):
                total, low = point_prediction(point, parameters)
                self.assertTrue(np.isfinite(total))
                self.assertGreater(total, low)
                self.assertGreater(low, 0)

    def test_higher_ua_reduces_total_power(self):
        point = dict(te_c=-40, tc_c=35, tm_c=-8, load_kw=8)
        improved = TRUE_PARAMETERS.copy()
        improved[2] *= 1.5
        base = point_prediction(point, TRUE_PARAMETERS)
        after = point_prediction(point, improved)
        self.assertLess(after[0], base[0])
        self.assertEqual(after[1], base[1])


class InferenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.narrow = analyze(case_rows("narrow"))
        cls.wide = analyze(case_rows("wide"))
        cls.drift = analyze(case_rows("drift"))

    def test_synthetic_cases_have_distinct_expected_diagnostics(self):
        self.assertEqual(self.narrow["summary"]["status"], "weak")
        self.assertEqual(self.wide["summary"]["status"], "informative")
        self.assertEqual(self.drift["summary"]["status"], "mismatch")
        self.assertLess(self.narrow["summary"]["rank"], 4)
        self.assertEqual(self.narrow["summary"]["numerical_rank"], 4)
        self.assertEqual(self.narrow["identifiability"]["effective_direction_threshold"], 1.0)
        self.assertEqual(self.wide["summary"]["rank"], 4)
        self.assertGreater(self.drift["summary"]["weighted_rmse"], 2.5)
        self.assertLess(self.wide["summary"]["condition"], self.narrow["summary"]["condition"] / 10)

    def test_noiseless_diverse_inputs_recover_generating_parameters(self):
        rows = case_rows("wide")
        for row in rows:
            row["power_kw"], row["low_power_kw"] = point_prediction(row, TRUE_PARAMETERS)
        result = analyze(rows, "split", 1)
        recovered = np.array([p["value"] for p in result["parameters"]])
        np.testing.assert_allclose(recovered, TRUE_PARAMETERS, rtol=1e-6, atol=1e-7)
        self.assertLess(result["summary"]["weighted_rmse"], 1e-6)

    def test_alternative_is_distinct_and_actually_fits_observations(self):
        alternative = self.narrow["alternative"]
        self.assertIsNotNone(alternative)
        self.assertGreaterEqual(alternative["distance"], 0.12)
        self.assertLessEqual(alternative["delta_sse"], DISPLAY_DELTA_SSE + 1e-6)
        self.assertGreaterEqual(alternative["delta_sse"], -1e-9)
        p = np.array([alternative["parameters"][key] for key in KEYS])
        errors = []
        for row, prediction in zip(self.narrow["rows"], self.narrow["predictions"]):
            actual = point_prediction(row, p)[0]
            self.assertAlmostEqual(actual, prediction["alternative_kw"])
            errors.append(actual - row["power_kw"])
        self.assertAlmostEqual(alternative["rmse_kw"], np.sqrt(np.mean(np.square(errors))))
        self.assertIsNone(self.wide["alternative"])

    def test_independent_split_noise_adds_positive_semidefinite_information(self):
        rows = case_rows("wide")
        x = (TRUE_PARAMETERS - LOWER) / SCALE
        j_total = _Fit(rows, "power").jacobian(x)
        j_split = _Fit(rows, "split").jacobian(x)
        added = j_split.T @ j_split - j_total.T @ j_total
        self.assertGreaterEqual(np.linalg.eigvalsh(added)[0], -1e-7)
        self.assertGreater(added[0, 0], 1000)
        np.testing.assert_allclose(added[1:, :], 0, atol=1e-7)
        result = analyze(rows, "split", 1)
        self.assertTrue(any("独立噪声" in w for w in result["warnings"]))

    def test_reports_are_finite_json_and_reproducible(self):
        for report in (self.narrow, self.wide, self.drift):
            json.dumps(report, allow_nan=False)
            self.assertIn(report["fit"]["search_method"], ("multistart", "profile_polish"))
            self.assertIsInstance(report["fit"]["converged"], bool)
            self.assertAlmostEqual(report["fit"]["weighted_sse"],
                                   report["summary"]["weighted_rmse"] ** 2 * report["fit"]["residual_count"])
            for version in ("numpy_version", "scipy_version", "coolprop_version"):
                self.assertTrue(report["model"][version])
        self.assertEqual(case_rows("narrow"), case_rows("narrow"))
        point = self.narrow["design"][0]["point"]
        self.assertEqual(virtual_measurement("narrow", point, 12), virtual_measurement("narrow", point, 12))

    def test_drift_uses_global_sequence_and_plateaus_after_initial_sweep(self):
        point = dict(te_c=-40, tc_c=35, tm_c=-8, load_kw=8)
        with patch("frostlens.core.np.random.default_rng") as random_generator:
            random_generator.return_value.normal.return_value = 0.0
            initial = virtual_measurement("drift", point, 0)
            final = virtual_measurement("drift", point, 15)
            appended = virtual_measurement("drift", point, 16)
        self.assertGreater(final["low_power_kw"], initial["low_power_kw"])
        self.assertAlmostEqual(initial["low_power_kw"] * 0.74, final["low_power_kw"] * 0.52)
        self.assertEqual(final, appended)


class SolverRegressionTests(unittest.TestCase):
    class QuadraticFit:
        target = np.array([0.5, 0.5, 0.5, 0.85])

        def residual(self, x):
            return x - self.target

        def jacobian(self, x):
            return np.eye(4)

    def test_better_profile_releases_fixed_coordinate_before_becoming_best(self):
        fit = self.QuadraticFit()
        for polish_success in (True, False):
            calls = []

            def interrupted_multistarts(fun, x0, **kwargs):
                calls.append(len(x0))
                if len(calls) <= 3:
                    # Model a finite-budget multistart stuck before convergence.
                    x = np.array([0.5, 0.5, 0.5, 0.1])
                    return SimpleNamespace(x=x, fun=fun(x), success=False)
                result = least_squares(fun, x0, **kwargs)
                if len(x0) == 4:
                    result.success = polish_success
                return result

            with self.subTest(polish_success=polish_success), patch(
                    "frostlens.core.least_squares", side_effect=interrupted_multistarts):
                best, alternative = _solve(fit)
                self.assertEqual(best[2], "profile_polish")
                self.assertEqual(best[3], polish_success)
                np.testing.assert_allclose(best[1], fit.target, atol=1e-7)
                self.assertLess(best[0], 1e-12)
                self.assertEqual(calls, [4, 4, 4, 3, 3, 3, 3, 4])
                self.assertIsNotNone(alternative)
                self.assertEqual(alternative[2], "bounded_profile")

    def test_profiles_that_do_not_improve_fit_need_no_extra_polish(self):
        with patch("frostlens.core.least_squares", wraps=least_squares) as solver:
            best, _ = _solve(self.QuadraticFit())
        self.assertEqual(best[2], "multistart")
        self.assertEqual(solver.call_count, 7)


class DesignTests(unittest.TestCase):
    def test_design_gain_matches_direct_logdet_for_well_conditioned_data(self):
        rows = case_rows("wide")
        report = analyze(rows, "split", 3)
        p = np.array([parameter["value"] for parameter in report["parameters"]])
        jac = _Fit(rows, "split").jacobian((p - LOWER) / SCALE)
        information = jac.T @ jac + report["design_meta"]["ridge"] * np.eye(4)
        sigma = report["design_meta"]["prospective_sigma_kw"]
        sigma_low = report["design_meta"]["prospective_sigma_low_kw"]
        for item in report["design"]:
            _, _, total_jac, low_jac = point_prediction(item["point"], p, derivative=True)
            additional = np.array([total_jac * SCALE / sigma, low_jac * SCALE / sigma_low])
            updated = information + additional.T @ additional
            gain = np.linalg.slogdet(updated)[1] - np.linalg.slogdet(information)[1]
            self.assertAlmostEqual(item["gain"], gain, places=7)
            information = updated

    def test_design_is_sequential_physical_and_within_user_bounds(self):
        bounds = {"te_c": [-44, -32], "tc_c": [30, 40], "tm_c": [-12, -3], "load_kw": [6, 12]}
        report = analyze(case_rows("narrow"), "power", 5, bounds)
        self.assertEqual(len(report["design"]), 5)
        self.assertEqual(report["design_meta"]["bounds"], bounds)
        self.assertEqual(report["design_meta"]["candidate_count"], 81)
        points = set()
        p = np.array([v["value"] for v in report["parameters"]])
        alt = np.array([report["alternative"]["parameters"][key] for key in KEYS])
        last_smallest = 0
        for item in report["design"]:
            for key, (lo, hi) in bounds.items():
                self.assertLessEqual(lo, item["point"][key])
                self.assertLessEqual(item["point"][key], hi)
            points.add(tuple(item["point"].values()))
            best_p = point_prediction(item["point"], p)[0]
            other_p = point_prediction(item["point"], alt)[0]
            self.assertAlmostEqual(best_p, item["predicted_kw"])
            self.assertAlmostEqual(other_p, item["alternative_kw"])
            self.assertAlmostEqual(abs(best_p - other_p) / 0.045, item["separation_sigma"])
            self.assertGreaterEqual(item["gain"], 0)
            self.assertGreaterEqual(item["smallest_singular_after"] + 1e-8, item["smallest_singular_before"])
            self.assertGreaterEqual(item["smallest_singular_before"] + 1e-8, last_smallest)
            last_smallest = item["smallest_singular_after"]
        self.assertEqual(len(points), 5)

    def test_virtual_experiment_closes_loop_and_adds_information(self):
        rows = case_rows("narrow")
        before = analyze(rows)
        for _ in range(3):
            report = analyze(rows, budget=1)
            rows.append(virtual_measurement("narrow", report["design"][0]["point"], len(rows)))
        after = analyze(rows, budget=1)
        self.assertEqual(after["summary"]["n"], before["summary"]["n"] + 3)
        self.assertGreater(after["identifiability"]["singular_values"][-1],
                           before["identifiability"]["singular_values"][-1] * 3)
        self.assertLess(after["summary"]["condition"], before["summary"]["condition"])

    def test_single_candidate_and_empty_valid_domain(self):
        fixed = {key: [value, value] for key, value in dict(te_c=-40, tc_c=35, tm_c=-8, load_kw=8).items()}
        result = analyze(case_rows("wide"), budget=5, bounds=fixed)
        self.assertEqual(len(result["design"]), 1)
        invalid = dict(fixed, te_c=[-20, -20], tm_c=[-18, -18])
        result = analyze(case_rows("wide"), bounds=invalid)
        self.assertEqual(result["design"], [])
        self.assertEqual(result["design_meta"]["candidate_count"], 0)
        json.dumps(result, allow_nan=False)

    def test_identical_rows_and_small_noise_do_not_break_design(self):
        row = dict(te_c=-40, tc_c=35, tm_c=-8, load_kw=8, sigma_kw=1.01e-6)
        row["power_kw"] = point_prediction(row, TRUE_PARAMETERS)[0]
        report = analyze([dict(row) for _ in range(5)], budget=2)
        self.assertIsNone(report["summary"]["condition"])
        self.assertEqual(report["summary"]["numerical_rank"], 1)
        self.assertEqual(len(report["design"]), 2)
        json.dumps(report, allow_nan=False)


class ValidationTests(unittest.TestCase):
    def test_invalid_inputs_are_rejected(self):
        good = case_rows("narrow")
        changes = [("power_kw", float("nan")), ("sigma_kw", 0), ("load_kw", float("inf")),
                   ("te_c", -100), ("tm_c", True), ("power_kw", "7.4")]
        for key, value in changes:
            rows = copy.deepcopy(good)
            rows[0][key] = value
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                validate_rows(rows)
        with self.assertRaises(ValueError):
            validate_rows(good, "invented")
        del good[0]["low_power_kw"]
        with self.assertRaises(ValueError):
            validate_rows(good, "split")

    def test_budget_and_design_bounds_are_checked(self):
        rows = case_rows("wide")
        for budget in (True, 0, 6, 1.1):
            with self.assertRaises(ValueError):
                analyze(rows, budget=budget)
        for bounds in ({"te_c": [-20, -40]}, {"load_kw": [-1, 10]},
                       {"te_c": [float("nan"), -30]}, {"unsafe_key": [1, 2]}):
            with self.assertRaises(ValueError):
                analyze(rows, bounds=bounds)


if __name__ == "__main__":
    unittest.main()
