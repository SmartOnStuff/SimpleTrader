import os
import pandas as pd
import datetime

# --- Configuration ---
EXTRACTED_FOLDER = "data/extracted"      # Folder where extracted CSV files are stored
OUTPUT_FOLDER = "data/logs"              # Folder to write trade logs to

# Trading settings
BASE_TRADE_PERCENTAGE = 0.2   # i.e. 20%
TRIGGER_PERCENTAGE = 0.03     # 3% threshold to trigger trade
MAX_TRADE_USD = 50.0          # Maximum amount per trade in USD equivalent
MIN_TRADE_USD = 10.0          # Minimum amount per trade in USD equivalent
MULTIPLIER = 1.1              # Multiplier for consecutive same-direction trades

# We assume USDC = 1 USD exactly.
# For each month, we start with an initial portfolio value of 1000 USD,
# which will be rebalanced to a 50/50 ETH/USDC mix at the opening price.
INITIAL_USDC_BALANCE = 1000.0

# --- Ensure the output directory exists ---
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

def simulate_trading(df):
    """
    Given a dataframe of kline data with known headers, simulate trading.
    Returns a list of dictionaries, each representing a trade log entry.
    
    The simulation initializes the portfolio on the first data point so that:
      - 50% of the value remains in USDC.
      - 50% is converted into ETH using the opening (first close) price.
    """
    # Simulation state (per file/month)
    eth_balance = 0.0
    usdc_balance = INITIAL_USDC_BALANCE
    base_price = None
    consecutive_count = 0
    last_action = None
    trade_id = 1
    trade_logs = []

    # Iterate over each row of the CSV file (chronologically)
    for idx, row in df.iterrows():
        try:
            # Get the price from the "close_price" field (as float)
            price = float(row["close_price"])
        except Exception as e:
            continue  # Skip rows that cannot be parsed

        # Convert timestamp (in ms) to date/time strings in UTC
        time_ms = int(row["timestamp_open"])
        dt = datetime.datetime.utcfromtimestamp(time_ms / 1000)
        date_str = dt.strftime("%Y%m%d")
        time_str = dt.strftime("%H%M%S")

        # On first encounter, initialize the portfolio to 50/50:
        if base_price is None:
            base_price = price
            half_usd = INITIAL_USDC_BALANCE / 2.0
            usdc_balance = half_usd    # Keep half in USDC
            eth_balance = half_usd / price  # Buy ETH with the other half
            # Optionally, you might log a message here that the entry position is 50/50.
            continue  # No trade executed on the very first data point

        # Calculate percentage change from the current base price
        price_change = (price - base_price) / base_price

        action = None
        trade_usd = 0.0
        quantity = 0.0

        # --- Determine Trade Action ---
        if price_change >= TRIGGER_PERCENTAGE:
            # SELL signal: Price has increased by at least 3%
            action = "SELL"
            if last_action == "SELL":
                consecutive_count += 1
            else:
                consecutive_count = 0  # Reset the multiplier on direction change

            effective_trade_percentage = BASE_TRADE_PERCENTAGE * (MULTIPLIER ** consecutive_count)
            # For a SELL, compute potential USD from the ETH balance
            potential_usd = eth_balance * price * effective_trade_percentage
            if potential_usd < MIN_TRADE_USD:
                base_price = price
                last_action = "SELL"
                continue  # Skip trade if below minimum trade size

            # Cap trade USD value at MAX_TRADE_USD
            trade_usd = min(potential_usd, MAX_TRADE_USD)
            quantity = trade_usd / price

            # Ensure we don’t sell more ETH than held
            if quantity > eth_balance:
                quantity = eth_balance
                trade_usd = quantity * price

            # Execute SELL: add USDC, subtract ETH
            usdc_balance += trade_usd
            eth_balance -= quantity

        elif price_change <= -TRIGGER_PERCENTAGE:
            # BUY signal: Price has fallen by at least 3%
            action = "BUY"
            if last_action == "BUY":
                consecutive_count += 1
            else:
                consecutive_count = 0  # Reset multiplier on direction change

            effective_trade_percentage = BASE_TRADE_PERCENTAGE * (MULTIPLIER ** consecutive_count)
            # For a BUY, compute potential USD from USDC balance
            potential_usd = usdc_balance * effective_trade_percentage
            if potential_usd < MIN_TRADE_USD:
                base_price = price
                last_action = "BUY"
                continue  # Skip trade if below minimum trade size

            trade_usd = min(potential_usd, MAX_TRADE_USD)
            quantity = trade_usd / price  # Quantity in ETH to buy
            
            # Ensure we don't overspend USDC
            if trade_usd > usdc_balance:
                trade_usd = usdc_balance
                quantity = trade_usd / price

            # Execute BUY: subtract USDC, add ETH
            usdc_balance -= trade_usd
            eth_balance += quantity

        else:
            # No trade trigger: continue to next row
            continue

        # After a trade, update the reference base price and log the trade
        base_price = price
        last_action = action

        # Calculate portfolio values
        eth_usd_value = eth_balance * price
        usdc_usd_value = usdc_balance  # USDC is pegged to 1 USD
        total_balance = eth_usd_value + usdc_usd_value

        # Assemble a trade log entry (ID is a zero-padded sequential number)
        log_entry = {
            "ID": f"{trade_id:06d}",
            "Date": date_str,
            "Time": time_str,
            "Action": action,
            "Price": round(price, 8),
            "Quantity": round(quantity, 8),
            "ETH_Balance": round(eth_balance, 8),
            "USDC_Balance": round(usdc_balance, 8),
            "ETH_USD_Price": round(price, 8),
            "USDC_USD_Price": 1.0,
            "ETH_USD_Value": round(eth_usd_value, 8),
            "USDC_USD_Value": round(usdc_usd_value, 8),
            "Trade_USD_Value": round(trade_usd, 8),
            "Total_Balance_USD": round(total_balance, 8),
            "Consecutive_Count": consecutive_count,
            "Actual_Trade_Percentage": round(effective_trade_percentage, 8)
        }
        trade_logs.append(log_entry)
        trade_id += 1

    return trade_logs

# --- Main Loop ---
# Process each extracted CSV file in the folder (each represents one month)
for file in sorted(os.listdir(EXTRACTED_FOLDER)):
    if not file.endswith(".csv"):
        continue

    file_path = os.path.join(EXTRACTED_FOLDER, file)
    # Read the CSV assuming no header rows (Binance kline format)
    df = pd.read_csv(file_path, header=None)
    df.columns = [
        "timestamp_open", "open_price", "high_price", "low_price",
        "close_price", "volume", "timestamp_close", "quote_asset_volume",
        "number_of_trades", "taker_buy_base_asset_volume",
        "taker_buy_quote_asset_volume", "ignore"
    ]

    # Run simulated trading on this month's data
    trade_logs = simulate_trading(df)
    
    # Write the log file (one per month)
    log_df = pd.DataFrame(trade_logs)
    out_filename = file.replace('.csv', '_log.csv')
    out_path = os.path.join(OUTPUT_FOLDER, out_filename)
    log_df.to_csv(out_path, index=False)
    print(f"Trade log for {file} saved to {out_path}")

print("✅ Simulation complete. Trade logs generated for each month.")
