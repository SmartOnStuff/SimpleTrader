import os
import pandas as pd
import datetime
import random
import itertools

# === CONFIGURATION ===
EXTRACTED_FOLDER = "data/extracted"  # Each CSV: one month of Binance kline data
OUTPUT_FILE = "data/final_balances_analysis.csv"

# Starting configuration
start_year = "2022"
start_month = "01"
INITIAL_USDC_BALANCE = 1000.0  # USD value

# === DYNAMIC PARAMETER GRID ===
base_trade_percentages = [0.02, 0.05, 0.1, 0.5, 1]         
trigger_percentages    = [0.02, 0.1, 0.2]           
max_trade_usd_values   = [10000]                   
min_trade_usd_values   = [15]                               
multipliers            = [1, 2, 5]                     

# Create the full grid of parameter combinations
full_grid = list(itertools.product(base_trade_percentages,
                                   trigger_percentages,
                                   max_trade_usd_values,
                                   min_trade_usd_values,
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
            filename = f"ETHUSDC-15m-{year}-{month:02d}.csv"
            file_path = os.path.join(EXTRACTED_FOLDER, filename)
            if os.path.exists(file_path):
                all_files.append((year, month, file_path))
    
    # Sort files by year and month to ensure chronological order
    all_files.sort(key=lambda x: (x[0], x[1]))
    return all_files

def simulate_trading_across_all_files(params):
    """
    Simulate trading across all files sequentially, maintaining balances between files.
    Returns final ETH and USDC balances and final price after processing all files.
    """
    # Extract dynamic parameters
    base_trade_percentage = params["base_trade_percentage"]
    trigger_percentage    = params["trigger_percentage"]
    max_trade_usd         = params["max_trade_usd"]
    min_trade_usd         = params["min_trade_usd"]
    multiplier            = params["multiplier"]

    # Initialize balances
    eth_balance = 0.0
    usdc_balance = INITIAL_USDC_BALANCE
    base_price = None
    consecutive_count = 0
    last_action = None
    first_trade = True
    final_price = None

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
                    
            except Exception:
                continue

            # Initialize base price and perform 50/50 split on first valid price
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

            # Check for SELL signal
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

            # Check for BUY signal
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

    return eth_balance, usdc_balance, final_price

def get_final_price():
    """Get the final price from the most recent data file"""
    all_files = get_sorted_files()
    
    if not all_files:
        return None
        
    # Get the last file we processed
    last_file = all_files[-1][2]  # Get file path from tuple
    try:
        df_last = pd.read_csv(last_file, header=None)
        df_last.columns = [
            "timestamp_open", "open_price", "high_price", "low_price",
            "close_price", "volume", "timestamp_close", "quote_asset_volume",
            "number_of_trades", "taker_buy_base_asset_volume",
            "taker_buy_quote_asset_volume", "ignore"
        ]
        final_price = float(df_last.iloc[-1]["close_price"])
        return final_price
    except Exception as e:
        print(f"Error getting final price from {last_file}: {e}")
        return None

def main():
    print("Starting final balance analysis across all parameter combinations...")
    
    results = []
    
    for i, combo in enumerate(sampled_param_combos):
        print(f"Processing combo {i+1}/{NUM_COMBOS}: {combo}", end="\r")
        
        params = {
            "base_trade_percentage": combo[0],
            "trigger_percentage": combo[1],
            "max_trade_usd": combo[2],
            "min_trade_usd": combo[3],
            "multiplier": combo[4]
        }
        
        try:
            final_eth, final_usdc, final_price = simulate_trading_across_all_files(params)
            
            if final_eth is None or final_usdc is None or final_price is None:
                print(f"\nSkipping combo {combo} due to processing error")
                continue
            
            # Use the final price returned from simulation, or get it separately if needed
            if final_price is None:
                final_price = get_final_price()
                if final_price is None:
                    print("Warning: Could not determine final price from processed files.")
                    continue
            
            total_usd_value = final_usdc + (final_eth * final_price)
            
            result = {
                "base_trade_percentage": combo[0],
                "trigger_percentage": combo[1],
                "max_trade_usd": combo[2],
                "min_trade_usd": combo[3],
                "multiplier": combo[4],
                "final_eth_balance": round(final_eth, 8),
                "final_usdc_balance": round(final_usdc, 2),
                "total_usd_value": round(total_usd_value, 2)
            }
            
            results.append(result)
            
        except Exception as e:
            print(f"\nError processing combo {combo}: {e}")
            continue
    
    print(f"\nCompleted processing {len(results)} combinations successfully.")
    
    # Create DataFrame and save results
    df_results = pd.DataFrame(results)
    df_results = df_results.sort_values("total_usd_value", ascending=False)
    df_results.to_csv(OUTPUT_FILE, index=False)
    
    print(f"Results saved to {OUTPUT_FILE}")
    print("\nTop 5 performing combinations:")
    print(df_results.head())
    
    print(f"\nSummary statistics:")
    print(f"Best total USD value: ${df_results['total_usd_value'].max():,.2f}")
    print(f"Worst total USD value: ${df_results['total_usd_value'].min():,.2f}")
    print(f"Average total USD value: ${df_results['total_usd_value'].mean():,.2f}")

if __name__ == "__main__":
    main()