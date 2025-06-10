import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import numpy as np
from matplotlib.gridspec import GridSpec
import warnings
warnings.filterwarnings('ignore')

# Configuration
INPUT_FILE = "data/final_balances_analysis.csv"
OUTPUT_FOLDER = "data/visualizations"
TRADING_PAIR = "ETHBTC"
BASE_ASSET = "ETH"
QUOTE_ASSET = "BTC"

def load_and_prepare_data():
    """Load the CSV data and prepare it for visualization"""
    try:
        df = pd.read_csv(INPUT_FILE)
        print(f"Loaded {len(df)} trading simulation results")
        return df
    except FileNotFoundError:
        print(f"Error: Could not find {INPUT_FILE}")
        return None
    except Exception as e:
        print(f"Error loading data: {e}")
        return None

def create_performance_overview(df):
    """Create overview charts of performance metrics"""
    fig = plt.figure(figsize=(20, 12))
    gs = GridSpec(3, 3, figure=fig, hspace=0.3, wspace=0.3)
    
    # 1. Performance Distribution
    ax1 = fig.add_subplot(gs[0, 0])
    df['eth_performance_percent'].hist(bins=30, alpha=0.7, color='orange', ax=ax1)
    ax1.set_title(f'{BASE_ASSET} Performance Distribution')
    ax1.set_xlabel('Performance (%)')
    ax1.set_ylabel('Frequency')
    ax1.axvline(df['eth_performance_percent'].mean(), color='red', linestyle='--', label=f'Mean: {df["eth_performance_percent"].mean():.1f}%')
    ax1.legend()
    
    # 2. Trade Count vs Performance
    ax2 = fig.add_subplot(gs[0, 1])
    scatter = ax2.scatter(df['trade_count'], df['eth_performance_percent'], 
                         c=df['btc_performance_percent'], cmap='viridis', alpha=0.6)
    ax2.set_xlabel('Number of Trades')
    ax2.set_ylabel(f'{BASE_ASSET} Performance (%)')
    ax2.set_title('Performance vs Trade Count')
    plt.colorbar(scatter, ax=ax2, label=f'{QUOTE_ASSET} Performance (%)')
    
    # 3. Price Change Impact
    ax3 = fig.add_subplot(gs[0, 2])
    ax3.scatter(df['price_change_percent'], df['eth_performance_percent'], alpha=0.6, color='green')
    ax3.set_xlabel('Price Change (%)')
    ax3.set_ylabel(f'{BASE_ASSET} Performance (%)')
    ax3.set_title('Performance vs Market Price Change')
    
    # 4. Parameter Heatmap - Base Trade % vs Trigger %
    ax4 = fig.add_subplot(gs[1, 0])
    pivot_data = df.pivot_table(values='eth_performance_percent', 
                               index='base_trade_percentage', 
                               columns='trigger_percentage', 
                               aggfunc='mean')
    sns.heatmap(pivot_data, annot=True, fmt='.1f', cmap='RdYlGn', ax=ax4)
    ax4.set_title('Avg Performance: Base Trade % vs Trigger %')
    
    # 5. Multiplier Impact
    ax5 = fig.add_subplot(gs[1, 1])
    multiplier_performance = df.groupby('multiplier')['eth_performance_percent'].mean()
    multiplier_performance.plot(kind='bar', ax=ax5, color='skyblue')
    ax5.set_title('Average Performance by Multiplier')
    ax5.set_xlabel('Multiplier')
    ax5.set_ylabel(f'Avg {BASE_ASSET} Performance (%)')
    ax5.tick_params(axis='x', rotation=0)
    
    # 6. Trade Limits Impact
    ax6 = fig.add_subplot(gs[1, 2])
    df['trade_range'] = df['max_trade_percentage'] - df['min_trade_percentage']
    ax6.scatter(df['trade_range'], df['eth_performance_percent'], alpha=0.6, color='purple')
    ax6.set_xlabel('Trade Range (Max - Min %)')
    ax6.set_ylabel(f'{BASE_ASSET} Performance (%)')
    ax6.set_title('Performance vs Trade Range')
    
    # 7. Top Performers Table
    ax7 = fig.add_subplot(gs[2, :])
    ax7.axis('tight')
    ax7.axis('off')
    
    top_performers = df.nlargest(10, 'eth_performance_percent')[
        ['base_trade_percentage', 'trigger_percentage', 'multiplier', 
         'eth_performance_percent', 'trade_count', 'final_eth_balance']
    ].round(3)
    
    table = ax7.table(cellText=top_performers.values,
                     colLabels=top_performers.columns,
                     cellLoc='center',
                     loc='center')
    table.auto_set_font_size(False)
    table.set_fontsize(9)
    table.scale(1.2, 1.5)
    ax7.set_title('Top 10 Performing Parameter Combinations', pad=20)
    
    plt.suptitle(f'{TRADING_PAIR} Trading Strategy Analysis - Performance Overview', fontsize=16, y=0.98)
    return fig

