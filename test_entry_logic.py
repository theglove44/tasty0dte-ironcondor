import asyncio
from datetime import time, datetime
import pytz

# Mocking the logic in main.py
target_times = [time(14, 45), time(15, 0), time(15, 30)]

async def mock_execution(name):
    print(f"[{name}] Triggered Trade Entry")

async def check_time(mock_now_time):
    print(f"Checking time: {mock_now_time}")
    for target in target_times:
        if mock_now_time.hour == target.hour and mock_now_time.minute == target.minute:
             print(f"Match found for {target}!")
             await mock_execution(str(target))
             return True
    return False

async def test_logic():
    print("Testing 14:45...")
    if await check_time(time(14, 45)):
        print("PASS")
    else:
        print("FAIL")

    print("\nTesting 15:00...")
    if await check_time(time(15, 0)):
        print("PASS")
    else:
        print("FAIL")

    print("\nTesting 15:30...")
    if await check_time(time(15, 30)):
        print("PASS")
    else:
        print("FAIL")

    print("\nTesting 14:00 (Should fail)...")
    if not await check_time(time(14, 0)):
        print("PASS")
    else:
        print("FAIL")

if __name__ == "__main__":
    asyncio.run(test_logic())
