import csv, os, time, json
import logging
import requests
from datetime import datetime
from binance.client import Client
from binance.exceptions import BinanceAPIException
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Load environment variables
API_KEY = os.getenv('BINANCE_API_KEY')
API_SECRET = os.getenv('BINANCE_API_SECRET')
CONFIG_FILE = os.getenv('CONFIG_FILE', 'config.json')
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
PRODUCTION = os.getenv('PRODUCTION', '0') == '1'  # Default to False if not set

# Initialize Binance client
client = Client(API_KEY, API_SECRET)

# Common USD stablecoins for price conversion
USD_STABLECOINS = ['USDT', 'USDC', 'BUSD', 'FDUSD']

def setup_logging():
    """Setup logging for main operations and errors."""
    # Main log for successful operations
    main_logger = logging.getLogger('main')
    main_logger.setLevel(logging.INFO)
    main_handler = logging.FileHandler('trading_main.log')
    main_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    main_handler.setFormatter(main_formatter)
    main_logger.addHandler(main_handler)
    
    # Error log for failures
    error_logger = logging.getLogger('errors')
    error_logger.setLevel(logging.ERROR)
    error_handler = logging.FileHandler('trading_errors.log')
    error_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    error_handler.setFormatter(error_formatter)
    error_logger.addHandler(error_handler)
    
    return main_logger, error_logger

