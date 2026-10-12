"""Tiny async load test for the redirect hot path.

Usage:
    python scripts/load_test.py --base http://localhost:8000 --code aB3xK9m \
        --total 1000 --concurrency 50
"""

import argparse
import asyncio
import time

import httpx


async def main() -> None:
    parser = argparse.ArgumentParser(description="Load sanity check for GET /{code}")
    parser.add_argument("--base", required=True, help="e.g. http://localhost:8000")
    parser.add_argument("--code", required=True, help="an existing short code")
    parser.add_argument("--total", type=int, default=1000)
    parser.add_argument("--concurrency", type=int, default=50)
    args = parser.parse_args()

    results: list[int] = []
    sem = asyncio.Semaphore(args.concurrency)
    client = httpx.AsyncClient(base_url=args.base, timeout=15.0)

    async def one() -> None:
        async with sem:
            try:
                response = await client.get(f"/{args.code}")
                results.append(response.status_code)
            except Exception as exc:  # noqa: BLE001
                results.append(-1)
                print(f"request error: {exc!r}")

    start = time.perf_counter()
    await asyncio.gather(*(one() for _ in range(args.total)))
    elapsed = time.perf_counter() - start
    await client.aclose()

    ok = results.count(302)
    errors = results.count(-1)
    other = len(results) - ok - errors
    print(f"total={len(results)} ok_302={ok} other_status={other} errors={errors}")
    print(f"elapsed={elapsed:.2f}s rps={len(results) / elapsed:.1f}")
    if errors == 0 and other == 0 and ok == len(results):
        print("RESULT: PASS")
    else:
        print("RESULT: FAIL")


if __name__ == "__main__":
    asyncio.run(main())
