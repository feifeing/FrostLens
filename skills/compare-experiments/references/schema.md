# Comparison contract v1

The file is UTF-8 JSON. Numeric values must be finite numbers, not numeric strings. Missing values are `null` or absent, never zero imputation. IDs are unique within their study. A study has at least two states and a declared baseline state ID.

```json
{
  "schema_version": "1.0",
  "title": "Latency under a fixed workload",
  "sources": [{"id":"raw", "file":"runs.csv", "sha256":"actual file digest", "locator":"rows 2–13", "method":"CSV", "verified":true}],
  "studies": [{
    "id": "latency", "label": "Inference latency", "domain": "Computing",
    "question": "Does caching reduce latency on the same workload?",
    "baseline": "off", "design": "paired",
    "context_keys": ["device", "workload"], "varying": ["cache"],
    "metrics": [{"id":"time", "label":"Latency", "unit":"ms", "direction":"lower", "margin":2}],
    "states": [
      {"id":"off", "label":"Cache off", "context":{"device":"cpu-a", "workload":"fixed-v1", "cache":false}, "observations":[
        {"replicate":"batch-1", "values":{"time":52}, "source_id":"raw", "locator":"row 2"},
        {"replicate":"batch-2", "values":{"time":48}, "source_id":"raw", "locator":"row 3"}
      ]},
      {"id":"on", "label":"Cache on", "context":{"device":"cpu-a", "workload":"fixed-v1", "cache":true}, "observations":[
        {"replicate":"batch-1", "values":{"time":0.042}, "units":{"time":"s"}},
        {"replicate":"batch-2", "values":{"time":0.040}, "units":{"time":"s"}}
      ]}
    ]
  }]
}
```

This small illustration supports descriptive inspection; two pairs do not support a confident preference label. For executable, larger synthetic cases see `assets/demo.json`.

## Fields that determine interpretation

- `design`: `paired` resamples complete matched experimental units together; `independent` resamples separate independent units; `descriptive` performs no inference. Do not infer independence from one row per timestamp.
- `context_keys`: controls required to be known for both states. Missing/unknown required controls block preference claims. Represent unknowns as `null` or blank, not literal placeholder strings such as `unknown`, which cannot be distinguished from real category names. `context` values are scalar strings, booleans or numbers; normalize units before storing numeric conditions. `varying`: explicitly allowed interventions. Other changed context fields block comparisons. An empty `context_keys` list permits descriptive inspection only.
- `direction`: `higher`, `lower`, `target` with numeric `target`, or `observe` when desirability is unknown. For `observe`, the engine reports changes without ranking. The target criterion is distance of the **mean** to target, not average absolute deviation of individual trials.
- `margin`: smallest practically meaningful benefit, in the declared metric unit. A margin is a decision preference, not measurement uncertainty. Zero means no practical buffer, not proof of significance. Record whether it was prespecified or explored later.
- `observations`: one record per experimental unit in each state. `replicate` identifies the sampling/pairing unit. Each `values` key references a declared metric. `units` optionally overrides a source unit for that observation; otherwise the metric's unit applies.
- `sources`: real file digest, locator, extraction method, and verification state. Optional observation `source_id` and `locator` connect individual values to source evidence. Do not put credentials into provenance. JSON output retains the source list; give exact raw locations in the narrative where needed.

Supported conversion families include time (`s`, `ms`, `min`), power (`W`, `kW`), pressure (`Pa`, `kPa`, `MPa`), length (`m`, `cm`, `mm`), mass (`kg`, `g`, `mg`), temperature (`K`, `degC`), and ratios (`1`, `fraction`, `%`). Use the same literal custom unit on both states when no conversion exists; the report warns that dimensional compatibility was not independently checked. Do not label a physical quantity as dimensionless to bypass a conversion failure.

Percent-of-baseline changes are omitted for temperature scales and non-positive baselines. A change of five percentage points is not necessarily a five-percent relative change.

The engine is intentionally strict about duplicate IDs, booleans as measurements, unsupported unit conversions and non-finite values. Fix the mapping from the source instead of coercing invalid data silently. For paired designs, if both states are missing the same metric on the same units, complete shared pairs can be used with a missingness warning; unequal valid-ID sets suppress inference. States with missing outcomes are excluded from the Pareto view.
