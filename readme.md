# Privacy Filter Evaluation: What Actually Breaks

A minimal experiment testing OpenAI’s Privacy Filter on messy, enterprise-style text.

This is not a benchmark.  
This is a failure-mode study.

---

## What this project does

This app evaluates Privacy Filter in two ways:

### 1. Single Text Test
- Paste real-world messy text
- See:
  - raw model redaction
  - cleaned redaction (after span merging)
  - detected spans
  - overlap diagnostics

### 2. CSV Evaluation
- Upload a labeled CSV (30 cases)
- Computes:
  - Precision
  - Recall
  - F1
- Compares:
  - Raw Privacy Filter output
  - Cleaned output (post-processed spans)

---

## Key idea

> Privacy filtering is not just detection.  
> It is detection + post-processing + evaluation.

This project isolates two questions:

1. **What does the model detect?** (recall / precision)
2. **Is the output usable?** (span quality)

---

## Dataset design

The test set contains ~30 cases across:

- Obfuscated text  
  `john dot smith at example dot com`

- Fragmented numbers  
  `7 0 4 . 5 5 5 . 0 1 9 8`

- Spelled-out numbers  
  `two four six two eight eight seven three eight zero`

- Enterprise identifiers  
  `EMP-10293`, `REQ-4491`, `CASE-778812`

- Medical-style notes  
- Customer service transcripts  
- System logs / secrets  
- Safe control cases (should NOT redact)

Each row is a **single decision**:
> Should this exact text be redacted or not?

---

## Evaluation logic

### For positive cases (`should_redact = true`)

- **TP**: expected text is removed
- **FN**: expected text remains

### For negative cases (`should_redact = false`)

- **FP**: model produces any spans
- **TN**: no spans detected

---

## What we observed

### 1. High precision, moderate recall

- Precision: ~1.0  
- Recall: ~0.78  

The model is **conservative**:
- avoids over-redaction
- misses some PII

---

### 2. Consistent failure patterns

Missed cases (FN):

- **Enterprise IDs**
  - `EMP-10293`
  - `REQ-4491`

- **Fragmented numbers**
  - spaced phone numbers
  - spaced credit cards

- **Spelled-out numbers**
  - `two four six...`

- **Partial identifiers**
  - `0198`

- **Some structured tokens**
  - IP addresses

> The model handles natural language well, but struggles with structured and non-standard formats.

---

### 3. Raw output is not usable

Example:
[private_person][private_person]
or
[private_address][private_address][private_address]

---

### 4. Cleaning fixes output, not detection

A simple span-merging layer:

- removes duplicates
- merges overlaps
- stabilizes redaction

Result:
Raw: [private_person][private_person]
Cleaned: [private_person]

But:

- Precision: unchanged
- Recall: unchanged

> Cleanup improves usability, not coverage.

---

## What this project does NOT claim

- This is not a compliance solution
- This is not a full PII benchmark
- This does not measure all PII categories
- This does not replace domain-specific rules

---

## How to run

```bash
pip install -r requirements.txt
streamlit run app.py