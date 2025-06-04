import csv, os, time, json
import logging
import requests
from datetime import datetime
from binance.client import Client
from binance.exceptions import BinanceAPIException
from dotenv import load_dotenv
from functools import wraps

# Add this after the logging setup in main():
os.makedirs('logs', exist_ok=True)
    
# Load environment variables from .env file
load_dotenv()

# Load environment variables
API_KEY = os.getenv('BINANCE_API_KEY')
API_SECRET = os.getenv('BINANCE_API_SECRET')
CONFIG_FILE = os.getenv('CONFIG_FILE', 'configmulti.json')
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
PRODUCTION = os.getenv('PRODUCTION', '0') == '1'  # Default to False if not set

# Initialize Binance client
client = Client(API_KEY, API_SECRET)

# Common USD stablecoins for price conversion
USD_STABLECOINS = ['USDT', 'USDC', 'BUSD', 'FDUSD']

# Global price cache to reduce API calls
class PriceCache:
    def __init__(self, ttl_seconds=60):
        self.cache = {}
        self.ttl = ttl_seconds
    
    def get_price(self, symbol):
        now = time.time()
        if symbol in self.cache:
            price, timestamp = self.cache[symbol]
            if now - timestamp < self.ttl:
                return price
        return None
    
    def set_price(self, symbol, price):
        self.cache[symbol] = (price, time.time())

price_cache = PriceCache()

def rate_limit(calls_per_second=10):
    """Rate limiting decorator to prevent API abuse."""
    min_interval = 1.0 / calls_per_second
    last_called = [0.0]
    
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            elapsed = time.time() - last_called[0]
            left_to_wait = min_interval - elapsed
            if left_to_wait > 0:
                time.sleep(left_to_wait)
            ret = func(*args, **kwargs)
            last_called[0] = time.time()
            return ret
        return wrapper
    return decorator

def setup_logging():
    """Setup logging for main operations and errors."""
    # Main log for successful operations
    main_logger = logging.getLogger('main')
    main_logger.setLevel(logging.INFO)
    main_handler = logging.FileHandler('logs/trading_main.log')
    main_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    main_handler.setFormatter(main_formatter)
    main_logger.addHandler(main_handler)
    
    # Error log for failures
    error_logger = logging.getLogger('errors')
    error_logger.setLevel(logging.ERROR)
    error_handler = logging.FileHandler('logs/trading_errors.log')
    error_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    error_handler.setFormatter(error_formatter)
    error_logger.addHandler(error_handler)  # FIXED: was error_logger before
    
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

@rate_limit(calls_per_second=5)
def get_usd_price(asset, depth=0, visited=None):
    """Get USD price for any asset with recursion protection."""
    # Initialize visited set to prevent infinite recursion
    if visited is None:
        visited = set()
    
    # Prevent infinite recursion
    if depth > 3 or asset in visited:
        error_logger.warning(f"Recursion depth exceeded or circular reference for {asset}")
        return 0.0
    
    visited.add(asset)
    
    # Check cache first
    cached_price = price_cache.get_price(f"{asset}_USD")
    if cached_price is not None:
        return cached_price
    
    if asset in USD_STABLECOINS:
        price_cache.set_price(f"{asset}_USD", 1.0)
        return 1.0
    
    # Try different USD pairs in order of preference
    for stablecoin in USD_STABLECOINS:
        try:
            symbol = f"{asset}{stablecoin}"
            ticker = client.get_symbol_ticker(symbol=symbol)
            price = float(ticker["price"])
            price_cache.set_price(f"{asset}_USD", price)
            return price
        except Exception as e:
            continue
    
    # If direct USD pair not found, try via BTC (only if not already looking for BTC)
    if asset != 'BTC' and 'BTC' not in visited:
        try:
            btc_price = get_usd_price('BTC', depth + 1, visited.copy())
            if btc_price > 0:
                asset_btc_symbol = f"{asset}BTC"
                asset_btc_ticker = client.get_symbol_ticker(symbol=asset_btc_symbol)
                price = float(asset_btc_ticker["price"]) * btc_price
                price_cache.set_price(f"{asset}_USD", price)
                return price
        except Exception as e:
            pass
    
    # Try via ETH (only if not already looking for ETH)
    if asset != 'ETH' and 'ETH' not in visited:
        try:
            eth_price = get_usd_price('ETH', depth + 1, visited.copy())
            if eth_price > 0:
                asset_eth_symbol = f"{asset}ETH"
                asset_eth_ticker = client.get_symbol_ticker(symbol=asset_eth_symbol)
                price = float(asset_eth_ticker["price"]) * eth_price
                price_cache.set_price(f"{asset}_USD", price)
                return price
        except Exception as e:
            pass
    
    error_logger.error(f"Could not get USD price for {asset}")
    return 0.0