def create_parameter_analysis(df):
    """Create detailed parameter analysis charts"""
    fig, axes = plt.subplots(2, 3, figsize=(18, 12))
    fig.suptitle(f'{TRADING_PAIR} Trading Strategy - Parameter Analysis', fontsize=16)
    
    # 1. Base Trade Percentage Analysis
    base_trade_stats = df.groupby('base_trade_percentage').agg({
        'eth_performance_percent': ['mean', 'std', 'count'],
        'trade_count': 'mean'
    }).round(2)
    
    ax = axes[0, 0]
    x_pos = range(len(base_trade_stats))
    ax.bar(x_pos, base_trade_stats['eth_performance_percent']['mean'], 
           yerr=base_trade_stats['eth_performance_percent']['std'],
           alpha=0.7, color='orange', capsize=5)
    ax.set_xticks(x_pos)
    ax.set_xticklabels(base_trade_stats.index, rotation=45)
    ax.set_title('Performance by Base Trade %')
    ax.set_ylabel(f'{BASE_ASSET} Performance (%)')
    
    # 2. Trigger Percentage Analysis
    trigger_stats = df.groupby('trigger_percentage').agg({
        'eth_performance_percent': ['mean', 'std'],
        'trade_count': 'mean'
    }).round(2)
    
    ax = axes[0, 1]
    x_pos = range(len(trigger_stats))
    ax.bar(x_pos, trigger_stats['eth_performance_percent']['mean'],
           yerr=trigger_stats['eth_performance_percent']['std'],
           alpha=0.7, color='green', capsize=5)
    ax.set_xticks(x_pos)
    ax.set_xticklabels(trigger_stats.index, rotation=45)
    ax.set_title('Performance by Trigger %')
    ax.set_ylabel(f'{BASE_ASSET} Performance (%)')
    
    # 3. Max Trade Percentage Analysis
    max_trade_stats = df.groupby('max_trade_percentage').agg({
        'eth_performance_percent': ['mean', 'std'],
        'trade_count': 'mean'
    }).round(2)
    
    ax = axes[0, 2]
    x_pos = range(len(max_trade_stats))
    ax.bar(x_pos, max_trade_stats['eth_performance_percent']['mean'],
           yerr=max_trade_stats['eth_performance_percent']['std'],
           alpha=0.7, color='blue', capsize=5)
    ax.set_xticks(x_pos)
    ax.set_xticklabels(max_trade_stats.index, rotation=45)
    ax.set_title('Performance by Max Trade %')
    ax.set_ylabel(f'{BASE_ASSET} Performance (%)')
    
    # 4. Min Trade Percentage Analysis
    min_trade_stats = df.groupby('min_trade_percentage').agg({
        'eth_performance_percent': ['mean', 'std'],
        'trade_count': 'mean'
    }).round(2)
    
    ax = axes[1, 0]
    x_pos = range(len(min_trade_stats))
    ax.bar(x_pos, min_trade_stats['eth_performance_percent']['mean'],
           yerr=min_trade_stats['eth_performance_percent']['std'],
           alpha=0.7, color='red', capsize=5)
    ax.set_xticks(x_pos)
    ax.set_xticklabels(min_trade_stats.index, rotation=45)
    ax.set_title('Performance by Min Trade %')
    ax.set_ylabel(f'{BASE_ASSET} Performance (%)')
    
    # 5. Trade Count Distribution
    ax = axes[1, 1]
    df['trade_count'].hist(bins=30, alpha=0.7, color='purple', ax=ax)
    ax.axvline(df['trade_count'].mean(), color='red', linestyle='--', 
               label=f'Mean: {df["trade_count"].mean():.0f}')
    ax.set_title('Trade Count Distribution')
    ax.set_xlabel('Number of Trades')
    ax.set_ylabel('Frequency')
    ax.legend()
    
    # 6. Performance vs Trade Activity
    ax = axes[1, 2]
    # Create bins for trade count
    df['trade_count_bin'] = pd.cut(df['trade_count'], bins=5, labels=['Very Low', 'Low', 'Medium', 'High', 'Very High'])
    trade_bin_performance = df.groupby('trade_count_bin')['eth_performance_percent'].mean()
    trade_bin_performance.plot(kind='bar', ax=ax, color='teal')
    ax.set_title('Performance by Trade Activity Level')
    ax.set_ylabel(f'{BASE_ASSET} Performance (%)')
    ax.tick_params(axis='x', rotation=45)
    
    plt.tight_layout()
    return fig

