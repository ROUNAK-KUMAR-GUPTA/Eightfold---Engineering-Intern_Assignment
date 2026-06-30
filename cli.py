#!/usr/bin/env python3
"""
CLI for the Multi-Source Candidate Data Transformer.

Usage:
  python cli.py --csv <file> --resume <file> --github <file> --config <file> --output <file>

Examples:
  # Default output with CSV + resume:
  python cli.py --csv sample_inputs/recruiter_export.csv --resume sample_inputs/jane_smith_resume.pdf -o output.jsonl

  # Custom config:
  python cli.py --csv sample_inputs/recruiter_export.csv --resume sample_inputs/jane_smith_resume.pdf --config sample_inputs/custom_config.json -o custom_output.jsonl

  # With confidence metadata:
  python cli.py --csv sample_inputs/recruiter_export.csv --resume sample_inputs/jane_smith_resume.pdf --include-confidence -o output_with_conf.jsonl

  # Print a single profile as JSON:
  python cli.py --csv sample_inputs/recruiter_export.csv --resume sample_inputs/jane_smith_resume.pdf --print
"""

import argparse
import json
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.pipeline import CandidatePipeline
from src.config.projection import ProjectionConfig


def main():
    parser = argparse.ArgumentParser(
        description="Multi-Source Candidate Data Transformer",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    
    # Input sources
    parser.add_argument(
        "--csv", nargs="*", default=[],
        help="Recruiter CSV export file(s)"
    )
    parser.add_argument(
        "--resume", nargs="*", default=[],
        help="Resume PDF file(s)"
    )
    parser.add_argument(
        "--github", action="append", default=[],
        help="GitHub profile JSON file (can be specified multiple times)"
    )
    
    # Output config
    parser.add_argument(
        "-o", "--output", default=None,
        help="Output NDJSONL file path"
    )
    parser.add_argument(
        "--config", default=None,
        help="Custom projection config JSON file"
    )
    parser.add_argument(
        "--include-confidence", action="store_true",
        help="Include confidence metadata in output"
    )
    parser.add_argument(
        "--on-missing", choices=["null", "omit", "error"], default="null",
        help="What to do when a value is missing"
    )
    
    # Display options
    parser.add_argument(
        "--print", action="store_true", dest="print_output",
        help="Print output to stdout as well"
    )
    parser.add_argument(
        "--stats", action="store_true",
        help="Print pipeline statistics"
    )
    parser.add_argument(
        "--validate", action="store_true",
        help="Validate output without printing"
    )
    
    args = parser.parse_args()
    
    # Must have at least one source
    if not args.csv and not args.resume and not args.github:
        parser.error("At least one input source is required (--csv, --resume, or --github)")
    
    # Build pipeline
    pipeline = CandidatePipeline()
    
    for csv_path in args.csv:
        if not os.path.exists(csv_path):
            print(f"Warning: CSV file not found: {csv_path} (skipping)", file=sys.stderr)
            continue
        pipeline.add_csv(csv_path)
    
    for resume_path in args.resume:
        if not os.path.exists(resume_path):
            print(f"Warning: Resume file not found: {resume_path} (skipping)", file=sys.stderr)
            continue
        pipeline.add_resume(resume_path)
    
    for github_path in args.github:
        if not os.path.exists(github_path):
            print(f"Warning: GitHub JSON not found: {github_path} (skipping)", file=sys.stderr)
            continue
        pipeline.add_github(github_path)
    
    # Build config
    if args.config:
        config = ProjectionConfig.from_file(args.config)
    else:
        # Build from CLI flags
        config_fields = [
            {"to": "candidate_id", "from": "candidate_id", "type": "string", "required": True},
            {"to": "full_name", "from": "full_name", "type": "string", "required": True},
            {"to": "emails", "from": "emails", "type": "array"},
            {"to": "phones", "from": "phones", "type": "array", "normalize": "E164"},
            {"to": "locations", "from": "locations", "type": "array"},
            {"to": "websites", "from": "websites", "type": "array"},
            {"to": "links", "from": "links", "type": "object"},
            {"to": "years_experience", "from": "years_experience", "type": "number"},
            {"to": "summary", "from": "summary", "type": "string"},
            {"to": "experience", "from": "experience", "type": "array"},
            {"to": "education", "from": "education", "type": "array"},
            {"to": "provenance", "from": "provenance", "type": "array"},
            {"to": "overall_confidence", "from": "overall_confidence", "type": "number"},
        ]
        config = ProjectionConfig({
            "fields": config_fields,
            "include_confidence": args.include_confidence,
            "on_missing": args.on_missing,
        })
    
    # Run
    if args.output:
        output_path = pipeline.run_and_save(
            output_path=args.output,
            config=config,
        )
        print(f"\nOutput saved to: {output_path}")
    else:
        projected = pipeline.run(config=config)
        if args.print_output or not args.validate:
            for record in projected:
                print(json.dumps(record, ensure_ascii=False, indent=2))
    
    # Stats
    if args.stats:
        stats = pipeline.stats()
        print(f"\n--- Pipeline Statistics ---")
        print(json.dumps(stats, indent=2))


if __name__ == "__main__":
    main()
