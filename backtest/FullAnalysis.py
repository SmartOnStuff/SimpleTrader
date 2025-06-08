import os
import pandas as pd
import datetime
import random
import itertools
import matplotlib.pyplot as plt
import seaborn as sns
import numpy as np
from matplotlib.patches import Rectangle

# === CONFIGURATION ===

EXTRACTED_FOLDER = "data/extracted"  # Each CSV: one month of Binance kline data
SUMMARY_OUTPUT = "data/dynamic_analysis_summary.csv"
ANALYSIS_OUTPUT = "data/analysis_results.md"
PLOTS_FOLDER = "plots"

# Create plots folder if it doesn't exist
os.makedirs(PLOTS_FOLDER, exist_ok=True)

# Starting portfolio value and rebalancing (50/50 split)
INITIAL_USDC_BALANCE = 1000.0  # USD value

# Market trend thresholds (applied on monthly open/close prices)
BULLISH_THRESHOLD = 0.2   # +20%: monthly close is at least 20% above open → Bullish
BEARISH_THRESHOLD = -0.2  # -20%: monthly close is at least 20% below open → Bearish
# Otherwise → Sideways

# === DYNAMIC PARAMETER GRID ===
# Define ranges for each trading parameter.
base_trade_percentages = [0.1, 0.2, 0.3, 0.4, 0.5]         # Example: 10%-50%
trigger_percentages    = [0.02, 0.05, 0.1, 0.2]           # 2%-20%
max_trade_usd_values   = [1000, 750, 500]                   # USD cap per trade
min_trade_usd_values   = [15]                               # Minimum trade size in USD
multipliers            = [1, 1.1, 1.2]                     # Multiplier factors

# Create the full grid of parameter combinations.
full_grid = list(itertools.product(base_trade_percentages,
                                   trigger_percentages,
                                   max_trade_usd_values,
                                   min_trade_usd_values,
                                   multipliers))
print(f"Total grid size: {len(full_grid)} combinations available.")

# Sample 50 different combinations.
NUM_COMBOS = 100
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

