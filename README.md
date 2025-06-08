# SimpleTrade

An advanced Python-based cryptocurrency trading bot that implements an automated buy-low/sell-high strategy with intelligent trade multipliers for Binance trading pairs. The bot monitors price movements, executes trades when thresholds are reached, and features comprehensive logging with Telegram notifications.

![Logo](image/IMG_7780.png "Logo")

## Features

- **Multi-pair Trading**: Support for multiple cryptocurrency trading pairs with individual configurations
- **Intelligent Trade Multipliers**: Consecutive trades in the same direction get progressively larger
- **Universal USD Price Conversion**: Supports any asset pair with automatic USD value calculation
- **Advanced Risk Management**: Maximum and minimum trade amount limits with USD-based controls
- **Production/Simulation Modes**: Test strategies without real trades
- **Comprehensive Logging**: Separate logs for trades and errors with detailed USD tracking
- **Telegram Notifications**: Real-time trade alerts with multiplier information
- **CSV Data Storage**: Historical price and trade data for analysis
- **Balance Tracking**: Monitor portfolio value in USD across all assets
- **Automated Git Integration**: Auto-commit trade data to GitHub repository
- **Rate Limiting**: Built-in API rate limiting to prevent abuse
- **Price Caching**: Reduces API calls with intelligent price caching

## How Trading Works - Business Logic

### 1. Base Price System
- Each trading pair maintains a "base price" - the reference point for all decisions
- Base price is updated after every trade execution
- If no base price exists, the bot sets the current price as base (no trade)

### 2. Price Movement Detection
The bot continuously monitors price changes against the base price:
```
Price Movement % = (Current Price - Base Price) / Base Price
```

### 3. Trade Triggers
- **SELL Signal**: When price rises ≥ trigger_percentage (e.g., +3%)
  - Action: Sell base asset (take profit)
- **BUY Signal**: When price falls ≤ -trigger_percentage (e.g., -3%)
  - Action: Buy base asset (buy the dip)

### 4. Intelligent Trade Multiplier System
The bot implements a progressive trading strategy:

- **First trade**: Uses base `trade_percentage` (e.g., 10%)
- **Consecutive same-direction trades**: Apply multiplier
  - 2nd consecutive: 10% × 1.1¹ = 11%
  - 3rd consecutive: 10% × 1.1² = 12.1%
  - 4th consecutive: 10% × 1.1³ = 13.31%
  - Maximum capped at 50% to prevent excessive risk

**Example Scenario:**
1. Price drops 3% → BUY 10% of quote balance
2. Price drops another 3% → BUY 11% of quote balance (multiplier applied)
3. Price rises 3% → SELL 10% of base balance (direction changed, reset multiplier)

### 5. Trade Amount Calculation
All limits are enforced in USD equivalent:
- **Percentage-based**: Trade a percentage of available balance
- **Maximum limit**: Caps individual trade size (USD)
- **Minimum limit**: Prevents tiny unprofitable trades (USD)
- **Balance validation**: Ensures sufficient funds exist

### 6. USD Value Tracking
The bot converts all assets to USD for:
- Portfolio value calculation
- Trade limit enforcement
- Comprehensive reporting
- Supports any asset through BTC/ETH conversion paths

## Installation & Setup

### Prerequisites
- Python 3.7+
- Binance account with API access
- Git (for auto-commit feature)
- Telegram bot (optional, for notifications)

### Quick Start

1. **Clone the repository**
   ```bash
   git clone https://github.com/yourusername/SimpleTrade.git
   cd SimpleTrade
   ```

2. **Create and activate virtual environment**
   ```bash
   python3 -m venv venv
   source venv/bin/activate  # Linux/Mac
   # or
   venv\Scripts\activate     # Windows
   ```

3. **Install dependencies**
   ```bash
   pip install python-binance requests python-dotenv
   ```

4. **Create configuration file** (`configmulti.json`):
   ```json
   {
     "trading_pairs": [
       {
         "symbol1": "ETH",
         "symbol2": "EURI",
         "trade_percentage": 0.2,
         "trigger_percentage": 0.03,
         "max_amount": 50.0,
         "minimum_amount": 10.0,
         "decimal": 3,
         "multiplier": 1.1
       },
       {
         "symbol1": "BTC",
         "symbol2": "USDT",
         "trade_percentage": 0.1,
         "trigger_percentage": 0.05,
         "max_amount": 100.0,
         "minimum_amount": 15.0,
         "decimal": 6,
         "multiplier": 1.2
       }
     ]
   }
   ```

