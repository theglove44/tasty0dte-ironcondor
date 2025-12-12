import pandas as pd
import monitor
import os

def test_empty_display():
    print("--- Simulating Empty Monitor Output ---")
    
    # Create empty CSV
    df = pd.DataFrame(columns=['Status'])
    df.to_csv("test_empty.csv", index=False)
    
    # We can't call check_open_positions easily because of async session.
    # But we can verify the logic we just added by mocking.
    # Or we can just inspect the code change.
    
    # Actually, we can use the same technique as before: mock refresh_console?
    # No, let's just create a small async wrapper if possible, or reliance on code correctness.
    
    # Let's mock the check_open_positions function's reading of CSV.
    # It reads "paper_trades.csv" by default or passed arg.
    # We will pass test_empty.csv
    
    # We need a dummy session.
    class DummySession:
        pass
    
    # We also need to mock refresh_console to capture output if we want automated test.
    # For now, visual confirmation via stdout capture if we run it.
    
    # Problem: check_open_positions is async.
    import asyncio
    
    # We can perform a slight hack: override refresh_console in monitor module
    original_refresh = monitor.refresh_console
    
    def mock_refresh(lines, reset_cursor=False):
        print("MOCK REFRESH CALLED WITH:")
        for line in lines:
            print(f"  {line}")
            
    monitor.refresh_console = mock_refresh
    
    try:
        asyncio.run(monitor.check_open_positions(DummySession(), "test_empty.csv"))
    except Exception as e:
        print(f"Error (expected if session is used): {e}")

if __name__ == "__main__":
    test_empty_display()
