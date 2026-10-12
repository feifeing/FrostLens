# Computation and interpretation

StateLens 0.2 is an exploratory comparison tool. The original implementation combines a declared comparison contract, evidence provenance, deterministic calculations and interactive sensitivity inspection. Bootstrap resampling, Pareto dominance and unit conversion are established methods; this project makes no claim to invent them or to be universally scientifically valid.

## Summary and differences

Each metric summarizes available observations using sample count, arithmetic mean, sample standard deviation and range. Values convert into the metric's declared unit. Raw change is candidate minus baseline. For higher/lower objectives, benefit is respectively change/negative change; for a target it is `abs(baseline_mean-target)-abs(candidate_mean-target)`. Higher benefit means closer to the declared goal. Goal definitions affect the answer and must be traceable to the user's question.

## Bootstrap intervals

The engine uses a local seeded pseudo-random generator and percentile endpoints (2.5% and 97.5%) of resampled mean-benefit estimates. Independent designs resample the two groups separately. Paired designs resample matching units together. IDs are aligned before sampling; incomplete pairing does not silently become an independent analysis. Replicate count below five suppresses confident labels even if an interval is displayed. This threshold is a conservative product rule, not a theorem guaranteeing validity at five observations.

Intervals are approximate, exploratory and unadjusted for multiple comparisons. They do not address confounding, selection bias, nonrepresentative data, hierarchical/serial dependence, instrument error, or unknown preprocessing. Very small samples, constant samples and nonlinear target objectives can make percentile intervals unreliable. A narrow interval is not evidence that controls were adequate. No p-values, significance declarations, universal power guarantees or causal effects are produced.

## Practical margin and sensitivity

For a comparable metric with sufficient data, an interval wholly above `margin` receives `better`; wholly below `-margin`, `worse`; strictly inside the practical band `[-margin,margin]`, `within_margin`; all other cases remain `uncertain`. These are decision labels conditional on assumptions, not confirmatory statistical tests. The report lets users change the margin without rerunning the bootstrap; an exported scenario stores these choices separately from the original measured report. A positive lower endpoint is the boundary beyond which an apparent improvement no longer clears the selected practical threshold.

Blocked, descriptive and insufficient comparisons cannot become confident merely by moving a control. A blocked comparison still shows descriptive values, because discovering why states cannot be fairly compared is useful.

## Pareto view

Within one study, eligible states are compared on their mean goal values. A state is dominated if another is at least as good on every objective and strictly better on one. This is descriptive, ignores joint uncertainty and does not select a universal winner. Missing objectives or failed comparability checks exclude states. Different studies and disciplines are never pooled into one leaderboard.

## Reproducibility

Reports record the normalized data's SHA-256, engine version, seed and resample count. Intake records raw-file hashes. Equal datasets and parameters produce equal calculations. Report shareability does not imply permission to publish private experimental data; generated reports embed their supplied evidence.

Method background: [Efron, Bootstrap Methods: Another Look at the Jackknife (1979)](https://doi.org/10.1214/aos/1176344552). This reference establishes bootstrap resampling, not a guarantee for this product's exact decision rules.
