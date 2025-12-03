# trend_strategy.py
"""
高级趋势跟踪策略 - 完整版
无未来函数，包含完整回测类
"""

import backtrader as bt
import pandas as pd
import numpy as np
import os
import glob


class AdvancedTrendFollowingStrategy(bt.Strategy):
    """
    高级趋势跟踪策略
    无未来函数，基于历史数据的多时间框架趋势确认
    """

    params = (
        ('printlog', True),
        ('ema_fast', 5),  # 快线周期
        ('ema_slow', 20),  # 慢线周期
        ('trend_period', 50),  # 趋势过滤周期
        ('rsi_period', 14),
        ('rsi_oversold', 30),
        ('rsi_overbought', 70),
        ('volume_threshold', 0.8),
        ('stop_loss', 0.03),
        ('take_profit', 0.08),
        ('position_size', 0.15),
    )

    def __init__(self):
        # 订单跟踪
        self.order = None
        self.entry_price = 0
        self.trade_count = 0
        self.win_count = 0
        self.entry_bar = 0

        # 趋势指标 - 基于历史数据
        self.ema_fast = bt.indicators.EMA(self.data.close, period=self.params.ema_fast)
        self.ema_slow = bt.indicators.EMA(self.data.close, period=self.params.ema_slow)
        self.trend_ma = bt.indicators.EMA(self.data.close, period=self.params.trend_period)
        self.crossover = bt.indicators.CrossOver(self.ema_fast, self.ema_slow)

        # 动量确认指标
        self.rsi = bt.indicators.RSI(self.data.close, period=self.params.rsi_period)
        self.macd = bt.indicators.MACD(self.data.close)

        # 成交量过滤
        self.volume_ma = bt.indicators.SMA(self.data.volume, period=20)
        self.volume_ratio = self.data.volume / self.volume_ma

        # 波动率管理
        self.atr = bt.indicators.ATR(self.data, period=14)

    def log(self, txt, dt=None):
        """日志记录"""
        if self.params.printlog:
            dt = dt or self.datas[0].datetime.date(0)
            print(f'{dt.isoformat()}, {txt}')

    def notify_order(self, order):
        """订单通知"""
        if order.status in [order.Submitted, order.Accepted]:
            return

        if order.status in [order.Completed]:
            if order.isbuy():
                self.entry_price = order.executed.price
                self.entry_bar = len(self.data)
                self.log(f'趋势买入: {order.executed.price:.2f}')
            else:
                profit_pct = (order.executed.price - self.entry_price) / self.entry_price * 100
                if profit_pct > 0:
                    self.win_count += 1
                self.log(f'趋势卖出: {order.executed.price:.2f}, 盈亏: {profit_pct:+.2f}%')
                self.trade_count += 1
            self.order = None

        elif order.status in [order.Canceled, order.Margin, order.Rejected]:
            self.log('订单取消/拒绝')
            self.order = None

    def next(self):
        """策略逻辑"""
        if self.order or len(self.data) < 50:
            return

        # 确保使用历史数据，避免未来函数
        # 所有指标都使用[0]当前值或[-1]历史值

        # 趋势条件 - 使用当前和历史数据
        trend_up = (self.data.close[0] > self.trend_ma[0] and
                    self.ema_fast[0] > self.ema_slow[0])

        # 动量确认 - 使用当前数据
        momentum_ok = (self.rsi[0] > 40 and
                       self.rsi[0] < 80 and
                       self.macd.macd[0] > self.macd.signal[0])

        # 成交量确认
        volume_ok = self.volume_ratio[0] > self.params.volume_threshold

        # 买入条件
        buy_condition = (trend_up and momentum_ok and volume_ok and
                         self.crossover[0] > 0)

        # 卖出条件
        sell_condition = (self.crossover[0] < 0 or
                          (self.position and
                           (self.data.close[0] - self.entry_price) / self.entry_price < -self.params.stop_loss))

        if not self.position:
            if buy_condition:
                size = int(self.broker.getcash() * self.params.position_size / self.data.close[0])
                if size > 0:
                    self.log(f'趋势买入 | 快线:{self.ema_fast[0]:.2f}, 慢线:{self.ema_slow[0]:.2f}')
                    self.order = self.buy(size=size)
        else:
            # 止盈条件
            current_profit = (self.data.close[0] - self.entry_price) / self.entry_price
            take_profit = current_profit > self.params.take_profit

            if sell_condition or take_profit:
                self.log(f'趋势卖出 | 价格:{self.data.close[0]:.2f}')
                self.order = self.close()

    def get_strategy_stats(self):
        """获取策略统计"""
        win_rate = (self.win_count / self.trade_count * 100) if self.trade_count > 0 else 0
        return {
            'total_trades': self.trade_count,
            'win_trades': self.win_count,
            'win_rate': win_rate,
            'final_portfolio_value': self.broker.getvalue()
        }


