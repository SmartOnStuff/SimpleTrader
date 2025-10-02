import json
import pathlib
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import numpy as np
from pathlib import Path
from telegram import Update, BotCommand
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes
)
from dotenv import load_dotenv
import datetime
import requests
import glob
import os

# Load environment variables
BASE_PATH = pathlib.Path(__file__).parent  # Script directory
load_dotenv(dotenv_path=BASE_PATH / ".env")

# Get bot token and API keys
bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
BINANCE_API_KEY = os.getenv("BINANCE_API_KEY")
BINANCE_SECRET_KEY = os.getenv("BINANCE_API_SECRET")

# File paths
PROJECT_ROOT = pathlib.Path(__file__).resolve().parent  # Same as BASE_PATH
LOGS_DIR = PROJECT_ROOT / "logs"  # Path for log files

# --- Binance API Functions ---

def get_binance_balances():
    """Get wallet balances from Binance API"""
    try:
        import hmac
        import hashlib
        import time
        
        if not BINANCE_API_KEY or not BINANCE_SECRET_KEY:
            return None
        
        # Binance API endpoint
        base_url = "https://api.binance.com"
        endpoint = "/api/v3/account"
        
        # Create timestamp and signature
        timestamp = int(time.time() * 1000)
        params = f"timestamp={timestamp}"
        
        signature = hmac.new(
            BINANCE_SECRET_KEY.encode('utf-8'),
            params.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        
        url = f"{base_url}{endpoint}?{params}&signature={signature}"
        
        headers = {
            'X-MBX-APIKEY': BINANCE_API_KEY
        }
        
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        
        data = response.json()
        balances = {}
        
        # Filter out zero balances and format
        for balance in data.get('balances', []):
            free_balance = float(balance['free'])
            locked_balance = float(balance['locked'])
            total_balance = free_balance + locked_balance
            
            if total_balance > 0:
                balances[balance['asset']] = {
                    'free': free_balance,
                    'locked': locked_balance,
                    'total': total_balance,
                    'symbol': balance['asset']
                }
        
        return balances
        
    except Exception as e:
        print(f"Error fetching Binance balances: {e}")
        return None
        

    
# --- Visualization Function ---
def chartTrades(log_dir):
    """
    Analyzes trade and price data, calculates total PnL,
    and generates a combined chart showing price action, buy/sell trades,
    total USD balance, and manual selloff indicators for all available cryptocurrency pairs.
    
    Args:
        log_dir (Path): The directory path where the log CSV files are located.
    """
    all_price_data = []
    all_trades_data = []
    all_selloff_data = {}

    # Dynamically find all trade log files for the specific user
    trade_files = list(log_dir.glob(f"*_trades.csv"))
    
    if not trade_files:
        print(f"No trade log files found in {log_dir}")
        return None

    # Load data for each pair
    for trade_file_path in trade_files:
        try:
            # Extract the pair name from the filename (e.g., 'RED_USDC' from 'RED_USDC_trades.csv')
            file_stem = trade_file_path.stem  # Gets 'RED_USDC_trades'
            if file_stem.endswith('_trades'):
                pair_name = file_stem[:-7]  # Remove '_trades' to get 'RED_USDC'
            else:
                continue
                
            price_file_path = log_dir / f"{pair_name}.csv"
            selloff_file_path = log_dir / f"{pair_name}_selloff.csv"

            # Load trade and price data for the current pair
            if not price_file_path.exists():
                print(f"Warning: Price file {price_file_path} not found for trades file {trade_file_path}")
                continue
                
            price_df = pd.read_csv(price_file_path)
            trades_df = pd.read_csv(trade_file_path)
            
            # Load selloff data if available
            if selloff_file_path.exists():
                try:
                    selloff_df = pd.read_csv(selloff_file_path)
                    # Parse the date column (format: yyMMDD)
                    selloff_df['date'] = selloff_df['date'].astype(str).str.zfill(6)
                    selloff_df['datetime'] = pd.to_datetime(selloff_df['date'], format='%y%m%d')
                    all_selloff_data[pair_name] = selloff_df
                    print(f"Loaded {len(selloff_df)} selloff indicators for {pair_name}")
                except Exception as e:
                    print(f"Warning: Could not load selloff file for {pair_name}: {e}")
            
            # Add a 'pair' column for later plotting and filtering
            price_df['pair'] = pair_name
            trades_df['pair'] = pair_name
            
            all_price_data.append(price_df)
            all_trades_data.append(trades_df)
            
        except FileNotFoundError as e:
            print(f"Warning: File not found: {e}")
            continue
        except Exception as e:
            print(f"Error loading file {trade_file_path.name}: {e}")
            continue

    if not all_trades_data:
        print(f"No valid trade data found")
        return None

    # Combine all data into single dataframes
    combined_price_df = pd.concat(all_price_data, ignore_index=True)
    combined_trades_df = pd.concat(all_trades_data, ignore_index=True)
    
    if combined_trades_df.empty:
        print(f"No trades found")
        return None

    # Parse datetime for both dataframes
    for df in [combined_price_df, combined_trades_df]:
        df['Date'] = df['Date'].astype(str).str.zfill(6)
        df['Time'] = df['Time'].astype(str).str.zfill(6)
        df['datetime'] = pd.to_datetime(df['Date'] + df['Time'], format='%y%m%d%H%M%S')
    
    # Sort data by datetime to ensure correct plotting order
    combined_price_df = combined_price_df.sort_values('datetime')
    combined_trades_df = combined_trades_df.sort_values('datetime')

    # --- PnL Calculation ---
    initial_balance_usd = 0
    final_balance_usd = 0
    final_buy_hold_usd = 0
    
    if not combined_trades_df.empty and 'Total_Balance_USD' in combined_trades_df.columns:
        initial_balance_usd = combined_trades_df.iloc[0]['Total_Balance_USD']
        final_balance_usd = combined_trades_df.iloc[-1]['Total_Balance_USD']
        
        # Calculate final buy & hold value for overall comparison
        if len(combined_trades_df) > 0:
            last_trade = combined_trades_df.iloc[-1]
            first_trade = combined_trades_df.iloc[0]
            
            # Get the pair name from the last trade
            last_pair = last_trade['pair']
            token_symbol = last_pair.split('_')[0]
            usdc_symbol = last_pair.split('_')[1] if '_' in last_pair else 'USDC'
            
            # Get initial balances from first trade
            initial_token_balance = first_trade.get(f'{token_symbol}_Balance', 0)
            initial_usdc_balance = first_trade.get(f'{usdc_symbol}_Balance', 0)
            
            # Calculate final buy & hold value
            final_price = last_trade['Price']
            final_buy_hold_usd = (initial_token_balance * final_price) + (initial_usdc_balance * 1.0)

    algorithm_pnl = 0
    buy_hold_pnl = 0
    algorithm_outperformance = 0
    
    if initial_balance_usd > 0:
        algorithm_pnl = ((final_balance_usd - initial_balance_usd) / initial_balance_usd) * 100
        if final_buy_hold_usd > 0:
            buy_hold_pnl = ((final_buy_hold_usd - initial_balance_usd) / initial_balance_usd) * 100
            algorithm_outperformance = algorithm_pnl - buy_hold_pnl

    # --- Plotting ---
    unique_pairs = combined_trades_df['pair'].unique()
    fig, axes = plt.subplots(nrows=len(unique_pairs), ncols=1, figsize=(15, 6 * len(unique_pairs)), sharex=True)
    
    # Handle case with only one subplot
    if len(unique_pairs) == 1:
        axes = [axes]

    title = 'Trading Algorithm Performance vs Buy & Hold'
    if initial_balance_usd > 0:
        title += f'\nAlgorithm PnL: {algorithm_pnl:.2f}%'
        if final_buy_hold_usd > 0:
            title += f' | Buy & Hold PnL: {buy_hold_pnl:.2f}%'
            title += f' | Outperformance: {algorithm_outperformance:+.2f}%'
    
    fig.suptitle(title, fontsize=16, fontweight='bold')
    
    for ax, pair_name in zip(axes, unique_pairs):
        pair_price_df = combined_price_df[combined_price_df['pair'] == pair_name]
        pair_trades_df = combined_trades_df[combined_trades_df['pair'] == pair_name]
        
        # Create secondary y-axis for USD values
        ax2 = ax.twinx()
        
        # Plot price action on primary axis
        if not pair_price_df.empty:
            ax.plot(pair_price_df['datetime'], pair_price_df['Price'], 
                   label=f'{pair_name} Price', linewidth=1, color='blue')
        
        # Plot total USD balance on secondary axis
        if not pair_trades_df.empty and 'Total_Balance_USD' in pair_trades_df.columns:
            ax2.plot(pair_trades_df['datetime'], pair_trades_df['Total_Balance_USD'], 
                    label='Algorithm Balance', linewidth=2, color='orange', alpha=0.8)
            
            # Calculate and plot "Buy & Hold" baseline
            if len(pair_trades_df) > 0:
                # Get initial balances from first trade
                first_trade = pair_trades_df.iloc[0]
                
                # Extract the token symbol from pair name (e.g., 'RED' from 'RED_USDC')
                token_symbol = pair_name.split('_')[0]
                usdc_symbol = pair_name.split('_')[1] if '_' in pair_name else 'USDC'
                
                # Get initial token and USDC balances
                initial_token_balance = first_trade.get(f'{token_symbol}_Balance', 0)
                initial_usdc_balance = first_trade.get(f'{usdc_symbol}_Balance', 0)
                
                # Calculate buy & hold values for each trade timestamp
                buy_hold_values = []
                for _, trade in pair_trades_df.iterrows():
                    current_token_price = trade['Price']
                    # Buy & Hold value = initial_token_amount * current_price + initial_usdc_amount * 1
                    buy_hold_value = (initial_token_balance * current_token_price) + (initial_usdc_balance * 1.0)
                    buy_hold_values.append(buy_hold_value)
                
                # Plot buy & hold line
                ax2.plot(pair_trades_df['datetime'], buy_hold_values, 
                        label='Buy & Hold Baseline', linewidth=2, color='purple', 
                        linestyle='--', alpha=0.8)
        
        # Plot selloff indicators as vertical lines
        if pair_name in all_selloff_data:
            selloff_df = all_selloff_data[pair_name]
            for _, row in selloff_df.iterrows():
                action = row['action'].upper()
                color = 'green' if action == 'BUY' else 'red'
                alpha = 0.3
                linestyle = '-'
                
                # Plot vertical line spanning both axes
                ax.axvline(x=row['datetime'], color=color, alpha=alpha, 
                          linestyle=linestyle, linewidth=2, zorder=1)
                
                # Add text label at the top of the chart
                ax.text(row['datetime'], ax.get_ylim()[1], 
                       f" {action}", rotation=90, 
                       verticalalignment='top', color=color, 
                       fontweight='bold', fontsize=9, alpha=0.8)
        
        # Set labels and formatting
        ax.set_ylabel(f'{pair_name} Price', color='blue')
        ax2.set_ylabel('Total USD Balance', color='orange')
        ax.set_title(f'{pair_name} Price and Trades')
        ax.grid(True, linestyle='--', alpha=0.6)
        
        # Color the tick labels to match their respective y-axes
        ax.tick_params(axis='y', labelcolor='blue')
        ax2.tick_params(axis='y', labelcolor='orange')

        # Plot buy/sell trades on primary axis if they exist for this pair
        if not pair_trades_df.empty:
            buy_trades = pair_trades_df[pair_trades_df['Action'] == 'BUY']
            sell_trades = pair_trades_df[pair_trades_df['Action'] == 'SELL']
            
            if not buy_trades.empty:
                ax.scatter(buy_trades['datetime'], buy_trades['Price'], 
                          color='green', marker='^', s=100, label='Buy', zorder=5)
            if not sell_trades.empty:
                ax.scatter(sell_trades['datetime'], sell_trades['Price'], 
                          color='red', marker='v', s=100, label='Sell', zorder=5)
        
        # Align starting points for easier visual comparison
        if not pair_price_df.empty and not pair_trades_df.empty and 'Total_Balance_USD' in pair_trades_df.columns:
            # Get the first values to align starting points
            first_price = pair_trades_df.iloc[0]['Price']  # Use price from first trade
            first_usd = pair_trades_df.iloc[0]['Total_Balance_USD']
            
            # Calculate the range for each dataset including buy & hold values
            min_price = pair_price_df['Price'].min()
            max_price = pair_price_df['Price'].max()
            price_range = max_price - min_price
            price_padding = price_range * 0.1
            
            # Include buy & hold values in USD range calculation
            all_usd_values = list(pair_trades_df['Total_Balance_USD'])
            if len(pair_trades_df) > 0:
                # Add buy & hold values to range calculation
                first_trade = pair_trades_df.iloc[0]
                token_symbol = pair_name.split('_')[0]
                usdc_symbol = pair_name.split('_')[1] if '_' in pair_name else 'USDC'
                initial_token_balance = first_trade.get(f'{token_symbol}_Balance', 0)
                initial_usdc_balance = first_trade.get(f'{usdc_symbol}_Balance', 0)
                
                buy_hold_values = []
                for _, trade in pair_trades_df.iterrows():
                    buy_hold_value = (initial_token_balance * trade['Price']) + (initial_usdc_balance * 1.0)
                    buy_hold_values.append(buy_hold_value)
                
                all_usd_values.extend(buy_hold_values)
            
            min_usd = min(all_usd_values)
            max_usd = max(all_usd_values)
            usd_range = max_usd - min_usd if max_usd != min_usd else max_usd * 0.2
            usd_padding = usd_range * 0.1 if usd_range > 0 else first_usd * 0.1
            
            # Calculate scaling factor to align starting points
            # We want both lines to start at the same visual height
            price_bottom = min_price - price_padding
            price_top = max_price + price_padding
            price_visual_range = price_top - price_bottom
            
            # Calculate where the first price point should be proportionally
            first_price_ratio = (first_price - price_bottom) / price_visual_range
            
            # Set USD limits so that first_usd appears at the same visual ratio
            usd_visual_range = usd_range + (2 * usd_padding)
            usd_bottom = first_usd - (first_price_ratio * usd_visual_range)
            usd_top = usd_bottom + usd_visual_range
            
            # Apply the calculated limits
            ax.set_ylim(price_bottom, price_top)
            ax2.set_ylim(usd_bottom, usd_top)
        elif not pair_price_df.empty:
            # Fallback to original price scaling if USD data not available
            min_price = pair_price_df['Price'].min()
            max_price = pair_price_df['Price'].max()
            padding = (max_price - min_price) * 0.1
            ax.set_ylim(min_price - padding, max_price + padding)
        
        # Combine legends from both axes
        lines1, labels1 = ax.get_legend_handles_labels()
        lines2, labels2 = ax2.get_legend_handles_labels()
        ax.legend(lines1 + lines2, labels1 + labels2, loc='upper left')

    if len(unique_pairs) > 0:
        axes[-1].set_xlabel('Date')
        fig.autofmt_xdate()
        date_format = mdates.DateFormatter('%Y-%m-%d %H:%M')
        axes[-1].xaxis.set_major_formatter(date_format)

    output_filename = f'trades_chart.png'
    plt.tight_layout(rect=[0, 0.03, 1, 0.95])
    plt.savefig(output_filename, dpi=300, bbox_inches='tight')
    plt.close(fig)
    return output_filename

async def chart_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the /chart command to generate and send trade history chart."""
    await update.message.reply_text("🔄 Generating trade history chart. This may take a moment...")

    # Generate chart from all trade data in logs
    chart_filename = chartTrades(LOGS_DIR)
    
    if chart_filename:
        # Send the generated chart and then delete the file
        try:
            with open(chart_filename, 'rb') as f:
                await update.message.reply_photo(photo=f, caption="📊 Trade History Chart")
            os.remove(chart_filename)
        except FileNotFoundError:
            await update.message.reply_text("❌ Error: Could not find the generated chart file.")
        except Exception as e:
            await update.message.reply_text(f"❌ Error sending chart: {e}")
    else:
        await update.message.reply_text("❌ No trade data found. Please ensure there are trade log files in the logs directory.")

async def balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle balance requests using Binance API"""
    await update.message.reply_text("🔄 Fetching your Binance account balances...")
    
    balances = get_binance_balances()
    
    if balances is None:
        await update.message.reply_text(
            "❌ Failed to fetch balances from Binance API.\n\n"
            "Please check that:\n"
            "• BINANCE_API_KEY is set in environment variables\n"
            "• BINANCE_SECRET_KEY is set in environment variables\n"
            "• Your API keys have the correct permissions\n"
            "• Your API keys are valid"
        )
        return
    
    if not balances:
        await update.message.reply_text("💰 All balances are zero or no assets found.")
        return
    
    balance_text = "💰 **Binance Account Balances**\n\n"
    
    # Sort balances by total value (highest first)
    sorted_balances = sorted(balances.items(), key=lambda x: x[1]['total'], reverse=True)
    
    for symbol, info in sorted_balances:
        balance_text += f"💎 **{symbol}**: {info['total']:.8f}\n"
        if info['locked'] > 0:
            balance_text += f"   • Free: {info['free']:.8f}\n"
            balance_text += f"   • Locked: {info['locked']:.8f}\n"
    
    # Split message if too long
    if len(balance_text) > 4000:
        # Send in chunks
        chunks = [balance_text[i:i+4000] for i in range(0, len(balance_text), 4000)]
        for i, chunk in enumerate(chunks):
            if i == 0:
                await update.message.reply_text(chunk, parse_mode='Markdown')
            else:
                await update.message.reply_text(f"**Continued...**\n\n{chunk}", parse_mode='Markdown')
    else:
        await update.message.reply_text(balance_text, parse_mode='Markdown')

# --- Bot Setup ---

async def setup_commands(app):
    """Set up the bot commands menu"""
    commands = [
        BotCommand("balance", "💰 Check Binance account balances"),
        BotCommand("chart", "📈 View trade history chart from logs"),
    ]
    await app.bot.set_my_commands(commands)

async def post_init(app):
    await setup_commands(app)

def main():
    if not bot_token:
        print("Error: TELEGRAM_BOT_TOKEN not found in environment variables")
        return

    app = ApplicationBuilder().token(bot_token).post_init(post_init).build()
    
    # Add command handlers
    app.add_handler(CommandHandler("balance", balance))
    app.add_handler(CommandHandler("chart", chart_command))
    
    print("Simplified Trading Bot (Chart & Balance only) is running...")
    app.run_polling()

if __name__ == "__main__":
    main()
