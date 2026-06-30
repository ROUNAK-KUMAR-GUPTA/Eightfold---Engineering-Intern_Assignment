# Multi-Source Candidate Data Transformer

A deterministic and extensible pipeline that ingests candidate information from multiple sources (Recruiter CSV, Resume PDF, and GitHub JSON), normalizes the data into a canonical format, merges duplicate records, validates the output schema, and exports the final result as NDJSON.

This project was developed for the **Eightfold AI Engineering Intern Assignment**.

---

## Features

- Parse candidate data from:
  - Recruiter CSV
  - Resume PDF
  - GitHub JSON
- Normalize names, emails, phone numbers, countries, dates, and skills
- Merge duplicate candidates using deterministic matching
- Track field provenance
- Runtime configurable output projection
- Validate output using Pydantic
- Export canonical candidate profiles as NDJSON
- Deterministic pipeline output

---

# Tech Stack

- Python 3.11+
- Pydantic
- Pytest
- phonenumbers
- pycountry
- Poppler (pdftotext)

---

# Project Structure

```
.
├── cli.py
├── README.md
├── requirements.txt
├── output.jsonl
├── docs/
├── sample_inputs/
├── sample_outputs/
├── src/
│   ├── config/
│   ├── merge/
│   ├── normalizers/
│   ├── parsers/
│   ├── validators/
│   ├── models.py
│   └── pipeline.py
└── tests/
```

---

# Installation

## Clone Repository

```bash
git clone https://github.com/ROUNAK-KUMAR-GUPTA/Eightfold---Engineering-Intern_Assignment.git

cd Eightfold---Engineering-Intern_Assignment
```

## Create Virtual Environment

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

## Install Dependencies

```bash
pip install -r requirements.txt
```

---

## Install Poppler (Required)

Resume parsing requires **pdftotext**.

### Windows

Download:

https://github.com/oschwartz10612/poppler-windows/releases

Extract it and add:

```
C:\poppler\poppler-26.02.0\Library\bin
```

to the system PATH.

Verify installation:

```bash
pdftotext -v
```

### Ubuntu

```bash
sudo apt install poppler-utils
```

---

# Run the Pipeline

```bash
python cli.py ^
--csv sample_inputs/recruiter_export.csv ^
--resume sample_inputs/jane_smith_resume.pdf ^
--github sample_inputs/github_profile_janesmith.json ^
--github sample_inputs/github_profile_johndoe.json ^
-o output.jsonl ^
--stats ^
--validate
```

---

# Run Tests

```bash
python -m pytest tests -v
```

Output:

```
68 passed
```

---

# Architecture

```
Recruiter CSV
       │
       ▼
   CSV Parser
       │
Resume PDF ─► Resume Parser
       │
GitHub JSON ─► GitHub Parser
       │
       ▼
  Merge Engine
       │
       ▼
Normalization
       │
       ▼
Schema Validation
       │
       ▼
 output.jsonl
```

---

# Merge Strategy

Candidate matching priority:

1. Email
2. Phone Number
3. Normalized Name

Rules:

- Normalize all fields before matching.
- Merge scalar fields using source priority.
- Merge list fields using union and deduplication.
- Preserve provenance.
- Generate deterministic candidate IDs.

---

# Design Decisions

- Modular parser architecture for easy extensibility.
- Deterministic merge engine using normalized identifiers.
- Runtime configurable output projection.
- Pydantic schema validation.
- Separation of parsing, normalization, merging, and validation.

---

# Assumptions

- Resume parsing uses **pdftotext**.
- GitHub profiles are provided as JSON files.
- LinkedIn integration is intentionally excluded.
- Candidate IDs are deterministic.

---

# Results

- Parsed data from multiple heterogeneous sources.
- Generated canonical candidate profiles.
- Exported validated NDJSON output.
- Passed **68/68 automated tests**.

---

# Future Improvements

- LinkedIn parser
- Live GitHub API integration
- OCR support for scanned resumes
- Fuzzy matching
- REST API deployment

---

---

## Author

**Rounak Gupta**  
B.Tech in Computer Science & Engineering (2022–2026)

- GitHub: https://github.com/ROUNAK-KUMAR-GUPTA
- Project: Eightfold AI Engineering Intern Assignment

---