def create_correlation_analysis(df):
    """Create correlation analysis and advanced insights"""
    fig, axes = plt.subplots(2, 2, figsize=(16, 12))
    fig.suptitle(f'{TRADING_PAIR} Trading Strategy - Correlation & Advanced Analysis', fontsize=16)
    
    # 1. Correlation Matrix
    correlation_cols = ['base_trade_percentage', 'trigger_percentage', 'max_trade_percentage', 
                       'min_trade_percentage', 'multiplier', 'eth_performance_percent', 
                       'btc_performance_percent', 'trade_count', 'price_change_percent']
    
    corr_matrix = df[correlation_cols].corr()
    
    ax = axes[0, 0]
    sns.heatmap(corr_matrix, annot=True, cmap='coolwarm', center=0, 
                square=True, fmt='.2f', ax=ax)
    ax.set_title('Parameter Correlation Matrix')
    
    # 2. Risk-Return Scatter
    ax = axes[0, 1]
    # Calculate volatility (standard deviation of performance across similar parameters)
    df['volatility'] = df.groupby(['base_trade_percentage', 'trigger_percentage'])['eth_performance_percent'].transform('std').fillna(0)
    
    scatter = ax.scatter(df['volatility'], df['eth_performance_percent'], 
                        c=df['trade_count'], cmap='plasma', alpha=0.6)
    ax.set_xlabel('Strategy Volatility (Performance Std Dev)')
    ax.set_ylabel(f'{BASE_ASSET} Performance (%)')
    ax.set_title('Risk-Return Profile')
    plt.colorbar(scatter, ax=ax, label='Trade Count')
    
    # 3. Efficiency Frontier
    ax = axes[1, 0]
    # Group by risk levels and find best performance for each risk level
    df['risk_bucket'] = pd.cut(df['volatility'], bins=10, labels=False)
    efficiency_data = df.groupby('risk_bucket').agg({
        'volatility': 'mean',
        'eth_performance_percent': 'max'
    }).dropna()
    
    ax.plot(efficiency_data['volatility'], efficiency_data['eth_performance_percent'], 
            'ro-', linewidth=2, markersize=8, label='Efficiency Frontier')
    ax.scatter(df['volatility'], df['eth_performance_percent'], alpha=0.3, color='gray')
    ax.set_xlabel('Risk (Volatility)')
    ax.set_ylabel(f'{BASE_ASSET} Performance (%)')
    ax.set_title('Strategy Efficiency Frontier')
    ax.legend()
    
    # 4. Parameter Interaction Effects
    ax = axes[1, 1]
    # Create interaction term
    df['base_trigger_interaction'] = df['base_trade_percentage'] * df['trigger_percentage']
    
    # Scatter plot of interaction vs performance
    scatter = ax.scatter(df['base_trigger_interaction'], df['eth_performance_percent'],
                        c=df['multiplier'], cmap='viridis', alpha=0.6)
    ax.set_xlabel('Base Trade % × Trigger % (Interaction)')
    ax.set_ylabel(f'{BASE_ASSET} Performance (%)')
    ax.set_title('Parameter Interaction Effects')
    plt.colorbar(scatter, ax=ax, label='Multiplier')
    
    plt.tight_layout()
    return fig