def get_pair_symbol(base_asset, quote_asset):
    """Construct trading pair symbol from base and quote assets."""
    return f"{base_asset}{quote_asset}"

def calculate_total_balance_usd(base_asset, quote_asset, base_balance, quote_balance):
    """Calculate total balance in USD."""
    try:
        base_usd_price = get_usd_price(base_asset)
        quote_usd_price = get_usd_price(quote_asset)
        
        base_value_usd = base_balance * base_usd_price
        quote_value_usd = quote_balance * quote_usd_price
        
        return base_value_usd + quote_value_usd, base_usd_price, quote_usd_price
    except Exception as e:
        error_logger.error(f"Error calculating total balance for {base_asset}/{quote_asset}: {e}")
        return 0.0, 0.0, 0.0

def load_config():
    """Load trading pairs configuration from JSON file."""
    try:
        with open(CONFIG_FILE, 'r') as f:
            config = json.load(f)
        
        # Validate new config structure
        for pair in config['trading_pairs']:
            if 'symbol1' not in pair or 'symbol2' not in pair:
                raise ValueError("Config must have 'symbol1' and 'symbol2' fields")
        
        main_logger.info(f"Loaded configuration for {len(config['trading_pairs'])} trading pairs")
        return config['trading_pairs']
    except FileNotFoundError:
        error_logger.error(f"Configuration file {CONFIG_FILE} not found")
        return []
    except (json.JSONDecodeError, ValueError) as e:
        error_logger.error(f"Invalid configuration file: {e}")
        return []

@rate_limit(calls_per_second=5)
def get_price(base_asset, quote_asset):
    """Return (date_str, time_str, price) for given trading pair."""
    try:
        symbol = get_pair_symbol(base_asset, quote_asset)
        
        # Check cache first
        cached_price = price_cache.get_price(symbol)
        if cached_price is not None:
            return time.strftime("%y%m%d"), time.strftime("%H%M%S"), cached_price
        
        ticker = client.get_symbol_ticker(symbol=symbol)
        price = float(ticker["price"])
        price_cache.set_price(symbol, price)
        return time.strftime("%y%m%d"), time.strftime("%H%M%S"), price
    except BinanceAPIException as e:
        raise Exception(f"Failed to get price for {base_asset}/{quote_asset}: {e}")

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

def store_price(base_asset, quote_asset, date_str, time_str, price, base_flag):
    """Append to BASE_QUOTE.csv: ID,Date,Time,Price,Base."""
    fn = f"logs/{base_asset}_{quote_asset}.csv"
    row_id = get_last_id(fn)
    row = [f"{row_id:06d}", date_str, time_str, f"{price:.6f}", base_flag]
    is_new = not os.path.isfile(fn)

    with open(fn, "a", newline="") as f:
        w = csv.writer(f)
        if is_new:
            w.writerow(["ID", "Date", "Time", "Price", "Base"])
        w.writerow(row)

def get_base_price(base_asset, quote_asset):
    """Return the last logged Base price, or None if none yet."""
    fn = f"logs/{base_asset}_{quote_asset}.csv"
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

