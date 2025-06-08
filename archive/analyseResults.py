import os
import pandas as pd

# --- Configuration ---
EXTRACTED_FOLDER = "data/extracted"      # Folder containing the original extracted kline CSV files (one per month)
LOGS_FOLDER = "data/logs"                # Folder containing the simulation trade log CSV files (one per month)
SUMMARY_OUTPUT = "data/analysis_summary.csv"

# We assume a starting portfolio value of 1000 USDC.
INITIAL_USDC_BALANCE = 1000.0

analysis_rows = []

# Process each extracted kline file (each representing one month)
for extracted_file in sorted(os.listdir(EXTRACTED_FOLDER)):
    if not extracted_file.endswith(".csv"):
        continue

    base_filename = extracted_file.replace(".csv", "")
    extracted_path = os.path.join(EXTRACTED_FOLDER, extracted_file)

    # Read the original kline data. We expect the Binance format with no header.
    try:
        df_prices = pd.read_csv(extracted_path, header=None)
    except Exception as e:
        print(f"Error reading {extracted_file}: {e}")
        continue

    # Define assumed columns (Binance kline standard)
    df_prices.columns = [
        "timestamp_open", "open_price", "high_price", "low_price",
        "close_price", "volume", "timestamp_close", "quote_asset_volume",
        "number_of_trades", "taker_buy_base_asset_volume",
        "taker_buy_quote_asset_volume", "ignore"
    ]

    # Use the first row for the open price and last row for the close price
    try:
        open_price = float(df_prices.iloc[0]["close_price"])
        close_price = float(df_prices.iloc[-1]["close_price"])
    except Exception as e:
        print(f"Error extracting open/close prices from {extracted_file}: {e}")
        continue

    # --- "Hold" (Buy-and-Hold) Outcome ---
    # At the open, a 50/50 allocation (500 USD in USDC and 500 USD in ETH) would be set.
    # For the hold outcome, we assume the ETH bought at the open remains unchanged,
    # and its value is recalculated at close.
    half_value = INITIAL_USDC_BALANCE / 2.0
    eth_hold = half_value / open_price
    # Hold final portfolio value = remaining USDC + ETH value at close.
    hold_final_value  = half_value + (eth_hold * close_price)

    # --- Simulation Outcome ---
    # Match the simulation log file for the month. We assume it's named "<base_filename>_log.csv"
    simulation_log_file = f"{base_filename}_log.csv"
    simulation_path = os.path.join(LOGS_FOLDER, simulation_log_file)

    if os.path.exists(simulation_path):
        df_sim = pd.read_csv(simulation_path)
        num_trades = len(df_sim)
        if num_trades > 0:
            simulation_final_value = float(df_sim.iloc[-1]["Total_Balance_USD"])
        else:
            simulation_final_value = INITIAL_USDC_BALANCE
    else:
        num_trades = 0
        simulation_final_value = INITIAL_USDC_BALANCE

    # --- Profitability Calculation ---
    profit_trading = simulation_final_value - INITIAL_USDC_BALANCE
    profit_hold = hold_final_value - INITIAL_USDC_BALANCE
    pct_change_trading = ((simulation_final_value / INITIAL_USDC_BALANCE) - 1) * 100
    pct_change_hold = ((hold_final_value / INITIAL_USDC_BALANCE) - 1) * 100

    # Extract a month label from the filename.
    # Adjust this if your filename format is different.
    month_label = base_filename.split('_')[0]

    analysis_rows.append({
        "Month": month_label,
        "Open_Price": open_price,
        "Close_Price": close_price,
        "Num_Trades": num_trades,
        "Simulation_Final_USD": round(simulation_final_value, 2),
        "Hold_Final_USD": round(hold_final_value, 2),
        "Profit_Trading_USD": round(profit_trading, 2),
        "Profit_Hold_USD": round(profit_hold, 2),
        "Pct_Change_Trading": round(pct_change_trading, 2),
        "Pct_Change_Hold": round(pct_change_hold, 2)
    })

# Create and display the summary DataFrame.
df_summary = pd.DataFrame(analysis_rows)

# Order the table by month if desired.
df_summary = df_summary.sort_values(by="Month")

print("Monthly Trading Analysis Summary:")
print(df_summary.to_string(index=False))

# Save summary to CSV for further analysis.
df_summary.to_csv(SUMMARY_OUTPUT, index=False)
print(f"\nAnalysis summary saved to {SUMMARY_OUTPUT}")
