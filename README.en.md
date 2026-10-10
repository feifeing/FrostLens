# FrostLens

**Two explanations fit your data. Which experiment should you run next?**

[中文](README.md) · [Research positioning](docs/RESEARCH.md) · [Methods](docs/METHODS.md)

FrostLens is a local, open-source experiment workbench for NH₃/CO₂ cascade refrigeration. Fit bounded grey-box parameters, inspect a competing explanation, diagnose weak local parameter directions, and choose the next experiment within your operating envelope.

The first release has a Chinese interface, three reproducible synthetic cases, CSV import, JSON/CSV export, and a virtual-measurement loop. All thermodynamic calculations use CoolProp. There is no account, API key, telemetry, cloud backend, or browser dependency download.

## Run

Python 3.11 or newer. On Windows, double-click `start.bat`; on macOS/Linux, run `sh start.sh`. The first run creates a virtual environment and installs dependencies. Or install manually:

```bash
python -m venv .venv
# Activate .venv for your OS, then:
python -m pip install .
python -m frostlens serve --open
```

Visit http://127.0.0.1:8765. Installation downloads dependencies; operation is local and offline. You may also open `frostlens/web/index.html` directly to inspect the included read-only computed snapshot. Recalculation and import require the server.

```bash
python -m frostlens demo --case narrow --output local-reports/demo.json
python -m frostlens analyze examples/wide.csv --sensor-mode split --output local-reports/result.json
python -m unittest discover -s tests -v
```

## Input contract

Required CSV columns: `te_c,tc_c,tm_c,load_kw,power_kw,sigma_kw`.
Optional channels: `low_power_kw,sigma_low_kw` (both required for split mode).

Temperatures are °C; loads, powers, and one-standard-deviation uncertainties are kW. `tm_c` is the CO₂ condensing saturation temperature, not a mean cascade temperature. At most 250 rows. Empty, nonfinite, out-of-domain and nonpositive-uncertainty inputs are rejected. Download an example through the UI or use `examples/`.

## Scope and originality

The contribution is the refrigeration-specific workflow: **competing explanations → identifiability → experiment design → new evidence**, with visible assumptions and reproducible artifacts. Least squares, Fisher information, D-optimal design and cascade-cycle simulation are established methods, not new algorithms claimed by this project.

This is an alpha research tool using a steady-state two-loop model with an equivalent cascade UA. Example observations are synthetic. No real equipment validation or energy-saving benefit is claimed. Local singular values do not prove global identifiability; displayed alternative fits are not confidence regions. Noise covariance and input uncertainty are not yet modeled. The operating envelope is a candidate-domain filter, not equipment safety certification.

Contributions are welcome: independent benchmarks, correlated-noise support, pressure/discharge-temperature limits, model extensions and translations. See [CONTRIBUTING.md](CONTRIBUTING.md). MIT licensed; dependencies retain their own licenses.