def get_last_trade_action(base_asset, quote_asset):
    """Get the last trade action and consecutive count for multiplier calculation."""
    fn = f"logs/{base_asset}_{quote_asset}_trades.csv"
    if not os.path.isfile(fn):
        return None, 0
    
    try:
        with open(fn, "r", newline="") as f:
            rows = list(csv.reader(f))
        
        if len(rows) < 2:  # No trades yet (only header or empty)
            return None, 0
        
        # Get the last trade
        last_row = rows[-1]
        if len(last_row) < 15:  # Old format without consecutive count
            return last_row[3], 0  # Return action, count=0
        
        last_action = last_row[3]  # Action column
        consecutive_count = int(last_row[14])  # Consecutive_Count column
        
        return last_action, consecutive_count
        
    except (ValueError, IndexError) as e:
        error_logger.error(f"Error reading last trade for {base_asset}/{quote_asset}: {e}")
        return None, 0

@rate_limit(calls_per_second=5)
def get_balances(base_asset, quote_asset):
    """Return (base_balance, quote_balance) for given assets."""
    try:
        account_info = client.get_account()
        balances = {b["asset"]: float(b["free"]) for b in account_info["balances"]}
        
        base_balance = balances.get(base_asset, 0.0)
        quote_balance = balances.get(quote_asset, 0.0)
        
        return base_balance, quote_balance
    except BinanceAPIException as e:
        raise Exception(f"Failed to get balances for {base_asset}/{quote_asset}: {e}")

def calculate_multiplied_trade_percentage(base_percentage, multiplier, current_action, last_action, last_consecutive_count):
    """Calculate trade percentage with multiplier for consecutive same-direction trades."""
    if last_action == current_action:
        # Same direction trade - apply multiplier
        consecutive_count = last_consecutive_count + 1
        multiplied_percentage = base_percentage * (multiplier ** consecutive_count)
        # Cap at 50% to avoid excessive trades
        actual_percentage = min(multiplied_percentage, 0.5)
        return actual_percentage, consecutive_count
    else:
        # Different direction or first trade - use base percentage
        return base_percentage, 0

def log_trade(base_asset, quote_asset, action, date_str, time_str, price, qty, 
              base_balance, quote_balance, total_balance_usd, base_usd_price, quote_usd_price,
              consecutive_count, actual_trade_percentage):
    """Append to BASE_QUOTE_trades.csv with all trade details including USD values and multiplier info."""
    fn = f"logs/{base_asset}_{quote_asset}_trades.csv"
    row_id = get_last_id(fn)
    
    # Calculate USD values
    base_value_usd = base_balance * base_usd_price
    quote_value_usd = quote_balance * quote_usd_price
    trade_value_usd = qty * price * quote_usd_price if action == "SELL" else qty * base_usd_price
    
    row = [
        f"{row_id:06d}",
        date_str, time_str,
        action,
        f"{price:.6f}",
        f"{qty:.6f}",
        f"{base_balance:.6f}",
        f"{quote_balance:.6f}",
        f"{base_usd_price:.6f}",
        f"{quote_usd_price:.6f}",
        f"{base_value_usd:.2f}",
        f"{quote_value_usd:.2f}",
        f"{trade_value_usd:.2f}",
        f"{total_balance_usd:.2f}",
        f"{consecutive_count}",
        f"{actual_trade_percentage:.6f}",
    ]
    is_new = not os.path.isfile(fn)

    with open(fn, "a", newline="") as f:
        w = csv.writer(f)
        if is_new:
            w.writerow([
                "ID", "Date", "Time", "Action",
                "Price", "Quantity",
                f"{base_asset}_Balance", f"{quote_asset}_Balance",
                f"{base_asset}_USD_Price", f"{quote_asset}_USD_Price",
                f"{base_asset}_USD_Value", f"{quote_asset}_USD_Value",
                "Trade_USD_Value", "Total_Balance_USD",
                "Consecutive_Count", "Actual_Trade_Percentage"
            ])
        w.writerow(row)

@rate_limit(calls_per_second=2)
def execute_trade(base_asset, quote_asset, action, quantity, decimal_places):
    """Execute trade on Binance."""
    symbol = get_pair_symbol(base_asset, quote_asset)
    
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