5. **Set up environment variables**

   **Option A: Create `.env` file:**
   ```bash
   # Binance API Configuration
   BINANCE_API_KEY=your_binance_api_key
   BINANCE_API_SECRET=your_binance_api_secret
   
   # Bot Configuration
   CONFIG_FILE=configmulti.json
   PRODUCTION=0  # Set to 1 for live trading
   
   # Telegram Notifications (Optional)
   TELEGRAM_BOT_TOKEN=your_telegram_bot_token
   TELEGRAM_CHAT_ID=your_telegram_chat_id
   
   # GitHub Auto-commit (Optional)
   GITHUB_USERNAME=your_github_username
   GITHUB_TOKEN=your_github_token
   GITHUB_REPO=github.com/yourusername/SimpleTrade.git
   ```

   **Option B: Export environment variables:**
   ```bash
   export BINANCE_API_KEY="your_binance_api_key"
   export BINANCE_API_SECRET="your_binance_api_secret"
   export CONFIG_FILE="configmulti.json"
   export PRODUCTION="0"
   # ... add other variables as needed
   ```

6. **Run the bot**

   **Manual execution:**
   ```bash
   # Simulation mode (safe testing)
   python3 main.py
   
   # Production mode (live trading)
   PRODUCTION=1 python3 main.py
   ```

   **Automated execution with auto-commit:**
   ```bash
   # Make script executable
   chmod +x run_bot.sh
   
   # Run continuously with auto-commit
   ./run_bot.sh
   ```

## Configuration Parameters

