import os
import pandas as pd
import backtrader as bt
from trend_strategy import AdvancedTrendFollowingStrategy
from mean_reversion_strategy import AdvancedMeanReversionStrategy
from breakout_strategy import AdvancedBreakoutStrategy
from ml_strategy import AdvancedMachineLearningStrategy

data_dir = 'correct_processed_data'
files = sorted(f for f in os.listdir(data_dir) if f.endswith('.csv'))
strategies = [
    (AdvancedTrendFollowingStrategy, 'trend'),
    (AdvancedMeanReversionStrategy, 'mean'),
    (AdvancedBreakoutStrategy, 'breakout'),
    (AdvancedMachineLearningStrategy, 'ml'),
]

for strat_cls, name in strategies:
    best = None
    summary = []
    aggregate_return = 0.0
    aggregate_wins = 0
    aggregate_trades = 0
    for file in files:
        cerebro = bt.Cerebro()
        cerebro.broker.setcash(100000)
        cerebro.broker.setcommission(commission=0.0003)
        cerebro.addstrategy(strat_cls, printlog=False)
        df = pd.read_csv(os.path.join(data_dir, file))
        df['date'] = pd.to_datetime(df['date'])
        df.set_index('date', inplace=True)
        df.sort_index(inplace=True)
        data = bt.feeds.PandasData(dataname=df, open='open', high='high', low='low', close='close', volume='volume')
        cerebro.adddata(data)
        cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name='trades')
        strat = cerebro.run()[0]
        final = cerebro.broker.getvalue()
        ret = (final / 100000 - 1) * 100
        trade_analysis = strat.analyzers.trades.get_analysis()
        total = trade_analysis.get('total', {}).get('total', 0) if isinstance(trade_analysis, dict) else 0
        won = trade_analysis.get('won', {}).get('total', 0) if isinstance(trade_analysis, dict) else 0
        win_rate = won / total * 100 if total else 0
        summary.append((file, ret, win_rate, total))
        aggregate_return += ret
        aggregate_wins += won
        aggregate_trades += total
        if best is None or ret > best[1]:
            best = (file, ret, win_rate)
    print(name, 'best', best)
    for file, ret, win_rate, total in summary:
        print('  ', file, f"ret {ret:.2f}%", f"win {win_rate:.1f}%", f"trades {total}")
    avg_return = aggregate_return / len(files) if files else 0.0
    overall_win = (aggregate_wins / aggregate_trades * 100) if aggregate_trades else 0.0
    print('  overall', f"avg_ret {avg_return:.2f}%", f"win_rate {overall_win:.1f}%", f"trades {aggregate_trades}")