class TrendBacktest:
    """趋势策略回测类"""

    def __init__(self, data_dir='correct_processed_data'):
        self.data_dir = data_dir
        self.strategy_name = "高级趋势跟踪策略"

    def get_available_files(self):
        """获取可用文件"""
        pattern = os.path.join(self.data_dir, '*.csv')
        return sorted([os.path.basename(f) for f in glob.glob(pattern)])

    def run_backtest(self, data_file, initial_cash=100000.0, **strategy_params):
        """运行回测"""
        cerebro = bt.Cerebro()
        cerebro.broker.setcash(initial_cash)
        cerebro.broker.setcommission(commission=0.0003)

        # 添加策略
        cerebro.addstrategy(AdvancedTrendFollowingStrategy, **strategy_params)

        # 加载数据
        try:
            filepath = os.path.join(self.data_dir, data_file)
            df = pd.read_csv(filepath)
            df['date'] = pd.to_datetime(df['date'])
            df.set_index('date', inplace=True)
            df.sort_index(inplace=True)

            data = bt.feeds.PandasData(
                dataname=df,
                datetime=None,
                open='open',
                high='high',
                low='low',
                close='close',
                volume='volume',
                openinterest=-1
            )
            cerebro.adddata(data)
        except Exception as e:
            print(f"❌ 数据加载失败: {e}")
            return None

        # 添加分析器
        cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name='trades')
        cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name='sharpe')
        cerebro.addanalyzer(bt.analyzers.DrawDown, _name='drawdown')

        print(f"\n🎯 开始回测: {self.strategy_name}")
        print(f"📁 数据文件: {data_file}")
        print(f"💰 初始资金: {initial_cash:,.2f}")
        print("=" * 60)

        # 运行回测
        try:
            results = cerebro.run()
            strat = results[0]

            # 输出结果
            final_value = strat.broker.getvalue()
            total_return = (final_value / initial_cash - 1) * 100
            stats = strat.get_strategy_stats()

            print(f"💰 最终资金: {final_value:,.2f}")
            print(f"📈 总收益率: {total_return:+.2f}%")
            print(f"🔄 总交易次数: {stats['total_trades']}")
            print(f"✅ 胜率: {stats['win_rate']:.2f}%")

            # 分析器结果
            trade_analysis = results[0].analyzers.trades.get_analysis()
            sharpe_analysis = results[0].analyzers.sharpe.get_analysis()
            drawdown_analysis = results[0].analyzers.drawdown.get_analysis()

            if 'sharperatio' in sharpe_analysis:
                print(f"📊 夏普比率: {sharpe_analysis['sharperatio']:.3f}")
            if 'max' in drawdown_analysis:
                print(f"📉 最大回撤: {drawdown_analysis['max']['drawdown']:.2f}%")

            return strat

        except Exception as e:
            print(f"❌ 回测失败: {e}")
            return None


def run_trend_example():
    """运行趋势策略示例"""
    backtester = TrendBacktest(data_dir='correct_processed_data')

    files = backtester.get_available_files()
    if files:
        test_file = files[0]
        backtester.run_backtest(test_file)
    else:
        print("❌ 未找到数据文件")


if __name__ == "__main__":
    run_trend_example()