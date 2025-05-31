import csv, os, time, json
import logging
import requests
from datetime import datetime
from binance.client import Client
from binance.exceptions import BinanceAPIException

# Load environment variables
API_KEY = os.getenv('BINANCE_API_KEY')
API_SECRET = os.getenv('BINANCE_API_SECRET')
CONFIG_FILE = os.getenv('CONFIG_FILE', 'config.json')
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
PRODUCTION = os.getenv('PRODUCTION', '0') == '1'  # Default to False if not set

# Initialize Binance client
client = Client(API_KEY, API_SECRET)

# Set up logging
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


def calculate_total_balance_usd(symbol, base_balance, quote_balance, current_price):
    """Calculate total balance in USD."""
    try:
        # Convert base asset to USD
        base_value_usd = base_balance * current_price
        
        # Quote balance is already in USD (assuming USDC/USDT)
        total_usd = base_value_usd + quote_balance
        return total_usd
    except Exception as e:
        error_logger.error(f"Error calculating total balance for {symbol}: {e}")
        return 0.0


main_logger, error_logger = setup_logging()


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
        t = client.get_symbol_ticker(symbol=symbol)
        price = float(t["price"])
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
    row = [f"{row_id:06d}", date_str, time_str, f"{price:.3f}", base_flag]
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
        # infer assets
        if symbol.endswith(("USDC", "USDT")):
            quote = symbol[-4:]
        else:
            raise ValueError(f"Unhandled quote asset for {symbol}")
        base = symbol.replace(quote, "")

        bal = client.get_account()["balances"]
        base_balance = next((float(x["free"]) for x in bal if x["asset"] == base), 0.0)
        quote_balance = next((float(x["free"]) for x in bal if x["asset"] == quote), 0.0)
        return base_balance, quote_balance
    except BinanceAPIException as e:
        raise Exception(f"Failed to get balances for {symbol}: {e}")


def log_trade(symbol, action, date_str, time_str, price, qty, base_balance, quote_balance, total_balance_usd):
    """
    Append to SYMBOL_trades.csv:
    ID,Date,Time,Action,Price,Quantity,Base_Balance,Quote_Balance,Total_Balance_USD
    """
    fn = f"{symbol}_trades.csv"
    row_id = get_last_id(fn)
    
    # Extract base and quote assets
    if symbol.endswith(("USDC", "USDT")):
        quote = symbol[-4:]
    else:
        quote = "QUOTE"
    base = symbol.replace(quote, "")
    
    row = [
        f"{row_id:06d}",
        date_str, time_str,
        action,
        f"{price:.3f}",
        f"{qty:.6f}",
        f"{base_balance:.6f}",
        f"{quote_balance:.3f}",
        f"{total_balance_usd:.2f}",
    ]
    is_new = not os.path.isfile(fn)

    with open(fn, "a", newline="") as f:
        w = csv.writer(f)
        if is_new:
            w.writerow([
                "ID", "Date", "Time", "Action",
                "Price", "Quantity",
                f"{base}_Balance", f"{quote}_Balance", "Total_Balance_USD"
            ])
        w.writerow(row)


