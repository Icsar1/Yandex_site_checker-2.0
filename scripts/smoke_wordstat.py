"""Smoke test for Wordstat Search API with real credentials."""
import asyncio
import sys
from pathlib import Path

# Ensure backend package is importable
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.config import get_settings
from app.services.wordstat import WordstatClient


async def main():
    settings = get_settings()
    api_key = settings.WORDSTAT_API_KEY.get_secret_value()
    folder_id = settings.WORDSTAT_FOLDER_ID
    
    if not api_key:
        print("ERROR: WORDSTAT_API_KEY is empty in .env")
        sys.exit(1)
    
    print(f"Folder ID: {folder_id}")
    print(f"API Key (first 8 chars): {api_key[:8]}...")
    
    client = WordstatClient(api_key=api_key, folder_id=folder_id)
    
    # Test 1: user_info
    print("\n--- user_info ---")
    try:
        info = await client.user_info()
        print(f"OK: {info}")
    except Exception as e:
        print(f"FAIL: {e}")
    
    # Test 2: top_requests
    print("\n--- top_requests('ремонт квартир') ---")
    try:
        keywords = await client.top_requests("ремонт квартир")
        print(f"OK: got {len(keywords)} keywords")
        for kw in keywords[:5]:
            print(f"  {kw['phrase']} — freq={kw['freq']}")
    except Exception as e:
        print(f"FAIL: {e}")
    
    # Test 3: top_requests with region (Moscow = 213 in Yandex geo)
    print("\n--- top_requests('ремонт квартир', region_ids=[213]) ---")
    try:
        keywords = await client.top_requests("ремонт квартир", region_ids=[213])
        print(f"OK: got {len(keywords)} keywords")
        for kw in keywords[:5]:
            print(f"  {kw['phrase']} — freq={kw['freq']}")
    except Exception as e:
        print(f"FAIL: {e}")
    
    # Test 4: get_regions_tree
    print("\n--- get_regions_tree ---")
    try:
        regions = await client.get_regions_tree()
        print(f"OK: got {len(regions)} regions")
        for r in regions[:5]:
            print(f"  id={r['id']}, name={r['name']}, parent={r['parent_id']}")
    except Exception as e:
        print(f"FAIL: {e}")


if __name__ == "__main__":
    asyncio.run(main())
