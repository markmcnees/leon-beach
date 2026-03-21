#!/usr/bin/env python3
"""
Fetches full season records from MaxPreps.
Strategy 1: FL classification pages (2A, 1A) — fast, gets all teams with games.
Strategy 2: Individual team schedule page — fallback for teams not on class pages.
"""

import json, re, sys, time, urllib.request, urllib.parse

FIREBASE_BASE = 'https://leon-beach-volleyball-default-rtdb.firebaseio.com/leon_queens_matches/standings'

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9',
}

CLASS_PAGES = [
    ('2A', 'https://www.maxpreps.com/fl/beach-volleyball/25-26/class/class-2a/?statedivisionid=1c33d1f9-9708-4efa-8dbe-a04ef7cd1b00'),
    ('1A', 'https://www.maxpreps.com/fl/beach-volleyball/25-26/class/class-1a/?statedivisionid=1c33d1f9-9708-4efa-8dbe-a04ef7cd1b00'),
]

# display name → (name fragments for class page matching, individual schedule URL)
TARGET_TEAMS = {
    'Chiles':                      (['chiles'],                    'https://www.maxpreps.com/fl/tallahassee/chiles-timberwolves/beach-volleyball/'),
    'Lincoln':                     (['lincoln'],                   'https://www.maxpreps.com/fl/tallahassee/lincoln-trojans/beach-volleyball/'),
    'Godby':                       (['godby'],                     'https://www.maxpreps.com/fl/tallahassee/godby-cougars/beach-volleyball/'),
    'Rickards':                    (['rickards'],                  'https://www.maxpreps.com/fl/tallahassee/rickards-raiders/beach-volleyball/'),
    'Maclay':                      (['maclay'],                    'https://www.maxpreps.com/fl/tallahassee/maclay-marauders/beach-volleyball/'),
    'Florida State University HS': (['florida state university'],  'https://www.maxpreps.com/fl/tallahassee/florida-state-university-high-school-flying-high/beach-volleyball/'),
    'Wakulla':                     (['wakulla'],                   'https://www.maxpreps.com/fl/crawfordville/wakulla-warriors/beach-volleyball/'),
    'Munroe':                      (['munroe'],                    'https://www.maxpreps.com/fl/quincy/munroe-bobcats/beach-volleyball/'),
    'Community Christian':         (['community christian'],       'https://www.maxpreps.com/fl/tallahassee/community-christian-chargers/beach-volleyball/'),
    'Gulf Breeze':                 (['gulf breeze'],               'https://www.maxpreps.com/fl/gulf-breeze/gulf-breeze-dolphins/beach-volleyball/'),
    'South Walton':                (['south walton'],              'https://www.maxpreps.com/fl/santa-rosa-beach/south-walton-seahawks/beach-volleyball/'),
    'Mosley':                      (['mosley'],                    'https://www.maxpreps.com/fl/lynn-haven/mosley-dolphins/beach-volleyball/'),
    'Sneads':                      (['sneads'],                    'https://www.maxpreps.com/fl/sneads/sneads-pirates/beach-volleyball/'),
    'Destin':                      (['destin'],                    'https://www.maxpreps.com/fl/destin/destin-sharks/beach-volleyball/'),
    'St- John Paul II':            (['john paul', 'jp ii'],        'https://www.maxpreps.com/fl/tallahassee/john-paul-ii-panthers/beach-volleyball/'),
}

def fetch(url):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=15) as r:
        return r.read().decode('utf-8', errors='replace')

def get_next_data(html):
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.DOTALL)
    if not m: return {}
    try: return json.loads(m.group(1))
    except: return {}

def extract_class_page(html, label):
    """Get all teams with overallWins from a classification page."""
    nd = get_next_data(html)
    all_rows = []
    def collect(obj, depth=0):
        if depth > 8 or not obj: return
        if isinstance(obj, list) and obj and isinstance(obj[0], dict) and 'overallWins' in obj[0]:
            all_rows.extend(obj); return
        if isinstance(obj, dict):
            for v in obj.values(): collect(v, depth+1)
        elif isinstance(obj, list):
            for i in obj: collect(i, depth+1)
    collect(nd)
    results = []
    for t in all_rows:
        name = t.get('schoolName','')
        w = int(t.get('overallWins') or 0)
        l = int(t.get('overallLosses') or 0)
        if name: results.append({'name': name, 'w': w, 'l': l})
    print(f'  [{label}] {len(results)} teams')
    # Print all FL-area team names for debugging
    fl_teams = [r['name'] for r in results if r['w'] or r['l'] or True]
    print(f'  [{label}] all names: {sorted(fl_teams)}')
    return results

