#!/usr/bin/env python3
"""
Fetches each area team's season record from MaxPreps.
Data structure confirmed: pageProps.standingsData.standingSections[].teams[]
Each team row has schoolId and record fields.
"""

import json, re, sys, time, urllib.request

FIREBASE_BASE = 'https://leon-beach-volleyball-default-rtdb.firebaseio.com/leon_queens_matches/standings'

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9',
}

# display name → (MaxPreps standings URL, schoolId from logs)
AREA_TEAMS = {
    'Chiles':                               ('https://www.maxpreps.com/fl/tallahassee/chiles-timberwolves/beach-volleyball/standings/',                               '2a954006-a714-45f1-9269-eda8ff3eacf9'),
    'Lincoln':                              ('https://www.maxpreps.com/fl/tallahassee/lincoln-trojans/beach-volleyball/standings/',                                   '591101da-0101-4341-af4b-76c985882eb5'),
    'Godby':                                ('https://www.maxpreps.com/fl/tallahassee/godby-cougars/beach-volleyball/standings/',                                     '589722ff-b98d-44ae-ba46-d8c9b4229bdb'),
    'Rickards':                             ('https://www.maxpreps.com/fl/tallahassee/rickards-raiders/beach-volleyball/standings/',                                  '12e8657a-0b8c-47cd-9e2f-e5344842e64b'),
    'Maclay':                               ('https://www.maxpreps.com/fl/tallahassee/maclay-marauders/beach-volleyball/standings/',                                  'fd0c505c-b1c8-4674-a9db-add16d564760'),
    'Florida State University High School': ('https://www.maxpreps.com/fl/tallahassee/florida-state-university-high-school-flying-high/beach-volleyball/standings/',  'e77af86d-d71d-4a52-83ce-cc03464e9fd6'),
    'Wakulla':                              ('https://www.maxpreps.com/fl/crawfordville/wakulla-warriors/beach-volleyball/standings/',                                 None),
    'Munroe':                               ('https://www.maxpreps.com/fl/quincy/munroe-bobcats/beach-volleyball/standings/',                                         '24184150-81dc-45a5-8cda-656961c3442c'),
    'Community Christian':                  ('https://www.maxpreps.com/fl/tallahassee/community-christian-chargers/beach-volleyball/standings/',                      '114c7396-6302-42f1-87e9-073e81017bc1'),
    'Gulf Breeze':                          ('https://www.maxpreps.com/fl/gulf-breeze/gulf-breeze-dolphins/beach-volleyball/standings/',                              '3225b375-e31b-4769-92f4-bb0c22580a47'),
    'South Walton':                         ('https://www.maxpreps.com/fl/santa-rosa-beach/south-walton-seahawks/beach-volleyball/standings/',                        'f939336f-4002-40ba-87b9-cba62ce794f2'),
    'Mosley':                               ('https://www.maxpreps.com/fl/lynn-haven/mosley-dolphins/beach-volleyball/standings/',                                    '2d16a5bc-9a51-41b3-9110-bc24500a2e37'),
    'Sneads':                               ('https://www.maxpreps.com/fl/sneads/sneads-pirates/beach-volleyball/standings/',                                         'f2b32bc9-fbc9-4624-9481-6372d8f34de7'),
    'Destin':                               ('https://www.maxpreps.com/fl/destin/destin-sharks/beach-volleyball/standings/',                                          '9ff74951-1304-470d-993a-17bc22eabcc2'),
    'St- John Paul II':                     ('https://www.maxpreps.com/fl/tallahassee/john-paul-ii-panthers/beach-volleyball/standings/',                             None),
}

def safe_key(name):
    return re.sub(r'[.$#\[\]/]', '-', name).strip()

def fetch(url):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=15) as r:
        return r.read().decode('utf-8', errors='replace'), r.geturl()

