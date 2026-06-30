# Multi-Source Candidate Data Transformer

A deterministic pipeline that ingests candidate data from multiple sources (Recruiter CSV, Resume PDF, and GitHub JSON), normalizes fields into a canonical format, merges duplicate records, validates the output schema, and exports the final result as NDJSON.

This project was developed for the **Eightfold AI Engineering Intern Assignment**.

---

## Features

- Parse candidate data from:
  - Recruiter CSV
  - Resume PDF
  - GitHub JSON
- Normalize names, emails, phone numbers, countries, skills, and dates
- Merge duplicate candidates into a canonical profile
- Validate output using Pydantic
- Export NDJSON output
- Deterministic processing
- Automated test suite

---

## Project Structure

```
.
├── cli.py
├── requirements.txt
├── README.md
├── docs/
├── sample_inputs/
├── sample_outputs/
├── src/
└── tests/
```

---

## Installation

### Prerequisites

- Python 3.11+
- Git
- Poppler (`pdftotext`) for PDF resume parsing

### Clone the Repository

```bash
git clone https://github.com/ROUNAK-KUMAR-GUPTA/Eightfold---Engineering-Intern_Assignment.git

cd Eightfold---Engineering-Intern_Assignment
```

### Create a Virtual Environment

#### Windows

```powershell
python -m venv venv

venv\Scripts\Activate.ps1
```

#### Linux / macOS

```bash
python3 -m venv venv

source venv/bin/activate
```

### Install Dependencies

```bash
pip install -r requirements.txt
```

### Install Poppler (Required for Resume Parsing)

#### Windows

Download Poppler:

https://github.com/oschwartz10612/poppler-windows/releases

Extract it and add:

```
C:\poppler\poppler-26.02.0\Library\bin
```

to your system PATH.

Verify:

```bash
pdftotext -v
```

#### Ubuntu

```bash
sudo apt install poppler-utils
```

#### macOS

```bash
brew install poppler
```

---

## Run the Pipeline

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

The generated output will be saved as:

```
output.jsonl
```

---

## Run with Custom Configuration

```bash
python cli.py ^
--csv sample_inputs/recruiter_export.csv ^
--resume sample_inputs/jane_smith_resume.pdf ^
--github sample_inputs/github_profile_janesmith.json ^
--github sample_inputs/github_profile_johndoe.json ^
--config sample_inputs/custom_config.json ^
--include-confidence ^
-o custom_output.jsonl
```

---

## Run Tests

```bash
python -m pytest tests -v
```

Expected output:

```
68 passed
```

---

## Pipeline Overview

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

## Results

- Successfully processed candidate data from CSV, Resume PDF, and GitHub JSON.
- Generated deterministic canonical candidate profiles.
- Exported validated NDJSON output.
- Passed **68/68 automated tests**.

---

## Author

**Rounak Gupta**

B.Tech in Computer Science & Engineering (2022–2026)

GitHub: https://github.com/ROUNAK-KUMAR-GUPTA

Project: Eightfold AI Engineering Intern Assignment