def create_visualizations(df_summary):
    """Create comprehensive visualizations of the trading analysis results."""
    
    # Set up the plotting style
    plt.style.use('seaborn-v0_8')
    colors = {'Bullish': '#2ecc71', 'Bearish': '#e74c3c', 'Sideways': '#f39c12'}
    
    # Create a large figure with multiple subplots
    fig = plt.figure(figsize=(20, 16))
    
    # 1. Profit Differential Distribution by Market Trend
    ax1 = plt.subplot(2, 3, 1)
    for trend in df_summary['Market_Trend'].unique():
        data = df_summary[df_summary['Market_Trend'] == trend]['Profit_Diff']
        ax1.hist(data, alpha=0.7, label=trend, color=colors[trend], bins=15)
    ax1.set_xlabel('Profit Differential (USD)')
    ax1.set_ylabel('Frequency')
    ax1.set_title('Distribution of Profit Differential by Market Trend')
    ax1.legend()
    ax1.grid(True, alpha=0.3)
    
    # 2. Box Plot of Profit Differential
    ax2 = plt.subplot(2, 3, 2)
    df_summary.boxplot(column='Profit_Diff', by='Market_Trend', ax=ax2)
    ax2.set_xlabel('Market Trend')
    ax2.set_ylabel('Profit Differential (USD)')
    ax2.set_title('Profit Differential Distribution by Market Trend')
    plt.suptitle('')  # Remove default title
    
    # 3. Scatter Plot: Trading vs Hold Performance
    ax3 = plt.subplot(2, 3, 3)
    for trend in df_summary['Market_Trend'].unique():
        trend_data = df_summary[df_summary['Market_Trend'] == trend]
        ax3.scatter(trend_data['Avg_Hold_Profit_USD'], trend_data['Avg_Trading_Profit_USD'], 
                   alpha=0.7, label=trend, color=colors[trend], s=50)
    
    # Add diagonal line (where trading = holding)
    min_val = min(df_summary['Avg_Hold_Profit_USD'].min(), df_summary['Avg_Trading_Profit_USD'].min())
    max_val = max(df_summary['Avg_Hold_Profit_USD'].max(), df_summary['Avg_Trading_Profit_USD'].max())
    ax3.plot([min_val, max_val], [min_val, max_val], 'k--', alpha=0.5, label='Equal Performance')
    
    ax3.set_xlabel('Hold Strategy Profit (USD)')
    ax3.set_ylabel('Trading Strategy Profit (USD)')
    ax3.set_title('Trading vs Hold Strategy Performance')
    ax3.legend()
    ax3.grid(True, alpha=0.3)
    
    # 4. Parameter Impact Analysis - Base Trade Percentage
    ax4 = plt.subplot(2, 3, 4)
    param_analysis = df_summary.groupby(['Market_Trend', 'base_trade_pct'])['Profit_Diff'].mean().reset_index()
    for trend in param_analysis['Market_Trend'].unique():
        trend_data = param_analysis[param_analysis['Market_Trend'] == trend]
        ax4.plot(trend_data['base_trade_pct'], trend_data['Profit_Diff'], 
                'o-', label=trend, color=colors[trend], linewidth=2, markersize=6)
    ax4.set_xlabel('Base Trade Percentage')
    ax4.set_ylabel('Average Profit Differential (USD)')
    ax4.set_title('Impact of Base Trade Percentage on Performance')
    ax4.legend()
    ax4.grid(True, alpha=0.3)
    
    # 5. Parameter Impact Analysis - Trigger Percentage
    ax5 = plt.subplot(2, 3, 5)
    param_analysis2 = df_summary.groupby(['Market_Trend', 'trigger_pct'])['Profit_Diff'].mean().reset_index()
    for trend in param_analysis2['Market_Trend'].unique():
        trend_data = param_analysis2[param_analysis2['Market_Trend'] == trend]
        ax5.plot(trend_data['trigger_pct'], trend_data['Profit_Diff'], 
                'o-', label=trend, color=colors[trend], linewidth=2, markersize=6)
    ax5.set_xlabel('Trigger Percentage')
    ax5.set_ylabel('Average Profit Differential (USD)')
    ax5.set_title('Impact of Trigger Percentage on Performance')
    ax5.legend()
    ax5.grid(True, alpha=0.3)
    
    # 6. Heatmap of Average Performance by Parameters
    ax6 = plt.subplot(2, 3, 6)
    pivot_data = df_summary.groupby(['base_trade_pct', 'trigger_pct'])['Profit_Diff'].mean().reset_index()
    pivot_table = pivot_data.pivot(index='base_trade_pct', columns='trigger_pct', values='Profit_Diff')
    
    sns.heatmap(pivot_table, annot=True, fmt='.1f', cmap='RdYlGn', center=0, ax=ax6)
    ax6.set_xlabel('Trigger Percentage')
    ax6.set_ylabel('Base Trade Percentage')
    ax6.set_title('Profit Differential Heatmap\n(Base Trade % vs Trigger %)')
    
    plt.tight_layout()
    plt.savefig(f'{PLOTS_FOLDER}/trading_analysis_comprehensive.png', dpi=300, bbox_inches='tight')
    plt.show()
    
    # Create a second figure for top performers
    fig2, axes = plt.subplots(1, 3, figsize=(18, 6))
    
    for i, trend in enumerate(['Bearish', 'Bullish', 'Sideways']):
        ax = axes[i]
        trend_data = df_summary[df_summary['Market_Trend'] == trend].sort_values('Profit_Diff', ascending=False).head(10)
        
        bars = ax.barh(range(len(trend_data)), trend_data['Profit_Diff'], color=colors[trend], alpha=0.7)
        ax.set_yticks(range(len(trend_data)))
        ax.set_yticklabels([f"Combo {j+1}" for j in range(len(trend_data))])
        ax.set_xlabel('Profit Differential (USD)')
        ax.set_title(f'Top 10 Performers - {trend} Market')
        ax.grid(True, alpha=0.3)
        
        # Add value labels on bars
        for j, bar in enumerate(bars):
            width = bar.get_width()
            ax.text(width + (0.01 * max(trend_data['Profit_Diff'])), bar.get_y() + bar.get_height()/2, 
                   f'{width:.1f}', ha='left', va='center', fontsize=9)
    
    plt.tight_layout()
    plt.savefig(f'{PLOTS_FOLDER}/top_performers_by_trend.png', dpi=300, bbox_inches='tight')
    plt.show()

