# Claude Code Notes

## Testing Individual Pools

Pool facility URLs are stored in `map_data/public_pools.json`. Example:

```python
import datetime
from zoneinfo import ZoneInfo
from pdf_parser import get_pool_schedule_from_pdf

# Get the URL from map_data/public_pools.json
# e.g., "https://sfrecpark.org/facilities/facility/details/Rossi-Pool-219"

result = get_pool_schedule_from_pdf(
    pool_name='Rossi Pool',
    facility_url='https://sfrecpark.org/facilities/facility/details/Rossi-Pool-219',
    current_date=datetime.datetime.now(tz=ZoneInfo('America/Los_Angeles')),
    pools_list=['Rossi Pool'],
    force_refresh=True
)
```

## Pool URLs (from public_pools.json)

- Balboa Pool: `https://sfrecpark.org/facilities/facility/details/Balboa-Pool-191`
- Coffman Pool: `https://sfrecpark.org/facilities/facility/details/Coffman-Pool-195`
- Garfield Pool: `https://sfrecpark.org/facilities/facility/details/Garfield-Pool-200`
- Hamilton Pool: `https://sfrecpark.org/facilities/facility/details/Hamilton-Pool-202`
- Martin Luther King Jr Pool: `https://sfrecpark.org/facilities/facility/details/Martin-Luther-King-Jr-Pool-208`
- Mission Community Pool: `https://sfrecpark.org/facilities/facility/details/Mission-Pool-211`
- North Beach Pool: `https://sfrecpark.org/facilities/facility/details/North-Beach-Pool-214`
- Rossi Pool: `https://sfrecpark.org/facilities/facility/details/Rossi-Pool-219`
- Sava Pool: `https://sfrecpark.org/facilities/facility/details/Sava-Pool-221`

## Running the Full Parser

```bash
source venv/bin/activate
python3.12 main.py              # Normal run (uses cache)
python3.12 main.py --force-refresh  # Force re-parse all PDFs
```

## Key Files

- `main.py` - Main entry point, orchestrates everything
- `pdf_parser.py` - PDF extraction logic (uses Claude API for vision)
- `map_data/public_pools.json` - Pool locations and facility URLs
- `map_data/latest_family_swim_data.json` - Current extracted schedule data
