# Multi-Source Candidate Data Transformer

A deterministic, extensible pipeline that ingests candidate data from multiple heterogeneous sources (recruiter CSV, resume PDF, GitHub JSON), normalizes fields to canonical representations, merges and deduplicates across sources into one canonical profile per candidate, tracks provenance for every field, and supports runtime-configurable output projection.

## Quick Start

```bash
# Install dependencies
pip install phonenumbers pycountry pydantic

# Run the pipeline with all sample inputs
python3 cli.py \
  --csv sample_inputs/recruiter_export.csv \
  --resume sample_inputs/jane_smith_resume.pdf \
  --github sample_inputs/github_profile_janesmith.json \
  --github sample_inputs/github_profile_johndoe.json \
  -o output.jsonl \
  --stats --validate

# Run with custom projection config (field renaming, confidence metadata)
python3 cli.py \
  --csv sample_inputs/recruiter_export.csv \
  --resume sample_inputs/jane_smith_resume.pdf \
  --github sample_inputs/github_profile_janesmith.json \
  --github sample_inputs/github_profile_johndoe.json \
  -o custom_output.jsonl \
  --config sample_inputs/custom_config.json \
  --include-confidence

# Print output to terminal instead of file
python3 cli.py \
  --csv sample_inputs/recruiter_export.csv \
  --print

# Run test suite
python3 -m pytest tests/test_pipeline.py -v
```

## Architecture

The pipeline follows a layered architecture:

1. **Parser Layer** — Source-specific parsers extract raw candidate data from each input format
2. **Normalization Layer** — Field normalizers convert raw values to canonical representations
3. **Merge/Conflation Engine** — Groups candidates by identity keys, merges fields with priority-based conflict resolution
4. **Projection Layer** — Runtime JSON config reshapes output (field selection, renaming, confidence metadata)
5. **Output Layer** — NDJSONL serialization with schema validation

## Source Types

| Source | Type | Priority | Parser | Key Fields |
|--------|------|----------|--------|------------|
| Recruiter CSV | Structured | 0.8 | `csv_parser` | name, email, phone, company, title, skills, location |
| Resume PDF | Unstructured | 0.9 | `resume_parser` | name, email, phone, skills, experience, education, links |
| GitHub JSON | Structured/API | 0.7 | `github_parser` | name, bio, location, blog, email, languages→skills |

## Normalizations

| Field | Input Examples | Output Format | Library |
|-------|---------------|---------------|---------|
| Phone | `(408) 555-1234`, `408-555-1234` | `+14085551234` (E.164) | `phonenumbers` |
| Date | `Jan 2020`, `01/2020`, `2020-01-15` | `2020-01` (YYYY-MM) | regex |
| Country | `United States`, `US`, `us` | `US` (ISO 3166 α2) | `pycountry` |
| Email | `Jane@Gmail.COM` | `jane@gmail.com` | lower() |
| Skill | `JS`, `Py`, `K8s`, `Postgres` | `javascript`, `python`, `kubernetes`, `postgresql` | alias map |
| Name | `jane  smith` | `Jane Smith` | title + collapse whitespace |
| URL | `example.com`, `https://example.com/` | `https://example.com` | add scheme, strip slashes |

## Merge Algorithm

1. **Match** — Group raw candidates by identity keys in priority order:
   - Email (exact, normalized) — primary
   - Phone (E.164) — secondary
   - Normalized name — tertiary
   - First match wins; grouping is transitive

2. **Normalize** — Apply all field normalizers to each raw candidate independently before merge

3. **Merge scalar fields** (name, years_experience, summary):
   - Pick value from highest-priority source
   - If ≥2 sources agree → corroborate (+0.1 confidence)
   - If sources disagree → conflict (−0.2 confidence), record `conflict_resolved` method

4. **Merge list fields** (emails, phones, skills, etc.):
   - Union with deduplication
   - Confidence = weighted average of contributing sources

5. **Provenance** — Every output field records: source, method, raw_value, confidence

6. **Candidate ID** — MD5 hex of first available match key for determinism

## Confidence Model

