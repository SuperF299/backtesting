import itertools
import os
from typing import Dict, List, Tuple, Type

import backtrader as bt
import pandas as pd

from trend_strategy import AdvancedTrendFollowingStrategy
from mean_reversion_strategy import AdvancedMeanReversionStrategy
from breakout_strategy import AdvancedBreakoutStrategy
from ml_strategy import AdvancedMachineLearningStrategy


DATA_DIR = 'correct_processed_data'
INITIAL_CASH = 100000
TARGET_RETURN = 3.0
TARGET_WIN = 50.0


def load_data() -> Dict[str, pd.DataFrame]:
    dataframes = {}
    for file in sorted(f for f in os.listdir(DATA_DIR) if f.endswith('.csv')):
        df = pd.read_csv(os.path.join(DATA_DIR, file))
        df['date'] = pd.to_datetime(df['date'])
        df.set_index('date', inplace=True)
        df.sort_index(inplace=True)
        dataframes[file] = df
    return dataframes


DATAFRAMES = load_data()


def evaluate(strategy_cls: Type[bt.Strategy], params: Dict) -> Tuple[float, float, int]:
    """Return avg_return, win_rate, total_trades for given parameter set."""
    total_return = 0.0
    total_trades = 0
    total_wins = 0

    for df in DATAFRAMES.values():
        cerebro = bt.Cerebro()
        cerebro.broker.setcash(INITIAL_CASH)
        cerebro.broker.setcommission(commission=0.0003)
        cerebro.addstrategy(strategy_cls, printlog=False, **params)

        data = bt.feeds.PandasData(
            dataname=df,
            open='open',
            high='high',
            low='low',
            close='close',
            volume='volume'
        )
        cerebro.adddata(data)
        cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name='trades')

        try:
            strat = cerebro.run()[0]
        except Exception as exc:  # pragma: no cover - guard bad parameter combos
            print(f"params {params} failed: {exc}")
            return float('-inf'), 0.0, 0

        final_value = cerebro.broker.getvalue()
        total_return += (final_value / INITIAL_CASH - 1) * 100

        trade_analysis = strat.analyzers.trades.get_analysis()
        trades = trade_analysis.get('total', {}).get('total', 0) if isinstance(trade_analysis, dict) else 0
        wins = trade_analysis.get('won', {}).get('total', 0) if isinstance(trade_analysis, dict) else 0

        total_trades += trades
        total_wins += wins

    avg_return = total_return / len(DATAFRAMES) if DATAFRAMES else 0.0
    win_rate = (total_wins / total_trades * 100) if total_trades else 0.0
    return avg_return, win_rate, total_trades


def grid_search(strategy_cls: Type[bt.Strategy], grid: Dict[str, List], constraint=None):
    keys = list(grid.keys())
    best = {'avg_return': float('-inf')}
    satisfied: List[Dict] = []

    for values in itertools.product(*(grid[k] for k in keys)):
        params = dict(zip(keys, values))
        if constraint and not constraint(params):
            continue
        avg_return, win_rate, trades = evaluate(strategy_cls, params)
        result = {
            'params': params,
            'avg_return': avg_return,
            'win_rate': win_rate,
            'trades': trades,
        }
        if avg_return >= TARGET_RETURN and win_rate >= TARGET_WIN:
            satisfied.append(result)
        if avg_return > best['avg_return']:
            best = result
    return satisfied, best


def main():
    trend_grid = {
        'ema_fast': [8, 10],
        'ema_slow': [30, 38],
        'trend_period': [70, 100],
        'stop_loss': [0.015, 0.02],
        'take_profit': [0.06, 0.09],
        'volume_threshold': [1.0, 1.2],
        'position_size': [0.18, 0.22],
    }
    mean_grid = {
        'bb_dev': [2.0, 2.4],
        'rsi_oversold': [25, 30],
        'stoch_oversold': [15, 25],
        'stop_loss': [0.012, 0.015],
        'take_profit': [0.03, 0.05],
        'max_hold_days': [6, 8],
        'position_size': [0.15, 0.2],
    }
    breakout_grid = {
        'breakout_period': [15, 20],
        'volume_multiplier': [1.1, 1.3],
        'volatility_ratio': [0.8, 1.0],
        'stop_loss': [0.02, 0.03],
        'take_profit': [0.08, 0.12],
        'min_consolidation_bars': [8, 12],
        'position_size': [0.18, 0.22],
    }
    ml_grid = {
        'prediction_threshold_long': [0.68, 0.72],
        'prediction_threshold_short': [0.4, 0.45],
        'stop_loss': [0.02, 0.025],
        'take_profit': [0.06, 0.08],
        'position_size': [0.12, 0.16],
        'min_hold_bars': [4, 6],
        'max_hold_bars': [20, 30],
    }

    print('Optimizing trend strategy...')
    satisfied, best = grid_search(
        AdvancedTrendFollowingStrategy,
        trend_grid,
        constraint=lambda p: p['ema_fast'] < p['ema_slow']
    )
    print('  satisfied:', satisfied[:3])
    print('  best:', best)

    print('Optimizing mean reversion strategy...')
    satisfied, best = grid_search(AdvancedMeanReversionStrategy, mean_grid)
    print('  satisfied:', satisfied[:3])
    print('  best:', best)

    print('Optimizing breakout strategy...')
    satisfied, best = grid_search(AdvancedBreakoutStrategy, breakout_grid)
    print('  satisfied:', satisfied[:3])
    print('  best:', best)

    print('Optimizing ML strategy...')
    satisfied, best = grid_search(AdvancedMachineLearningStrategy, ml_grid)
    print('  satisfied:', satisfied[:3])
    print('  best:', best)


if __name__ == '__main__':
    main()