def calculate_trade_amounts(action, base_balance, quote_balance, price, trade_percentage, 
                          max_amount, minimum_amount, base_usd_price, quote_usd_price):
    """Calculate trade quantity and value, applying limits. All limits are in USD."""
    if action == "SELL":
        # Selling base asset
        qty_from_percentage = base_balance * trade_percentage
        # Convert max_amount from USD to base asset quantity
        max_qty_allowed = (max_amount / base_usd_price) if max_amount > 0 else float('inf')
        qty = min(qty_from_percentage, max_qty_allowed)
        # Trade value in USD
        trade_value_usd = qty * base_usd_price
    else:  # BUY
        # Buying base asset with quote
        quote_to_trade = quote_balance * trade_percentage
        # Convert max_amount from USD to quote asset
        quote_max_allowed = (max_amount / quote_usd_price) if max_amount > 0 else float('inf')
        quote_to_trade = min(quote_to_trade, quote_max_allowed)
        qty = quote_to_trade / price
        # Trade value in USD
        trade_value_usd = quote_to_trade * quote_usd_price
    
    meets_minimum = trade_value_usd >= minimum_amount
    return qty, trade_value_usd, meets_minimum

def calculate_new_balances(action, base_balance, quote_balance, qty, price):
    """Calculate balances after trade execution."""
    if action == "SELL":
        new_base_balance = base_balance - qty
        new_quote_balance = quote_balance + (qty * price)
    else:  # BUY
        new_base_balance = base_balance + qty
        new_quote_balance = quote_balance - (qty * price)
    
    return new_base_balance, new_quote_balance

def send_trade_notification(base_asset, quote_asset, action, qty, trade_value_usd, base_price, current_price, move_pct, 
                           new_base_balance, new_quote_balance, total_balance_usd, date_str, consecutive_count, actual_trade_percentage):
    """Send Telegram notification for executed trade."""
    mode_text = "🔴 PRODUCTION" if PRODUCTION else "🟡 SIMULATION"
    direction_emoji = "📉" if action == "BUY" else "📈"
    
    # Add multiplier info if consecutive trades
    multiplier_text = ""
    if consecutive_count > 0:
        multiplier_text = f"\n<b>🔥 Consecutive #{consecutive_count + 1}:</b> {actual_trade_percentage*100:.2f}% trade size"
    
    message = f"""
{mode_text} TRADE EXECUTED {direction_emoji}

<b>Pair:</b> {base_asset}/{quote_asset}
<b>Action:</b> {action} {base_asset}
<b>Amount:</b> {qty:.6f} {base_asset}
<b>Trade Value:</b> ${trade_value_usd:.2f}{multiplier_text}

<b>Base Price:</b> {base_price:.6f} {quote_asset} ({date_str})
<b>Current Price:</b> {current_price:.6f} {quote_asset}
<b>Price Change:</b> {move_pct*100:+.2f}%

<b>Current Balances:</b>
• {base_asset}: {new_base_balance:.6f}
• {quote_asset}: {new_quote_balance:.6f}
• <b>Total USD: ${total_balance_usd:.2f}</b>
"""
    send_telegram_message(message)

