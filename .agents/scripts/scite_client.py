#!/usr/bin/env python3
"""
Scite.ai Research Client & Second Brain Integration Tool
Author: Engine Quantitative Architecture
Description: Interfaces with Scite.ai REST API to search scholarly literature,
             retrieve paper metadata, analyze smart citations (supporting, mentioning, contradicting),
             and recommend peer-reviewed trading microstructure papers.
"""

import os
import sys
import json
import argparse
from typing import Optional, Dict, Any, List
import requests

# Default API Key location and fallback
ENV_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), ".env")

def load_api_key() -> str:
    key = os.environ.get("SCITE_API_KEY")
    if key:
        return key
    if os.path.exists(ENV_PATH):
        with open(ENV_PATH, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("SCITE_API_KEY="):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
    return "scite_HcQiTAuZm4LwsfYoRvoG069bIMSPomwg8_zEUtTDzVE"

class SciteClient:
    BASE_URL = "https://api.scite.ai"

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or load_api_key()
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "User-Agent": "EngineQuantitativeResearcher/1.0"
        }

    def get_paper(self, doi: str) -> Optional[Dict[str, Any]]:
        """Fetch metadata, abstract, and authors for a specific DOI."""
        url = f"{self.BASE_URL}/papers/{doi}"
        resp = requests.get(url, headers=self.headers, timeout=10)
        if resp.status_code == 200:
            return resp.json()
        print(f"Error fetching paper {doi}: HTTP {resp.status_code} - {resp.text[:100]}", file=sys.stderr)
        return None

    def get_citations(self, doi: str) -> Optional[Dict[str, Any]]:
        """Fetch citation details, citing publications, and smart citation counts."""
        url = f"{self.BASE_URL}/api_partner/citations/citing/{doi}"
        resp = requests.get(url, headers=self.headers, timeout=10)
        if resp.status_code == 200:
            return resp.json()
        print(f"Error fetching citations for {doi}: HTTP {resp.status_code}", file=sys.stderr)
        return None

    def recommend_papers(self, doi: str) -> Optional[List[Dict[str, Any]]]:
        """Fetch papers recommended by Scite based on citation context and graph similarity."""
        url = f"{self.BASE_URL}/api_partner/recommend-papers/{doi}"
        resp = requests.get(url, headers=self.headers, timeout=10)
        if resp.status_code == 200:
            return resp.json()
        print(f"Error fetching recommendations for {doi}: HTTP {resp.status_code}", file=sys.stderr)
        return None

    def search(self, query: str, limit: int = 10) -> Optional[Dict[str, Any]]:
        """Search papers across 1.2B citation statements."""
        url = f"{self.BASE_URL}/api_partner/search"
        params = {"term": query, "limit": limit}
        resp = requests.get(url, headers=self.headers, params=params, timeout=15)
        if resp.status_code == 200:
            return resp.json()
        print(f"Error executing search '{query}': HTTP {resp.status_code} - {resp.text[:100]}", file=sys.stderr)
        return None

def main():
    parser = argparse.ArgumentParser(description="Scite.ai API Research Assistant")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Paper lookup
    p_paper = subparsers.add_parser("paper", help="Fetch paper metadata by DOI")
    p_paper.add_argument("doi", help="Digital Object Identifier (e.g. 10.5195/ledger.2024.325)")

    # Citations lookup
    p_cite = subparsers.add_parser("citations", help="Fetch citation breakdown by DOI")
    p_cite.add_argument("doi", help="Digital Object Identifier")

    # Recommendations lookup
    p_rec = subparsers.add_parser("recommend", help="Fetch recommended papers by DOI")
    p_rec.add_argument("doi", help="Digital Object Identifier")

    # Search
    p_search = subparsers.add_parser("search", help="Execute keyword/topic search")
    p_search.add_argument("query", help="Search query string")
    p_search.add_argument("--limit", type=int, default=5, help="Number of papers to return")

    args = parser.parse_args()
    client = SciteClient()

    if args.command == "paper":
        data = client.get_paper(args.doi)
        if data:
            print(json.dumps({
                "title": data.get("title"),
                "year": data.get("year"),
                "journal": data.get("journal") or data.get("shortJournal"),
                "doi": data.get("doi"),
                "abstract": data.get("abstract")[:300] + "..." if data.get("abstract") else None
            }, indent=2))

    elif args.command == "citations":
        data = client.get_citations(args.doi)
        if data:
            print(json.dumps(data.get("metadata", {}), indent=2))

    elif args.command == "recommend":
        data = client.recommend_papers(args.doi)
        if data:
            recs = [{"doi": r.get("doi"), "title": r.get("title")} for r in data[:5]]
            print(json.dumps(recs, indent=2))

    elif args.command == "search":
        data = client.search(args.query, limit=args.limit)
        if data:
            print(json.dumps(data, indent=2))

if __name__ == "__main__":
    main()
