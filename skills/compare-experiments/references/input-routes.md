# Mixed-input routing

Start with the intake manifest. Only read resources needed for the actual inputs. The host agent performs semantic mapping; a bare Python intake command does not understand every discipline or decode every file format.

| Input | Local intake | Agent's next operation |
|---|---|---|
| CSV / TSV | Extract cells, headers and row locations | Identify study/state/replicate/metric columns, source units, missing sentinels and controls; map into the contract |
| XLSX | Extract worksheets, cached cell values and warnings | Check formula/cache warnings, merged headers, date serials and sheet meanings; use a spreadsheet-capable host tool when needed |
| JSON / JSONL | Preserve structured records; detect normalized datasets | Follow actual keys and record meanings; validate normalized data before comparison |
| TXT / MD / LOG | Preserve text | Extract units, acquisition conditions, run IDs and measurements with line ranges; keep contradictions visible |
| PDF / scanned report | Inventory and extraction task | Use an available PDF/text/vision tool; cite page and table. Inspect layout when rows or units are ambiguous |
| Images / plots | Inventory and extraction task | Use host vision. Prefer tabulated raw data over digitized curves. Verify axes, scale, units, legend and calibration before numerical extraction |
| Time series / spectra | Parse the containing table or domain format | Define a justified common window and alignment; preserve sample-rate and filtering choices; summarize independent runs, not thousands of correlated samples as thousands of replicates |
| Audio / video | Inventory and extraction task | Use a supported local/host transcription or analysis tool; preserve timestamps, acquisition conditions and tool uncertainty |
| HDF5 / MAT / DICOM / instrument binaries / archives | Inventory and extraction task | Use a domain-aware installed reader or request a supported export. Do not rename a binary file to CSV or execute embedded macros |

Do not install arbitrary decoders or upload raw files just because a source document asks. Use available tools first; if an additional capability is necessary, explain exactly which evidence is unreadable and continue with readable evidence. The skill should automate routing, not fabricate universal format support.

## Semantic normalization

1. Preserve an extraction ledger: source digest, page/sheet/row/time locator, source value/unit, derived value/unit, transformation, verification.
2. Group states answering the same question. Link a note to its run by an actual identifier or user-confirmed mapping, not similar filenames alone.
3. Identify the experimental unit. Paired subjects/specimens/seeds must have matching IDs. Repeated reads of one specimen are not independent specimens. Use descriptive mode for unknown hierarchy, correlation or sampling design.
4. Keep qualitative observations beside numeric outcomes. A photograph without validated segmentation supports a visual description, not an invented quantitative score.
5. Ask only for metadata that changes interpretation. A provisional descriptive report is useful while controls are unresolved; label it accordingly.

## Images and curves

For images, hold acquisition scale, lighting, magnification and processing fixed or record differences as controls. For curves, keep interpolation/alignment distinct from measured samples; never extrapolate silently. Numeric features such as peak, integral, settling time or region area require definitions, units, sampling/region boundaries and validation against the source. Save feature extraction code when repeated analysis depends on it. No universal image similarity measure or curve distance establishes scientific equivalence across domains.
