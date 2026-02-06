import csv
import os
import shutil
from datetime import datetime
import logging

LOG_FILE = "paper_trades.csv"
logger = logging.getLogger("logger")

HEADER = [
    "Date", "Entry Time", "Symbol", "Strategy", "StrategyId",
    "Short Call", "Long Call", "Short Put", "Long Put", 
    "Credit Collected", "Buying Power", "Profit Target", 
    "Status", "Exit Time", "Exit P/L", "Notes", "IV Rank"
]

def init_log_file():
    """
    Initializes the log file. 
    If it exists but doesn't have the new 'Strategy' or 'IV Rank' columns, it migrates the file.
    """
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, mode='w', newline='') as file:
            writer = csv.writer(file)
            writer.writerow(HEADER)
    else:
        # Check header
        with open(LOG_FILE, mode='r', newline='') as file:
            reader = csv.reader(file)
            try:
                headers = next(reader)
            except StopIteration:
                headers = []
        
        # Check for missing columns
        missing_strategy = "Strategy" not in headers
        missing_iv = "IV Rank" not in headers
        missing_id = "StrategyId" not in headers
        
        if missing_strategy or missing_iv or missing_id:
            logger.info(f"Migrating CSV. Missing Strat: {missing_strategy}, IV: {missing_iv}, ID: {missing_id}")
            migrate_csv(headers)

def migrate_csv(old_headers):
    # Read all data
    with open(LOG_FILE, mode='r', newline='') as file:
        reader = csv.reader(file)
        # Skip header since we read it above, or just read all and pop 0
        all_lines = list(reader)
    
    if not all_lines:
        return

    # all_lines[0] is the old header
    data_rows = all_lines[1:]
    
    new_rows = []
    
    # We need to map old data to new structure.
    # To keep it simple, we'll rebuild each row based on the old header.
    
    for row in data_rows:
        row_dict = dict(zip(old_headers, row))
        new_row = []
        for col in HEADER:
            if col in row_dict:
                new_row.append(row_dict[col])
            elif col == "Strategy":
                # Default existing trades to "20 Delta" since that was the only strategy before
                new_row.append("20 Delta") 
            elif col == "StrategyId":
                # Generate ID based on Strategy and Time
                strat = row_dict.get("Strategy", "20 Delta")
                if "Strategy" not in row_dict:
                     # If we are migrating from very old format where Strategy didn't exist, it was 20 Delta
                     strat = "20 Delta"
                
                # Parse Time
                time_str = row_dict.get("Entry Time", "00:00:00")
                try:
                    # HH:MM:SS
                    t_parts = time_str.split(':')
                    hm = f"{t_parts[0]}{t_parts[1]}" # HHMM
                except:
                    hm = "0000"

                # Map Strategy Name to Short Code
                if "20 Delta" in strat:
                    s_code = "IC-20D"
                elif "30 Delta" in strat:
                    s_code = "IC-30D"
                elif "Iron Fly V1" in strat:
                    s_code = "IF-V1"
                elif "Iron Fly V2" in strat:
                    s_code = "IF-V2"
                elif "Iron Fly V3" in strat:
                    s_code = "IF-V3"
                elif "Iron Fly V4" in strat:
                    s_code = "IF-V4"
                else:
                    s_code = "UNK"
                
                new_row.append(f"{s_code}-{hm}")
            else:
                new_row.append("") # padding for other new columns
        new_rows.append(new_row)
        
    # Write back
    with open(LOG_FILE, mode='w', newline='') as file:
        writer = csv.writer(file)
        writer.writerow(HEADER)
        writer.writerows(new_rows)
    logger.info("Migration complete.")

def log_trade_entry(legs, credit, buying_power, profit_target, iv_rank=0.0, strategy_name="20 Delta", strategy_id=""):
    init_log_file()

    with open(LOG_FILE, mode='a', newline='') as file:
        ivr_val = float(iv_rank)
        # Normalize if it looks like a ratio (e.g. 0.15 -> 15.0)
        # But be careful if IVR is actually < 1.0 (e.g. 0.5). 
        # Usually IVR is 0-100. If it's consistently < 1 across the board we assume ratio.
        # Ideally rely on knowledge of source. Tasty API usually gives 0-100 string or decimal.
        # But previous data showed 0.126... which implies ratio.
        # Let's assume if it is <= 1.0 and > 0, it is a ratio.
        # However, IVR can naturally be 0.5 (percentile). 
        # A safer bet might be: if we see values > 1 in the wild, the source is 0-100.
        # If the source is `metrics[0].implied_volatility_index_rank`, Tasty documentation says it's 0-100? 
        # Looking at previous CSV data: "13.54%" and "0.126410256". 
        # 0.126... is clearly 12.6%.
        if 0 < ivr_val <= 1.0:
             ivr_val *= 100.0
             
        writer = csv.writer(file)
        writer.writerow([
            datetime.now().date(),
            datetime.now().strftime("%H:%M:%S"),
            "SPX",
            strategy_name,
            strategy_id,
            legs['short_call']['symbol'],
            legs['long_call']['symbol'],
            legs['short_put']['symbol'],
            legs['long_put']['symbol'],
            f"{float(credit):.2f}",
            f"{float(buying_power):.2f}",
            f"{float(profit_target):.2f}",
            "OPEN",
            "",
            "",
            f"0DTE {strategy_name}",
            f"{ivr_val:.2f}"
        ])
