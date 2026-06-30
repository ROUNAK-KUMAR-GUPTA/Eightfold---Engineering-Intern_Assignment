# Demo Video Script — Multi-Source Candidate Data Transformer

**Duration**: ~3-4 minutes
**Setup**: Terminal open in `candidate-transformer/` directory

---

## 1. Introduction (30s)

"Hi, I'm Aman Kumar, and this is a demo of the Multi-Source Candidate Data Transformer — a pipeline that ingests candidate data from multiple sources, normalizes fields, merges and deduplicates across sources, and tracks provenance for every field."

"Let me show you how it works end-to-end."

---

## 2. Show the Input Sources (30s)

```bash
cat sample_inputs/recruiter_export.csv
```

"Here's a recruiter CSV with 4 rows — notice two entries for Jane Smith with slightly different data, plus John Doe and Alice Chen."

```bash
cat sample_inputs/github_profile_janesmith.json
```

"And here's a GitHub profile JSON for Jane Smith with her languages and bio."

```bash
pdftotext sample_inputs/jane_smith_resume.pdf -
```

"And a resume PDF for Jane Smith with detailed experience and education."

---

## 3. Run the Pipeline (30s)

```bash
python3 cli.py \
  --csv sample_inputs/recruiter_export.csv \
  --resume sample_inputs/jane_smith_resume.pdf \
  --github sample_inputs/github_profile_janesmith.json \
  --github sample_inputs/github_profile_johndoe.json \
  -o output.jsonl \
  --stats --validate
```

"The pipeline loads 7 raw candidates from 4 sources, normalizes all fields, matches candidates across sources by email then phone then name, and merges them into 3 canonical profiles. The output validates successfully."

---

## 4. Examine the Output (45s)

```bash
head -1 output.jsonl | python3 -m json.tool
```

"Let's look at the first merged profile — Jane Smith. Notice how data from all three sources has been merged: emails from both CSV rows plus resume and GitHub, the phone number normalized to E.164 format `+14085551234`, skills canonicalized (`python` not `Python`), and dates in YYYY-MM format."

"Scroll down to show provenance entries..."

"And here's the provenance — every field tracks where it came from, the merge method used, and a confidence score. For example, `full_name` came from `resume_pdf` with method `priority_pick` and confidence 1.0, because resume has the highest priority at 0.9 and all sources corroborated."

---

## 5. Custom Projection (30s)

```bash
cat sample_inputs/custom_config.json
```

"Now let's use a custom projection config — this renames `emails[0]` to `contact_email`, adds confidence metadata, and applies normalization."

```bash
python3 cli.py \
  --csv sample_inputs/recruiter_export.csv \
  --resume sample_inputs/jane_smith_resume.pdf \
  --github sample_inputs/github_profile_janesmith.json \
  --github sample_inputs/github_profile_johndoe.json \
  -o custom_output.jsonl \
  --config sample_inputs/custom_config.json \
  --include-confidence
```

```bash
head -1 custom_output.jsonl | python3 -m json.tool | head -30
```

"Notice the output shape is completely different — `contact_email` instead of `emails[0]`, and each field now has a `{value, confidence, sources}` wrapper. All driven by the config file, no code changes."

---

## 6. Run Tests (20s)

```bash
python3 -m pytest tests/test_pipeline.py -v
```

"68 tests covering normalization, parsing, merge, projection, validation, integration, and edge cases — all passing."

---

## 7. Determinism Check (15s)

```bash
python3 cli.py --csv sample_inputs/recruiter_export.csv --resume sample_inputs/jane_smith_resume.pdf --github sample_inputs/github_profile_janesmith.json --github sample_inputs/github_profile_johndoe.json -o run1.jsonl
python3 cli.py --csv sample_inputs/recruiter_export.csv --resume sample_inputs/jane_smith_resume.pdf --github sample_inputs/github_profile_janesmith.json --github sample_inputs/github_profile_johndoe.json -o run2.jsonl
diff run1.jsonl run2.jsonl && echo "IDENTICAL - Deterministic"
```

"Running the pipeline twice produces byte-identical output — the pipeline is fully deterministic."

---

## 8. Graceful Degradation (15s)

```bash
python3 cli.py --csv nonexistent.csv --resume sample_inputs/jane_smith_resume.pdf -o degraded.jsonl --stats
```

"Even with a missing CSV file, the pipeline continues with the available sources and prints a warning — graceful degradation."

---

## 9. Wrap-up (15s)

"To summarize: the pipeline handles structured and unstructured sources, normalizes all fields to canonical forms, merges and deduplicates with provenance tracking, supports runtime configurable output projection, is deterministic, and gracefully degrades on bad input. The technical design document and full source code with tests are included. Thank you."
