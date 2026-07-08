#!/usr/bin/env python3

import re
import sys

RANKFILE_RE = re.compile(r'rank\s+(\d+)=\S+\s+slot=(\d+)')
BINDING_RE  = re.compile(r'MCW rank\s+(\d+)\s+bound to[^[]+\[core\s+(\d+)\[')

def parse_rankfile_line(line):
    m = RANKFILE_RE.search(line)
    return (int(m.group(1)), int(m.group(2))) if m else None

def parse_binding_line(line):
    m = BINDING_RE.search(line)
    return (int(m.group(1)), int(m.group(2))) if m else None

def parse_out(filename):
    """Returns list of (config_line, rf1_dict, rf2_dict)."""
    segments = []
    with open(filename) as f:
        lines = [l.rstrip('\n') for l in f]

    i = 0
    while i < len(lines):
        if not lines[i].startswith('# RUN:'):
            i += 1
            continue
        config = lines[i]
        rf1, rf2, current = {}, {}, None
        i += 1
        while i < len(lines) and not lines[i].startswith('# RUN:'):
            l = lines[i].strip()
            if l == '## RANKFILE 1:':
                current = rf1
            elif l == '## RANKFILE 2:':
                current = rf2
            elif l.startswith('##'):
                current = None
            elif current is not None:
                parsed = parse_rankfile_line(l)
                if parsed:
                    current[parsed[0]] = parsed[1]
            i += 1
        segments.append((config, rf1, rf2))
    return segments

def parse_err(filename):
    """Returns list of (config_line, bench1_runs, bench2_runs).

    bench1_runs and bench2_runs are lists of dicts (one per ### mpirun N),
    each mapping rank -> core.
    """
    segments = []
    with open(filename) as f:
        lines = [l.rstrip('\n') for l in f]

    i = 0
    while i < len(lines):
        if not lines[i].startswith('# RUN:'):
            i += 1
            continue
        config = lines[i]
        bench1_runs, bench2_runs = [], []
        current_runs = None
        current_dict = None
        i += 1
        while i < len(lines) and not lines[i].startswith('# RUN:'):
            l = lines[i].strip()
            if l == '## BENCH 1:':
                current_runs = bench1_runs
                current_dict = None
            elif l == '## BENCH 2:':
                current_runs = bench2_runs
                current_dict = None
            elif l.startswith('### mpirun') and current_runs is not None:
                current_dict = {}
                current_runs.append(current_dict)
            elif current_dict is not None:
                parsed = parse_binding_line(lines[i])
                if parsed:
                    current_dict[parsed[0]] = parsed[1]
            i += 1
        segments.append((config, bench1_runs, bench2_runs))
    return segments

def compare(rf, d):
    if rf == d:
        return True, []
    mismatches = []
    for rank in sorted(set(rf) | set(d)):
        r, b = rf.get(rank, '?'), d.get(rank, '?')
        if r != b:
            mismatches.append(f"      rank {rank:3d}: rankfile={r}, binding={b}")
    return False, mismatches

def check_runs(label, rf, runs):
    all_ok = True
    for idx, d in enumerate(runs, 1):
        ok, mismatches = compare(rf, d)
        if not ok:
            all_ok = False
            print(f"  [{label} run {idx}] NO MATCH !!!")
            print('\n'.join(mismatches))
    return all_ok

def main():
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <jobid>")
        sys.exit(1)

    jobid = sys.argv[1]
    out_segs = parse_out(f"{jobid}.out")
    err_segs = parse_err(f"{jobid}.err")

    if len(out_segs) != len(err_segs):
        print(f"WARNING: {len(out_segs)} segments in .out but {len(err_segs)} in .err")

    for (out_cfg, rf1, rf2), (_, bench1_runs, bench2_runs) in zip(out_segs, err_segs):
        ok1 = check_runs("BENCH 1", rf1, bench1_runs)
        ok2 = check_runs("BENCH 2", rf2, bench2_runs)
        status = "MATCH" if (ok1 and ok2) else "NO MATCH !!!"
        print(f"{out_cfg}: {status} (BENCH 1: {len(bench1_runs)} runs, BENCH 2: {len(bench2_runs)} runs)")
        cores1 = ' '.join(str(rf1[r]) for r in sorted(rf1))
        cores2 = ' '.join(str(rf2[r]) for r in sorted(rf2))
        print(f"  RF1: {cores1}")
        print(f"  RF2: {cores2}")

if __name__ == '__main__':
    main()
