import os
import pandas as pd
import datetime
import random
import itertools
import json
from typing import Dict, Optional, Tuple

# === CONFIGURATION ===
EXTRACTED_FOLDER = "data/extracted"  # Each CSV: one month of Binance kline data
OUTPUT_FILE = "data/final_balances_analysis.csv"
TRADES_LOG_FOLDER = "data/trades_logs"

# Trading pair configuration - SET THESE FOR YOUR PAIR
TRADING_PAIR = "ETHBTC"  # The trading pair (e.g., ETHBTC, ADAETH, etc.)
BASE_ASSET = "ETH"       # The asset being bought/sold
QUOTE_ASSET = "BTC"      # The asset used as payment

# Starting configuration
start_year = "2022"
start_month = "01"
INITIAL_BASE_BALANCE = 1.0  # Initial balance in base asset (e.g., 10 ETH for ETHBTC)

# === DYNAMIC PARAMETER GRID ===
base_trade_percentages = [0.02, 0.05, 0.1, 0.5, 1]         
trigger_percentages    = [0.02, 0.1, 0.2]           
max_trade_percentages  = [0.1, 0.25, 0.5]  # Max percentage of balance to trade         
min_trade_percentages  = [0.001, 0.005, 0.01]  # Min percentage of balance to trade                         
multipliers            = [1, 2, 5]                     

# Create the full grid of parameter combinations
full_grid = list(itertools.product(base_trade_percentages,
                                   trigger_percentages,
                                   max_trade_percentages,
                                   min_trade_percentages,
                                   multipliers))
print(f"Total grid size: {len(full_grid)} combinations available.")

# Sample combinations (adjust NUM_COMBOS as needed)
NUM_COMBOS = 45
sampled_param_combos = random.sample(full_grid, NUM_COMBOS)

def get_sorted_files():
    """Get all files sorted by year and month, starting from specified start date"""
    all_files = []
    start_year_int = int(start_year)
    start_month_int = int(start_month)
    
    for year in range(start_year_int, 2026):  # From start year to 2025
        start_m = start_month_int if year == start_year_int else 1
        end_m = 13 if year < 2025 else 6  # Only up to 2025-05
        
        for month in range(start_m, end_m):
            filename = f"{TRADING_PAIR}-15m-{year}-{month:02d}.csv"
            file_path = os.path.join(EXTRACTED_FOLDER, filename)
            if os.path.exists(file_path):
                all_files.append((year, month, file_path))
    
    # Sort files by year and month to ensure chronological order
    all_files.sort(key=lambda x: (x[0], x[1]))
    return all_files

def create_trade_log_filename(params: Dict) -> str:
    """Create a unique filename for the trade log based on parameters"""
    param_str = f"bt{params['base_trade_percentage']}_tr{params['trigger_percentage']}_max{params['max_trade_percentage']}_min{params['min_trade_percentage']}_mult{params['multiplier']}"
    return f"{TRADING_PAIR}_trades_{param_str.replace('.', '_')}.csv"

