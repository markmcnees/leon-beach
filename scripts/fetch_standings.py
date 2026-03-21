#!/usr/bin/env python3
"""
Fetches beach volleyball area standings from MaxPreps and writes them
to Firebase Realtime Database under leon_queens_matches/standings.
Runs as a GitHub Action on a nightly schedule.
"""

import json, re, sys, urllib.request, urllib.parse

MAXPREPS_URL = 'https://www.maxpreps.com/fl/tallahassee/leon-lions/beach-volleyball/'
FIREBASE_URL = 'https://leon-beach-volleyball-default-rtdb.firebaseio.com/leon_queens_matches/standings.json'

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9',
}

def fetch(url):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=15) as r:
        return r.read().decode('utf-8', errors='replace')

def deep_find(obj, depth=0):
    """Walk a JSON tree looking for an array of standings-shaped objects."""
    if depth > 10 or not obj:
        return None
    if isinstance(obj, list) and len(obj) >= 2:
        s = obj[0]
        if isinstance(s, dict) and any(k in s for k in ('wins','losses','schoolName','overallRecord','w','l')):
            return obj
    if isinstance(obj, dict):
        for v in obj.values():
            r = deep_find(v, depth + 1)
            if r:
                return r
    return None

def parse_next_data(html):
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.DOTALL)
    if not m:
        print('  __NEXT_DATA__ not found')
        return None
    print(f'  __NEXT_DATA__ found, {len(m.group(1))} chars')
    nd = json.loads(m.group(1))
    rows = deep_find(nd)
    if not rows:
        print('  No standings array found in __NEXT_DATA__')
        return None
    teams = {}
    for t in rows:
        name = (t.get('schoolName') or t.get('name') or t.get('teamName') or
                (t.get('school') or {}).get('name') or '?')
        rec  = t.get('overallRecord') or t.get('seasonRecord') or t.get('record') or {}
        w = int(t.get('wins') or t.get('w') or rec.get('wins') or rec.get('w') or 0)
        l = int(t.get('losses') or t.get('l') or rec.get('losses') or rec.get('l') or 0)
        name = str(name).strip()
        if name and name != '?':
            teams[name] = {'w': w, 'l': l}
    print(f'  Parsed {len(teams)} teams from __NEXT_DATA__')
    return teams if teams else None

def parse_html_table(html):
    """Fallback: find a <table> whose rows look like  Team | int | int."""
    from html.parser import HTMLParser
    class TP(HTMLParser):
        def __init__(self):
            super().__init__()
            self.rows, self._row, self._cell, self._in = [], [], '', False
        def handle_starttag(self, tag, _):
            if tag == 'tr': self._row = []
            elif tag == 'td': self._in = True; self._cell = ''
        def handle_endtag(self, tag):
            if tag == 'td': self._row.append(self._cell.strip()); self._in = False
            elif tag == 'tr' and self._row: self.rows.append(self._row)
        def handle_data(self, d):
            if self._in: self._cell += d
    p = TP(); p.feed(html)
    teams = {}
    for row in p.rows:
        if len(row) >= 3 and re.match(r'^\d+$', row[1]) and re.match(r'^\d+$', row[2]):
            teams[row[0]] = {'w': int(row[1]), 'l': int(row[2])}
    print(f'  HTML table scrape found {len(teams)} teams')
    return teams if teams else None

def write_firebase(teams):
    payload = json.dumps(teams).encode('utf-8')
    req = urllib.request.Request(FIREBASE_URL, data=payload, method='PUT',
                                  headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=15) as r:
        print(f'  Firebase write OK — {r.status} — {len(teams)} teams')

def main():
    print(f'Fetching {MAXPREPS_URL}')
    try:
        html = fetch(MAXPREPS_URL)
        print(f'  Got {len(html)} bytes')
    except Exception as e:
        print(f'FETCH ERROR: {e}'); sys.exit(1)

    teams = parse_next_data(html) or parse_html_table(html)

    if not teams:
        print('ERROR: could not parse any standings — aborting Firebase write')
        # Print first 1000 chars of page title area for debugging
        m = re.search(r'<title>(.*?)</title>', html)
        print(f'  Page title: {m.group(1) if m else "none"}')
        sys.exit(1)

    print(f'Teams found: {sorted(teams.keys())}')
    write_firebase(teams)
    print('Done.')

if __name__ == '__main__':
    main()

