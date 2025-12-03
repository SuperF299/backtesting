# mean_reversion_strategy.py
"""
高级均值回归策略 - 完整版
无未来函数，包含完整回测类
"""

import backtrader as bt
import pandas as pd
import numpy as np
import os
import glob


class AdvancedMeanReversionStrategy(bt.Strategy):
    """
    高级均值回归策略
    无未来函数，基于统计套利原理
    """

    params = (
        ('printlog', True),
        ('bb_period', 20),
        ('bb_dev', 2.0),
        ('rsi_period', 14),
        ('rsi_oversold', 30),
        ('rsi_overbought', 70),
        ('stoch_oversold', 20),
        ('stoch_overbought', 80),
        ('mean_reversion_period', 30),
        ('stop_loss', 0.02),
        ('take_profit', 0.04),
        ('position_size', 0.12),
        ('max_hold_days', 10),
    )

    def __init__(self):
        # 订单跟踪
        self.order = None
        self.entry_price = 0
        self.entry_bar = 0
        self.trade_count = 0
        self.win_count = 0
        self.hold_days = 0

        # 布林带指标 - 基于历史数据
        self.bb = bt.indicators.BollingerBands(
            self.data.close,
            period=self.params.bb_period,
            devfactor=self.params.bb_dev
        )
        self.bb_position = (self.data.close - self.bb.lines.bot) / (self.bb.lines.top - self.bb.lines.bot)

        # 振荡指标
        self.rsi = bt.indicators.RSI(self.data.close, period=self.params.rsi_period)
        self.stoch = bt.indicators.Stochastic(self.data)

        # 均值回归统计
        self.sma_mean = bt.indicators.SMA(self.data.close, period=self.params.mean_reversion_period)
        self.zscore = (self.data.close - self.sma_mean) / bt.indicators.StdDev(
            self.data.close, period=self.params.mean_reversion_period
        )

        # 成交量确认
        self.volume_ma = bt.indicators.SMA(self.data.volume, period=20)
        self.volume_ratio = self.data.volume / self.volume_ma

        # 反转确认
        self.reversal_signal = bt.indicators.CrossOver(self.rsi, 30)

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
                self.hold_days = 0
                self.log(f'均值买入: {order.executed.price:.2f}')
            else:
                profit_pct = (order.executed.price - self.entry_price) / self.entry_price * 100
                if profit_pct > 0:
                    self.win_count += 1
                self.log(f'均值卖出: {order.executed.price:.2f}, 盈亏: {profit_pct:+.2f}%')
                self.trade_count += 1
            self.order = None

        elif order.status in [order.Canceled, order.Margin, order.Rejected]:
            self.log('订单取消/拒绝')
            self.order = None

    def next(self):
        """策略逻辑"""
        if self.order or len(self.data) < 50:
            return

        if self.position:
            self.hold_days += 1

        # 均值回归信号 - 使用当前和历史数据
        oversold = (self.bb_position[0] < 0.05 or
                    self.rsi[0] < self.params.rsi_oversold or
                    self.stoch[0] < self.params.stoch_oversold)

        overbought = (self.bb_position[0] > 0.95 or
                      self.rsi[0] > self.params.rsi_overbought or
                      self.stoch[0] > self.params.stoch_overbought)

        # 反转确认 - 使用当前数据
        reversal_confirmed = self.reversal_signal[0] > 0
        volume_ok = self.volume_ratio[0] > 0.8

        if not self.position:
            # 买入条件：超卖反弹
            if oversold and reversal_confirmed and volume_ok:
                size = int(self.broker.getcash() * self.params.position_size / self.data.close[0])
                if size > 0:
                    self.log(f'均值买入 | RSI:{self.rsi[0]:.2f}, Z-score:{self.zscore[0]:.2f}')
                    self.order = self.buy(size=size)
        else:
            # 卖出条件 - 使用当前数据
            current_profit = (self.data.close[0] - self.entry_price) / self.entry_price
            target_profit = current_profit > self.params.take_profit
            stop_loss = current_profit < -self.params.stop_loss
            hold_expired = self.hold_days >= self.params.max_hold_days
            reached_mean = abs(self.zscore[0]) < 0.5
            overbought_exit = overbought and self.hold_days > 3

            if target_profit or stop_loss or hold_expired or reached_mean or overbought_exit:
                profit_pct = current_profit * 100
                self.log(f'均值卖出 | 持仓:{self.hold_days}天, 盈亏:{profit_pct:+.2f}%')
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


class MeanReversionBacktest:
    """均值回归策略回测类"""

    def __init__(self, data_dir='correct_processed_data'):
        self.data_dir = data_dir
        self.strategy_name = "高级均值回归策略"

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
        cerebro.addstrategy(AdvancedMeanReversionStrategy, **strategy_params)

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


def run_mean_reversion_example():
    """运行均值回归策略示例"""
    backtester = MeanReversionBacktest(data_dir='correct_processed_data')

    files = backtester.get_available_files()
    if files:
        test_file = files[0]
        backtester.run_backtest(test_file)
    else:
        print("❌ 未找到数据文件")


if __name__ == "__main__":
    run_mean_reversion_example()