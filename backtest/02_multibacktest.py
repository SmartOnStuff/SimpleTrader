import os
import pandas as pd
import datetime
import random
import itertools

# === CONFIGURATION ===

EXTRACTED_FOLDER = "data/extracted"  # Each CSV: one month of Binance kline data
SUMMARY_OUTPUT = "data/dynamic_analysis_summary.csv"

# Starting portfolio value and rebalancing (50/50 split)
INITIAL_USDC_BALANCE = 1000.0  # USD value

# Market trend thresholds (applied on monthly open/close prices)
BULLISH_THRESHOLD = 0.1   # +3%: monthly close is at least 3% above open → Bullish
BEARISH_THRESHOLD = -0.1  # -3%: monthly close is at least 3% below open → Bearish
# Otherwise → Sideways

# === DYNAMIC PARAMETER GRID ===
# Define ranges for each trading parameter.
base_trade_percentages = [0.1, 0.15, 0.2, 0.25, 0.3]         # Example: 10%-30%
trigger_percentages    = [0.02, 0.025, 0.03, 0.035, 0.04]       # 2%-4%
max_trade_usd_values   = [750, 500, 250]                           # USD cap per trade
min_trade_usd_values   = [15]                            # Minimum trade size in USD
multipliers            = [1.05, 1.1, 1.1, 1.15, 1.2]                   # Multiplier factors

# Create the full grid of parameter combinations.
full_grid = list(itertools.product(base_trade_percentages,
                                   trigger_percentages,
                                   max_trade_usd_values,
                                   min_trade_usd_values,
                                   multipliers))
print(f"Total grid size: {len(full_grid)} combinations available.")

# Sample 50 different combinations.
NUM_COMBOS = 50
sampled_param_combos = random.sample(full_grid, NUM_COMBOS)

# === HELPER FUNCTIONS ===

def classify_market_trend(open_price, close_price):
    """Classify the market based solely on the monthly open and close prices."""
    pct_change = (close_price - open_price) / open_price
    if pct_change >= BULLISH_THRESHOLD:
        return "Bullish"
    elif pct_change <= BEARISH_THRESHOLD:
        return "Bearish"
    else:
        return "Sideways"