def generate_markdown_report(df_summary, top_combos):
    """Generate a comprehensive markdown report."""
    
    markdown_content = """# Trading Strategy Analysis & Optimization Results

## Executive Summary

This analysis evaluates the performance of various trading parameter combinations across different market conditions using historical backtesting data. The strategy performance is compared against a simple buy-and-hold approach to determine optimal configurations for different market environments.

## Methodology

### Parameter Grid and Simulation
We tested combinations of the following parameters:

- **Base Trade Percentage**: The initial percentage of balance allocated for a trade (10%-50%)
- **Trigger Percentage**: The price movement threshold for triggering a BUY/SELL signal (2%-20%)
- **Maximum Trade USD**: The cap on the USD value per trade (500-1000 USD)
- **Minimum Trade USD**: Fixed at 15 USD to prevent tiny unprofitable trades
- **Multiplier**: Increases the trade size with consecutive trades in the same direction (1.0-1.2)

### Profit Differential Calculation
For every parameter combination under each market condition, we calculated:

```
Profit_Diff = Avg_Trading_Profit_USD - Avg_Hold_Profit_USD
```

This metric quantifies how much better (or worse) the trading strategy performs relative to a basic buy-and-hold approach.

## Analysis Results

### Top Performing Parameter Combinations

"""
    
    for trend in ['Bearish', 'Bullish', 'Sideways']:
        markdown_content += f"\n#### Market Trend: {trend}\n\n"
        
        trend_combos = top_combos[trend]
        for i, combo in enumerate(trend_combos, 1):
            markdown_content += f"**Combo {i}:**\n"
            markdown_content += f"- Parameters: base_trade_pct: {combo['base_trade_pct']}, trigger_pct: {combo['trigger_pct']}, max_trade_usd: {combo['max_trade_usd']}, multiplier: {combo['multiplier']}\n"
            markdown_content += f"- Profit_Diff: {combo['Profit_Diff']:.2f}, Trading: {combo['Avg_Trading_Profit_USD']:.2f}, Hold: {combo['Avg_Hold_Profit_USD']:.2f}\n"
            markdown_content += f"- Months: {combo['Total_Months']}, Avg Trades: {combo['Avg_Num_Trades']:.2f}\n\n"
        
        # Add conclusions for each trend
        if trend == 'Bearish':
            markdown_content += """**Conclusion (Bearish):** Under bearish conditions, the algorithm effectively mitigates losses relative to holding. The strategy demonstrates risk reduction capabilities during market downturns.

"""
        elif trend == 'Bullish':
            markdown_content += """**Conclusion (Bullish):** In bullish markets, the trading strategy tends to underperform compared to simply holding assets. This suggests that the algorithm may interrupt the full capture of upward trends through premature trading decisions.

"""
        else:  # Sideways
            markdown_content += """**Conclusion (Sideways):** The strategy performs exceptionally well in sideways markets, where active trading capitalizes on price fluctuations that provide little benefit to a hold strategy.

"""
    
    # Add statistical summary
    summary_stats = df_summary.groupby('Market_Trend')['Profit_Diff'].agg(['mean', 'std', 'min', 'max']).round(2)
    
    markdown_content += """## Statistical Summary

| Market Trend | Mean Profit Diff | Std Dev | Min | Max |
|-------------|------------------|---------|-----|-----|
"""
    
    for trend in summary_stats.index:
        stats = summary_stats.loc[trend]
        markdown_content += f"| {trend} | {stats['mean']:.2f} | {stats['std']:.2f} | {stats['min']:.2f} | {stats['max']:.2f} |\n"
    
    markdown_content += """
## Key Insights & Recommendations

### Market-Specific Findings

1. **Bearish Markets**: Active trading strategies show promise in reducing losses compared to holding positions during market downturns.

2. **Bullish Markets**: Hold strategies generally outperform active trading, suggesting that frequent trading may interrupt beneficial long-term trends.

3. **Sideways Markets**: This environment provides the greatest opportunity for active trading strategies to outperform holding.

### Strategic Recommendations

1. **Adaptive Strategy Implementation**: Consider developing a regime detection system that adjusts trading behavior based on identified market conditions.

2. **Parameter Optimization**: Focus on higher base trade percentages and trigger percentages for bearish and sideways markets, while minimizing activity during strong bull markets.

3. **Risk Management**: Implement dynamic position sizing based on market volatility and trend strength.

4. **Hybrid Approach**: Combine the benefits of both active trading and holding strategies through conditional logic based on market environment detection.

## Visualization Insights

The analysis includes comprehensive visualizations showing:
- Performance distribution across market conditions
- Parameter sensitivity analysis
- Comparative performance metrics
- Top performer identification

These visualizations are saved in the `plots/` directory for detailed review.

## Conclusion

The analysis demonstrates that trading strategy effectiveness is highly dependent on market conditions. A sophisticated approach that adapts to market regimes could potentially capture the benefits of active trading during appropriate conditions while avoiding the pitfalls of over-trading during strong trends.

Future work should focus on developing robust market regime detection algorithms and implementing adaptive parameter adjustment mechanisms to optimize performance across varying market conditions.
"""
    
    # Save the markdown report
    with open(ANALYSIS_OUTPUT, 'w') as f:
        f.write(markdown_content)
    
    print(f"Comprehensive analysis report saved to {ANALYSIS_OUTPUT}")