def process_trade_signal(base_asset, quote_asset, action, date_str, time_str, price, base_balance, quote_balance, 
                        base_trade_percentage, multiplier, max_amount, minimum_amount, decimal_places, base_price, move_pct,
                        base_usd_price, quote_usd_price):
    """Process a trade signal (BUY or SELL) with multiplier logic."""
    
    # Get last trade info for multiplier calculation
    last_action, last_consecutive_count = get_last_trade_action(base_asset, quote_asset)
    
    # Calculate actual trade percentage with multiplier
    actual_trade_percentage, consecutive_count = calculate_multiplied_trade_percentage(
        base_trade_percentage, multiplier, action, last_action, last_consecutive_count
    )
    
    # Calculate trade amounts using the multiplied percentage
    qty, trade_value_usd, meets_minimum = calculate_trade_amounts(
        action, base_balance, quote_balance, price, actual_trade_percentage, max_amount, minimum_amount,
        base_usd_price, quote_usd_price
    )
    
    if not meets_minimum:
        # Trade too small, just update base
        store_price(base_asset, quote_asset, date_str, time_str, price, base_flag=1)
        main_logger.info(f"[{base_asset}/{quote_asset}] Trade too small (${trade_value_usd:.2f} < ${minimum_amount}) → new base set, no trade")
        return True
    
    # Calculate new balances
    new_base_balance, new_quote_balance = calculate_new_balances(action, base_balance, quote_balance, qty, price)
    total_balance_usd, _, _ = calculate_total_balance_usd(base_asset, quote_asset, new_base_balance, new_quote_balance)
    
    # Execute trade
    try:
        order = execute_trade(base_asset, quote_asset, action, qty, decimal_places)
        
        # Log trade with multiplier info and update base price
        log_trade(base_asset, quote_asset, action, date_str, time_str, price, qty, 
                 new_base_balance, new_quote_balance, total_balance_usd, base_usd_price, quote_usd_price,
                 consecutive_count, actual_trade_percentage)
        store_price(base_asset, quote_asset, date_str, time_str, price, base_flag=1)
        
        # Send notification with multiplier info
        send_trade_notification(base_asset, quote_asset, action, qty, trade_value_usd, base_price, price, move_pct,
                              new_base_balance, new_quote_balance, total_balance_usd, date_str, consecutive_count, actual_trade_percentage)
        
        action_text = f"{'SOLD' if action == 'SELL' else 'BOUGHT'}" if PRODUCTION else f"SIMULATED {action}"
        multiplier_info = f" (consecutive #{consecutive_count + 1}, {actual_trade_percentage*100:.2f}%)" if consecutive_count > 0 else ""
        main_logger.info(f"[{base_asset}/{quote_asset}] {action_text} {qty:.6f} for ${trade_value_usd:.2f} at {price:.6f}{multiplier_info} → new base")
        
        return True
        
    except Exception as e:
        error_logger.error(f"[{base_asset}/{quote_asset}] Failed to execute {action} trade: {e}")
        return False

def process_trading_pair(pair_config):
    """Process a single trading pair based on its configuration."""
    base_asset = pair_config['symbol1']
    quote_asset = pair_config['symbol2']
    base_trade_percentage = pair_config['trade_percentage']
    multiplier = pair_config.get('multiplier', 1.1)  # Default to 1.1
    trigger_percentage = pair_config['trigger_percentage']
    max_amount = pair_config.get('max_amount', 0)  # 0 means no limit, in USD
    minimum_amount = pair_config.get('minimum_amount', 0)  # in USD
    decimal_places = pair_config.get('decimal', 6)
    
    try:
        date_str, time_str, price = get_price(base_asset, quote_asset)
        base_price = get_base_price(base_asset, quote_asset)

        # If no base yet → set it, no trade
        if base_price is None:
            store_price(base_asset, quote_asset, date_str, time_str, price, base_flag=1)
            main_logger.info(f"[{base_asset}/{quote_asset}] Base price initialized to {price:.6f}")
            return True

        move_pct = (price - base_price) / base_price
        base_balance, quote_balance = get_balances(base_asset, quote_asset)
        
        # Get USD prices for both assets
        total_balance_usd, base_usd_price, quote_usd_price = calculate_total_balance_usd(
            base_asset, quote_asset, base_balance, quote_balance
        )

        # Check for trade signals
        if move_pct >= trigger_percentage:
            # Price increased → SELL base asset
            return process_trade_signal(base_asset, quote_asset, "SELL", date_str, time_str, price, 
                                      base_balance, quote_balance, base_trade_percentage, multiplier, max_amount, minimum_amount, 
                                      decimal_places, base_price, move_pct, base_usd_price, quote_usd_price)
            
        elif move_pct <= -trigger_percentage:
            # Price decreased → BUY base asset
            return process_trade_signal(base_asset, quote_asset, "BUY", date_str, time_str, price, 
                                      base_balance, quote_balance, base_trade_percentage, multiplier, max_amount, minimum_amount, 
                                      decimal_places, base_price, move_pct, base_usd_price, quote_usd_price)
        else:
            # No trade (within trigger range)
            store_price(base_asset, quote_asset, date_str, time_str, price, base_flag=0)
            main_logger.info(f"[{base_asset}/{quote_asset}] No trade. Price logged at {price:.6f}")
            return True

    except Exception as e:
        error_logger.error(f"[{base_asset}/{quote_asset}] Error processing trading pair: {str(e)}")
        return False

