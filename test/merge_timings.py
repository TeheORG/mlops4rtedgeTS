#!/usr/bin/env python3
"""
Merges timing data from test/timing/*.csv into variants_parameters.txt
Prepends script duration to each make variant? line.
"""

import csv
import re
from pathlib import Path
from sys import argv

def load_timings(csv_path):
    """Load script timings from CSV: {(phase, variant, target): duration_s}"""
    timings = {}
    with open(csv_path, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            key = (row['phase'], row['variant'], row['target'])
            timings[key] = int(row['duration_s'])
    return timings

def extract_variant_and_phase(line):
    """Extract VARIANT=vXYZ and infer phase from 'make variant?' """
    match = re.search(r'VARIANT=(\w+)', line)
    if not match:
        return None, None
    
    variant = match.group(1)
    # Infer phase from variant name: v100->f01, v200->f02, etc.
    phase_num = variant[1:2]  # Second char
    phase = f"f0{phase_num}"
    return phase, variant

def lookup_script_duration(phase, variant, timings):
    """Find script duration in timings dict (exact match only)"""
    key = (phase, variant, f'script{phase[2]}')
    return timings.get(key)

def merge_timings(variants_txt, timings_csv=None, timings_dict=None):
    """Add timing durations to variants_parameters.txt"""
    if timings_dict is None:
        timings_dict = load_timings(timings_csv)
    
    output_txt = variants_txt
    lines = []
    
    with open(variants_txt, 'r') as f:
        for line_text in f:
            line_text = line_text.rstrip('\n')
            # Strip existing timing prefix if re-running
            line_text = re.sub(r'^\[[\d?]+s\] ', '', line_text)
            if not line_text.strip() or not line_text.startswith('make'):
                lines.append(line_text)
                continue
            
            phase, variant = extract_variant_and_phase(line_text)
            if not phase or not variant:
                lines.append(line_text)
                continue
            
            duration = lookup_script_duration(phase, variant, timings_dict)
            if duration is not None:
                new_line = f"[{duration}s] {line_text}"
            else:
                new_line = f"[?s] {line_text}"
            
            lines.append(new_line)
    
    with open(output_txt, 'w') as f:
        f.write('\n'.join(lines))
    
    filled = sum(1 for l in lines if l.startswith('[') and not l.startswith('[?'))
    pending = sum(1 for l in lines if l.startswith('[?s]'))
    print(f"Updated: {output_txt}  ({filled} filled, {pending} pending)")

if __name__ == '__main__':
    script_dir = Path(__file__).parent
    variants_txt = script_dir / 'variants_parameters.txt'

    # Merge all CSVs from timing-linux2 (exact variant names, f01-f06)
    # plus the largest CSV from timing/ for f07/f08 when available
    timing_dirs = [
        script_dir / 'timing-linux2',
        script_dir / 'timing',
    ]

    timings = {}
    for tdir in timing_dirs:
        if not tdir.exists():
            continue
        for csv_path in sorted(tdir.glob('run*.csv')):
            loaded = load_timings(csv_path)
            timings.update(loaded)
            print(f"Loaded {len(loaded)} entries from {tdir.name}/{csv_path.name}")

    print(f"Total timing entries: {len(timings)}")
    merge_timings(variants_txt, timings_dict=timings)
