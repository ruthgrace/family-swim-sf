#!/usr/bin/env python3
"""Compare PDF-parsed data with current API-based data"""

import json

# Read both datasets
with open('/tmp/balboa_schedule_parsed.json', 'r') as f:
    pdf_data = json.load(f)

with open('/var/www/family-swim-sf/map_data/latest_family_swim_data.json', 'r') as f:
    current_data = json.load(f)

balboa_current = current_data["Balboa Pool"]

print("=" * 80)
print("COMPARISON: Balboa Pool Schedule")
print("=" * 80)

weekdays = ["Saturday", "Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]

for day in weekdays:
    pdf_slots = pdf_data.get(day, [])
    current_slots = balboa_current.get(day, [])

    print(f"\n{day}:")
    print("-" * 40)

    print(f"  PDF Data ({len(pdf_slots)} slots):")
    for slot in pdf_slots:
        print(f"    {slot['start']:8} - {slot['end']:8}  {slot['note']}")

    print(f"\n  Current API Data ({len(current_slots)} slots):")
    for slot in current_slots:
        print(f"    {slot['start']:8} - {slot['end']:8}  {slot['note']}")

    # Find differences
    if len(pdf_slots) != len(current_slots):
        print(f"\n  ⚠️  DIFFERENCE: PDF has {len(pdf_slots)} slots, API has {len(current_slots)} slots")

    # Check for missing slots
    pdf_times = set((s['start'], s['end']) for s in pdf_slots)
    current_times = set((s['start'], s['end']) for s in current_slots)

    missing_in_pdf = current_times - pdf_times
    missing_in_api = pdf_times - current_times

    if missing_in_pdf:
        print(f"\n  ❌ Missing in PDF (present in API):")
        for start, end in missing_in_pdf:
            matching = [s for s in current_slots if s['start'] == start and s['end'] == end]
            for slot in matching:
                print(f"    {slot['start']:8} - {slot['end']:8}  {slot['note']}")

    if missing_in_api:
        print(f"\n  ✨ New in PDF (not in API):")
        for start, end in missing_in_api:
            matching = [s for s in pdf_slots if s['start'] == start and s['end'] == end]
            for slot in matching:
                print(f"    {slot['start']:8} - {slot['end']:8}  {slot['note']}")

print("\n" + "=" * 80)
print("SUMMARY")
print("=" * 80)

total_pdf = sum(len(pdf_data.get(day, [])) for day in weekdays)
total_current = sum(len(balboa_current.get(day, [])) for day in weekdays)

print(f"Total slots in PDF data: {total_pdf}")
print(f"Total slots in current API data: {total_current}")
print(f"Difference: {total_pdf - total_current}")
