# SimpleTrade

A Python-based cryptocurrency trading bot that implements an automated buy-low/sell-high strategy for Binance trading pairs. The bot monitors price movements and executes trades when specified thresholds are reached, with comprehensive logging and Telegram notifications.
![Logo](img_7780.png "Logo")
## Features

- **Multi-pair Trading**: Support for multiple cryptocurrency trading pairs with individual configurations
- **Percentage-based Trading**: Configurable trigger and trade percentages for each pair
- **Risk Management**: Maximum and minimum trade amount limits
- **Production/Simulation Modes**: Test strategies without real trades
- **Comprehensive Logging**: Separate logs for trades and errors
- **Telegram Notifications**: Real-time trade alerts via Telegram
- **CSV Data Storage**: Historical price and trade data for analysis
- **Balance Tracking**: Monitor portfolio value in USD

## How It Works

1. **Base Price Tracking**: The bot establishes a "base price" for each trading pair
2. **Price Monitoring**: Continuously monitors current prices against the base price
3. **Trigger Logic**: 
   - When price rises by the trigger percentage → SELL (take profit)
   - When price falls by the trigger percentage → BUY (buy the dip)
4. **Trade Execution**: Trades a configurable percentage of available balance
5. **Base Price Update**: Updates the base price after each trade

## Installation & Setup

### Prerequisites

- Python 3.7+
- Binance account with API access
- Telegram bot (optional, for notifications)

### Local Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/smartonstuff/SimpleTrade.git
   cd SimpleTrade
   ```

2. **Create and activate virtual environment**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   pip install python-binance requests python-dotenv
   ```

### Configuration

1. **Create configuration file** (`config.json`):
   ```json
   {
     "trading_pairs": [
       {
         "symbol": "BTCUSDT",
         "trade_percentage": 0.1,
         "trigger_percentage": 0.05,
         "max_amount": 100,
         "minimum_amount": 10
       },
       {
         "symbol": "ETHUSDT",
         "trade_percentage": 0.15,
         "trigger_percentage": 0.04,
         "max_amount": 50,
         "minimum_amount": 5
       }
     ]
   }
   ```

2. **Set up environment variables**:
   ```bash
   export BINANCE_API_KEY="your_binance_api_key"
   export BINANCE_API_SECRET="your_binance_api_secret"
   export CONFIG_FILE="config.json"
   export TELEGRAM_BOT_TOKEN="your_telegram_bot_token"  # Optional
   export TELEGRAM_CHAT_ID="your_telegram_chat_id"     # Optional
   export PRODUCTION="0"  # Set to "1" for live trading
   ```

   Or create a `.env` file:
   ```env
   BINANCE_API_KEY=your_binance_api_key
   BINANCE_API_SECRET=your_binance_api_secret
   CONFIG_FILE=config.json
   TELEGRAM_BOT_TOKEN=your_telegram_bot_token
   TELEGRAM_CHAT_ID=your_telegram_chat_id
   PRODUCTION=0
   ```

## Configuration Parameters

| Parameter | Description | Example |
|-----------|-------------|---------|
| `symbol` | Trading pair symbol | `"BTCUSDT"` |
| `trade_percentage` | Percentage of balance to trade | `0.1` (10%) |
| `trigger_percentage` | Price change threshold to trigger trade | `0.05` (5%) |
| `max_amount` | Maximum USD amount per trade | `100` |
| `minimum_amount` | Minimum USD amount to execute trade | `10` |

## Usage

### Manual Execution

```bash
# Simulation mode (default)
python trading_bot.py

# Production mode (live trading)
export PRODUCTION=1
python trading_bot.py
```

### Automated Execution (Cron Job)

1. **Create environment file** (`.env`):
   ```bash
   cd SimpleTrade
   nano .env
   ```
   
   Add your configuration:
   ```env
   BINANCE_API_KEY=your_binance_api_key
   BINANCE_API_SECRET=your_binance_api_secret
   CONFIG_FILE=config.json
   TELEGRAM_BOT_TOKEN=your_telegram_bot_token
   TELEGRAM_CHAT_ID=your_telegram_chat_id
   PRODUCTION=1
   ```

2. **Install python-dotenv** (to load .env file):
   ```bash
   source venv/bin/activate
   pip install python-dotenv
   ```

3. **Update your script** to load .env (add this at the top of trading_bot.py):
   ```python
   from dotenv import load_dotenv
   load_dotenv()
   ```

4. **Add to crontab**:
   ```bash
   crontab -e
   ```
   
   Add line for desired frequency:
   ```bash
   # Run every 5 minutes
   */5 * * * * cd ~/SimpleTrade && source venv/bin/activate && python trading_bot.py
   
   # Run every hour
   0 * * * * cd ~/SimpleTrade && source venv/bin/activate && python trading_bot.py
   
   # Run every 30 minutes
   */30 * * * * cd ~/SimpleTrade && source venv/bin/activate && python trading_bot.py
   ```

## File Structure

```
SimpleTrade/
├── trading_bot.py          # Main trading bot script
├── config.json            # Trading pairs configuration
├── .env                   # Environment variables (API keys, etc.)
├── README.md              # This file
├── trading_main.log       # Main operations log
├── trading_errors.log     # Error log
├── BTCUSDT.csv           # Price history for BTC/USDT
├── BTCUSDT_trades.csv    # Trade history for BTC/USDT
└── venv/                 # Virtual environment
```

## Output Files

- **`{SYMBOL}.csv`**: Price history with base price markers
- **`{SYMBOL}_trades.csv`**: Complete trade history with balances
- **`trading_main.log`**: Successful operations and info
- **`trading_errors.log`**: Errors and failures

## Safety Features

- **Simulation Mode**: Test strategies without real money
- **Minimum Trade Amounts**: Prevents tiny, unprofitable trades
- **Maximum Trade Limits**: Caps individual trade sizes
- **Error Handling**: Comprehensive error logging and recovery
- **Balance Validation**: Ensures sufficient funds before trading

## Telegram Integration

To receive trade notifications:

1. Create a Telegram bot via @BotFather
2. Get your chat ID by messaging @userinfobot
3. Set the environment variables:
   ```bash
   export TELEGRAM_BOT_TOKEN="your_bot_token"
   export TELEGRAM_CHAT_ID="your_chat_id"
   ```

## Risk Warning

⚠️ **IMPORTANT**: This bot trades real cryptocurrency. Always:
- Test in simulation mode first
- Start with small amounts
- Monitor the bot's performance
- Understand that cryptocurrency trading involves risk of loss
- Never invest more than you can afford to lose

## License

MIT License

Copyright (c) 2025 smartonstuff

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test thoroughly in simulation mode
5. Submit a pull request

## Support

Check the log files for debugging:
- `trading_main.log` - Successful operations
- `trading_errors.log` - Errors and issues

For issues, please create a GitHub issue with relevant log entries.
