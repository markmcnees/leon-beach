#!/usr/bin/env python3
"""
Fetches each area team's full season record from their individual MaxPreps page
and writes to Firebase under leon_queens_matches/standings.
Only updates teams with at least 1 game played — never overwrites with 0-0.
"""

import json, re, sys, time, urllib.request

FIREBASE_BASE = 'https://leon-beach-volleyball-default-rtdb.firebaseio.com/leon_queens_matches/standings'

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9',
}

# Area teams: display name → MaxPreps standings URL
AREA_TEAMS = {
    'Chiles':                       'https://www.maxpreps.com/fl/tallahassee/chiles-timberwolves/beach-volleyball/standings/',
    'Lincoln':                      'https://www.maxpreps.com/fl/tallahassee/lincoln-trojans/beach-volleyball/standings/',
    'Godby':                        'https://www.maxpreps.com/fl/tallahassee/godby-cougars/beach-volleyball/standings/',
    'Rickards':                     'https://www.maxpreps.com/fl/tallahassee/rickards-raiders/beach-volleyball/standings/',
    'Maclay':                       'https://www.maxpreps.com/fl/tallahassee/maclay-marauders/beach-volleyball/standings/',
    'Florida State University High School': 'https://www.maxpreps.com/fl/tallahassee/florida-state-university-high-school-flying-high/beach-volleyball/standings/',
    'Wakulla':                      'https://www.maxpreps.com/fl/crawfordville/wakulla-warriors/beach-volleyball/standings/',
    'Munroe':                       'https://www.maxpreps.com/fl/quincy/munroe-bobcats/beach-volleyball/standings/',
    'Community Christian':          'https://www.maxpreps.com/fl/tallahassee/community-christian-chargers/beach-volleyball/standings/',
    'Gulf Breeze':                  'https://www.maxpreps.com/fl/gulf-breeze/gulf-breeze-dolphins/beach-volleyball/standings/',
    'South Walton':                 'https://www.maxpreps.com/fl/santa-rosa-beach/south-walton-seahawks/beach-volleyball/standings/',
    'Mosley':                       'https://www.maxpreps.com/fl/lynn-haven/mosley-dolphins/beach-volleyball/standings/',
    'Sneads':                       'https://www.maxpreps.com/fl/sneads/sneads-pirates/beach-volleyball/standings/',
    'Destin':                       'https://www.maxpreps.com/fl/destin/destin-sharks/beach-volleyball/standings/',
    'St- John Paul II':             'https://www.maxpreps.com/fl/tallahassee/john-paul-ii-panthers/beach-volleyball/standings/',
}

def safe_key(name):
    return re.sub(r'[.$#\[\]/]', '-', name).strip()

def fetch(url):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=15) as r:
        return r.read().decode('utf-8', errors='replace'), r.geturl()

def get_leon_record(html):
    """From Leon's own standings page, extract Leon's overall record."""
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.DOTALL)
    if not m:
        return None
    try:
        nd = json.loads(m.group(1))
        # Look for Leon in the standings array
        def find(obj, depth=0):
            if depth > 10 or not obj: return None
            if isinstance(obj, list) and len(obj) >= 1:
                s = obj[0]
                if isinstance(s, dict) and any(k in s for k in ('wins','losses','schoolName','overallRecord')):
                    return obj
            if isinstance(obj, dict):
                for v in obj.values():
                    r = find(v, depth+1)
                    if r: return r
            return None
        rows = find(nd)
        if rows:
            for t in rows:
                name = (t.get('schoolName') or t.get('name') or '')
                if 'leon' in str(name).lower():
                    rec = t.get('overallRecord') or t.get('record') or {}
                    w = int(t.get('wins') or rec.get('wins') or 0)
                    l = int(t.get('losses') or rec.get('losses') or 0)
                    return w, l
    except Exception as e:
        print(f'  Leon parse error: {e}')
    return None

