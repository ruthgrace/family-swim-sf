#!/usr/bin/env python3
"""
Simple script to get raw schedule for Garfield Pool
"""
import json
from datetime import datetime
from pdf_parser import (
    get_facility_documents,
    select_schedule_pdf,
    download_pdf,
    extract_raw_schedule
)

# Configuration
POOL_NAME = "Garfield Pool"
FACILITY_URL = "https://sfrecpark.org/Facilities/Facility/Details/Garfield-Pool-214"
CURRENT_DATE = datetime.now()
POOLS_LIST = ["Garfield Pool"]  # Simple list for this test
PDF_CACHE_DIR = "/tmp"

def main():
    print(f"Getting raw schedule for {POOL_NAME}")
    print(f"Date: {CURRENT_DATE.strftime('%Y-%m-%d')}")
    print("="*60)

    # Step 1: Get documents
    print("\n1. Fetching documents from facility page...")
    documents = get_facility_documents(FACILITY_URL)
    if not documents:
        print("ERROR: No documents found")
        return
    print(f"   Found {len(documents)} documents")

    # Step 2: Select PDF
    print("\n2. Selecting schedule PDF...")
    selected_pdf = select_schedule_pdf(documents, POOL_NAME, CURRENT_DATE, POOLS_LIST)
    if not selected_pdf:
        print("ERROR: No schedule PDF found")
        return
    print(f"   Selected: {selected_pdf['name']}")

    # Step 3: Download PDF
    print("\n3. Downloading PDF...")
    pdf_path = f"{PDF_CACHE_DIR}/{POOL_NAME.replace(' ', '_')}_schedule.pdf"
    if not download_pdf(selected_pdf['url'], pdf_path):
        print("ERROR: Failed to download PDF")
        return
    print(f"   Downloaded to: {pdf_path}")

    # Step 4: Extract raw schedule
    print("\n4. Extracting raw schedule from PDF...")
    raw_schedule = extract_raw_schedule(pdf_path, POOL_NAME)
    if not raw_schedule:
        print("ERROR: Failed to extract raw schedule")
        return

    print("\n" + "="*60)
    print("RAW SCHEDULE FOR GARFIELD POOL")
    print("="*60)
    print(json.dumps(raw_schedule, indent=2))

    # Save to file
    output_file = f"{PDF_CACHE_DIR}/{POOL_NAME.replace(' ', '_')}_raw_schedule.json"
    with open(output_file, 'w') as f:
        json.dump(raw_schedule, f, indent=2)
    print(f"\nSaved to: {output_file}")

if __name__ == "__main__":
    main()