```
base_confidence = source_priority
per corroborating source: +0.1
per conflicting source:  -0.2
clamped to [0, 1]
```

Example: A name from resume (0.9) corroborated by CSV (0.8) and GitHub (0.7):
- base = 0.9, +0.1 (CSV agrees) +0.1 (GitHub agrees) = 1.0 → clamped to 1.0

## Projection Configuration

Runtime JSON config reshapes output without code changes. Example (`sample_inputs/custom_config.json`):

```json
{
  "fields": [
    {"path": "full_name"},
    {"path": "emails[0]", "output_name": "contact_email"},
    {"path": "phones[0]", "output_name": "phone", "normalization": "E164"},
    {"path": "skills", "normalization": "canonical"},
    {"path": "experience"},
    {"path": "years_experience"}
  ],
  "include_confidence": true,
  "on_missing": "null"
}
```

Supported projection options:
- **path** — Dot-separated field path with optional array index (e.g., `phones[0]`, `experience[0].company`)
- **output_name** — Rename the field in output
- **normalization** — Per-field transform: `E164`, `canonical`, `lowercase`, `uppercase`, `trim`
- **include_confidence** — Attach `{value, confidence, sources}` wrapper to each field
- **on_missing** — Handling for absent fields: `null` (default), `omit`, `error`

## CLI Reference

```
python3 cli.py [OPTIONS]

Input Sources:
  --csv FILE         Recruiter CSV file (can specify multiple)
  --resume FILE      Resume PDF file (can specify multiple)
  --github FILE      GitHub profile JSON file (can specify multiple)

Output:
  -o, --output FILE  Output NDJSONL file path
  --config FILE      Custom projection configuration JSON
  --include-confidence  Include confidence metadata in output
  --on-missing VAL   Missing field handling: null, omit, error (default: null)
  --print            Print output to terminal
  --stats            Print pipeline statistics
  --validate         Validate output against schema
```

## Project Structure

```
candidate-transformer/
├── cli.py                              # CLI entry point
├── src/
│   ├── __init__.py
│   ├── models.py                       # Pydantic v2 canonical schema
│   ├── pipeline.py                     # Pipeline orchestrator
│   ├── normalizers/
│   │   ├── __init__.py
│   │   └── fields.py                   # All field normalizers
│   ├── parsers/
│   │   ├── __init__.py
│   │   ├── csv_parser.py              # Recruiter CSV parser
│   │   ├── resume_parser.py           # Resume PDF parser (pdftotext + regex)
│   │   └── github_parser.py           # GitHub JSON parser
│   ├── merge/
│   │   ├── __init__.py
│   │   └── engine.py                  # Merge/conflation engine
│   ├── config/
│   │   ├── __init__.py
│   │   └── projection.py             # Runtime projection configuration
│   └── validators/
│       ├── __init__.py
│       └── schema.py                  # Output schema validation
├── tests/
│   └── test_pipeline.py              # 68 tests (normalization, parsing, merge, projection, validation, integration, edge cases)
├── sample_inputs/
│   ├── recruiter_export.csv           # 4 candidate rows (2 Jane Smith, 1 John Doe, 1 Alice Chen)
│   ├── jane_smith_resume.pdf          # Resume PDF for Jane Smith
│   ├── github_profile_janesmith.json  # GitHub profile for Jane Smith
│   ├── github_profile_johndoe.json    # GitHub profile for John Doe
│   └── custom_config.json            # Custom projection config example
├── sample_outputs/
│   ├── default_output.jsonl           # Default NDJSONL output (3 merged profiles)
│   └── custom_output.jsonl            # Custom projection output with confidence
└── docs/
    └── design_doc.html               # Technical design document source
```

## Sample Output

Running the full pipeline produces 3 merged canonical profiles from 7 raw candidates:

```json
{
  "candidate_id": "c_65536e21c61f",
  "full_name": "Jane Smith",
  "emails": ["jane.smith@techcorp.com", "jane.smith@gmail.com"],
  "phones": ["+14085551234"],
  "locations": ["San Jose, CA"],
  "skills": ["python", "javascript", "typescript", "kubernetes", "docker", ...],
  "experience": [
    {"company": "TechCorp Inc", "title": "Senior Software Engineer", "start": "2020-01", "end": "present", ...},
    {"company": "DataSystems LLC", "title": "Software Engineer", "start": "2017-06", "end": "2019-12", ...},
    {"company": "WebStartup", "title": "Junior Developer", "start": "2015-08", "end": "2017-05", ...}
  ],
  "education": [
    {"institution": "University of California, Berkeley", "degree": "Bachelor of Science", "field": "Computer Science"}
  ],
  "years_experience": 8.0,
  "provenance": [
    {"field": "full_name", "source": "resume_pdf", "method": "priority_pick", "confidence": 1.0},
    {"field": "emails", "source": "recruiter_csv,recruiter_csv,resume_pdf,github_api", "method": "concatenated", "confidence": 0.9},
    ...
  ]
}
```

## Assumptions & Design Decisions

1. **Resume extraction uses pdftotext + regex** — No ML/NLP model for resume parsing. This is a deliberate trade-off: simpler, deterministic, and sufficient for well-structured resumes. An LLM-based extractor could be added as a future enhancement.

2. **GitHub data provided as JSON files** — The assignment mentions "GitHub profile" as a source. Instead of calling the GitHub API at runtime (which would require auth tokens and network access), the profile data is provided as pre-fetched JSON files. The parser is designed so a live API adapter could be trivially added.

3. **LinkedIn is not implemented** — Listed as a source in the assignment but excluded due to LinkedIn's Terms of Service restricting scraping. The architecture supports adding a LinkedIn parser as a new source type with a priority entry.

4. **Skill canonicalization uses a static alias map** — A fixed dictionary maps common abbreviations/variants to canonical forms. This covers the most frequent cases. A more scalable approach would use a fuzzy matching system or embedding similarity, but the static map is deterministic and easy to extend.

5. **Match keys are ordered email → phone → name** — Email is the most reliable identifier. Phone is secondary (E.164 normalized). Name is tertiary (normalized to title case, collapsed whitespace), used only when email and phone don't match. This prevents false positives from common names.

6. **Confidence is heuristic-based** — The confidence model uses source priority, corroboration, and conflict signals. It is not a statistical model but provides a reasonable signal for downstream consumers. A principled Bayesian approach would be a natural extension.

7. **Determinism** — The pipeline is fully deterministic: sorted processing order, MD5 IDs from stable keys, no random state. Running the pipeline twice on the same inputs produces byte-identical output.

8. **NDJSONL output** — One JSON object per line, facilitating streaming processing and downstream consumption by data systems.

9. **Graceful degradation** — Missing or unreadable source files are skipped with warnings. Malformed CSV rows produce empty candidates. Unparseable phones/dates are passed through with low confidence scores. The pipeline never crashes on bad input.

10. **Provenance on concatenated list fields** — When multiple sources contribute to a list field (e.g., emails from CSV + resume + GitHub), the provenance records all contributing sources comma-separated with method "concatenated" and confidence as the weighted average.

## Requirements

- Python 3.11+
- phonenumbers
- pycountry
- pydantic
- pdftotext (system package: `poppler-utils`)
- pytest (for running tests)

## Tests

68 tests covering all components:

- **Normalization** (20 tests): Phone E.164, dates YYYY-MM, email lowercasing, name title-casing, skill canonicalization, country ISO α2, years experience
- **Parsing** (8 tests): CSV parsing with column aliases, resume PDF extraction, GitHub JSON parsing, missing file handling
- **Merge Engine** (4 tests): Email matching, phone matching, different people, canonical profile output
- **Projection** (6 tests): Default config, field renaming, confidence metadata, missing value policies, sub-path resolution
- **Validation** (2 tests): Valid default output, missing required field detection
- **Pipeline Integration** (7 tests): CSV-only, resume-only, GitHub-only, multi-source merge, determinism, custom config, NDJSONL output
- **Edge Cases** (7 tests): Empty sources, garbage CSV, conflicting names, email dedup, provenance tracking, confidence range
