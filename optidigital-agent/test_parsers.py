import asyncio
from parser.freelancehunt import get_new_projects as fh
from parser.kabanchik import get_new_projects as kb

async def main():
    print("=== Freelancehunt ===")
    results = await fh()
    print(f"Знайдено: {len(results)}")
    if results:
        print(results[0])

    print("\n=== Kabanchik ===")
    results2 = await kb()
    print(f"Знайдено: {len(results2)}")
    if results2:
        print(results2[0])

asyncio.run(main())
