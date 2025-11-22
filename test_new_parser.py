#!/usr/bin/env python3
"""
Test the new simplified PDF parser on Garfield Pool
"""

import json
from pdf_parser import extract_raw_schedule, filter_family_swim, extract_lap_swim_from_raw, extract_all_activities_from_raw, add_secret_swim_times

# Test with the Garfield Pool PDF we downloaded earlier
pdf_path = "/tmp/garfield_fall_2025.pdf"
pool_name = "Garfield Pool"

print("="*60)
print("Testing New Simplified PDF Parser")
print("="*60)

# PASS 1: Extract raw schedule
print("\nPASS 1: Extracting raw schedule from PDF...")
raw_schedule = extract_raw_schedule(pdf_path, pool_name)

if raw_schedule:
    print(f"✓ Raw schedule extracted successfully")
    print(f"  Days with activities: {[day for day, slots in raw_schedule.items() if slots]}")

    # Save for inspection
    with open('/tmp/garfield_raw_schedule.json', 'w') as f:
        json.dump(raw_schedule, f, indent=2)
    print(f"  Saved to /tmp/garfield_raw_schedule.json")

    # PASS 2: Filter for family swim
    print("\nPASS 2: Filtering for family/parent-child swim...")
    family_swim_data = filter_family_swim(raw_schedule, pool_name)

    if family_swim_data:
        print(f"✓ Family swim data filtered successfully")
        for day, slots in family_swim_data.items():
            if slots:
                print(f"  {day}: {len(slots)} slot(s)")
                for slot in slots:
                    print(f"    - {slot['start']} - {slot['end']}: {slot['note']}")

        # PASS 3: Extract lap swim (Python)
        print("\nPASS 3: Extracting lap swim from raw schedule (Python)...")
        lap_swim_data = extract_lap_swim_from_raw(raw_schedule, pool_name)
        total_lap_slots = sum(len(slots) for slots in lap_swim_data.values())
        print(f"✓ Found {total_lap_slots} lap swim slots")
        for day, slots in lap_swim_data.items():
            if slots:
                print(f"  {day}: {len(slots)} slot(s)")
                for slot in slots:
                    print(f"    - {slot['start']} - {slot['end']}")

        # PASS 4: Extract all activities (Python)
        print("\nPASS 4: Extracting all activities for conflict detection (Python)...")
        all_activities_data = extract_all_activities_from_raw(raw_schedule)
        total_activity_slots = sum(len(slots) for slots in all_activities_data.values())
        print(f"✓ Found {total_activity_slots} non-lap activity slots")

        # PASS 5: Calculate secret swims
        print("\nPASS 5: Calculating secret swim times (Python)...")
        combined_data = add_secret_swim_times(family_swim_data, lap_swim_data, pool_name, all_activities_data)

        print(f"\n✓ Final schedule for {pool_name}:")
        for day, slots in combined_data.items():
            if slots:
                print(f"\n{day}:")
                for slot in slots:
                    print(f"  {slot['start']} - {slot['end']}: {slot['note']}")

        # Save final output
        with open('/tmp/garfield_final_schedule.json', 'w') as f:
            json.dump(combined_data, f, indent=2)
        print(f"\nSaved final schedule to /tmp/garfield_final_schedule.json")

        # Validate against known issues
        print("\n" + "="*60)
        print("VALIDATION CHECKS:")
        print("="*60)

        tuesday_7am = any(slot['start'] == '7:00AM' for slot in combined_data.get('Tuesday', []))
        thursday_7am = any(slot['start'] == '7:00AM' for slot in combined_data.get('Thursday', []))

        if tuesday_7am:
            print("❌ FAIL: Tuesday has 7:00AM slot (should NOT exist)")
        else:
            print("✅ PASS: Tuesday does not have 7:00AM slot")

        if thursday_7am:
            print("❌ FAIL: Thursday has 7:00AM slot (should NOT exist)")
        else:
            print("✅ PASS: Thursday does not have 7:00AM slot")

        monday_7am = any(slot['start'] == '7:00AM' for slot in combined_data.get('Monday', []))
        wednesday_7am = any(slot['start'] == '7:00AM' for slot in combined_data.get('Wednesday', []))

        if not monday_7am:
            print("❌ FAIL: Monday missing 7:00AM slot (should exist)")
        else:
            print("✅ PASS: Monday has 7:00AM slot")

        if not wednesday_7am:
            print("❌ FAIL: Wednesday missing 7:00AM slot (should exist)")
        else:
            print("✅ PASS: Wednesday has 7:00AM slot")

        friday_slots = len(combined_data.get('Friday', []))
        if friday_slots > 0:
            print(f"❌ FAIL: Friday has {friday_slots} slot(s) (should be closed)")
        else:
            print("✅ PASS: Friday is closed (no slots)")
    else:
        print("❌ Failed to filter family swim data")
else:
    print("❌ Failed to extract raw schedule")