def extract_record(team_obj):
    """Try every known field pattern for W-L in a team standings row."""
    # Pattern 1: overallRecord sub-object
    for rec_key in ('overallRecord', 'seasonRecord', 'record', 'stats'):
        rec = team_obj.get(rec_key)
        if isinstance(rec, dict):
            w = int(rec.get('wins') or rec.get('w') or rec.get('overallWins') or 0)
            l = int(rec.get('losses') or rec.get('l') or rec.get('overallLosses') or 0)
            if w or l:
                return w, l
    # Pattern 2: top-level wins/losses
    w = int(team_obj.get('wins') or team_obj.get('w') or 0)
    l = int(team_obj.get('losses') or team_obj.get('l') or 0)
    if w or l:
        return w, l
    return None

def get_record(standings_data, school_id, team_name):
    """
    Walk standingsData.standingSections[].teams[] looking for our school.
    Also try teamContext for overall record.
    """
    sections = standings_data.get('standingSections') or []

    all_teams = []
    for section in sections:
        # Section may have 'teams', 'standings', 'rows', or similar
        for key in ('teams', 'standings', 'rows', 'entries', 'data'):
            rows = section.get(key)
            if isinstance(rows, list):
                all_teams.extend(rows)
                break
        # Some structures nest deeper
        if not all_teams:
            for v in section.values():
                if isinstance(v, list) and v and isinstance(v[0], dict):
                    all_teams.extend(v)

    print(f'  Total team rows across all sections: {len(all_teams)}')
    if all_teams:
        print(f'  First row keys: {list(all_teams[0].keys())}')

    # Try to find by schoolId first (most reliable)
    if school_id:
        for t in all_teams:
            if t.get('schoolId') == school_id or (t.get('school') or {}).get('id') == school_id:
                rec = extract_record(t)
                if rec:
                    print(f'  Matched by schoolId → {rec[0]}-{rec[1]}')
                    return rec
                # Log the full row so we can see what fields exist
                print(f'  Matched schoolId but no record found. Row: {json.dumps(t)[:300]}')

    # Fallback: match by name
    for t in all_teams:
        name = (t.get('schoolName') or t.get('name') or
                (t.get('school') or {}).get('name') or '')
        if team_name.lower().split()[0] in str(name).lower():
            rec = extract_record(t)
            if rec:
                print(f'  Matched by name "{name}" → {rec[0]}-{rec[1]}')
                return rec

    # Nothing found — log a sample row in full so we know the structure
    if all_teams:
        print(f'  Sample full row: {json.dumps(all_teams[0])[:500]}')
    return None

def get_team_record(html, team_name, school_id):
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.DOTALL)
    if not m:
        print(f'  No __NEXT_DATA__')
        return None
    try:
        nd = json.loads(m.group(1))
        pp = (nd.get('props') or {}).get('pageProps') or {}

        # Also check teamContext for overall record
        tc = pp.get('teamContext') or {}
        for rec_key in ('overallRecord', 'record', 'seasonRecord'):
            rec = tc.get(rec_key)
            if isinstance(rec, dict):
                w = int(rec.get('wins') or rec.get('w') or 0)
                l = int(rec.get('losses') or rec.get('l') or 0)
                if w or l:
                    print(f'  Found in teamContext.{rec_key}: {w}-{l}')
                    return w, l

        standings_data = pp.get('standingsData')
        if standings_data:
            return get_record(standings_data, school_id, team_name)
        else:
            print(f'  No standingsData')
    except Exception as e:
        print(f'  Parse error: {e}')
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
    results = {}

    for team_name, (url, school_id) in AREA_TEAMS.items():
        print(f'\n{team_name}')
        try:
            html, _ = fetch(url)
            print(f'  {len(html)} bytes')
            rec = get_team_record(html, team_name, school_id)
            if rec:
                results[team_name] = rec
            else:
                print(f'  ✗ No record found')
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
        sys.exit(1)

if __name__ == '__main__':
    main()
