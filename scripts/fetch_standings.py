#!/usr/bin/env python3
"""
Fetches each area team's season record from MaxPreps.
Record field confirmed: overallWinLossTies = "W-L-T" string.
"""

import json, re, sys, time, urllib.request

FIREBASE_BASE = 'https://leon-beach-volleyball-default-rtdb.firebaseio.com/leon_queens_matches/standings'

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9',
}

# display name → (standings URL, schoolId)
# schoolIds confirmed from run #5 logs; Wakulla schoolId from Rickards sample row
AREA_TEAMS = {
    'Chiles':                               ('https://www.maxpreps.com/fl/tallahassee/chiles-timberwolves/beach-volleyball/standings/',                '2a954006-a714-45f1-9269-eda8ff3eacf9'),
    'Lincoln':                              ('https://www.maxpreps.com/fl/tallahassee/lincoln-trojans/beach-volleyball/standings/',                    '591101da-0101-4341-af4b-76c985882eb5'),
    'Godby':                                ('https://www.maxpreps.com/fl/tallahassee/godby-cougars/beach-volleyball/standings/',                      '589722ff-b98d-44ae-ba46-d8c9b4229bdb'),
    'Rickards':                             ('https://www.maxpreps.com/fl/tallahassee/rickards-raiders/beach-volleyball/standings/',                   '12e8657a-0b8c-47cd-9e2f-e5344842e64b'),
    'Maclay':                               ('https://www.maxpreps.com/fl/tallahassee/maclay-marauders/beach-volleyball/standings/',                   'fd0c505c-b1c8-4674-a9db-add16d564760'),
    'Florida State University High School': ('https://www.maxpreps.com/fl/tallahassee/florida-state-university-high-school-flying-high/beach-volleyball/standings/', 'e77af86d-d71d-4a52-83ce-cc03464e9fd6'),
    'Wakulla':                              ('https://www.maxpreps.com/fl/crawfordville/wakulla-warriors/beach-volleyball/standings/',                  '1bcaff05-ef8c-4e92-961e-b516f7179ce1'),
    'Munroe':                               ('https://www.maxpreps.com/fl/quincy/munroe-bobcats/beach-volleyball/standings/',                          '24184150-81dc-45a5-8cda-656961c3442c'),
    'Community Christian':                  ('https://www.maxpreps.com/fl/tallahassee/community-christian-chargers/beach-volleyball/standings/',       '114c7396-6302-42f1-87e9-073e81017bc1'),
    'Gulf Breeze':                          ('https://www.maxpreps.com/fl/gulf-breeze/gulf-breeze-dolphins/beach-volleyball/standings/',               '3225b375-e31b-4769-92f4-bb0c22580a47'),
    'South Walton':                         ('https://www.maxpreps.com/fl/santa-rosa-beach/south-walton-seahawks/beach-volleyball/standings/',         'f939336f-4002-40ba-87b9-cba62ce794f2'),
    'Mosley':                               ('https://www.maxpreps.com/fl/lynn-haven/mosley-dolphins/beach-volleyball/standings/',                     '2d16a5bc-9a51-41b3-9110-bc24500a2e37'),
    'Sneads':                               ('https://www.maxpreps.com/fl/sneads/sneads-pirates/beach-volleyball/standings/',                          'f2b32bc9-fbc9-4624-9481-6372d8f34de7'),
    'Destin':                               ('https://www.maxpreps.com/fl/destin/destin-sharks/beach-volleyball/standings/',                           '9ff74951-1304-470d-993a-17bc22eabcc2'),
    'St- John Paul II':                     ('https://www.maxpreps.com/fl/tallahassee/john-paul-ii-panthers/beach-volleyball/standings/',              None),
}

def safe_key(name):
    return re.sub(r'[.$#\[\]/]', '-', name).strip()

def fetch(url):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=15) as r:
        return r.read().decode('utf-8', errors='replace'), r.geturl()

def parse_wlt(wlt_str):
    """Parse 'W-L-T' string like '7-0-0' → (7, 0)"""
    if not wlt_str:
        return None
    parts = str(wlt_str).split('-')
    if len(parts) >= 2:
        try:
            return int(parts[0]), int(parts[1])
        except ValueError:
            pass
    return None

def get_record(standings_data, school_id, team_name):
    sections = standings_data.get('standingSections') or []
    all_teams = []
    for section in sections:
        for key in ('teams', 'standings', 'rows', 'entries', 'data'):
            rows = section.get(key)
            if isinstance(rows, list):
                all_teams.extend(rows)
                break

    # Match by schoolId
    if school_id:
        for t in all_teams:
            if t.get('schoolId') == school_id:
                # PRIMARY: overallWinLossTies = "W-L-T"
                rec = parse_wlt(t.get('overallWinLossTies'))
                if rec:
                    print(f'  ✓ overallWinLossTies="{t.get("overallWinLossTies")}" → {rec[0]}-{rec[1]}')
                    return rec
                # FALLBACK: conferenceWinLossTies
                rec = parse_wlt(t.get('conferenceWinLossTies'))
                if rec:
                    print(f'  ✓ conferenceWinLossTies="{t.get("conferenceWinLossTies")}" → {rec[0]}-{rec[1]}')
                    return rec
                print(f'  Matched schoolId but WLT fields empty. overallWinLossTies={t.get("overallWinLossTies")!r}')
                return None

    # Fallback: name match
    for t in all_teams:
        name = t.get('schoolName') or ''
        if team_name.lower().split()[0] in name.lower():
            rec = parse_wlt(t.get('overallWinLossTies'))
            if rec:
                print(f'  ✓ name match "{name}" → {rec[0]}-{rec[1]}')
                return rec

    print(f'  No match found in {len(all_teams)} rows')
    return None

def get_team_record(html, team_name, school_id):
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.DOTALL)
    if not m:
        print(f'  No __NEXT_DATA__')
        return None
    try:
        nd = json.loads(m.group(1))
        pp = (nd.get('props') or {}).get('pageProps') or {}
        standings_data = pp.get('standingsData')
        if standings_data:
            return get_record(standings_data, school_id, team_name)
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
