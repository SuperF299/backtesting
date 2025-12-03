# breakout_strategy.py
"""
高级突破策略 - 完整版
无未来函数，包含完整回测类
"""

import backtrader as bt
import pandas as pd
import numpy as np
import os
import glob


class AdvancedBreakoutStrategy(bt.Strategy):
    """
    高级突破策略
    无未来函数，基于波动率压缩和价格突破
    """

    params = (
        ('printlog', True),
        ('breakout_period', 20),
        ('volume_multiplier', 1.5),
        ('volatility_ratio', 0.7),
        ('stop_loss', 0.03),
        ('take_profit', 0.10),
        ('position_size', 0.15),
        ('min_consolidation_bars', 10),
    )

    def __init__(self):
        # 订单跟踪
        self.order = None
        self.entry_price = 0
        self.entry_bar = 0
        self.trade_count = 0
        self.win_count = 0

        # 突破检测指标 - 基于历史数据
        self.resistance = bt.indicators.Highest(self.data.high, period=self.params.breakout_period)
        self.support = bt.indicators.Lowest(self.data.low, period=self.params.breakout_period)
        self.consolidation_range = self.resistance - self.support
        self.consolidation_ratio = self.consolidation_range / self.data.close

        # 波动率压缩检测
        self.true_range = bt.indicators.TrueRange(self.data)
        self.avg_true_range = bt.indicators.SMA(self.true_range, period=self.params.breakout_period)
        self.volatility_ratio = self.true_range / self.avg_true_range

        # 突破信号
        self.breakout_signal = bt.indicators.CrossOver(self.data.high, self.resistance)
        self.breakdown_signal = bt.indicators.CrossOver(self.data.low, self.support)

        # 成交量确认
        self.volume_ma = bt.indicators.SMA(self.data.volume, period=20)
        self.volume_ratio = self.data.volume / self.volume_ma

        # 动量确认
        self.breakout_momentum = bt.indicators.ROC(self.data.close, period=5)

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
                self.log(f'突破买入: {order.executed.price:.2f}')
            else:
                profit_pct = (order.executed.price - self.entry_price) / self.entry_price * 100
                if profit_pct > 0:
                    self.win_count += 1
                self.log(f'突破卖出: {order.executed.price:.2f}, 盈亏: {profit_pct:+.2f}%')
                self.trade_count += 1
            self.order = None

        elif order.status in [order.Canceled, order.Margin, order.Rejected]:
            self.log('订单取消/拒绝')
            self.order = None

    def next(self):
        """策略逻辑"""
        if self.order or len(self.data) < self.params.breakout_period + 10:
            return

        # 整理形态判断 - 使用当前和历史数据
        tight_consolidation = self.consolidation_ratio[0] < 0.08
        low_volatility = self.volatility_ratio[0] < self.params.volatility_ratio
        sufficient_consolidation = len(self.data) > self.params.min_consolidation_bars

        # 突破信号 - 使用当前数据
        high_breakout = self.breakout_signal[0] > 0
        low_breakdown = self.breakdown_signal[0] > 0

        # 成交量确认
        volume_confirmation = self.volume_ratio[0] > self.params.volume_multiplier

        # 动量确认
        positive_momentum = self.breakout_momentum[0] > 0

        if not self.position:
            # 上突破买入条件
            if (high_breakout and tight_consolidation and low_volatility and
                    sufficient_consolidation and volume_confirmation and positive_momentum):

                size = int(self.broker.getcash() * self.params.position_size / self.data.close[0])
                if size > 0:
                    self.log(f'突破买入 | 价格:{self.data.close[0]:.2f}, 前高:{self.resistance[0]:.2f}')
                    self.order = self.buy(size=size)

        else:
            # 持仓中的管理
            current_profit = (self.data.close[0] - self.entry_price) / self.entry_price

            # 下突破止损
            if low_breakdown:
                self.log(f'假突破止损 | 价格:{self.data.close[0]:.2f}')
                self.order = self.close()
                return

            # 止盈止损
            take_profit = current_profit > self.params.take_profit
            stop_loss = current_profit < -self.params.stop_loss

            if take_profit or stop_loss:
                profit_pct = current_profit * 100
                self.log(f'突破退出 | 盈亏:{profit_pct:+.2f}%')
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


class BreakoutBacktest:
    """突破策略回测类"""

    def __init__(self, data_dir='correct_processed_data'):
        self.data_dir = data_dir
        self.strategy_name = "高级突破策略"

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
        cerebro.addstrategy(AdvancedBreakoutStrategy, **strategy_params)

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


def run_breakout_example():
    """运行突破策略示例"""
    backtester = BreakoutBacktest(data_dir='correct_processed_data')

    files = backtester.get_available_files()
    if files:
        test_file = files[0]
        backtester.run_backtest(test_file)
    else:
        print("❌ 未找到数据文件")


if __name__ == "__main__":
    run_breakout_example()