def simulate_trading_across_all_files(params: Dict, log_trades: bool = True):
    """
    Simulate trading across all files sequentially, maintaining balances between files.
    Returns final balances, prices, trade count, and starting/ending prices.
    """
    # Extract dynamic parameters
    base_trade_percentage = params["base_trade_percentage"]
    trigger_percentage    = params["trigger_percentage"]
    max_trade_percentage  = params["max_trade_percentage"]
    min_trade_percentage  = params["min_trade_percentage"]
    multiplier            = params["multiplier"]

    # Initialize balances - start with 50/50 split in trading pair terms
    base_balance = 0.0
    quote_balance = 0.0
    base_price = None
    consecutive_count = 0
    last_action = None
    trade_count = 0
    starting_price = None
    final_price = None
    
    # Trade log
    trades_log = []
    trade_id = 1

    # Get all files sorted by year and month
    all_files = get_sorted_files()
    
    print(f"Processing {len(all_files)} files in chronological order...")
    
    for year, month, file_path in all_files:
        try:
            df = pd.read_csv(file_path, header=None)
        except Exception as e:
            print(f"Error reading {file_path}: {e}")
            continue

        # Set column names based on timestamp format
        df.columns = [
            "timestamp_open", "open_price", "high_price", "low_price",
            "close_price", "volume", "timestamp_close", "quote_asset_volume",
            "number_of_trades", "taker_buy_base_asset_volume",
            "taker_buy_quote_asset_volume", "ignore"
        ]

        for idx, row in df.iterrows():
            try:
                price = float(row["close_price"])
                if final_price is None:
                    final_price = price
                else:
                    final_price = price  # Keep updating final_price as we process
            except Exception:
                continue

            # Handle timestamp conversion (microseconds vs milliseconds)
            try:
                ts_raw = str(row["timestamp_open"]).strip()
                ts_number = int(float(ts_raw))
                ts_str = str(ts_number)
                
                # Determine if timestamp is in microseconds or milliseconds
                if len(ts_str) >= 16:  # 2025+ format (microseconds)
                    seconds = ts_number / 1e6
                elif len(ts_str) >= 13:  # Pre-2025 format (milliseconds)
                    seconds = ts_number / 1e3
                else:
                    seconds = ts_number

                if seconds < 946684800 or seconds > 4102444800:
                    continue
                    
                # Convert to datetime for logging
                trade_datetime = datetime.datetime.fromtimestamp(seconds)
                
            except Exception:
                continue

            # Initialize base price and perform 50/50 split on first valid price
            if base_price is None and starting_price is None:
                base_price = price
                starting_price = price
                
                # Start with 50/50 split based on initial base asset balance
                half_base = INITIAL_BASE_BALANCE / 2.0
                base_balance = half_base
                quote_balance = half_base * price  # Convert other half to quote asset
                continue

            price_change = (price - base_price) / base_price

            action = None
            trade_value_quote = 0.0
            quantity = 0.0
            actual_trade_percentage = 0.0

            # Check for SELL signal (sell base asset for quote asset)
            if price_change >= trigger_percentage:
                action = "SELL"
                if last_action == "SELL":
                    consecutive_count += 1
                else:
                    consecutive_count = 0

                effective_trade_percentage = base_trade_percentage * (multiplier ** consecutive_count)
                
                # Calculate potential trade quantity
                potential_base_quantity = base_balance * effective_trade_percentage
                
                # Apply min/max trade limits based on percentage of current balance
                total_balance_in_base = base_balance + (quote_balance / price)
                min_trade_quantity = total_balance_in_base * min_trade_percentage
                max_trade_quantity = total_balance_in_base * max_trade_percentage
                
                if potential_base_quantity < min_trade_quantity:
                    base_price = price
                    last_action = "SELL"
                    continue

                # Apply max trade limit
                quantity = min(potential_base_quantity, max_trade_quantity)
                
                if quantity > base_balance:
                    quantity = base_balance

                if quantity <= 0:
                    continue

                trade_value_quote = quantity * price

                # Execute trade
                quote_balance += trade_value_quote
                base_balance -= quantity
                trade_count += 1
                actual_trade_percentage = quantity / (base_balance + quantity) if (base_balance + quantity) > 0 else 0

            # Check for BUY signal (buy base asset with quote asset)
            elif price_change <= -trigger_percentage:
                action = "BUY"
                if last_action == "BUY":
                    consecutive_count += 1
                else:
                    consecutive_count = 0

                effective_trade_percentage = base_trade_percentage * (multiplier ** consecutive_count)
                
                # Calculate potential trade in quote terms
                potential_quote_value = quote_balance * effective_trade_percentage
                
                # Apply min/max trade limits based on percentage of current balance
                total_balance_in_base = base_balance + (quote_balance / price)
                min_trade_value_base = total_balance_in_base * min_trade_percentage
                max_trade_value_base = total_balance_in_base * max_trade_percentage
                
                min_trade_value_quote = min_trade_value_base * price
                max_trade_value_quote = max_trade_value_base * price
                
                if potential_quote_value < min_trade_value_quote:
                    base_price = price
                    last_action = "BUY"
                    continue

                # Apply max trade limit
                trade_value_quote = min(potential_quote_value, max_trade_value_quote)
                
                if trade_value_quote > quote_balance:
                    trade_value_quote = quote_balance

                if trade_value_quote <= 0:
                    continue

                quantity = trade_value_quote / price

                # Execute trade
                quote_balance -= trade_value_quote
                base_balance += quantity
                trade_count += 1
                actual_trade_percentage = trade_value_quote / (quote_balance + trade_value_quote) if (quote_balance + trade_value_quote) > 0 else 0
            else:
                continue

            # Log the trade if enabled
            if log_trades and action:
                total_balance_base = base_balance + (quote_balance / price)
                total_balance_quote = quote_balance + (base_balance * price)
                
                trade_log_entry = {
                    'ID': f"{trade_id:06d}",
                    'Date': trade_datetime.strftime('%y%m%d'),
                    'Time': trade_datetime.strftime('%H%M%S'),
                    'Action': action,
                    'Price': f"{price:.6f}",
                    'Quantity': f"{quantity:.6f}",
                    f'{BASE_ASSET}_Balance': f"{base_balance:.6f}",
                    f'{QUOTE_ASSET}_Balance': f"{quote_balance:.6f}",
                    f'Total_Balance_{BASE_ASSET}': f"{total_balance_base:.6f}",
                    f'Total_Balance_{QUOTE_ASSET}': f"{total_balance_quote:.6f}",
                    'Consecutive_Count': consecutive_count,
                    'Actual_Trade_Percentage': f"{actual_trade_percentage:.6f}"
                }
                trades_log.append(trade_log_entry)
                trade_id += 1

            base_price = price
            last_action = action

    # Save trades log if logging is enabled
    if log_trades and trades_log:
        os.makedirs(TRADES_LOG_FOLDER, exist_ok=True)
        log_filename = create_trade_log_filename(params)
        log_path = os.path.join(TRADES_LOG_FOLDER, log_filename)
        
        df_trades = pd.DataFrame(trades_log)
        df_trades.to_csv(log_path, index=False)

    return base_balance, quote_balance, final_price, starting_price, trade_count, trades_log

