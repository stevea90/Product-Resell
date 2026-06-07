"""Check what HotUKDeals RSS is actually returning."""
import asyncio
import httpx

async def main():
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-GB,en;q=0.9",
    }
    url = "https://www.hotukdeals.com/rss/deals?filter=all"
    async with httpx.AsyncClient(headers=headers, follow_redirects=True, http2=True) as client:
        r = await client.get(url)
        print(f"Status:       {r.status_code}")
        print(f"Content-Type: {r.headers.get('content-type', 'unknown')}")
        print(f"CF-Mitigated: {r.headers.get('cf-mitigated', 'not present')}")
        print(f"First 300:    {repr(r.text[:300])}")

asyncio.run(main())
