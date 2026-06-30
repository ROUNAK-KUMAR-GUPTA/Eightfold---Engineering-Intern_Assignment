# Multi-Source Candidate Data Transformer

A deterministic and extensible candidate data processing pipeline that ingests candidate information from multiple heterogeneous sources (Recruiter CSV, Resume PDF, and GitHub JSON), normalizes fields into canonical representations, merges duplicate records, validates the final schema, and exports the output as NDJSON.

This project was developed as part of the **Eightfold AI Engineering Intern Assignment**.

---

## Features

- Parse candidate data from:
  - Recruiter CSV
  - Resume PDF
  - GitHub JSON
- Normalize:
  - Names
  - Emails
  - Phone numbers (E.164)
  - Countries (ISO-3166 Alpha-2)
  - Skills
  - Dates
- Merge duplicate candidates using deterministic identity matching
- Track provenance for every merged field
- Runtime-configurable output projection
- Validate output schema using Pydantic
- Export canonical profiles as NDJSON
- Fully deterministic output
- Comprehensive automated test suite (**68 tests**)

---

# Tech Stack

- Python 3.11+
- Pydantic
- Pytest
- phonenumbers
- pycountry
- Poppler / pdftotext
- argparse

---

# Project Architecture

```
                    Recruiter CSV
                          │
                    CSV Parser
                          │
Resume PDF ──► Resume Parser
                          │
GitHub JSON ─► GitHub Parser
                          │
                    Merge Engine
                          │
                 Field Normalizers
                          │
                 Schema Validation
                          │
                    output.jsonl
```

---

# Project Structure

```
candidate-transformer/
│
├── cli.py
├── README.md
├── requirements.txt
├── output.jsonl
│
├── docs/
│   ├── design_doc.html
│   └── demo_script.md
│
├── sample_inputs/
│   ├── recruiter_export.csv
│   ├── jane_smith_resume.pdf
│   ├── github_profile_janesmith.json
│   ├── github_profile_johndoe.json
│   └── custom_config.json
│
├── sample_outputs/
│   ├── default_output.jsonl
│   └── custom_output.jsonl
│
├── src/
│   ├── config/
│   ├── merge/
│   ├── normalizers/
│   ├── parsers/
│   ├── validators/
│   ├── models.py
│   └── pipeline.py
│
└── tests/
    └── test_pipeline.py
```

---

# Installation

## 1. Clone Repository

```bash
git clone https://github.com/YOUR_USERNAME/Eightfold---Engineering-Intern_Assignment.git

cd Eightfold---Engineering-Intern_Assignment
```

---

## 2. Create Virtual Environment

### Windows

```powershell
python -m venv venv

venv\Scripts\Activate.ps1
```

### Linux / macOS

```bash
python3 -m venv venv

source venv/bin/activate
```

---

## 3. Install Python Dependencies

```bash
pip install -r requirements.txt
```

---

## 4. Install Poppler (Required)

Resume parsing requires **pdftotext**.

### Windows

Download Poppler:

https://github.com/oschwartz10612/poppler-windows/releases

Extract and add the following folder to your system PATH:

```
C:\poppler\poppler-26.02.0\Library\bin
```

Verify installation:

```bash
pdftotext -v
```

### Ubuntu

```bash
sudo apt install poppler-utils
```

### macOS

```bash
brew install poppler
```

---

# Running the Pipeline

## Default Pipeline

```bash
python cli.py \
--csv sample_inputs/recruiter_export.csv \
--resume sample_inputs/jane_smith_resume.pdf \
--github sample_inputs/github_profile_janesmith.json \
--github sample_inputs/github_profile_johndoe.json \
-o output.jsonl \
--stats \
--validate
```

---

## Custom Projection

```bash
python cli.py \
--csv sample_inputs/recruiter_export.csv \
--resume sample_inputs/jane_smith_resume.pdf \
--github sample_inputs/github_profile_janesmith.json \
--github sample_inputs/github_profile_johndoe.json \
--config sample_inputs/custom_config.json \
--include-confidence \
-o custom_output.jsonl
```

---

## Print Output to Terminal

```bash
python cli.py \
--csv sample_inputs/recruiter_export.csv \
--print
```

---

# Running Tests

```bash
python -m pytest tests -v
```

**Result**

```
68 tests passed
```

---

# Normalization

| Field | Output |
|--------|--------|
| Phone | E.164 |
| Country | ISO-3166 Alpha-2 |
| Email | Lowercase |
| Name | Title Case |
| Skills | Canonical Form |
| Date | YYYY-MM |

---

# Merge Strategy

Candidate matching priority:

1. Email
2. Phone Number
3. Normalized Name

Rules:

- Normalize before matching
- Merge scalar fields using source priority
- Merge list fields using union + deduplication
- Preserve provenance
- Generate deterministic candidate IDs

---

# Confidence Model

```
Base Confidence = Source Priority

+0.1  for corroborating sources

-0.2  for conflicting values

Clamp between 0 and 1
```

---

# Projection Configuration

Supports runtime JSON configuration.

Features:

- Field selection
- Field renaming
- Confidence metadata
- Missing field policy
- Nested field projection

Example:

```json
{
  "fields": [
    {
      "path":"full_name"
    },
    {
      "path":"emails[0]",
      "output_name":"contact_email"
    }
  ]
}
```

---

# Sample Output

```json
{
  "candidate_id": "c_65536e21c61f",
  "full_name": "Jane Smith",
  "emails": [
    "jane.smith@techcorp.com"
  ],
  "phones": [
    "+14085551234"
  ],
  "skills": [
    "python",
    "javascript",
    "docker",
    "kubernetes"
  ]
}
```

---

# Design Decisions

- Modular parser architecture
- Deterministic merge engine
- Runtime configurable projections
- Pydantic schema validation
- Provenance tracking
- Separation of parsing, normalization, merging, and validation
- Fully deterministic output

---

# Edge Cases Handled

- Missing email
- Invalid phone number
- Duplicate candidates
- Empty CSV
- Missing GitHub fields
- Corrupted resume
- Missing resume
- Conflicting candidate information
- Invalid dates
- Empty inputs

---

# Assumptions

- Resume extraction uses **pdftotext** rather than ML/NLP.
- GitHub profiles are provided as JSON rather than fetched from the live API.
- LinkedIn integration is intentionally omitted due to platform restrictions.
- Skill normalization uses a deterministic alias mapping.
- Candidate IDs are deterministic.

---

# Results

- Parsed candidate data from multiple heterogeneous sources.
- Generated canonical candidate profiles.
- Exported validated NDJSON output.
- Runtime configurable projections.
- Deterministic merge behavior.
- **68/68 automated tests passed successfully.**

---

# Future Improvements

- LinkedIn connector
- GitHub live API integration
- OCR support for scanned resumes
- ML-based resume parsing
- Fuzzy matching for candidate identity
- Semantic skill normalization
- REST API deployment

---

# Author

**Rounak Gupta**

B.Tech Computer Science & Engineering (2022–2026)

Eightfold AI Engineering Intern Assignment

---