def simulate_trading(df, params):
    """
    Simulate trading on a DataFrame of kline data (Binance format) using dynamic parameters.
    This function handles timestamps (which may be in milliseconds or microseconds) and implements
    a 50/50 portfolio rebalancing at the first valid data point.
    
    Returns a tuple: (trade_logs, final_usdc, final_eth)
    """
    # Extract dynamic parameters.
    base_trade_percentage = params["base_trade_percentage"]
    trigger_percentage    = params["trigger_percentage"]
    max_trade_usd         = params["max_trade_usd"]
    min_trade_usd         = params["min_trade_usd"]
    multiplier            = params["multiplier"]

    eth_balance = 0.0
    usdc_balance = INITIAL_USDC_BALANCE
    base_price = None
    consecutive_count = 0
    last_action = None
    trade_id = 1
    trade_logs = []

    for idx, row in df.iterrows():
        try:
            price = float(row["close_price"])
        except Exception:
            continue

        try:
            # Handle timestamp conversion.
            ts_raw = str(row["timestamp_open"]).strip()
            ts_number = int(float(ts_raw))
            ts_str = str(ts_number)
            if len(ts_str) >= 16:
                seconds = ts_number / 1e6  # microseconds to seconds
            elif len(ts_str) >= 13:
                seconds = ts_number / 1e3  # milliseconds to seconds
            else:
                seconds = ts_number

            if seconds < 946684800 or seconds > 4102444800:
                raise ValueError(f"Timestamp out of expected range: {seconds}")
            dt = datetime.datetime.fromtimestamp(seconds, tz=datetime.timezone.utc)
        except Exception as e:
            print(f"Warning: invalid timestamp {ts_raw} encountered at row {idx}: {e}. Skipping row.")
            continue

        date_str = dt.strftime("%Y%m%d")
        time_str = dt.strftime("%H%M%S")

        if base_price is None:
            base_price = price
            half_usd = INITIAL_USDC_BALANCE / 2.0
            usdc_balance = half_usd
            eth_balance = half_usd / price
            continue

        price_change = (price - base_price) / base_price

        action = None
        trade_usd = 0.0
        quantity = 0.0

        if price_change >= trigger_percentage:
            action = "SELL"
            if last_action == "SELL":
                consecutive_count += 1
            else:
                consecutive_count = 0

            effective_trade_percentage = base_trade_percentage * (multiplier ** consecutive_count)
            potential_usd = eth_balance * price * effective_trade_percentage
            if potential_usd < min_trade_usd:
                base_price = price
                last_action = "SELL"
                continue

            trade_usd = min(potential_usd, max_trade_usd)
            quantity = trade_usd / price
            if quantity > eth_balance:
                quantity = eth_balance
                trade_usd = quantity * price

            usdc_balance += trade_usd
            eth_balance -= quantity

        elif price_change <= -trigger_percentage:
            action = "BUY"
            if last_action == "BUY":
                consecutive_count += 1
            else:
                consecutive_count = 0

            effective_trade_percentage = base_trade_percentage * (multiplier ** consecutive_count)
            potential_usd = usdc_balance * effective_trade_percentage
            if potential_usd < min_trade_usd:
                base_price = price
                last_action = "BUY"
                continue

            trade_usd = min(potential_usd, max_trade_usd)
            quantity = trade_usd / price
            if trade_usd > usdc_balance:
                trade_usd = usdc_balance
                quantity = trade_usd / price

            usdc_balance -= trade_usd
            eth_balance += quantity
        else:
            continue

        base_price = price
        last_action = action
        eth_usd_value = eth_balance * price
        usdc_usd_value = usdc_balance
        total_balance = eth_usd_value + usdc_usd_value

        trade_logs.append({
            "ID": f"{trade_id:06d}",
            "Date": date_str,
            "Time": time_str,
            "Action": action,
            "Price": round(price, 8),
            "Quantity": round(quantity, 8),
            "ETH_Balance": round(eth_balance, 8),
            "USDC_Balance": round(usdc_balance, 8),
            "Total_Balance_USD": round(total_balance, 8),
            "Consecutive_Count": consecutive_count,
            "Effective_Trade_Pct": round(effective_trade_percentage, 8)
        })
        trade_id += 1

    return trade_logs, usdc_balance, eth_balance

# === PRE-COMPUTE MONTHLY INFO ===
# Create a dictionary mapping each month file to its monthly open, close, and market trend.
monthly_info = {}
month_files = sorted([f for f in os.listdir(EXTRACTED_FOLDER) if f.endswith(".csv")])

for file in month_files:
    file_path = os.path.join(EXTRACTED_FOLDER, file)
    try:
        df_prices = pd.read_csv(file_path, header=None)
    except Exception as e:
        print(f"Error reading {file}: {e}")
        continue

    df_prices.columns = [
        "timestamp_open", "open_price", "high_price", "low_price",
        "close_price", "volume", "timestamp_close", "quote_asset_volume",
        "number_of_trades", "taker_buy_base_asset_volume",
        "taker_buy_quote_asset_volume", "ignore"
    ]
    try:
        open_price = float(df_prices.iloc[0]["close_price"])
        close_price = float(df_prices.iloc[-1]["close_price"])
    except Exception as e:
        print(f"Error extracting prices from {file}: {e}")
        continue

    trend = classify_market_trend(open_price, close_price)
    monthly_info[file] = {"open": open_price, "close": close_price, "trend": trend}

# === AGGREGATE SIMULATION RESULTS ACROSS COMBOS, GROUPED BY Pre-computed Monthly Trend ===

analysis_records = []

