import csv
import os
import shutil
from datetime import datetime
import logging

LOG_FILE = "paper_trades.csv"
logger = logging.getLogger("logger")

HEADER = [
    "Date", "Entry Time", "Symbol", "Strategy",
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
        
        if missing_strategy or missing_iv:
            logger.info(f"Migrating CSV. Missing Strategy: {missing_strategy}, Missing IV: {missing_iv}")
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
            else:
                new_row.append("") # padding for other new columns
        new_rows.append(new_row)
        
    # Write back
    with open(LOG_FILE, mode='w', newline='') as file:
        writer = csv.writer(file)
        writer.writerow(HEADER)
        writer.writerows(new_rows)
    logger.info("Migration complete.")

def log_trade_entry(legs, credit, buying_power, profit_target, iv_rank=0.0, strategy_name="20 Delta"):
    init_log_file()
    
    with open(LOG_FILE, mode='a', newline='') as file:
        writer = csv.writer(file)
        writer.writerow([
            datetime.now().date(),
            datetime.now().strftime("%H:%M:%S"),
            "SPX",
            strategy_name,
            legs['short_call']['symbol'],
            legs['long_call']['symbol'],
            legs['short_put']['symbol'],
            legs['long_put']['symbol'],
            credit,
            buying_power,
            profit_target,
            "OPEN",
            "",
            "",
            "0DTE Iron Condor",
            iv_rank
        ])
        
def log_trade_exit(trade_id, exit_time, pl, notes=""):
    # This would require finding the row and updating it.
    pass
