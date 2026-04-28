# Privacy Filter Failure Modes

A small, focused evaluation of what actually breaks when OpenAI Privacy Filter is applied to messy, real-world enterprise text.

This is not a benchmark.  
This is a failure-mode study.

---

## Why this exists

PII detection is often treated as a solved preprocessing step.

In practice:
- text is messy
- identifiers are custom
- formats are inconsistent

> If I drop Privacy Filter into a real pipeline today, what actually fails?

---

## Quick Start (2 minutes)

```bash
git clone https://github.com/mariyamayoob/privacy-filter-failure-modes
cd privacy-filter-failure-modes
pip install -r requirements.txt
streamlit run app.py
```

Then:
- Open CSV Evaluation
- Upload test.csv
- Click Run Evaluation

Expected:
- Precision ≈ 1.0  
- Recall ≈ 0.75–0.8  

---

## What this app does

### Single Text Test
- Raw model redaction
- Cleaned redaction
- Span diagnostics

### CSV Evaluation
- Precision, Recall, F1
- Raw vs Cleaned comparison

---

## Example Output

### Metrics

![Metrics](docs/metrics.png)

Precision: 1.0  
Recall: ~0.78  
F1: ~0.87  

---

### Failure Example 
![Failed Cases](docs/failure.png)

Input:
Employee EMP-10293 escalated the issue

Output:
Employee EMP-10293 escalated the issue

Result:
Missed completely

---

## Key Findings

### High precision, moderate recall

The model is conservative:
- avoids over-redaction
- misses structured identifiers

### Consistent failure patterns

- Enterprise IDs (EMP-10293, REQ-4491)
- Fragmented numbers
- Spelled-out numbers
- Partial identifiers
- Some structured tokens
- Unlabelled credit card numbers

### Raw output is not usable

[private_person][private_person]

### Cleaning fixes output, not detection

Raw: [private_person][private_person]  
Cleaned: [private_person]

---

## What this proves

- Strong on natural language PII
- Weak on structured enterprise identifiers
- Needs post-processing layer

---

## What this does NOT prove

- Not a compliance solution
- Not a full benchmark
- Not exhaustive PII coverage

---

## Takeaway

The hardest PII problems are not emails or names.  
They are the identifiers your organization invented.
