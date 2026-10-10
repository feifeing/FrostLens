# Synthetic examples

All data in this directory are generated, not laboratory measurements.

Run `python tools/rebuild_examples.py` from the repository root to rebuild CSV, JSON and the browser's read-only snapshot. JSON reports record software/property versions and an SHA-256 fingerprint of normalized input rows. Report timestamps change on each rebuild; generated measurements use deterministic seeds derived from the case, operating point and measurement index.

- `narrow`: 12 nearly repeated operating conditions. Good fit, weak local parameter constraints.
- `wide`: 16 diverse operating conditions using the same fixed generating parameters.
- `drift`: the same diverse schedule with low-stage efficiency declining across measurement order. A fixed-parameter model is intentionally misspecified.

Generating values for the fixed cases are eta_low=0.70, eta_high=0.74, UA=1.80 kW/K, auxiliary power=0.35 kW. Total and low-stage measurements receive independent Gaussian noise with standard deviations 0.045 and 0.025 kW. Drift uses eta_low = 0.74 − 0.22·min(index/15, 1); appended measurements continue the index instead of resetting it. Inference and recommendation do not read these hidden generating parameters.

Reimporting any of these CSV files correctly marks them as **user-imported** data; it does not turn them into real laboratory measurements. The tool does not generate additional observations for imported data.
