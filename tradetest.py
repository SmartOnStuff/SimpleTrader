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
PRODUCTION = 1  
symbol = "ETHUSDC"

def main():

    # Initialize Binance client
    client = Client(API_KEY, API_SECRET)
    if not API_KEY or not API_SECRET:
        raise ValueError("API_KEY and API_SECRET must be set in the environment variables.")
    
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        raise ValueError("TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID must be set in the environment variables.")


    info = client.get_symbol_info('ETHUSDC')
    #print(info)
    print(info['filters'][1]['minQty'])

    # 0.00001
    order = client.order_market_sell(symbol=symbol, quantity=0.01)
    print(f"[{symbol}] PRODUCTION: Order executed - {order}")  


def send_telegram_message(message):

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    data = {
        'chat_id': TELEGRAM_CHAT_ID,
        'text': message,
        'parse_mode': 'HTML'
    }
    response = requests.post(url, data=data, timeout=10)
    response.raise_for_status()
    return True


if __name__ == "__main__":
    try:
        main()
        send_telegram_message(f"Trade executed successfully for {symbol}.")
    except BinanceAPIException as e:
        logging.error(f"Binance API Exception: {e}")
        send_telegram_message(f"Trade failed for {symbol}. Error: {e}")
    except Exception as e:
        logging.error(f"An error occurred: {e}")
        send_telegram_message(f"Trade failed for {symbol}. Error: {e}")
