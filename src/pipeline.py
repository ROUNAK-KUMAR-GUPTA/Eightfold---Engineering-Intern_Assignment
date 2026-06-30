"""
Main Pipeline: Multi-Source Candidate Data Transformer.

Orchestrates the full pipeline:
  1. Detect source types
  2. Extract/parse from each source
  3. Normalize fields
  4. Match candidates across sources
  5. Merge into canonical profiles
  6. Score confidence
  7. Project to configured output
  8. Validate output

Usage:
  from src.pipeline import CandidatePipeline
  
  pipeline = CandidatePipeline()
  pipeline.add_csv("recruiter_export.csv")
  pipeline.add_resume("candidate_resume.pdf")
  pipeline.add_github("github_profile.json")
  
  profiles = pipeline.run()
  
  # Or with custom config:
  profiles = pipeline.run(config_path="custom_config.json")
  
  # Output as NDJSONL
  pipeline.run_and_save(output_path="output.jsonl")
"""

from __future__ import annotations
import json
import os
import sys
from typing import List, Dict, Any, Optional

from src.models import RawCandidate, CanonicalProfile, SourceType
from src.parsers.csv_parser import parse_csv_file
from src.parsers.resume_parser import parse_resume_pdf
from src.parsers.github_parser import parse_github_json
from src.merge.engine import transform
from src.config.projection import ProjectionConfig, project_all, project
from src.validators.schema import validate_default_schema, validate_ndjsonl


class CandidatePipeline:
    """Full pipeline for multi-source candidate data transformation."""
    
    def __init__(self):
        self.raw_candidates: List[RawCandidate] = []
        self.profiles: List[CanonicalProfile] = []
        self._source_files: List[str] = []
    
    def add_csv(self, path: str) -> "CandidatePipeline":
        """Add a recruiter CSV export as a source."""
        candidates = parse_csv_file(path)
        self.raw_candidates.extend(candidates)
        self._source_files.append(path)
        print(f"[Pipeline] Loaded {len(candidates)} candidates from CSV: {path}")
        return self
    
    def add_resume(self, path: str) -> "CandidatePipeline":
        """Add a resume PDF as a source."""
        candidates = parse_resume_pdf(path)
        self.raw_candidates.extend(candidates)
        self._source_files.append(path)
        print(f"[Pipeline] Loaded {len(candidates)} candidates from resume: {path}")
        return self
    
    def add_github(self, path: str) -> "CandidatePipeline":
        """Add a GitHub profile JSON as a source."""
        candidates = parse_github_json(path)
        self.raw_candidates.extend(candidates)
        self._source_files.append(path)
        print(f"[Pipeline] Loaded {len(candidates)} candidates from GitHub: {path}")
        return self
    
    def add_raw(self, raw: RawCandidate) -> "CandidatePipeline":
        """Add a pre-built RawCandidate."""
        self.raw_candidates.append(raw)
        return self
    
    def run(self, config: Optional[ProjectionConfig] = None) -> List[Dict[str, Any]]:
        """Run the full pipeline.
        
        Steps:
        1. Match candidates across sources
        2. Normalize + merge into canonical profiles
        3. Score confidence
        4. Project to configured output
        5. Validate
        
        Returns list of projected output dicts.
        """
        if not self.raw_candidates:
            print("[Pipeline] Warning: No raw candidates to process")
            return []
        
        print(f"[Pipeline] Processing {len(self.raw_candidates)} raw candidates from {len(self._source_files)} sources...")
        
        # Match + Normalize + Merge + Confidence
        self.profiles = transform(self.raw_candidates)
        print(f"[Pipeline] Merged into {len(self.profiles)} canonical profiles")
        
        # Project
        if config is None:
            config = ProjectionConfig.default()
        
        projected = project_all(self.profiles, config)
        
        # Validate
        all_valid = True
        for i, output in enumerate(projected):
            is_valid, errors = validate_default_schema(output) if config == ProjectionConfig.default() else (True, [])
            if not is_valid:
                all_valid = False
                print(f"[Pipeline] Validation errors for profile {i}:")
                for err in errors:
                    print(f"  - {err}")
        
        if all_valid:
            print("[Pipeline] All outputs validated successfully")
        
        return projected
    
    def run_and_save(
        self,
        output_path: str = "output.jsonl",
        config: Optional[ProjectionConfig] = None,
        config_path: Optional[str] = None,
    ) -> str:
        """Run the pipeline and save results as NDJSONL.
        
        Returns the output file path.
        """
        # Load config if specified
        if config is None and config_path:
            config = ProjectionConfig.from_file(config_path)
        
        projected = self.run(config=config)
        
        # Write NDJSONL
        with open(output_path, 'w', encoding='utf-8') as f:
            for record in projected:
                f.write(json.dumps(record, ensure_ascii=False) + '\n')
        
        print(f"[Pipeline] Saved {len(projected)} records to {output_path}")
        
        # Validate the output file
        is_valid, errors = validate_ndjsonl(output_path, config)
        if not is_valid:
            print(f"[Pipeline] Output validation errors:")
            for err in errors[:10]:  # Show first 10
                print(f"  - {err}")
        else:
            print(f"[Pipeline] Output file validated successfully")
        
        return output_path
    
    def get_profiles(self) -> List[CanonicalProfile]:
        """Get the canonical profiles (before projection)."""
        return self.profiles
    
    def stats(self) -> Dict[str, Any]:
        """Get pipeline statistics."""
        source_counts = {}
        for raw in self.raw_candidates:
            src = raw.source_type.value
            source_counts[src] = source_counts.get(src, 0) + 1
        
        return {
            "total_raw_candidates": len(self.raw_candidates),
            "sources": source_counts,
            "merged_profiles": len(self.profiles),
            "source_files": self._source_files,
        }
