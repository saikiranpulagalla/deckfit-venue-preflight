"""Measure the real deployed planner via independent, authenticated demo sessions.

No slide text is submitted to third-party AI; the same project-owned demo runs
through the application and the server's bounded planning boundary.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import statistics
from urllib.parse import urlsplit

from live_deployment_check import _request, _expect, _json


def run(base_url: str, release_id: str, count: int) -> dict:
    health = _request(base_url, '/health', timeout=20)
    _expect(health, 200, 'probe health')
    if _json(health).get('release_id') != release_id:
        raise RuntimeError('probe release mismatch')
    rows = []
    for i in range(count):
        sid = token = None
        try:
            res = _request(base_url, '/api/demo', method='POST', timeout=20)
            _expect(res, 200, 'probe demo')
            created = _json(res)
            sid, token = created['session_id'], created['session_token']
            res = _request(base_url, f'/api/sessions/{sid}/analyze', method='POST', token=token,
                           json_body={'venue': {'active_image_height_m': 1.8,
                           'farthest_viewer_distance_m': 10.8, 'measurement_basis': 'MEASURED'}}, timeout=75)
            _expect(res, 200, 'probe analyze')
            if _json(res).get('state') != 'ANALYZED':
                raise RuntimeError('probe analysis did not reach ANALYZED')
            res = _request(base_url, f'/api/sessions/{sid}/plan', method='POST', token=token,
                           json_body={'constraints': {'max_mutations': 2,
                           'max_scale_factor': 1.6, 'minimum_target_coverage': 0.9,
                           'protect_titles': True, 'semantic_rewrite': False}}, timeout=75)
            _expect(res, 200, 'probe plan')
            planned = _json(res)
            decision = planned.get('decision') or {}
            planner = str(decision.get('planner_used') or '')
            fallback = decision.get('fallback_used')
            ids = decision.get('selected_candidate_ids') or []
            if (planned.get('state') != 'AWAITING_APPROVAL' or not ids
                    or fallback is not False or not planner.startswith('gemini-')):
                raise RuntimeError('public Gemini planning did not complete without fallback')
            rows.append({'run': i + 1, 'selected_candidate_ids': ids,
                         'planner_used': planner, 'fallback_used': fallback,
                         'latency_ms': res.elapsed_ms})
        finally:
            if sid and token:
                deleted = _request(base_url, f'/api/sessions/{sid}', method='DELETE', token=token, timeout=25)
                _expect(deleted, 200, 'probe delete')
    modes = Counter(tuple(row['selected_candidate_ids']) for row in rows)
    models = {row['planner_used'] for row in rows}
    if len(models) != 1:
        raise RuntimeError('Gemini model identity changed during public probe')
    return {'runs': count, 'origin': base_url.rstrip('/'), 'release_id': release_id,
            'proof_mode': 'public_fresh_sessions', 'model': next(iter(models)),
            'fallback_count': 0, 'rows': rows,
            'selection_counts': [{'candidate_ids': list(ids), 'count': n}
                                 for ids, n in modes.most_common()],
            'median_latency_ms': statistics.median(row['latency_ms'] for row in rows)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--base-url', required=True)
    parser.add_argument('--expected-release-id', required=True)
    parser.add_argument('--runs', type=int, default=5)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    parsed = urlsplit(args.base_url)
    if (parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password
            or parsed.hostname.lower() in {'localhost', '127.0.0.1', '::1'}
            or parsed.hostname.lower().endswith(('.local', '.localhost'))
            or parsed.path.strip('/') or parsed.query or parsed.fragment):
        parser.error('public Gemini stability evidence requires a clean public HTTPS origin')
    if args.runs < 5 or args.runs > 20:
        parser.error('runs must be between 5 and 20')
    result = run(args.base_url, args.expected_release_id, args.runs)
    output = json.dumps(result, indent=2) + '\n'
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output, encoding='utf8')
    print(output, end='')


if __name__ == '__main__':
    main()
