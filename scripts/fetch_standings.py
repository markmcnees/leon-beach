#!/usr/bin/env python3
"""
Fetches full season records from MaxPreps FL classification standings pages.
One page covers all teams in that class — no need for per-team fetches.
Falls back to individual team pages if needed.
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
    'https://www.maxpreps.com/fl/beach-volleyball/25-26/class/class-2a/?statedivisionid=1c33d1f9-9708-4efa-8dbe-a04ef7cd1b00',
    'https://www.maxpreps.com/fl/beach-volleyball/25-26/class/class-1a/?statedivisionid=1c33d1f9-9708-4efa-8dbe-a04ef7cd1b00',
    # Fallback: Leon's own standings page (has area teams in district view)
    'https://www.maxpreps.com/fl/tallahassee/leon-lions/beach-volleyball/standings/',
]

# Teams we care about — name → schoolId (for matching)
TARGET_SCHOOLS = {
    '2a954006-a714-45f1-9269-eda8ff3eacf9': 'Chiles',
    '591101da-0101-4341-af4b-76c985882eb5': 'Lincoln',
    '589722ff-b98d-44ae-ba46-d8c9b4229bdb': 'Godby',
    '12e8657a-0b8c-47cd-9e2f-e5344842e64b': 'Rickards',
    'fd0c505c-b1c8-4674-a9db-add16d564760': 'Maclay',
    'e77af86d-d71d-4a52-83ce-cc03464e9fd6': 'Florida State University High School',
    '1bcaff05-ef8c-4e92-961e-b516f7179ce1': 'Wakulla',
    '24184150-81dc-45a5-8cda-656961c3442c': 'Munroe',
    '114c7396-6302-42f1-87e9-073e81017bc1': 'Community Christian',
    '3225b375-e31b-4769-92f4-bb0c22580a47': 'Gulf Breeze',
    'f939336f-4002-40ba-87b9-cba62ce794f2': 'South Walton',
    '2d16a5bc-9a51-41b3-9110-bc24500a2e37': 'Mosley',
    'f2b32bc9-fbc9-4624-9481-6372d8f34de7': 'Sneads',
    '9ff74951-1304-470d-993a-17bc22eabcc2': 'Destin',
    'bcab8ab9-4bed-4f1d-b451-d3fcdbf6e97c': 'Leon',  # skip writing Leon — auto-computed
}

def safe_key(name):
    return re.sub(r'[.$#\[\]/]', '-', name).strip()

def fetch(url):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=15) as r:
        return r.read().decode('utf-8', errors='replace')

def parse_wlt(wlt_str):
    """'7-0-0' → (7, 0)"""
    if not wlt_str:
        return None
    parts = str(wlt_str).split('-')
    if len(parts) >= 2:
        try:
            return int(parts[0]), int(parts[1])
        except ValueError:
            pass
    return None

def extract_teams_from_page(html, page_label):
    """Return dict of schoolId → (w, l, name) from any MaxPreps standings page."""
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.DOTALL)
    if not m:
        print(f'  [{page_label}] No __NEXT_DATA__')
        return {}

    nd = json.loads(m.group(1))
    pp = nd.get('props', {}).get('pageProps', {})

    # Collect all team rows from every possible location
    all_rows = []

    # Path 1: standingsData.standingSections[].teams[]
    sd = pp.get('standingsData') or {}
    for section in (sd.get('standingSections') or []):
        for key in ('teams', 'standings', 'rows', 'entries'):
            rows = section.get(key)
            if isinstance(rows, list):
                all_rows.extend(rows)
                break

    # Path 2: rankingsData or similar top-level list
    for key in ('rankingsData', 'rankings', 'teams', 'teamsList', 'schoolRankings'):
        val = pp.get(key)
        if isinstance(val, list) and val and isinstance(val[0], dict):
            all_rows.extend(val)

    # Path 3: deep-walk pageProps for any list with schoolId + WLT
    def deep_collect(obj, depth=0):
        if depth > 6 or not isinstance(obj, (dict, list)):
            return
        if isinstance(obj, list):
            if obj and isinstance(obj[0], dict) and 'schoolId' in obj[0]:
                all_rows.extend(obj)
                return
            for item in obj:
                deep_collect(item, depth+1)
        elif isinstance(obj, dict):
            for v in obj.values():
                deep_collect(v, depth+1)

    if not all_rows:
        deep_collect(pp)

    print(f'  [{page_label}] {len(all_rows)} team rows found')
    if all_rows:
        print(f'  [{page_label}] keys: {list(all_rows[0].keys())[:8]}')

    results = {}
    for t in all_rows:
        sid = t.get('schoolId')
        if not sid:
            continue
        # Try overall first, then conference
        rec = parse_wlt(t.get('overallWinLossTies')) or parse_wlt(t.get('conferenceWinLossTies'))
        if rec and sid:
            name = t.get('schoolName') or sid
            results[sid] = (rec[0], rec[1], name)

    print(f'  [{page_label}] parsed records for {len(results)} schools')
    return results

def main():
    found = {}  # schoolId → (w, l, display_name)

    for page_url in CLASS_PAGES:
        label = page_url.split('/')[-2] if '?' not in page_url else page_url.split('class-')[1].split('/')[0] if 'class-' in page_url else 'leon'
        print(f'\nFetching: {page_url[:80]}')
        try:
            html = fetch(page_url)
            print(f'  {len(html)} bytes')
            page_results = extract_teams_from_page(html, label)
            for sid, rec in page_results.items():
                if sid not in found:
                    found[sid] = rec
            time.sleep(0.5)
        except Exception as e:
            print(f'  FETCH ERROR: {e}')

    # Map to display names and filter to our area teams
    print('\n── Results for area teams ──')
    to_write = {}
    for sid, display_name in TARGET_SCHOOLS.items():
        if sid in found:
            w, l, raw_name = found[sid]
            print(f'  {display_name}: {w}-{l}  (MaxPreps name: {raw_name})')
            if display_name != 'Leon':  # Leon is auto-computed from schedule
                to_write[display_name] = (w, l)
        else:
            print(f'  {display_name}: NOT FOUND')

    print('\n── Writing to Firebase ──')
    written = skipped = 0
    for name, (w, l) in to_write.items():
        if w == 0 and l == 0:
            print(f'  SKIP {name}: 0-0')
            skipped += 1
            continue
        key = safe_key(name)
        url = f'{FIREBASE_BASE}/{key}.json'
        payload = json.dumps({'w': w, 'l': l, 'name': name}).encode('utf-8')
        req = urllib.request.Request(url, data=payload, method='PUT',
                                      headers={'Content-Type': 'application/json'})
        try:
            with urllib.request.urlopen(req, timeout=15) as r:
                print(f'  ✓ {name}: {w}-{l}  (HTTP {r.status})')
                written += 1
        except Exception as e:
            print(f'  WRITE ERROR {name}: {e}')

    print(f'\nDone — {written} written, {skipped} skipped (0-0)')
    if written == 0 and len(to_write) == 0:
        print('WARNING: No area teams found in any page')
        sys.exit(1)

if __name__ == '__main__':
    main()