def extract_schedule_record(html):
    """Get overall W-L from a team's schedule/home page."""
    nd = get_next_data(html)
    pp = (nd.get('props') or {}).get('pageProps') or {}

    # Try teamRecord or similar
    for key in ('teamRecord', 'overallRecord', 'seasonRecord', 'record'):
        rec = pp.get(key)
        if isinstance(rec, dict):
            w = int(rec.get('wins') or rec.get('overallWins') or rec.get('w') or 0)
            l = int(rec.get('losses') or rec.get('overallLosses') or rec.get('l') or 0)
            if w or l: return w, l

    # Try teamContext
    tc = pp.get('teamContext') or {}
    for key in ('overallRecord', 'record', 'teamRecord'):
        rec = tc.get(key)
        if isinstance(rec, dict):
            w = int(rec.get('wins') or rec.get('w') or 0)
            l = int(rec.get('losses') or rec.get('l') or 0)
            if w or l: return w, l

    # Try scheduleData — count wins/losses from schedule entries
    sd = pp.get('scheduleData') or pp.get('schedule') or []
    if isinstance(sd, list):
        w = sum(1 for g in sd if isinstance(g, dict) and str(g.get('result','')).upper().startswith('W'))
        l = sum(1 for g in sd if isinstance(g, dict) and str(g.get('result','')).upper().startswith('L'))
        if w or l: return w, l

    # Deep search for wins/losses integers near schoolName
    def find_record(obj, depth=0):
        if depth > 6 or not isinstance(obj, dict): return None
        w = obj.get('overallWins') or obj.get('wins') or obj.get('w')
        l = obj.get('overallLosses') or obj.get('losses') or obj.get('l')
        if w is not None and l is not None:
            try:
                wi, li = int(w), int(l)
                if wi or li: return wi, li
            except: pass
        for v in obj.values():
            if isinstance(v, dict):
                r = find_record(v, depth+1)
                if r: return r
        return None

    r = find_record(pp)
    if r: return r
    return None

def find_in_class(all_rows, fragments):
    for row in all_rows:
        name_lower = row['name'].lower()
        if any(frag in name_lower for frag in fragments):
            return row
    return None

def write_team(name, w, l):
    encoded = urllib.parse.quote(name, safe='')
    url = f'{FIREBASE_BASE}/{encoded}.json'
    payload = json.dumps({'w': w, 'l': l, 'name': name}).encode('utf-8')
    req = urllib.request.Request(url, data=payload, method='PUT',
                                  headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=15) as r:
        return r.status

def main():
    # Step 1: fetch classification pages
    all_class_rows = []
    for label, url in CLASS_PAGES:
        print(f'Fetching {label} class page...')
        try:
            html = fetch(url)
            rows = extract_class_page(html, label)
            all_class_rows.extend(rows)
            time.sleep(0.5)
        except Exception as e:
            print(f'  ERROR: {e}')

    print(f'Total class rows: {len(all_class_rows)}\n')

    # Step 2: match each team
    results = {}
    for display_name, (fragments, schedule_url) in TARGET_TEAMS.items():
        # Try class page first
        row = find_in_class(all_class_rows, fragments)
        if row:
            print(f'✓ {display_name}: {row["w"]}-{row["l"]}  (class page: "{row["name"]}")')
            results[display_name] = (row['w'], row['l'])
            continue

        # Fall back to individual schedule page
        print(f'  {display_name}: not on class page, trying schedule page...')
        try:
            html = fetch(schedule_url)
            rec = extract_schedule_record(html)
            if rec:
                print(f'✓ {display_name}: {rec[0]}-{rec[1]}  (schedule page)')
                results[display_name] = rec
            else:
                print(f'✗ {display_name}: no record found (0-0 or not started)')
            time.sleep(0.4)
        except Exception as e:
            print(f'✗ {display_name}: fetch error — {e}')

    # Step 3: write to Firebase
    print('\n── Writing to Firebase ──')
    written = skipped = 0
    for name, (w, l) in results.items():
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

    print(f'\nDone — {written} written, {skipped} skipped (0-0)')

if __name__ == '__main__':
    main()
