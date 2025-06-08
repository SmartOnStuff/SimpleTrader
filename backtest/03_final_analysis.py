import pandas as pd

# Path to the analysis summary CSV produced by your simulation analysis.
INPUT_FILE = "data/dynamic_analysis_summary.csv"

# Read the CSV into a DataFrame.
df = pd.read_csv(INPUT_FILE)

# Optionally, create a unique key for clarity.
df['combo_key'] = (
    df['base_trade_pct'].astype(str) + "_" +
    df['trigger_pct'].astype(str) + "_" +
    df['max_trade_usd'].astype(str) + "_" +
    df['min_trade_usd'].astype(str) + "_" +
    df['multiplier'].astype(str)
)

# Compute a new column 'Profit_Diff' as the difference between Avg_Trading_Profit_USD and Avg_Hold_Profit_USD.
df["Profit_Diff"] = df["Avg_Trading_Profit_USD"] - df["Avg_Hold_Profit_USD"]

# Identify unique market trends.
market_trends = df["Market_Trend"].unique()

for trend in market_trends:
    # Filter for the current trend.
    df_trend = df[df["Market_Trend"] == trend].copy()
    
    # Sort by Profit_Diff in descending order.
    df_trend = df_trend.sort_values(by="Profit_Diff", ascending=False)
    
    # Select only the top 3 records.
    top3 = df_trend.head(3)
    
    print("=" * 70)
    print(f"Top 3 Combos for Market Trend: {trend}")
    print("=" * 70)
    for idx, row in top3.iterrows():
        print(f"combo: base_trade_pct: {row['base_trade_pct']}, trigger_pct: {row['trigger_pct']}, "
              f"max_trade_usd: {row['max_trade_usd']}, min_trade_usd: {row['min_trade_usd']}, multiplier: {row['multiplier']}  --> "
              f"Profit_Diff: {row['Profit_Diff']:.2f}, Trading: {row['Avg_Trading_Profit_USD']:.2f}, "
              f"Hold: {row['Avg_Hold_Profit_USD']:.2f}, Months: {row['Total_Months']}, Trades: {row['Avg_Num_Trades']}")
    
    print("\n")
