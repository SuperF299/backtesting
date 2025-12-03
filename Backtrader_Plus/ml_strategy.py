# ml_strategy.py
"""
高级机器学习策略 - 完整版
无未来函数，包含完整回测类
"""

import backtrader as bt
import pandas as pd
import numpy as np
import os
import glob


class AdvancedMachineLearningStrategy(bt.Strategy):
    """
    高级机器学习策略
    无未来函数，基于多因子集成学习
    """

    params = (
        ('printlog', True),
        ('prediction_threshold_long', 0.65),
        ('prediction_threshold_short', 0.35),
        ('stop_loss', 0.03),
        ('take_profit', 0.08),
        ('position_size', 0.12),
        ('min_hold_bars', 5),
        ('max_hold_bars', 30),
    )

    def __init__(self):
        # 订单跟踪
        self.order = None
        self.entry_price = 0
        self.entry_bar = 0
        self.trade_count = 0
        self.win_count = 0

        # 多因子特征指标 - 全部基于历史数据
        # 价格特征
        self.roc_5 = bt.indicators.ROC(self.data.close, period=5)
        self.roc_10 = bt.indicators.ROC(self.data.close, period=10)
        self.roc_20 = bt.indicators.ROC(self.data.close, period=20)

        # 均线特征
        self.sma_10 = bt.indicators.SMA(self.data.close, period=10)
        self.sma_20 = bt.indicators.SMA(self.data.close, period=20)
        self.sma_50 = bt.indicators.SMA(self.data.close, period=50)
        self.price_vs_sma_10 = self.data.close / self.sma_10 - 1
        self.price_vs_sma_20 = self.data.close / self.sma_20 - 1

        # 技术指标特征
        self.rsi = bt.indicators.RSI(self.data.close, period=14)
        self.macd = bt.indicators.MACD(self.data.close)
        self.stoch = bt.indicators.Stochastic(self.data)

        # 布林带特征
        self.bb = bt.indicators.BollingerBands(self.data.close, period=20, devfactor=2)
        self.bb_position = (self.data.close - self.bb.lines.bot) / (self.bb.lines.top - self.bb.lines.bot)

        # 成交量特征
        self.volume_ma = bt.indicators.SMA(self.data.volume, period=20)
        self.volume_ratio = self.data.volume / self.volume_ma

        # 波动率特征
        self.atr = bt.indicators.ATR(self.data, period=14)
        self.volatility = self.atr / self.data.close

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
                self.log(f'ML买入: {order.executed.price:.2f}')
            else:
                profit_pct = (order.executed.price - self.entry_price) / self.entry_price * 100
                if profit_pct > 0:
                    self.win_count += 1
                self.log(f'ML卖出: {order.executed.price:.2f}, 盈亏: {profit_pct:+.2f}%')
                self.trade_count += 1
            self.order = None

        elif order.status in [order.Canceled, order.Margin, order.Rejected]:
            self.log('订单取消/拒绝')
            self.order = None

    def calculate_ml_signal(self):
        """计算机器学习信号 - 无未来函数"""
        if len(self.data) < 50:
            return 0.5, 0.0

        bullish_factors = 0
        total_factors = 0

        # 1. 价格动量因子 (25%)
        momentum_score = 0
        momentum_factors = 0

        if self.roc_5[0] > 0: momentum_score += 1
        momentum_factors += 1
        if self.roc_10[0] > 0: momentum_score += 1
        momentum_factors += 1
        if self.roc_20[0] > 0: momentum_score += 1
        momentum_factors += 1

        momentum_prob = momentum_score / momentum_factors if momentum_factors > 0 else 0.5

        # 2. 趋势因子 (25%)
        trend_score = 0
        trend_factors = 0

        if self.price_vs_sma_10[0] > 0: trend_score += 1
        trend_factors += 1
        if self.price_vs_sma_20[0] > 0: trend_score += 1
        trend_factors += 1
        if self.macd.macd[0] > self.macd.signal[0]: trend_score += 1
        trend_factors += 1

        trend_prob = trend_score / trend_factors if trend_factors > 0 else 0.5

        # 3. 均值回归因子 (25%)
        mean_reversion_score = 0
        mean_reversion_factors = 0

        if 30 < self.rsi[0] < 70: mean_reversion_score += 1
        mean_reversion_factors += 1
        if 0.2 < self.bb_position[0] < 0.8: mean_reversion_score += 1
        mean_reversion_factors += 1
        if 20 < self.stoch[0] < 80: mean_reversion_score += 1
        mean_reversion_factors += 1

        mean_reversion_prob = mean_reversion_score / mean_reversion_factors if mean_reversion_factors > 0 else 0.5

        # 4. 市场情绪因子 (25%)
        sentiment_score = 0
        sentiment_factors = 0

        if self.volume_ratio[0] > 0.8: sentiment_score += 1
        sentiment_factors += 1
        if self.data.close[0] > self.data.open[0]: sentiment_score += 1  # 阳线
        sentiment_factors += 1
        if self.volatility[0] < 0.04: sentiment_score += 1  # 低波动率
        sentiment_factors += 1

        sentiment_prob = sentiment_score / sentiment_factors if sentiment_factors > 0 else 0.5

        # 集成预测
        final_prob = (momentum_prob * 0.25 +
                      trend_prob * 0.25 +
                      mean_reversion_prob * 0.25 +
                      sentiment_prob * 0.25)

        # 置信度计算
        confidence = 1 - abs((momentum_prob + trend_prob + mean_reversion_prob + sentiment_prob) / 4 - 0.5) * 2

        return final_prob, confidence

    def next(self):
        """策略逻辑"""
        if self.order or len(self.data) < 50:
            return

        # 计算ML信号 - 使用当前和历史数据
        bullish_probability, confidence = self.calculate_ml_signal()

        current_bar = len(self.data)
        hold_bars = current_bar - self.entry_bar if self.position else 0

        if not self.position:
            # 买入条件：高看涨概率且合理置信度
            if (bullish_probability > self.params.prediction_threshold_long and
                    confidence > 0.4 and
                    hold_bars == 0):

                size = int(self.broker.getcash() * self.params.position_size / self.data.close[0])
                if size > 0:
                    self.log(f'ML买入 | 看涨概率:{bullish_probability:.3f}, 置信度:{confidence:.3f}')
                    self.order = self.buy(size=size)

        else:
            # 持仓管理
            current_profit = (self.data.close[0] - self.entry_price) / self.entry_price
            hold_too_long = hold_bars >= self.params.max_hold_bars

            # 卖出条件
            sell_condition = (
                    bullish_probability < self.params.prediction_threshold_short or
                    current_profit > self.params.take_profit or
                    current_profit < -self.params.stop_loss or
                    hold_too_long
            )

            if sell_condition and hold_bars >= self.params.min_hold_bars:
                profit_pct = current_profit * 100
                self.log(f'ML卖出 | 看涨概率:{bullish_probability:.3f}, 盈亏:{profit_pct:+.2f}%')
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


class MLBacktest:
    """机器学习策略回测类"""

    def __init__(self, data_dir='correct_processed_data'):
        self.data_dir = data_dir
        self.strategy_name = "高级机器学习策略"

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
        cerebro.addstrategy(AdvancedMachineLearningStrategy, **strategy_params)

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


def run_ml_example():
    """运行机器学习策略示例"""
    backtester = MLBacktest(data_dir='correct_processed_data')

    files = backtester.get_available_files()
    if files:
        test_file = files[0]
        backtester.run_backtest(test_file)
    else:
        print("❌ 未找到数据文件")


if __name__ == "__main__":
    run_ml_example()