# Loop over each sampled parameter combo.
for i, combo in enumerate(sampled_param_combos):
    print(f"Processing combo {i+1}/{NUM_COMBOS}", end="\r")
    params = {
        "base_trade_percentage": combo[0],
        "trigger_percentage": combo[1],
        "max_trade_usd": combo[2],
        "min_trade_usd": combo[3],
        "multiplier": combo[4]
    }
    # Dictionary to hold results grouped by market trend.
    results_by_trend = {"Bullish": [], "Bearish": [], "Sideways": []}

    for file in month_files:
        file_path = os.path.join(EXTRACTED_FOLDER, file)
        try:
            df = pd.read_csv(file_path, header=None)
        except Exception as e:
            print(f"Error reading {file}: {e}")
            continue
        df.columns = [
            "timestamp_open", "open_price", "high_price", "low_price",
            "close_price", "volume", "timestamp_close", "quote_asset_volume",
            "number_of_trades", "taker_buy_base_asset_volume",
            "taker_buy_quote_asset_volume", "ignore"
        ]
        if file not in monthly_info:
            continue
        open_price = monthly_info[file]["open"]
        close_price = monthly_info[file]["close"]
        market_trend = monthly_info[file]["trend"]

        # Run simulation for this month with the current parameters.
        trade_logs, final_usdc, final_eth = simulate_trading(df, params)
        final_value = final_usdc + (final_eth * close_price)

        # Buy-and-hold outcome: 50/50 allocation at open.
        half_value = INITIAL_USDC_BALANCE / 2.0
        eth_hold = half_value / open_price
        hold_final_value = half_value + (eth_hold * close_price)

        profit_trading = final_value - INITIAL_USDC_BALANCE
        profit_hold = hold_final_value - INITIAL_USDC_BALANCE
        num_trades = len(trade_logs)

        results_by_trend[market_trend].append({
            "Month_File": file,
            "Open_Price": open_price,
            "Close_Price": close_price,
            "Market_Trend": market_trend,
            "Num_Trades": num_trades,
            "Final_Portfolio_USD": final_value,
            "Profit_Trading_USD": profit_trading,
            "Profit_Hold_USD": profit_hold
        })

    # Local list to collect aggregated records for the current combo.
    combo_records = []
    for trend in ["Bullish", "Bearish", "Sideways"]:
        records = results_by_trend[trend]
        if records:
            df_records = pd.DataFrame(records)
            avg_trading_profit = df_records["Profit_Trading_USD"].mean()
            avg_hold_profit = df_records["Profit_Hold_USD"].mean()
            total_months = len(df_records)
            avg_trades = df_records["Num_Trades"].mean()
        else:
            avg_trading_profit = None
            avg_hold_profit = None
            total_months = 0
            avg_trades = None

        rec = {
            "base_trade_pct": params["base_trade_percentage"],
            "trigger_pct": params["trigger_percentage"],
            "max_trade_usd": params["max_trade_usd"],
            "min_trade_usd": params["min_trade_usd"],
            "multiplier": params["multiplier"],
            "Market_Trend": trend,
            "Avg_Trading_Profit_USD": round(avg_trading_profit, 2) if avg_trading_profit is not None else None,
            "Avg_Hold_Profit_USD": round(avg_hold_profit, 2) if avg_hold_profit is not None else None,
            "Total_Months": total_months,
            "Avg_Num_Trades": round(avg_trades, 2) if avg_trades is not None else None
        }
        combo_records.append(rec)
        analysis_records.append(rec)
    
    # --- Extra summary print for this parameter combo ---
    print(f"Summary for combo (base_trade_pct: {params['base_trade_percentage']}, "
          f"trigger_pct: {params['trigger_percentage']}, max_trade_usd: {params['max_trade_usd']}, "
          f"min_trade_usd: {params['min_trade_usd']}, multiplier: {params['multiplier']}):")
    for rec in combo_records:
        print(f"  {rec['Market_Trend']}: Avg_Trading_Profit_USD: {rec['Avg_Trading_Profit_USD']}, "
              f"Avg_Hold_Profit_USD: {rec['Avg_Hold_Profit_USD']}, "
              f"Total_Months: {rec['Total_Months']}, Avg_Num_Trades: {rec['Avg_Num_Trades']}")
    print("____________________________________________________________")

# Create a summary DataFrame.
df_summary = pd.DataFrame(analysis_records)
df_summary = df_summary.sort_values(by=["Market_Trend", "Avg_Trading_Profit_USD"], ascending=[True, False])
print("\nDynamic Simulation Analysis Summary (50 sample parameter combinations):")
print(df_summary.to_string(index=False))

# Save the summary.
df_summary.to_csv(SUMMARY_OUTPUT, index=False)
print(f"\nAnalysis summary saved to {SUMMARY_OUTPUT}")