def create_summary_statistics(df):
    """Create summary statistics and insights"""
    print("\n" + "="*80)
    print(f"TRADING SIMULATION ANALYSIS SUMMARY - {TRADING_PAIR}")
    print("="*80)
    
    print(f"\n📊 DATASET OVERVIEW:")
    print(f"   • Total parameter combinations tested: {len(df)}")
    print(f"   • Market price change during period: {df['price_change_percent'].iloc[0]:.2f}%")
    print(f"   • Starting price: {df['starting_price'].iloc[0]:.6f}")
    print(f"   • Final price: {df['final_price'].iloc[0]:.6f}")
    
    print(f"\n🎯 PERFORMANCE METRICS:")
    print(f"   • Best {BASE_ASSET} performance: {df['eth_performance_percent'].max():.2f}%")
    print(f"   • Worst {BASE_ASSET} performance: {df['eth_performance_percent'].min():.2f}%")
    print(f"   • Average {BASE_ASSET} performance: {df['eth_performance_percent'].mean():.2f}%")
    print(f"   • Median {BASE_ASSET} performance: {df['eth_performance_percent'].median():.2f}%")
    print(f"   • Performance std deviation: {df['eth_performance_percent'].std():.2f}%")
    
    print(f"\n📈 TRADING ACTIVITY:")
    print(f"   • Average trades per strategy: {df['trade_count'].mean():.0f}")
    print(f"   • Maximum trades: {df['trade_count'].max()}")
    print(f"   • Minimum trades: {df['trade_count'].min()}")
    print(f"   • Strategies with >500 trades: {(df['trade_count'] > 500).sum()}")
    
    print(f"\n🏆 TOP PERFORMING STRATEGIES:")
    top_5 = df.nlargest(5, 'eth_performance_percent')
    for i, (_, row) in enumerate(top_5.iterrows(), 1):
        print(f"   {i}. Base: {row['base_trade_percentage']:.2f}, Trigger: {row['trigger_percentage']:.2f}, "
              f"Mult: {row['multiplier']:.0f} → {row['eth_performance_percent']:.2f}% ({row['trade_count']:.0f} trades)")
    
    print(f"\n⚡ PARAMETER INSIGHTS:")
    best_base = df.groupby('base_trade_percentage')['eth_performance_percent'].mean().idxmax()
    best_trigger = df.groupby('trigger_percentage')['eth_performance_percent'].mean().idxmax()
    best_mult = df.groupby('multiplier')['eth_performance_percent'].mean().idxmax()
    
    print(f"   • Best average base trade %: {best_base}")
    print(f"   • Best average trigger %: {best_trigger}")
    print(f"   • Best average multiplier: {best_mult}")
    
    # Performance vs market comparison
    market_performance = df['price_change_percent'].iloc[0]
    beat_market = (df['eth_performance_percent'] > market_performance).sum()
    print(f"\n📊 MARKET COMPARISON:")
    print(f"   • Market performance: {market_performance:.2f}%")
    print(f"   • Strategies beating market: {beat_market}/{len(df)} ({beat_market/len(df)*100:.1f}%)")
    
    return df.describe()

def main():
    """Main function to run all visualizations"""
    import os
    
    # Create output folder
    os.makedirs(OUTPUT_FOLDER, exist_ok=True)
    
    # Load data
    df = load_and_prepare_data()
    if df is None:
        return
    
    print("Creating visualizations...")
    
    # Create visualizations
    try:
        # 1. Performance Overview
        fig1 = create_performance_overview(df)
        fig1.savefig(f"{OUTPUT_FOLDER}/01_performance_overview.png", dpi=300, bbox_inches='tight')
        plt.close()
        print("✓ Performance overview chart saved")
        
        # 2. Parameter Analysis
        fig2 = create_parameter_analysis(df)
        fig2.savefig(f"{OUTPUT_FOLDER}/02_parameter_analysis.png", dpi=300, bbox_inches='tight')
        plt.close()
        print("✓ Parameter analysis chart saved")
        
        # 3. Correlation Analysis
        fig3 = create_correlation_analysis(df)
        fig3.savefig(f"{OUTPUT_FOLDER}/03_correlation_analysis.png", dpi=300, bbox_inches='tight')
        plt.close()
        print("✓ Correlation analysis chart saved")
        
        # 4. Summary Statistics
        summary_stats = create_summary_statistics(df)
        summary_stats.to_csv(f"{OUTPUT_FOLDER}/04_summary_statistics.csv")
        print("✓ Summary statistics saved")
        
        print(f"\n🎉 All visualizations saved to: {OUTPUT_FOLDER}/")
        print("📁 Files created:")
        print("   • 01_performance_overview.png")
        print("   • 02_parameter_analysis.png") 
        print("   • 03_correlation_analysis.png")
        print("   • 04_summary_statistics.csv")
        
    except Exception as e:
        print(f"Error creating visualizations: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()