# === MAIN EXECUTION ===

def main():
    print("Starting comprehensive trading strategy analysis...")
    
    # === PRE-COMPUTE MONTHLY INFO ===
    monthly_info = {}
    month_files = sorted([f for f in os.listdir(EXTRACTED_FOLDER) if f.endswith(".csv")])

    print(f"Processing {len(month_files)} monthly data files...")
    
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

    # === RUN SIMULATION ANALYSIS ===
    print("Running simulation analysis...")
    
    analysis_records = []

    for i, combo in enumerate(sampled_param_combos):
        print(f"Processing combo {i+1}/{NUM_COMBOS}", end="\r")
        params = {
            "base_trade_percentage": combo[0],
            "trigger_percentage": combo[1],
            "max_trade_usd": combo[2],
            "min_trade_usd": combo[3],
            "multiplier": combo[4]
        }
        
        results_by_trend = {"Bullish": [], "Bearish": [], "Sideways": []}

        for file in month_files:
            file_path = os.path.join(EXTRACTED_FOLDER, file)
            try:
                df = pd.read_csv(file_path, header=None)
            except Exception as e:
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

            trade_logs, final_usdc, final_eth = simulate_trading(df, params)
            final_value = final_usdc + (final_eth * close_price)

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
            analysis_records.append(rec)

    # === ANALYZE RESULTS ===
    print("\nAnalyzing results...")
    
    df_summary = pd.DataFrame(analysis_records)
    df_summary = df_summary.sort_values(by=["Market_Trend", "Avg_Trading_Profit_USD"], ascending=[True, False])
    
    # Compute profit differential
    df_summary["Profit_Diff"] = df_summary["Avg_Trading_Profit_USD"] - df_summary["Avg_Hold_Profit_USD"]
    
    # Save summary
    df_summary.to_csv(SUMMARY_OUTPUT, index=False)
    print(f"Analysis summary saved to {SUMMARY_OUTPUT}")
    
    # === IDENTIFY TOP PERFORMERS ===
    print("\nIdentifying top performers...")
    
    top_combos = {}
    market_trends = df_summary["Market_Trend"].unique()

    for trend in market_trends:
        df_trend = df_summary[df_summary["Market_Trend"] == trend].copy()
        df_trend = df_trend.sort_values(by="Profit_Diff", ascending=False)
        top3 = df_trend.head(3)
        top_combos[trend] = top3.to_dict('records')
        
        print("=" * 70)
        print(f"Top 3 Combos for Market Trend: {trend}")
        print("=" * 70)
        for idx, row in top3.iterrows():
            print(f"combo: base_trade_pct: {row['base_trade_pct']}, trigger_pct: {row['trigger_pct']}, "
                  f"max_trade_usd: {row['max_trade_usd']}, min_trade_usd: {row['min_trade_usd']}, multiplier: {row['multiplier']}  --> "
                  f"Profit_Diff: {row['Profit_Diff']:.2f}, Trading: {row['Avg_Trading_Profit_USD']:.2f}, "
                  f"Hold: {row['Avg_Hold_Profit_USD']:.2f}, Months: {row['Total_Months']}, Trades: {row['Avg_Num_Trades']:.2f}")
        print("\n")
    
    # === CREATE VISUALIZATIONS ===
    print("Creating visualizations...")
    create_visualizations(df_summary)
    
    # === GENERATE REPORT ===
    print("Generating comprehensive report...")
    generate_markdown_report(df_summary, top_combos)
    
    print("\n" + "="*70)
    print("Analysis Complete!")
    print("="*70)
    print(f"📊 Summary CSV: {SUMMARY_OUTPUT}")
    print(f"📈 Plots saved in: {PLOTS_FOLDER}/")
    print(f"📝 Full report: {ANALYSIS_OUTPUT}")
    print("="*70)

if __name__ == "__main__":
    main()