def main():
    print(f"Starting trading simulation for {TRADING_PAIR} ({BASE_ASSET}/{QUOTE_ASSET})")
    print(f"Initial balance: {INITIAL_BASE_BALANCE} {BASE_ASSET}")
    print(f"Processing {NUM_COMBOS} parameter combinations...")
    
    results = []
    
    for i, combo in enumerate(sampled_param_combos):
        print(f"Processing combo {i+1}/{NUM_COMBOS}: {combo}")
        
        params = {
            "base_trade_percentage": combo[0],
            "trigger_percentage": combo[1],
            "max_trade_percentage": combo[2],
            "min_trade_percentage": combo[3],
            "multiplier": combo[4]
        }
        
        try:
            final_base, final_quote, final_price, starting_price, trade_count, trades_log = simulate_trading_across_all_files(params, log_trades=True)
            
            if final_base is None or final_quote is None or final_price is None:
                print(f"Skipping combo {combo} due to processing error")
                continue
            
            # Calculate total values in both currencies
            total_base_value = final_base + (final_quote / final_price) if final_price > 0 else final_base
            total_quote_value = final_quote + (final_base * final_price)
            
            # Calculate performance metrics
            initial_base_value = INITIAL_BASE_BALANCE
            initial_quote_value = INITIAL_BASE_BALANCE * starting_price if starting_price else 0
            
            base_performance = ((total_base_value - initial_base_value) / initial_base_value * 100) if initial_base_value > 0 else 0
            quote_performance = ((total_quote_value - initial_quote_value) / initial_quote_value * 100) if initial_quote_value > 0 else 0
            
            result = {
                "base_trade_percentage": combo[0],
                "trigger_percentage": combo[1],
                "max_trade_percentage": combo[2],
                "min_trade_percentage": combo[3],
                "multiplier": combo[4],
                f"final_{BASE_ASSET.lower()}_balance": round(final_base, 8),
                f"final_{QUOTE_ASSET.lower()}_balance": round(final_quote, 8),
                f"total_{BASE_ASSET.lower()}_value": round(total_base_value, 8),
                f"total_{QUOTE_ASSET.lower()}_value": round(total_quote_value, 8),
                f"{BASE_ASSET.lower()}_performance_percent": round(base_performance, 2),
                f"{QUOTE_ASSET.lower()}_performance_percent": round(quote_performance, 2),
                "trade_count": trade_count,
                "starting_price": round(starting_price, 8) if starting_price else 0,
                "final_price": round(final_price, 8),
                "price_change_percent": round(((final_price - starting_price) / starting_price * 100), 2) if starting_price else 0,
                "trades_log_file": create_trade_log_filename(params)
            }
            
            results.append(result)
            
            print(f"  → {BASE_ASSET}: {final_base:.6f} | {QUOTE_ASSET}: {final_quote:.6f} | Total {BASE_ASSET}: {total_base_value:.6f} | Trades: {trade_count}")
            
        except Exception as e:
            print(f"Error processing combo {combo}: {e}")
            continue
    
    print(f"\nCompleted processing {len(results)} combinations successfully.")
    
    # Create DataFrame and save results
    df_results = pd.DataFrame(results)
    df_results = df_results.sort_values(f"total_{BASE_ASSET.lower()}_value", ascending=False)
    df_results.to_csv(OUTPUT_FILE, index=False)
    
    print(f"Results saved to {OUTPUT_FILE}")
    print(f"Trade logs saved to {TRADES_LOG_FOLDER}/")
    
    print("\nTop 5 performing combinations:")
    print(df_results.head().to_string())
    
    if not df_results.empty:
        print(f"\nSummary statistics:")
        print(f"Best total {BASE_ASSET} value: {df_results[f'total_{BASE_ASSET.lower()}_value'].max():.6f}")
        print(f"Worst total {BASE_ASSET} value: {df_results[f'total_{BASE_ASSET.lower()}_value'].min():.6f}")
        print(f"Average total {BASE_ASSET} value: {df_results[f'total_{BASE_ASSET.lower()}_value'].mean():.6f}")
        print(f"Average {BASE_ASSET} performance: {df_results[f'{BASE_ASSET.lower()}_performance_percent'].mean():.2f}%")
        print(f"Average number of trades: {df_results['trade_count'].mean():.1f}")
        print(f"Max number of trades: {df_results['trade_count'].max()}")

if __name__ == "__main__":
    main()