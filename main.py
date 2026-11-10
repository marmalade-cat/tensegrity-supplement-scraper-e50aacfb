# Small prototype scraper: tensegrity-supplement-scraper
# Usage: python3 main.py <article_url>
# Notes: stdlib only, untested in this environment. Deterministic behavior and replay log.

import sys
import urllib.request
import urllib.parse
import hashlib
import json
import csv
import io
import zipfile
import time
from html.parser import HTMLParser

LOG = []

def log(step, detail=None):
    entry = {"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "step": step}
    if detail is not None:
        entry["detail"] = detail
    LOG.append(entry)

class LinkParser(HTMLParser):
    def __init__(self, base_url):
        super().__init__()
        self.links = []
        self.base = base_url
    def handle_starttag(self, tag, attrs):
        if tag.lower() == 'a':
            href = None
            for k,v in attrs:
                if k.lower() == 'href':
                    href = v
            if href:
                full = urllib.parse.urljoin(self.base, href)
                self.links.append(full)

def fetch_url(url, max_bytes=50_000_000):
    log('fetch_start', url)
    req = urllib.request.Request(url, headers={'User-Agent': 'tensegrity-scraper/0'})
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = resp.read(max_bytes+1)
        if len(data) > max_bytes:
            log('fetch_truncated', {'url': url, 'max_bytes': max_bytes})
            data = data[:max_bytes]
    log('fetch_done', {'url': url, 'size': len(data)})
    return data

def sha256_hex(b):
    h = hashlib.sha256()
    h.update(b)
    return h.hexdigest()

def inspect_csv(b):
    try:
        text = b.decode('utf-8')
    except Exception:
        try:
            text = b.decode('latin1')
        except Exception:
            return {'valid': False, 'error': 'decode_failed'}
    buf = io.StringIO(text)
    try:
        reader = csv.reader(buf)
        headers = next(reader, None)
        return {'valid': True, 'headers': headers}
    except Exception as e:
        return {'valid': False, 'error': str(e)}

def inspect_json(b):
    try:
        text = b.decode('utf-8')
    except Exception:
        return {'valid': False, 'error': 'decode_failed'}
    try:
        obj = json.loads(text)
        if isinstance(obj, dict):
            keys = list(obj.keys())
        else:
            keys = ['<non-dict top-level: %s>' % type(obj).__name__]
        return {'valid': True, 'top_keys': keys}
    except Exception as e:
        return {'valid': False, 'error': str(e)}

def inspect_zip(b):
    try:
        z = zipfile.ZipFile(io.BytesIO(b))
        names = z.namelist()
        # try to inspect inner known types
        inner = []
        for name in names:
            if name.lower().endswith('.csv') or name.lower().endswith('.json'):
                try:
                    with z.open(name) as fh:
                        data = fh.read(2000000)  # up to 2MB
                    if name.lower().endswith('.csv'):
                        ins = inspect_csv(data)
                    else:
                        ins = inspect_json(data)
                except Exception as e:
                    ins = {'valid': False, 'error': str(e)}
                inner.append({'name': name, 'inspect': ins})
        return {'valid': True, 'members': names, 'inner_inspections': inner}
    except Exception as e:
        return {'valid': False, 'error': str(e)}

def candidate_filter(url):
    lower = url.lower()
    for ext in ['.csv', '.json', '.zip']:
        if lower.split('?')[0].endswith(ext):
            return True
    return False

def summarize_artifact(url, b):
    size = len(b)
    h = sha256_hex(b)
    entry = {'url': url, 'size_bytes': size, 'sha256': h}
    if url.lower().endswith('.csv'):
        entry['type'] = 'csv'
        entry['inspect'] = inspect_csv(b)
    elif url.lower().endswith('.json'):
        entry['type'] = 'json'
        entry['inspect'] = inspect_json(b)
    elif url.lower().endswith('.zip'):
        entry['type'] = 'zip'
        entry['inspect'] = inspect_zip(b)
    else:
        entry['type'] = 'unknown'
    return entry

def find_supplement_links(html_bytes, base_url):
    try:
        html = html_bytes.decode('utf-8', errors='ignore')
    except Exception:
        html = html_bytes.decode('latin1', errors='ignore')
    p = LinkParser(base_url)
    p.feed(html)
    links = list(dict.fromkeys(p.links))
    log('links_found', {'count': len(links)})
    cand = [u for u in links if candidate_filter(u)]
    log('candidates_filtered', {'count': len(cand)})
    return cand

def main(argv):
    if len(argv) < 2:
        print('Usage: python3 main.py <article_url>')
        sys.exit(2)
    url = argv[1]
    summary = {'article_url': url, 'artifacts': [], 'log': LOG}
    try:
        page = fetch_url(url)
    except Exception as e:
        log('error_fetch_article', str(e))
        summary['error'] = 'fetch_article_failed'
        print(json.dumps(summary, indent=2))
        return
    links = find_supplement_links(page, url)
    for link in links:
        try:
            data = fetch_url(link)
            art = summarize_artifact(link, data)
            summary['artifacts'].append(art)
            log('artifact_processed', {'url': link, 'size': art['size_bytes']})
        except Exception as e:
            log('artifact_error', {'url': link, 'error': str(e)})
    # Small heuristic: look inside artifact metadata for words indicating poses, connection, calibration
    keywords = ['pose', 'poses', 'connection', 'connections', 'calibration', 'module']
    for art in summary['artifacts']:
        text_blob = ''
        try:
            if art.get('type') in ('csv', 'json'):
                # re-fetch tiny portion: we already have sha; but we didn't keep content to limit memory
                # In this prototype we won't re-download; instead inspect names/headers
                pass
            if art.get('inspect'):
                s = json.dumps(art['inspect'])
                text_blob += s.lower()
        except Exception:
            pass
        tags = [k for k in keywords if k in text_blob]
        art['likely_contains'] = tags
    summary['log'] = LOG
    print(json.dumps(summary, indent=2))

if __name__ == '__main__':
    main(sys.argv)
