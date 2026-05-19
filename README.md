# Invenra ADC Capital Map — Layer 1.2

Streamlit intelligence layer for tracking ADC clinical-trial activity by target using ClinicalTrials.gov v2.

## Layer 1.2 updates

- Anchors YoY comparisons to the actual current year instead of the latest future-dated trial start year returned by ClinicalTrials.gov.
- Excludes future-dated estimated starts from current-year momentum calculations.
- Normalizes phase strings such as `PHASE2; PHASE3` into clean buckets like `Phase 2/3`.
- Separates unspecified / not-applicable phase records from the main enrollment-by-phase charts so the visual signal is cleaner.
- Adds target-level basket momentum table so basket scans do not collapse into one ambiguous aggregate.
- Adds sponsor-by-target output for basket scans.
- Improves chart readability and sidebar control styling.

## Run locally

```bash
pip install -r requirements.txt
streamlit run app.py
```
