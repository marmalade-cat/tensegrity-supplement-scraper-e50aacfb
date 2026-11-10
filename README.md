Tensegrity Supplement Scraper

A small deterministic prototype (Python 3, stdlib only). Given an article URL, it:
- fetches HTML
- finds links whose filenames end with .csv, .json, or .zip
- downloads them to memory (streamed)
- validates format (CSV rows/headers, JSON parse, ZIP contents)
- extracts metadata: filename, size bytes, sha256 hex, CSV headers or JSON top keys, ZIP member names
- writes a replayable log (timestamped steps) and a single JSON summary to stdout

Usage: python3 main.py https://doi.org/.../fulltext

Limitations: prototype; no JavaScript rendering, no authentication, limited link discovery. Treat as an inspection tool, not a full crawler.