def send_telegram_message(message):
    """Send message to Telegram chat."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        error_logger.error("Telegram credentials not configured")
        return False
    
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        data = {
            'chat_id': TELEGRAM_CHAT_ID,
            'text': message,
            'parse_mode': 'HTML'
        }
        response = requests.post(url, data=data, timeout=10)
        response.raise_for_status()
        return True
    except Exception as e:
        error_logger.error(f"Failed to send Telegram message: {e}")
        return False

def parse_symbol_assets(symbol):
    """Parse symbol to extract base and quote assets."""
    # Try common stablecoins first (longer matches first)
    for stablecoin in sorted(USD_STABLECOINS, key=len, reverse=True):
        if symbol.endswith(stablecoin):
            base = symbol[:-len(stablecoin)]
            quote = stablecoin
            return base, quote
    
    # Try common crypto pairs
    common_quotes = ['BTC', 'ETH', 'BNB']
    for quote in common_quotes:
        if symbol.endswith(quote):
            base = symbol[:-len(quote)]
            return base, quote
    
    # Fallback - assume last 3-4 characters are quote
    if len(symbol) >= 6:
        # Try 4 char quote first, then 3 char
        for quote_len in [4, 3]:
            if len(symbol) > quote_len:
                base = symbol[:-quote_len]
                quote = symbol[-quote_len:]
                return base, quote
    
    raise ValueError(f"Cannot parse symbol: {symbol}")

def get_usd_price(asset):
    """Get USD price for any asset."""
    if asset in USD_STABLECOINS:
        return 1.0
    
    # Try different USD pairs
    for stablecoin in USD_STABLECOINS:
        try:
            ticker = client.get_symbol_ticker(symbol=f"{asset}{stablecoin}")
            return float(ticker["price"])
        except:
            continue
    
    # If direct USD pair not found, try via BTC
    try:
        btc_price = get_usd_price('BTC')
        asset_btc_ticker = client.get_symbol_ticker(symbol=f"{asset}BTC")
        return float(asset_btc_ticker["price"]) * btc_price
    except:
        pass
    
    return 0.0

def calculate_total_balance_usd(base_asset, quote_asset, base_balance, quote_balance):
    """Calculate total balance in USD."""
    try:
        base_usd_price = get_usd_price(base_asset)
        quote_usd_price = get_usd_price(quote_asset)
        
        base_value_usd = base_balance * base_usd_price
        quote_value_usd = quote_balance * quote_usd_price
        
        return base_value_usd + quote_value_usd
    except Exception as e:
        error_logger.error(f"Error calculating total balance for {base_asset}/{quote_asset}: {e}")
        return 0.0

def load_config():
    """Load trading pairs configuration from JSON file."""
    try:
        with open(CONFIG_FILE, 'r') as f:
            config = json.load(f)
        main_logger.info(f"Loaded configuration for {len(config['trading_pairs'])} trading pairs")
        return config['trading_pairs']
    except FileNotFoundError:
        error_logger.error(f"Configuration file {CONFIG_FILE} not found")
        return []
    except json.JSONDecodeError as e:
        error_logger.error(f"Invalid JSON in configuration file: {e}")
        return []

def get_price(symbol):
    """Return (date_str, time_str, price) for given symbol."""
    try:
        ticker = client.get_symbol_ticker(symbol=symbol)
        price = float(ticker["price"])
        return time.strftime("%y%m%d"), time.strftime("%H%M%S"), price
    except BinanceAPIException as e:
        raise Exception(f"Failed to get price for {symbol}: {e}")

def get_last_id(file_path):
    """Return next ID (1-based) by scanning existing CSV, zero-pad to 6 digits."""
    if not os.path.isfile(file_path):
        return 1
    try:
        with open(file_path, "r", newline="") as f:
            rows = list(csv.reader(f))
        if len(rows) < 2:
            return 1
        return int(rows[-1][0]) + 1
    except (ValueError, IndexError):
        return 1

def store_price(symbol, date_str, time_str, price, base_flag):
    """Append to SYMBOL.csv: ID,Date,Time,Price,Base."""
    fn = f"{symbol}.csv"
    row_id = get_last_id(fn)
    row = [f"{row_id:06d}", date_str, time_str, f"{price:.6f}", base_flag]
    is_new = not os.path.isfile(fn)

    with open(fn, "a", newline="") as f:
        w = csv.writer(f)
        if is_new:
            w.writerow(["ID", "Date", "Time", "Price", "Base"])
        w.writerow(row)

def get_base_price(symbol):
    """Return the last logged Base price, or None if none yet."""
    fn = f"{symbol}.csv"
    if not os.path.isfile(fn):
        return None

    try:
        with open(fn, "r", newline="") as f:
            rows = list(csv.reader(f))
        # pick the last row where Base == '1'
        base_rows = [r for r in rows[1:] if len(r) > 4 and r[4] == "1"]
        if not base_rows:
            return None
        return float(base_rows[-1][3])
    except (ValueError, IndexError):
        return None

def get_balances(symbol):
    """Return (base_balance, quote_balance) for given symbol."""
    try:
        base_asset, quote_asset = parse_symbol_assets(symbol)
        
        account_info = client.get_account()
        balances = {b["asset"]: float(b["free"]) for b in account_info["balances"]}
        
        base_balance = balances.get(base_asset, 0.0)
        quote_balance = balances.get(quote_asset, 0.0)
        
        return base_balance, quote_balance
    except BinanceAPIException as e:
        raise Exception(f"Failed to get balances for {symbol}: {e}")

def log_trade(symbol, action, date_str, time_str, price, qty, base_balance, quote_balance, total_balance_usd):
    """Append to SYMBOL_trades.csv with all trade details."""
    fn = f"{symbol}_trades.csv"
    row_id = get_last_id(fn)
    
    base_asset, quote_asset = parse_symbol_assets(symbol)
    
    row = [
        f"{row_id:06d}",
        date_str, time_str,
        action,
        f"{price:.6f}",
        f"{qty:.6f}",
        f"{base_balance:.6f}",
        f"{quote_balance:.6f}",
        f"{total_balance_usd:.2f}",
    ]
    is_new = not os.path.isfile(fn)

    with open(fn, "a", newline="") as f:
        w = csv.writer(f)
        if is_new:
            w.writerow([
                "ID", "Date", "Time", "Action",
                "Price", "Quantity",
                f"{base_asset}_Balance", f"{quote_asset}_Balance", "Total_Balance_USD"
            ])
        w.writerow(row)

def execute_trade(symbol, action, quantity, decimal_places):
    """Execute trade on Binance."""
    if not PRODUCTION:
        return {"status": "SIMULATION", "symbol": symbol, "side": action, "quantity": quantity}
    
    try:
        rounded_qty = round(quantity, decimal_places)
        if action == "BUY":
            order = client.order_market_buy(symbol=symbol, quantity=rounded_qty)
        elif action == "SELL":
            order = client.order_market_sell(symbol=symbol, quantity=rounded_qty)
        else:
            raise ValueError(f"Invalid action: {action}")
        
        main_logger.info(f"[{symbol}] PRODUCTION: Order executed - {order}")
        return order
    except BinanceAPIException as e:
        error_logger.error(f"[{symbol}] Failed to execute {action} order: {e}")
        raise

def calculate_trade_amounts(action, base_balance, quote_balance, price, trade_percentage, max_amount, minimum_amount):
    """Calculate trade quantity and value, applying limits."""
    if action == "SELL":
        # Selling base asset
        qty_from_percentage = base_balance * trade_percentage
        max_qty_allowed = max_amount / price if max_amount > 0 else float('inf')
        qty = min(qty_from_percentage, max_qty_allowed)
        trade_value = qty * price
    else:  # BUY
        # Buying base asset with quote
        quote_to_trade = quote_balance * trade_percentage
        quote_to_trade = min(quote_to_trade, max_amount) if max_amount > 0 else quote_to_trade
        qty = quote_to_trade / price
        trade_value = quote_to_trade
    
    meets_minimum = trade_value >= minimum_amount
    return qty, trade_value, meets_minimum

def calculate_new_balances(action, base_balance, quote_balance, qty, price):
    """Calculate balances after trade execution."""
    if action == "SELL":
        new_base_balance = base_balance - qty
        new_quote_balance = quote_balance + (qty * price)
    else:  # BUY
        new_base_balance = base_balance + qty
        new_quote_balance = quote_balance - (qty * price)
    
    return new_base_balance, new_quote_balance

def send_trade_notification(symbol, action, qty, trade_value, base_price, current_price, move_pct, 
                           new_base_balance, new_quote_balance, total_balance_usd, date_str):
    """Send Telegram notification for executed trade."""
    base_asset, quote_asset = parse_symbol_assets(symbol)
    mode_text = "🔴 PRODUCTION" if PRODUCTION else "🟡 SIMULATION"
    direction_emoji = "📉" if action == "BUY" else "📈"
    
    # Format price display based on quote asset
    if quote_asset in USD_STABLECOINS:
        price_format = f"${current_price:.6f}"
        base_price_format = f"${base_price:.6f}"
    else:
        price_format = f"{current_price:.6f} {quote_asset}"
        base_price_format = f"{base_price:.6f} {quote_asset}"
    
    message = f"""
{mode_text} TRADE EXECUTED {direction_emoji}

