"""Load test: 25 concurrent requests against Pipeline API."""

import asyncio
import httpx


async def send_request(client: httpx.AsyncClient, request_id: int) -> dict:
    """Send a single chat completion request."""
    try:
        response = await client.post(
            "http://localhost:9099/v1/chat/completions",
            headers={"Authorization": "Bearer portal-pipeline"},
            json={
                "model": "auto",
                "messages": [{"role": "user", "content": "Say 'ok'"}],
                "stream": False,
            },
            timeout=30.0,
        )
        return {
            "id": request_id,
            "status": response.status_code,
            "ok": response.status_code in (200, 503),  # 503 is valid (no backends)
        }
    except Exception as e:
        return {"id": request_id, "status": "error", "error": str(e)}


async def main():
    """Run 25 concurrent requests."""
    print("Starting load test: 25 concurrent requests...")

    async with httpx.AsyncClient() as client:
        tasks = [send_request(client, i) for i in range(25)]
        results = await asyncio.gather(*tasks)

    # Analyze results
    successes = sum(1 for r in results if r.get("ok"))
    errors = [r for r in results if not r.get("ok")]

    print(f"\nResults:")
    print(f"  Total requests: 25")
    print(f"  Successful (200/503): {successes}")
    print(f"  Errors: {len(errors)}")

    if errors:
        print(f"\nErrors:")
        for e in errors[:5]:
            print(f"  Request {e['id']}: {e.get('status')} - {e.get('error', 'unknown')}")

    # Check for any connection errors (not 503 which is expected without Ollama)
    unexpected = [r for r in results if r.get("status") not in (200, 503, "error")]
    if unexpected:
        print(f"\nWARNING: Unexpected status codes: {set(r['status'] for r in unexpected)}")
    else:
        print("\nPASS: All requests handled correctly (200 or 503)")

    return len(errors) == 0


if __name__ == "__main__":
    success = asyncio.run(main())
    exit(0 if success else 1)