| Parameter | Description | Type | Example |
|-----------|-------------|------|---------|
| `symbol1` | Base asset (what you're trading) | string | `"ETH"` |
| `symbol2` | Quote asset (what you're pricing in) | string | `"USDT"` |
| `trade_percentage` | Percentage of balance to trade | float | `0.1` (10%) |
| `trigger_percentage` | Price change threshold | float | `0.03` (3%) |
| `max_amount` | Maximum USD per trade | float | `100.0` |
| `minimum_amount` | Minimum USD to execute trade | float | `10.0` |
| `decimal` | Decimal places for quantity | int | `6` |
| `multiplier` | Consecutive trade multiplier | float | `1.1` |

## Automated Execution Script

The included `run_bot.sh` script provides:
- Continuous execution with 59-second intervals
- Automatic Git commits when trades occur
- Environment variable loading
- Force push to prevent conflicts

```bash
#!/bin/bash
source .env
while true; do
    python3 main.py
    sleep 59
    if git status --porcelain | grep -E '_trades.csv$'; then
        echo "Detected trade changes, pushing to GitHub..."
        git add $(git status --porcelain | awk '{print $2}' | grep -E '_trades.csv$')
        git commit -m "Auto-push: Updated trade data"
        git push --force https://${GITHUB_USERNAME}:${GITHUB_TOKEN}@${GITHUB_REPO} main
    fi
done
```

## Output Files

- **`{SYMBOL1}_{SYMBOL2}.csv`**: Price history with base price markers
- **`{SYMBOL1}_{SYMBOL2}_trades.csv`**: Complete trade history with USD values and multiplier data
- **`trading_main.log`**: Successful operations and trade executions
- **`trading_errors.log`**: Errors, failures, and warnings

## Sample Trade Output

```
🔴 PRODUCTION TRADE EXECUTED 📈

Pair: ETH/EURI
Action: SELL ETH
Amount: 0.045000 ETH
Trade Value: $150.75
🔥 Consecutive #2: 12.10% trade size

Base Price: 3250.000000 EURI (241204)
Current Price: 3347.500000 EURI
Price Change: +3.00%

Current Balances:
• ETH: 0.455000
• EURI: 1523.625000
• Total USD: $2,847.32
```

## Safety Features

- **Simulation Mode**: Test strategies without real money
- **USD-based Limits**: All limits enforced in USD equivalent
- **Progressive Risk**: Multiplier system with maximum 50% cap
- **Comprehensive Validation**: Balance and configuration checks
- **Error Recovery**: Robust error handling and logging
- **Rate Limiting**: API call throttling to prevent abuse

## Code Walkthrough

### Core Components

1. **Price Cache System** (`PriceCache`): Reduces API calls with 60-second TTL
2. **USD Conversion** (`get_usd_price`): Converts any asset to USD via multiple paths
3. **Multiplier Logic** (`calculate_multiplied_trade_percentage`): Handles consecutive trade scaling
4. **Trade Execution** (`process_trade_signal`): Orchestrates the complete trade process
5. **Balance Management** (`calculate_trade_amounts`): USD-based trade sizing with limits

### Key Functions

- `get_usd_price()`: Multi-path USD conversion (direct pairs → BTC → ETH)
- `process_trading_pair()`: Main logic loop for each trading pair
- `calculate_multiplied_trade_percentage()`: Progressive trade sizing
- `execute_trade()`: Binance API interaction with simulation mode
- `send_trade_notification()`: Rich Telegram notifications

### Execution Flow

1. Load configuration and validate trading pairs
2. For each pair: Get current price and compare to base
3. If trigger threshold met: Calculate trade amount with multiplier
4. Execute trade (or simulate) and update base price
5. Log trade data and send notifications
6. Auto-commit changes to Git repository

## Risk Warning

⚠️ **IMPORTANT**: This bot trades real cryptocurrency. Always:
- Test thoroughly in simulation mode (`PRODUCTION=0`)
- Start with small amounts and conservative settings
- Monitor the bot's performance regularly
- Understand that multipliers increase risk exposure
- Never invest more than you can afford to lose
- Review all trades and adjust parameters based on performance

## Troubleshooting

**Common Issues:**
- API rate limits → Increase sleep intervals
- Price conversion failures → Check asset pairs exist on Binance
- Trade execution errors → Verify sufficient balances and API permissions
- Git push failures → Check GitHub credentials and repository access

**Check log files:**
- `trading_main.log` - Successful operations
- `trading_errors.log` - Errors and issues


# Analysis & Optimization Results

In order to refine the trading strategy and evaluate its performance under different market conditions, we ran extensive backtesting using a dynamic parameter grid and compared the simulation results against a simple buy-and-hold approach. This section summarizes our methodology, findings, and recommendations.

## Methodology

### Parameter Grid and Simulation
We defined a grid of key parameters:

- **Base Trade Percentage**: The initial percentage of balance allocated for a trade (e.g., 0.1, 0.15, 0.2, 0.25, 0.3)
- **Trigger Percentage**: The price movement threshold for triggering a BUY/SELL signal (e.g., 0.02, 0.025, 0.03, 0.035, 0.04)
- **Maximum Trade USD**: The cap on the USD value per trade (e.g., 750, 500, 250)
- **Minimum Trade USD**: Fixed at 15 USD to prevent tiny unprofitable trades
- **Multiplier**: Increases the trade size with consecutive trades in the same direction (e.g., 1.05, 1.1, 1.1, 1.15, 1.2)

For each parameter combination, the bot was simulated over historical monthly data. Each month was classified as Bullish, Bearish, or Sideways based solely on the percentage change between its opening and closing prices.

### Profit Differential Calculation
For every parameter combo under each market condition, we calculated Profit_Diff as follows:

```
Profit_Diff = Avg_Trading_Profit_USD - Avg_Hold_Profit_USD
```

This metric quantifies how much better (or worse) the trading strategy performs relative to a basic buy-and-hold approach.

### Ranking and Selection of Top Combos
We then ranked the parameter combos within each market trend (Bullish, Bearish, Sideways) based on Profit_Diff, selecting the top three for further analysis. A higher positive Profit_Diff means the active trading strategy outperformed holding by a larger margin.

## Analysis Results

Below are the top three parameter combos for each market trend:

### Market Trend: Bearish

**Combo 1:**
- Parameters: base_trade_pct: 0.3, trigger_pct: 0.04, max_trade_usd: 750, min_trade_usd: 15, multiplier: 1.1
- Profit_Diff: 14.82, Trading: -95.01, Hold: -109.83, Months: 16, Trades: 34.94

**Combo 2:**
- Parameters: base_trade_pct: 0.2, trigger_pct: 0.04, max_trade_usd: 500, min_trade_usd: 15, multiplier: 1.1
- Profit_Diff: 11.25, Trading: -98.58, Hold: -109.83, Months: 16, Trades: 34.94

**Combo 3:**
- Parameters: base_trade_pct: 0.3, trigger_pct: 0.035, max_trade_usd: 250, min_trade_usd: 15, multiplier: 1.1
- Profit_Diff: 10.93, Trading: -98.90, Hold: -109.83, Months: 16, Trades: 42.81

**Conclusion (Bearish):** Under bearish conditions, the algorithm mitigates losses relative to holding. The best bearish combo (0.3, 0.04, 750, 15, 1.1) reduces losses by approximately 14.82 USD over a 16‑month period compared to a 50/50 hold, demonstrating that the strategy is effective in reducing downside risk.

### Market Trend: Bullish

**Combo 1:**
- Parameters: base_trade_pct: 0.1, trigger_pct: 0.03, max_trade_usd: 500, min_trade_usd: 15, multiplier: 1.05
- Profit_Diff: -19.19, Trading: 151.25, Hold: 170.44, Months: 24, Trades: 48.62

**Combo 2:**
- Parameters: base_trade_pct: 0.1, trigger_pct: 0.025, max_trade_usd: 250, min_trade_usd: 15, multiplier: 1.05
- Profit_Diff: -19.29, Trading: 151.15, Hold: 170.44, Months: 24, Trades: 65.17

**Combo 3:**
- Parameters: base_trade_pct: 0.1, trigger_pct: 0.02, max_trade_usd: 500, min_trade_usd: 15, multiplier: 1.05
- Profit_Diff: -20.49, Trading: 149.95, Hold: 170.44, Months: 24, Trades: 94.25

**Conclusion (Bullish):** In bullish markets, all evaluated combos yielded a negative Profit_Diff. This indicates that the trading strategy underperforms compared to simply holding assets — likely because the algorithm initiates trades that interrupt the full capture of upward trends. In strong uptrends, a straightforward hold strategy appears to be superior.

### Market Trend: Sideways

**Combo 1:**
- Parameters: base_trade_pct: 0.3, trigger_pct: 0.04, max_trade_usd: 750, min_trade_usd: 15, multiplier: 1.1
- Profit_Diff: 17.78, Trading: 20.62, Hold: 2.84, Months: 20, Trades: 20.90

**Combo 2:**
- Parameters: base_trade_pct: 0.2, trigger_pct: 0.03, max_trade_usd: 250, min_trade_usd: 15, multiplier: 1.2
- Profit_Diff: 17.23, Trading: 20.07, Hold: 2.84, Months: 20, Trades: 32.80

**Combo 3:**
- Parameters: base_trade_pct: 0.15, trigger_pct: 0.04, max_trade_usd: 500, min_trade_usd: 15, multiplier: 1.2
- Profit_Diff: 16.61, Trading: 19.45, Hold: 2.84, Months: 20, Trades: 20.95

**Conclusion (Sideways):** The strategy performs exceptionally in sideways environments. Active trading in these conditions results in a significant profit improvement (a positive Profit_Diff of roughly 16.6 to 17.8 USD) compared to holding. This outcome implies that during flat markets, the bot's ability to capitalize on minor fluctuations provides superior returns over a static portfolio.

## Overall Insights & Recommendations

### Key Findings

- **Bearish Markets**: The algorithm is effective in mitigating losses, suggesting that in downturns, aggressive trading (e.g., a higher base_trade_pct and trigger_pct) can reduce downside risk relative to holding.

- **Bullish Markets**: In uptrends, the strategy underperforms due to over-trading or early exits, which prevent full benefit from sustained price rises. A dynamic approach that minimizes trades when the market is strongly bullish may yield better performance.

- **Sideways Markets**: The highest profit improvement is observed in sideways conditions, indicating that an active trading approach is particularly valuable when price movements are moderate.

### Recommendations for Improvement

1. **Hybrid Strategy**: Consider implementing regime detection to switch between active trading and a hold strategy depending on market conditions. For example, deploy active trading during bearish or sideways periods, and limit trades during bullish trends.

2. **Adaptive Parameters**: Explore expanding the parameter grid or using an optimizer to dynamically update trade thresholds and multipliers based on current market volatility.

3. **Risk Management Enhancements**: Refine position sizing, potentially with dynamic adjustments based on historical volatility, to further protect capital in adverse conditions and improve gains in favorable ones.

These insights form the basis for further development and optimization of the trading bot, ultimately aiming to combine the best aspects of active trading and simple holding strategies depending on market conditions.


## License

MIT License - See LICENSE file for details.

## Contributing

1. Fork the repository
2. Create a feature branch
3. Test thoroughly in simulation mode
4. Submit a pull request with detailed description

## Support

For issues, create a GitHub issue with:
- Configuration file (remove sensitive data)
- Relevant log entries
- Steps to reproduce the problem