def validate_trading_pair(pair_config):
    """Validate a trading pair configuration before processing."""
    required_fields = ['symbol1', 'symbol2', 'trade_percentage', 'trigger_percentage']
    for field in required_fields:
        if field not in pair_config:
            error_logger.error(f"Missing required field '{field}' in trading pair config")
            return False
    
    # Validate percentage values
    if not (0 < pair_config['trade_percentage'] <= 1):
        error_logger.error(f"Invalid trade_percentage: {pair_config['trade_percentage']}. Must be between 0 and 1")
        return False
    
    if not (0 < pair_config['trigger_percentage'] <= 1):
        error_logger.error(f"Invalid trigger_percentage: {pair_config['trigger_percentage']}. Must be between 0 and 1")
        return False
    
    return True

def main():
    """Main function to process all trading pairs."""
    global main_logger, error_logger
    main_logger, error_logger = setup_logging()
    
    # Validate environment variables
    if not API_KEY or not API_SECRET:
        error_logger.error("Missing BINANCE_API_KEY or BINANCE_API_SECRET environment variables")
        print("ERROR: Please set BINANCE_API_KEY and BINANCE_API_SECRET environment variables")
        return

    # Test Binance connection
    try:
        client.ping()
        main_logger.info("Successfully connected to Binance API")
    except Exception as e:
        error_logger.error(f"Failed to connect to Binance API: {e}")
        print(f"ERROR: Cannot connect to Binance API: {e}")
        return

    # Load configuration
    trading_pairs = load_config()
    if not trading_pairs:
        error_logger.error("No trading pairs loaded from configuration")
        print("ERROR: No trading pairs found in configuration")
        return

    # Validate all trading pairs before processing
    valid_pairs = []
    for pair_config in trading_pairs:
        if validate_trading_pair(pair_config):
            valid_pairs.append(pair_config)
        else:
            error_logger.error(f"Invalid configuration for pair: {pair_config}")

    if not valid_pairs:
        error_logger.error("No valid trading pairs found")
        print("ERROR: No valid trading pairs found")
        return

    mode_text = "PRODUCTION" if PRODUCTION else "SIMULATION"
    main_logger.info(f"Starting trading session in {mode_text} mode with {len(valid_pairs)} pairs")
    
    successful_pairs = 0
    failed_pairs = 0

    # Process each valid trading pair
    for pair_config in valid_pairs:
        base_asset = pair_config.get('symbol1', 'UNKNOWN')
        quote_asset = pair_config.get('symbol2', 'UNKNOWN')
        main_logger.info(f"Processing {base_asset}/{quote_asset}...")
        
        try:
            if process_trading_pair(pair_config):
                successful_pairs += 1
                main_logger.info(f"[{base_asset}/{quote_asset}] Successfully processed")
            else:
                failed_pairs += 1
                error_logger.error(f"[{base_asset}/{quote_asset}] Processing failed")
        except Exception as e:
            failed_pairs += 1
            error_logger.error(f"[{base_asset}/{quote_asset}] Unexpected error: {e}")
        
        # Add small delay between pairs to respect rate limits
        time.sleep(0.5)

    # Summary
    main_logger.info(f"Trading session completed: {successful_pairs} successful, {failed_pairs} failed")
    
    if failed_pairs > 0:
        print(f"Check trading_errors.log for details on {failed_pairs} failed pairs")
    
    print(f"Trading session completed successfully. {successful_pairs} pairs processed, {failed_pairs} failed.")

if __name__ == "__main__":
    main()
