#!/usr/bin/env python3
"""Compare PDF-parsed data with API-based data for ALL pools"""

import json
from collections import defaultdict

# Read both datasets
with open('/tmp/api_method_data.json', 'r') as f:
    api_data = json.load(f)

with open('/var/www/family-swim-sf/map_data/latest_family_swim_data.json', 'r') as f:
    pdf_data = json.load(f)

weekdays = ["Saturday", "Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]

# Get all pool names from both datasets
all_pools = sorted(set(list(api_data.keys()) + list(pdf_data.keys())))

# Track overall statistics
overall_stats = {
    'pools_compared': 0,
    'total_api_slots': 0,
    'total_pdf_slots': 0,
    'pools_with_differences': 0,
    'pools_identical': 0,
    'pools_only_in_api': [],
    'pools_only_in_pdf': []
}

print("=" * 100)
print("COMPREHENSIVE COMPARISON: ALL POOLS")
print("API Method (Oct 30, 2025) vs PDF Method (Nov 20, 2025)")
print("=" * 100)

for pool in all_pools:
    api_pool_data = api_data.get(pool, {})
    pdf_pool_data = pdf_data.get(pool, {})

    # Check if pool exists in both
    if not api_pool_data:
        overall_stats['pools_only_in_pdf'].append(pool)
        continue
    if not pdf_pool_data:
        overall_stats['pools_only_in_api'].append(pool)
        continue

    overall_stats['pools_compared'] += 1

    # Count total slots for this pool
    pool_api_total = sum(len(api_pool_data.get(day, [])) for day in weekdays)
    pool_pdf_total = sum(len(pdf_pool_data.get(day, [])) for day in weekdays)

    overall_stats['total_api_slots'] += pool_api_total
    overall_stats['total_pdf_slots'] += pool_pdf_total

    # Check if there are any differences
    has_differences = False
    difference_details = []

    for day in weekdays:
        api_slots = api_pool_data.get(day, [])
        pdf_slots = pdf_pool_data.get(day, [])

        if len(api_slots) != len(pdf_slots):
            has_differences = True
            difference_details.append(f"{day}: API={len(api_slots)} slots, PDF={len(pdf_slots)} slots")
        else:
            # Check time slots
            api_times = set((s['start'], s['end']) for s in api_slots)
            pdf_times = set((s['start'], s['end']) for s in pdf_slots)
            if api_times != pdf_times:
                has_differences = True
                difference_details.append(f"{day}: Different time slots")

    if has_differences:
        overall_stats['pools_with_differences'] += 1
    else:
        overall_stats['pools_identical'] += 1

    # Print pool header
    print(f"\n{'=' * 100}")
    print(f"POOL: {pool}")
    print(f"{'=' * 100}")

    if has_differences:
        print(f"⚠️  DIFFERENCES FOUND: {', '.join(difference_details)}")
    else:
        print(f"✅ IDENTICAL (API: {pool_api_total} slots, PDF: {pool_pdf_total} slots)")

    print(f"\nTotal slots: API={pool_api_total}, PDF={pool_pdf_total}")

    # Print day-by-day comparison
    for day in weekdays:
        api_slots = api_pool_data.get(day, [])
        pdf_slots = pdf_pool_data.get(day, [])

        # Skip if both are empty
        if not api_slots and not pdf_slots:
            continue

        print(f"\n  {day}:")
        print(f"  {'-' * 80}")

        print(f"    API Data ({len(api_slots)} slots):")
        if api_slots:
            for slot in api_slots:
                print(f"      {slot['start']:8} - {slot['end']:8}  {slot['note']}")
        else:
            print(f"      (no slots)")

        print(f"\n    PDF Data ({len(pdf_slots)} slots):")
        if pdf_slots:
            for slot in pdf_slots:
                print(f"      {slot['start']:8} - {slot['end']:8}  {slot['note']}")
        else:
            print(f"      (no slots)")

        # Find differences
        if len(api_slots) != len(pdf_slots):
            print(f"\n    ⚠️  DIFFERENCE: API has {len(api_slots)} slots, PDF has {len(pdf_slots)} slots")

        # Check for missing slots
        api_times = set((s['start'], s['end']) for s in api_slots)
        pdf_times = set((s['start'], s['end']) for s in pdf_slots)

        missing_in_pdf = api_times - pdf_times
        missing_in_api = pdf_times - api_times

        if missing_in_pdf:
            print(f"\n    ❌ Missing in PDF (present in API):")
            for start, end in missing_in_pdf:
                matching = [s for s in api_slots if s['start'] == start and s['end'] == end]
                for slot in matching:
                    print(f"      {slot['start']:8} - {slot['end']:8}  {slot['note']}")

        if missing_in_api:
            print(f"\n    ✨ New in PDF (not in API):")
            for start, end in missing_in_api:
                matching = [s for s in pdf_slots if s['start'] == start and s['end'] == end]
                for slot in matching:
                    print(f"      {slot['start']:8} - {slot['end']:8}  {slot['note']}")

# Print overall summary
print(f"\n{'=' * 100}")
print("OVERALL SUMMARY")
print(f"{'=' * 100}")
print(f"\nPools compared: {overall_stats['pools_compared']}")
print(f"Pools identical: {overall_stats['pools_identical']}")
print(f"Pools with differences: {overall_stats['pools_with_differences']}")

if overall_stats['pools_only_in_api']:
    print(f"\nPools only in API data: {', '.join(overall_stats['pools_only_in_api'])}")
if overall_stats['pools_only_in_pdf']:
    print(f"Pools only in PDF data: {', '.join(overall_stats['pools_only_in_pdf'])}")

print(f"\nTotal swim slots:")
print(f"  API method:  {overall_stats['total_api_slots']} slots")
print(f"  PDF method:  {overall_stats['total_pdf_slots']} slots")
print(f"  Difference:  {overall_stats['total_pdf_slots'] - overall_stats['total_api_slots']:+d} slots")

if overall_stats['total_pdf_slots'] > overall_stats['total_api_slots']:
    print(f"\n✨ PDF method found {overall_stats['total_pdf_slots'] - overall_stats['total_api_slots']} MORE swim slots!")
elif overall_stats['total_pdf_slots'] < overall_stats['total_api_slots']:
    print(f"\n⚠️  PDF method found {overall_stats['total_api_slots'] - overall_stats['total_pdf_slots']} FEWER swim slots")
else:
    print(f"\n✅ Both methods found the same number of slots")

print(f"\n{'=' * 100}\n")