<b>Pair:</b> {symbol}
<b>Action:</b> {action} {base_asset}
<b>Amount:</b> {qty:.6f} {base_asset} (${trade_value:.2f})

<b>Base Price:</b> {base_price_format} ({date_str})
<b>Current Price:</b> {price_format}
<b>Price Change:</b> {move_pct*100:+.2f}%

<b>Current Balances:</b>
• {base_asset}: {new_base_balance:.6f}
• {quote_asset}: {new_quote_balance:.6f}
• <b>Total USD: ${total_balance_usd:.2f}</b>
"""
    send_telegram_message(message)

def process_trade_signal(symbol, action, date_str, time_str, price, base_balance, quote_balance, 
                        trade_percentage, max_amount, minimum_amount, decimal_places, base_price, move_pct):
    """Process a trade signal (BUY or SELL)."""
    base_asset, quote_asset = parse_symbol_assets(symbol)
    
    # Calculate trade amounts
    qty, trade_value, meets_minimum = calculate_trade_amounts(
        action, base_balance, quote_balance, price, trade_percentage, max_amount, minimum_amount
    )
    
    if not meets_minimum:
        # Trade too small, just update base
        store_price(symbol, date_str, time_str, price, base_flag=1)
        main_logger.info(f"[{symbol}] Trade too small (${trade_value:.2f} < ${minimum_amount}) → new base set, no trade")
        return True
    
    # Calculate new balances
    new_base_balance, new_quote_balance = calculate_new_balances(action, base_balance, quote_balance, qty, price)
    total_balance_usd = calculate_total_balance_usd(base_asset, quote_asset, new_base_balance, new_quote_balance)
    
    # Execute trade
    try:
        order = execute_trade(symbol, action, qty, decimal_places)
        
        # Log trade and update base price
        log_trade(symbol, action, date_str, time_str, price, qty, new_base_balance, new_quote_balance, total_balance_usd)
        store_price(symbol, date_str, time_str, price, base_flag=1)
        
        # Send notification
        send_trade_notification(symbol, action, qty, trade_value, base_price, price, move_pct,
                              new_base_balance, new_quote_balance, total_balance_usd, date_str)
        
        action_text = f"{'SOLD' if action == 'SELL' else 'BOUGHT'}" if PRODUCTION else f"SIMULATED {action}"
        main_logger.info(f"[{symbol}] {action_text} {qty:.6f} for ${trade_value:.2f} at {price:.6f} → new base")
        
        return True
        
    except Exception as e:
        error_logger.error(f"[{symbol}] Failed to execute {action} trade: {e}")
        return False

def process_trading_pair(pair_config):
    """Process a single trading pair based on its configuration."""
    symbol = pair_config['symbol']
    trade_percentage = pair_config['trade_percentage']
    trigger_percentage = pair_config['trigger_percentage']
    max_amount = pair_config.get('max_amount', 0)  # 0 means no limit
    minimum_amount = pair_config.get('minimum_amount', 0)
    decimal_places = pair_config.get('decimal', 6)
    
    try:
        date_str, time_str, price = get_price(symbol)
        base_price = get_base_price(symbol)

        # If no base yet → set it, no trade
        if base_price is None:
            store_price(symbol, date_str, time_str, price, base_flag=1)
            main_logger.info(f"[{symbol}] Base price initialized to {price:.6f}")
            return True

        move_pct = (price - base_price) / base_price
        base_balance, quote_balance = get_balances(symbol)

        # Check for trade signals
        if move_pct >= trigger_percentage:
            # Price increased → SELL base asset
            return process_trade_signal(symbol, "SELL", date_str, time_str, price, base_balance, quote_balance,
                                      trade_percentage, max_amount, minimum_amount, decimal_places, base_price, move_pct)
            
        elif move_pct <= -trigger_percentage:
            # Price decreased → BUY base asset
            return process_trade_signal(symbol, "BUY", date_str, time_str, price, base_balance, quote_balance,
                                      trade_percentage, max_amount, minimum_amount, decimal_places, base_price, move_pct)
        else:
            # No trade (within trigger range)
            store_price(symbol, date_str, time_str, price, base_flag=0)
            main_logger.info(f"[{symbol}] No trade. Price logged at {price:.6f}")
            return True

    except Exception as e:
        error_logger.error(f"[{symbol}] Error processing trading pair: {str(e)}")
        return False

def main():
    """Main function to process all trading pairs."""
    global main_logger, error_logger
    main_logger, error_logger = setup_logging()
    
    # Validate environment variables
    if not API_KEY or not API_SECRET:
        error_logger.error("Missing BINANCE_API_KEY or BINANCE_API_SECRET environment variables")
        print("ERROR: Please set BINANCE_API_KEY and BINANCE_API_SECRET environment variables")
        return

    # Load configuration
    trading_pairs = load_config()
    if not trading_pairs:
        error_logger.error("No trading pairs loaded from configuration")
        print("ERROR: No trading pairs found in configuration")
        return

    mode_text = "PRODUCTION" if PRODUCTION else "SIMULATION"
    main_logger.info(f"Starting trading session in {mode_text} mode with {len(trading_pairs)} pairs")
    
    successful_pairs = 0
    failed_pairs = 0

    # Process each trading pair
    for pair_config in trading_pairs:
        symbol = pair_config.get('symbol', 'UNKNOWN')
        main_logger.info(f"Processing {symbol}...")
        
        if process_trading_pair(pair_config):
            successful_pairs += 1
        else:
            failed_pairs += 1

    # Summary
    main_logger.info(f"Trading session completed: {successful_pairs} successful, {failed_pairs} failed")
    
    if failed_pairs > 0:
        print(f"Check trading_errors.log for details on {failed_pairs} failed pairs")

if __name__ == "__main__":
    main()