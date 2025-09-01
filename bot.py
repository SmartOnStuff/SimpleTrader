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
    and generates a combined chart showing price action and buy/sell trades
    for all available cryptocurrency pairs.
    
    Args:
        log_dir (Path): The directory path where the log CSV files are located.
    """
    all_price_data = []
    all_trades_data = []

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

            # Load trade and price data for the current pair
            if not price_file_path.exists():
                print(f"Warning: Price file {price_file_path} not found for trades file {trade_file_path}")
                continue
                
            price_df = pd.read_csv(price_file_path)
            trades_df = pd.read_csv(trade_file_path)
            
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
    if not combined_trades_df.empty and 'Total_Balance_USD' in combined_trades_df.columns:
        initial_balance_usd = combined_trades_df.iloc[0]['Total_Balance_USD']
        final_balance_usd = combined_trades_df.iloc[-1]['Total_Balance_USD']

    pnl_percentage = 0
    if initial_balance_usd > 0:
        pnl_percentage = ((final_balance_usd - initial_balance_usd) / initial_balance_usd) * 100

    # --- Plotting ---
    unique_pairs = combined_trades_df['pair'].unique()
    fig, axes = plt.subplots(nrows=len(unique_pairs), ncols=1, figsize=(15, 6 * len(unique_pairs)), sharex=True)
    
    # Handle case with only one subplot
    if len(unique_pairs) == 1:
        axes = [axes]

    title = 'Trade History'
    if initial_balance_usd > 0:
        title += f'\nOverall PnL: {pnl_percentage:.2f}%'
    
    fig.suptitle(title, fontsize=16, fontweight='bold')
    
    for ax, pair_name in zip(axes, unique_pairs):
        pair_price_df = combined_price_df[combined_price_df['pair'] == pair_name]
        pair_trades_df = combined_trades_df[combined_trades_df['pair'] == pair_name]
        
        # Plot price action
        if not pair_price_df.empty:
            ax.plot(pair_price_df['datetime'], pair_price_df['Price'], label=f'{pair_name} Price', linewidth=1)
        ax.set_ylabel('Price')
        ax.set_title(f'{pair_name} Price and Trades')
        ax.grid(True, linestyle='--', alpha=0.6)

        # Plot buy/sell trades if they exist for this pair
        if not pair_trades_df.empty:
            buy_trades = pair_trades_df[pair_trades_df['Action'] == 'BUY']
            sell_trades = pair_trades_df[pair_trades_df['Action'] == 'SELL']
            
            if not buy_trades.empty:
                ax.scatter(buy_trades['datetime'], buy_trades['Price'], color='green', marker='^', s=100, label='Buy', zorder=5)
            if not sell_trades.empty:
                ax.scatter(sell_trades['datetime'], sell_trades['Price'], color='red', marker='v', s=100, label='Sell', zorder=5)
        
        ax.legend()
        if not pair_price_df.empty:
            min_price = pair_price_df['Price'].min()
            max_price = pair_price_df['Price'].max()
            padding = (max_price - min_price) * 0.1
            ax.set_ylim(min_price - padding, max_price + padding)

    if len(unique_pairs) > 0:
        axes[-1].set_xlabel('Date')
        fig.autofmt_xdate()
        date_format = mdates.DateFormatter('%Y-%m-%d %H:%M')
        axes[-1].xaxis.set_major_formatter(date_format)

    output_filename = f'trades_chart.png'
    plt.tight_layout(rect=[0, 0.03, 1, 0.95])
    plt.savefig(output_filename)
    plt.close(fig)
    return output_filename

# --- Command Handlers ---

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