def process_trading_pair(pair_config):
    """Process a single trading pair based on its configuration."""
    symbol = pair_config['symbol']
    trade_percentage = pair_config['trade_percentage']
    trigger_percentage = pair_config['trigger_percentage']
    max_amount = pair_config['max_amount']
    minimum_amount = pair_config['minimum_amount']
    
    try:
        date_str, time_str, price = get_price(symbol)
        base_price = get_base_price(symbol)

        # If no base yet → set it, no trade
        if base_price is None:
            store_price(symbol, date_str, time_str, price, base_flag=1)
            main_logger.info(f"[{symbol}] Base price initialized to {price:.3f}")
            return True

        move_pct = (price - base_price) / base_price
        base_balance, quote_balance = get_balances(symbol)

        # Trade up? (Price increased → SELL base asset)
        if move_pct >= trigger_percentage:
            # Calculate quantity based on trade percentage
            qty_from_percentage = base_balance * trade_percentage
            
            # Apply MAX_AMOUNT limit (convert USD to base asset)
            max_qty_allowed = max_amount / price
            qty = min(qty_from_percentage, max_qty_allowed)
            
            # Check if trade meets MINIMUM_AMOUNT
            trade_value_usd = qty * price
            
            if trade_value_usd >= minimum_amount:
                # Calculate new balances
                new_base_balance = base_balance - qty
                new_quote_balance = quote_balance + qty * price
                total_balance_usd = calculate_total_balance_usd(symbol, new_base_balance, new_quote_balance, price)
                
                # Execute trade only in production mode
                if PRODUCTION:
                    try:
                        order = client.order_market_sell(symbol=symbol, quantity=qty)
                        main_logger.info(f"[{symbol}] PRODUCTION: Order executed - {order}")
                    except BinanceAPIException as e:
                        error_logger.error(f"[{symbol}] Failed to execute SELL order: {e}")
                        return False
                
                # Log trade and update base price
                log_trade(symbol, "SELL", date_str, time_str, price, qty, new_base_balance, new_quote_balance, total_balance_usd)
                store_price(symbol, date_str, time_str, price, base_flag=1)
                
                # Get base and quote asset names for display
                if symbol.endswith(("USDC", "USDT")):
                    quote_asset = symbol[-4:]
                    base_asset = symbol.replace(quote_asset, "")
                
                # Send Telegram notification
                mode_text = "🔴 PRODUCTION" if PRODUCTION else "🟡 SIMULATION"
                message = f"""
{mode_text} TRADE EXECUTED 📈

<b>Pair:</b> {symbol}
<b>Action:</b> SELL {base_asset}
<b>Amount:</b> {qty:.6f} {base_asset} (${trade_value_usd:.2f})

<b>Base Price:</b> ${base_price:.3f} ({date_str})
<b>Current Price:</b> ${price:.3f}
<b>Price Change:</b> +{move_pct*100:.2f}%

<b>Current Balances:</b>
• {base_asset}: {new_base_balance:.6f}
• {quote_asset}: ${new_quote_balance:.2f}
• <b>Total USD: ${total_balance_usd:.2f}</b>
"""
                send_telegram_message(message)
                
                main_logger.info(f"[{symbol}] {'SOLD' if PRODUCTION else 'SIMULATED SELL'} {qty:.6f} for ${trade_value_usd:.2f} at {price:.3f} → new base")
            else:
                # Trade too small, just update base
                store_price(symbol, date_str, time_str, price, base_flag=1)
                main_logger.info(f"[{symbol}] Trade too small (${trade_value_usd:.2f} < ${minimum_amount}) → new base set, no trade")

        # Trade down? (Price decreased → BUY base asset)
        elif move_pct <= -trigger_percentage:
            # Calculate quantity based on trade percentage
            quote_to_trade = quote_balance * trade_percentage
            
            # Apply MAX_AMOUNT limit
            quote_to_trade = min(quote_to_trade, max_amount)
            qty = quote_to_trade / price
            
            # Check if trade meets MINIMUM_AMOUNT
            trade_value_usd = quote_to_trade
            
            if trade_value_usd >= minimum_amount:
                # Calculate new balances
                new_base_balance = base_balance + qty
                new_quote_balance = quote_balance - quote_to_trade
                total_balance_usd = calculate_total_balance_usd(symbol, new_base_balance, new_quote_balance, price)
                
                # Execute trade only in production mode
                if PRODUCTION:
                    try:
                        order = client.order_market_buy(symbol=symbol, quantity=qty)
                        main_logger.info(f"[{symbol}] PRODUCTION: Order executed - {order}")
                    except BinanceAPIException as e:
                        error_logger.error(f"[{symbol}] Failed to execute BUY order: {e}")
                        return False
                
                # Log trade and update base price
                log_trade(symbol, "BUY", date_str, time_str, price, qty, new_base_balance, new_quote_balance, total_balance_usd)
                store_price(symbol, date_str, time_str, price, base_flag=1)
                
                # Get base and quote asset names for display
                if symbol.endswith(("USDC", "USDT")):
                    quote_asset = symbol[-4:]
                    base_asset = symbol.replace(quote_asset, "")
                
                # Send Telegram notification
                mode_text = "🔴 PRODUCTION" if PRODUCTION else "🟡 SIMULATION"
                message = f"""
{mode_text} TRADE EXECUTED 📉

<b>Pair:</b> {symbol}
<b>Action:</b> BUY {base_asset}
<b>Amount:</b> {qty:.6f} {base_asset} (${trade_value_usd:.2f})

<b>Base Price:</b> ${base_price:.3f} ({date_str})
<b>Current Price:</b> ${price:.3f}
<b>Price Change:</b> {move_pct*100:.2f}%

<b>Current Balances:</b>
• {base_asset}: {new_base_balance:.6f}
• {quote_asset}: ${new_quote_balance:.2f}
• <b>Total USD: ${total_balance_usd:.2f}</b>
"""
                send_telegram_message(message)
                
                main_logger.info(f"[{symbol}] {'BOUGHT' if PRODUCTION else 'SIMULATED BUY'} {qty:.6f} for ${trade_value_usd:.2f} at {price:.3f} → new base")
            else:
                # Trade too small, just update base
                store_price(symbol, date_str, time_str, price, base_flag=1)
                main_logger.info(f"[{symbol}] Trade too small (${trade_value_usd:.2f} < ${minimum_amount}) → new base set, no trade")

        # No trade (within trigger range)
        else:
            store_price(symbol, date_str, time_str, price, base_flag=0)
            main_logger.info(f"[{symbol}] No trade. Price logged at {price:.3f}")

        return True

    except Exception as e:
        error_logger.error(f"[{symbol}] Error processing trading pair: {str(e)}")
        return False


def main():
    """Main function to process all trading pairs."""
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
    print(f"Starting trading session in {mode_text} mode with {len(trading_pairs)} pairs")
    
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
    print(f"Trading session completed: {successful_pairs} successful, {failed_pairs} failed")
    
    if failed_pairs > 0:
        print(f"Check trading_errors.log for details on {failed_pairs} failed pairs")


if __name__ == "__main__":
    main()
