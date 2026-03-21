#!/usr/bin/env python3
"""
Fetches full season records from MaxPreps FL classification standings pages.
Fields confirmed: overallWins, overallLosses (integers), schoolName (string).
No schoolId on these pages — match by name.
"""

import json, re, sys, time, urllib.request

FIREBASE_BASE = 'https://leon-beach-volleyball-default-rtdb.firebaseio.com/leon_queens_matches/standings'

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9',
}

# Classification pages — each covers all teams in that class statewide
CLASS_PAGES = [
    ('2A', 'https://www.maxpreps.com/fl/beach-volleyball/25-26/class/class-2a/?statedivisionid=1c33d1f9-9708-4efa-8dbe-a04ef7cd1b00'),
    ('1A', 'https://www.maxpreps.com/fl/beach-volleyball/25-26/class/class-1a/?statedivisionid=1c33d1f9-9708-4efa-8dbe-a04ef7cd1b00'),
]

# Display name → list of possible MaxPreps name fragments (lowercase) for matching
# Leon is excluded — auto-computed from schedule
TARGET_TEAMS = {
    'Chiles':                               ['chiles'],
    'Lincoln':                              ['lincoln'],
    'Godby':                                ['godby'],
    'Rickards':                             ['rickards'],
    'Maclay':                               ['maclay'],
    'Florida State University High School': ['florida state university high', 'fsu high', 'fsus'],
    'Wakulla':                              ['wakulla'],
    'Munroe':                               ['munroe'],
    'Community Christian':                  ['community christian'],
    'Gulf Breeze':                          ['gulf breeze'],
    'South Walton':                         ['south walton'],
    'Mosley':                               ['mosley'],
    'Sneads':                               ['sneads'],
    'Destin':                               ['destin'],
    'St- John Paul II':                     ['john paul', 'jp ii', 'jpii'],
}

def safe_key(name):
    return re.sub(r'[.$#\[\]/ ]', '-', name).strip()

def fetch(url):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=15) as r:
        return r.read().decode('utf-8', errors='replace')

def extract_teams_from_page(html, label):
    """Return list of {name, w, l} from a classification page."""
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.DOTALL)
    if not m:
        print(f'  [{label}] No __NEXT_DATA__')
        return []

    nd = json.loads(m.group(1))

    # Deep-walk looking for list with overallWins field
    all_rows = []
    def deep_collect(obj, depth=0):
        if depth > 8 or not obj:
            return
        if isinstance(obj, list) and len(obj) > 0 and isinstance(obj[0], dict):
            if 'overallWins' in obj[0]:
                all_rows.extend(obj)
                return
        if isinstance(obj, dict):
            for v in obj.values():
                deep_collect(v, depth+1)
        elif isinstance(obj, list):
            for item in obj:
                deep_collect(item, depth+1)

    deep_collect(nd)
    print(f'  [{label}] {len(all_rows)} rows, keys: {list(all_rows[0].keys())[:6] if all_rows else []}')

    results = []
    for t in all_rows:
        name = t.get('schoolName', '')
        w = t.get('overallWins') or t.get('wins') or 0
        l = t.get('overallLosses') or t.get('losses') or 0
        if name:
            results.append({'name': name, 'w': int(w), 'l': int(l)})
    return results

def find_team(all_rows, fragments):
    """Find best matching row for a team given name fragments."""
    for row in all_rows:
        name_lower = row['name'].lower()
        if any(frag in name_lower for frag in fragments):
            return row
    return None

def write_team(name, w, l):
    key = safe_key(name)
    url = f'{FIREBASE_BASE}/{key}.json'
    payload = json.dumps({'w': w, 'l': l, 'name': name}).encode('utf-8')
    req = urllib.request.Request(url, data=payload, method='PUT',
                                  headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=15) as r:
        return r.status

def main():
    # Collect all rows from all class pages
    all_rows = []
    for label, url in CLASS_PAGES:
        print(f'\nFetching {label}: {url[:80]}')
        try:
            html = fetch(url)
            print(f'  {len(html)} bytes')
            rows = extract_teams_from_page(html, label)
            all_rows.extend(rows)
            time.sleep(0.5)
        except Exception as e:
            print(f'  FETCH ERROR: {e}')

    print(f'\nTotal rows collected: {len(all_rows)}')

    # Match and report
    print('\n── Results for area teams ──')
    to_write = {}
    for display_name, fragments in TARGET_TEAMS.items():
        row = find_team(all_rows, fragments)
        if row:
            print(f'  ✓ {display_name}: {row["w"]}-{row["l"]}  (matched: "{row["name"]}")')
            to_write[display_name] = (row['w'], row['l'])
        else:
            print(f'  ✗ {display_name}: NOT FOUND')

    print('\n── Writing to Firebase ──')
    written = skipped = 0
    for name, (w, l) in to_write.items():
        if w == 0 and l == 0:
            print(f'  SKIP {name}: 0-0')
            skipped += 1
            continue
        try:
            status = write_team(name, w, l)
            print(f'  ✓ {name}: {w}-{l}  (HTTP {status})')
            written += 1
        except Exception as e:
            print(f'  WRITE ERROR {name}: {e}')

    print(f'\nDone — {written} written, {skipped} skipped')
    if written == 0 and len(to_write) == 0:
        sys.exit(1)

if __name__ == '__main__':
    main()
