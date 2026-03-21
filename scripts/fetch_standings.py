#!/usr/bin/env python3
"""
Fetches each area team's full season record from their individual MaxPreps page.
Data lives in pageProps.standingsData — confirmed from live logs.
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
    'Chiles':                               'https://www.maxpreps.com/fl/tallahassee/chiles-timberwolves/beach-volleyball/standings/',
    'Lincoln':                              'https://www.maxpreps.com/fl/tallahassee/lincoln-trojans/beach-volleyball/standings/',
    'Godby':                                'https://www.maxpreps.com/fl/tallahassee/godby-cougars/beach-volleyball/standings/',
    'Rickards':                             'https://www.maxpreps.com/fl/tallahassee/rickards-raiders/beach-volleyball/standings/',
    'Maclay':                               'https://www.maxpreps.com/fl/tallahassee/maclay-marauders/beach-volleyball/standings/',
    'Florida State University High School': 'https://www.maxpreps.com/fl/tallahassee/florida-state-university-high-school-flying-high/beach-volleyball/standings/',
    'Wakulla':                              'https://www.maxpreps.com/fl/crawfordville/wakulla-warriors/beach-volleyball/standings/',
    'Munroe':                               'https://www.maxpreps.com/fl/quincy/munroe-bobcats/beach-volleyball/standings/',
    'Community Christian':                  'https://www.maxpreps.com/fl/tallahassee/community-christian-chargers/beach-volleyball/standings/',
    'Gulf Breeze':                          'https://www.maxpreps.com/fl/gulf-breeze/gulf-breeze-dolphins/beach-volleyball/standings/',
    'South Walton':                         'https://www.maxpreps.com/fl/santa-rosa-beach/south-walton-seahawks/beach-volleyball/standings/',
    'Mosley':                               'https://www.maxpreps.com/fl/lynn-haven/mosley-dolphins/beach-volleyball/standings/',
    'Sneads':                               'https://www.maxpreps.com/fl/sneads/sneads-pirates/beach-volleyball/standings/',
    'Destin':                               'https://www.maxpreps.com/fl/destin/destin-sharks/beach-volleyball/standings/',
    'St- John Paul II':                     'https://www.maxpreps.com/fl/tallahassee/john-paul-ii-panthers/beach-volleyball/standings/',
}

def safe_key(name):
    return re.sub(r'[.$#\[\]/]', '-', name).strip()

def fetch(url):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=15) as r:
        return r.read().decode('utf-8', errors='replace'), r.geturl()

def get_record_from_standings_data(standings_data, team_name):
    """
    pageProps.standingsData is confirmed present.
    Walk it to find the entry matching this team and extract overall W-L.
    """
    if not standings_data:
        return None

    # It may be a list of groups/conferences, each with a teams array
    # Or a direct list of team entries
    def search(obj, depth=0):
        if depth > 6 or not obj:
            return None
        if isinstance(obj, list):
            for item in obj:
                r = search(item, depth+1)
                if r:
                    return r
        if isinstance(obj, dict):
            # Check if this looks like a team entry with a record
            name = (obj.get('schoolName') or obj.get('name') or
                    obj.get('teamName') or (obj.get('school') or {}).get('name') or '')
            if name:
                # Try to get overall record
                rec = (obj.get('overallRecord') or obj.get('record') or
                       obj.get('seasonRecord') or {})
                w = int(obj.get('wins') or obj.get('w') or
                        rec.get('wins') or rec.get('w') or
                        rec.get('overallWins') or 0)
                l = int(obj.get('losses') or obj.get('l') or
                        rec.get('losses') or rec.get('l') or
                        rec.get('overallLosses') or 0)
                if w or l:
                    print(f'  Found team "{name}": {w}-{l}')
                    return w, l

            # Recurse into all values
            for v in obj.values():
                r = search(v, depth+1)
                if r:
                    return r
        return None

    result = search(standings_data)

    # If nothing found, log the structure so we can debug
    if not result:
        if isinstance(standings_data, list) and standings_data:
            print(f'  standingsData is list[{len(standings_data)}], first item keys: {list(standings_data[0].keys()) if isinstance(standings_data[0], dict) else type(standings_data[0])}')
        elif isinstance(standings_data, dict):
            print(f'  standingsData keys: {list(standings_data.keys())[:10]}')

    return result

def get_team_record(html, team_name):
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.DOTALL)
    if not m:
        print(f'  No __NEXT_DATA__')
        return None
    try:
        nd = json.loads(m.group(1))
        pp = (nd.get('props') or {}).get('pageProps') or {}

        # ── Primary: standingsData (confirmed key from logs) ──
        standings_data = pp.get('standingsData')
        if standings_data is not None:
            result = get_record_from_standings_data(standings_data, team_name)
            if result:
                return result
            print(f'  standingsData present but record not found — logging raw:')
            print(f'  {json.dumps(standings_data)[:400]}')
        else:
            print(f'  standingsData key missing — pageProps keys: {list(pp.keys())[:12]}')

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

    for team_name, url in AREA_TEAMS.items():
        print(f'\n{team_name}')
        try:
            html, final_url = fetch(url)
            print(f'  {len(html)} bytes')
            rec = get_team_record(html, team_name)
            if rec:
                results[team_name] = rec
            else:
                print(f'  ✗ Could not extract record')
            time.sleep(0.4)
        except Exception as e:
            print(f'  FETCH ERROR: {e}')

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

    print(f'\nDone — {written} written, {skipped} skipped')
    if written == 0 and len(results) == 0:
        print('ERROR: No records found at all')
        sys.exit(1)

if __name__ == '__main__':
    main()