def get_team_record_from_page(html, team_name):
    """Extract a team's overall W-L from their own MaxPreps page."""
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.DOTALL)
    if not m:
        print(f'  No __NEXT_DATA__ on {team_name} page')
        return None
    try:
        nd = json.loads(m.group(1))

        # Strategy 1: look for overallRecord at top level of pageProps
        pp = (nd.get('props') or {}).get('pageProps') or {}

        # Try teamRecord, seasonRecord, record fields directly
        for field in ('teamRecord','seasonRecord','overallRecord','record','teamStats'):
            rec = pp.get(field)
            if rec and isinstance(rec, dict):
                w = int(rec.get('wins') or rec.get('overallWins') or rec.get('w') or 0)
                l = int(rec.get('losses') or rec.get('overallLosses') or rec.get('l') or 0)
                if w or l:
                    print(f'  Found via pageProps.{field}: {w}-{l}')
                    return w, l

        # Strategy 2: look for the team in a standings array on their own page
        def find_team(obj, depth=0):
            if depth > 10 or not obj: return None
            if isinstance(obj, list) and len(obj) >= 1:
                s = obj[0]
                if isinstance(s, dict) and any(k in s for k in ('wins','losses','schoolName','overallRecord')):
                    return obj
            if isinstance(obj, dict):
                for v in obj.values():
                    r = find_team(v, depth+1)
                    if r: return r
            return None

        rows = find_team(nd)
        if rows:
            # On a team's own page, the first or only entry should be that team
            for t in rows:
                rec = t.get('overallRecord') or t.get('record') or {}
                w = int(t.get('wins') or rec.get('wins') or 0)
                l = int(t.get('losses') or rec.get('losses') or 0)
                if w or l:
                    print(f'  Found in standings array: {w}-{l}')
                    return w, l

        # Strategy 3: look for wins/losses directly in pageProps
        w = int(pp.get('wins') or pp.get('overallWins') or 0)
        l = int(pp.get('losses') or pp.get('overallLosses') or 0)
        if w or l:
            print(f'  Found in pageProps root: {w}-{l}')
            return w, l

        # Log top-level keys for debugging
        print(f'  pageProps keys: {list(pp.keys())[:12]}')
        # Log sample of first standings entry if any
        if rows:
            print(f'  First row keys: {list(rows[0].keys())}')

    except Exception as e:
        print(f'  Parse error: {e}')
    return None

def write_team(name, w, l):
    key = safe_key(name)
    url = f'{FIREBASE_BASE}/{key}.json'
    data = {'w': w, 'l': l, 'name': name}
    payload = json.dumps(data).encode('utf-8')
    req = urllib.request.Request(url, data=payload, method='PUT',
                                  headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=15) as r:
        return r.status

def main():
    results = {}

    # ── Fetch each area team's page ──────────────────────────────────────────
    for team_name, url in AREA_TEAMS.items():
        print(f'\n{team_name}')
        try:
            html, final_url = fetch(url)
            print(f'  URL: {final_url[:80]}')
            rec = get_team_record_from_page(html, team_name)
            if rec:
                w, l = rec
                results[team_name] = (w, l)
            else:
                print(f'  Could not parse record')
            time.sleep(0.5)  # be polite
        except Exception as e:
            print(f'  FETCH ERROR: {e}')

    # ── Write results to Firebase ────────────────────────────────────────────
    print('\n── Writing to Firebase ──')
    written = skipped = 0
    for name, (w, l) in results.items():
        if w == 0 and l == 0:
            print(f'  SKIP {name}: 0-0')
            skipped += 1
            continue
        try:
            status = write_team(name, w, l)
            print(f'  WROTE {name}: {w}-{l} (HTTP {status})')
            written += 1
        except Exception as e:
            print(f'  WRITE ERROR {name}: {e}')

    print(f'\nDone — {written} written, {skipped} skipped')
    if not written and not skipped:
        print('WARNING: No records found at all')
        sys.exit(1)

if __name__ == '__main__':
    main()
