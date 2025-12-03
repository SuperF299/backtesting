# optimized_backtest_v2.py
"""
双均线策略 - 专业优化版
集成：ADX过滤、ATR风险控仓、无滞后信号、高效部分减仓、智能移动止损、保本止损
"""

import backtrader as bt
import pandas as pd
import os
import glob
import numpy as np
from itertools import product
import math


class ProfessionalDoubleMAStrategy(bt.Strategy):
    """
    专业优化版双均线策略
    """
    params = (
        # --- 信号参数 ---
        ('fast_period', 10),  # 快线
        ('slow_period', 30),  # 慢线
        ('trend_period', 60),  # 趋势过滤 (EMA)

        # --- 风险管理参数 ---
        ('risk_pct', 0.02),  # 单笔交易风险 (2% 总资金)
        ('atr_period', 14),  # ATR 周期
        ('atr_stop_mult', 2.0),  # 初始止损距离 (N倍ATR)
        ('max_pos_size', 0.8),  # 最大单次持仓比例 (防止单吊)

        # --- 交易逻辑参数 ---
        ('retain_pct', 0.15),  # 死叉后保留仓位比例
        ('trail_trigger', 0.005),  # 移动止损更新阈值 (0.5%)，防止订单刷屏

        # --- 过滤器开关 ---
        ('use_vol_filter', True),  # 成交量过滤
        ('use_rsi_filter', True),  # RSI 过滤

        # --- ADX 过滤（新增） ---
        ('use_adx_filter', True),
        ('adx_period', 14),
        ('adx_threshold', 25),

        ('printlog', True),
    )

    def __init__(self):
        # 1. 均线指标 (使用当前 [0] 逻辑，无滞后)
        self.fast_ma = bt.indicators.EMA(self.data.close, period=self.params.fast_period)
        self.slow_ma = bt.indicators.EMA(self.data.close, period=self.params.slow_period)
        self.crossover = bt.indicators.CrossOver(self.fast_ma, self.slow_ma)

        # 2. 趋势过滤 (升级为 EMA)
        self.trend_ma = bt.indicators.EMA(self.data.close, period=self.params.trend_period)

        # 3. 波动率指标 (用于仓位计算和动态止损)
        self.atr = bt.indicators.ATR(self.data, period=self.params.atr_period)

        # 4. 辅助过滤器
        if self.params.use_rsi_filter:
            self.rsi = bt.indicators.RSI(self.data.close, period=14)

        if self.params.use_vol_filter:
            self.vol_ma = bt.indicators.SMA(self.data.volume, period=20)

        # 5. ADX 指标（趋势强度过滤）
        if self.params.use_adx_filter:
            # backtrader 提供 ADX 指标（含 +DI 和 -DI）
            self.adx = bt.indicators.ADX(self.data, period=self.params.adx_period)

        # 6. 交易状态变量
        self.stop_order = None  # 止损单对象
        self.last_stop_price = 0  # 记录上一次止损价，防止频繁改单

        # 保本止损相关
        self.entry_price = 0
        self.initial_stop = 0
        self.break_even_active = False

        # 统计变量
        self.trade_count = 0
        self.win_count = 0

    def log(self, txt, dt=None):
        if self.params.printlog:
            dt = dt or self.datas[0].datetime.date(0)
            try:
                print(f'{dt.isoformat()}, {txt}')
            except Exception:
                print(f'{dt}, {txt}')

    def notify_order(self, order):
        # 订单状态回调
        if order.status in [order.Completed]:
            if order.isbuy():
                self.entry_price = order.executed.price
                self.log(f'✅ 买入成交: {order.executed.price:.2f}, 数量: {order.executed.size}')
            elif order.issell():
                # 计算这笔卖出的盈亏
                try:
                    pnl = (order.executed.price - self.entry_price) * abs(order.executed.size)
                except Exception:
                    pnl = 0
                symbol = "🟢" if pnl > 0 else "🔴"
                self.log(
                    f'{symbol} 卖出成交: {order.executed.price:.2f}, 数量: {abs(order.executed.size)}, 本次盈亏: {pnl:.2f}')

                # 只有平仓行为才计入胜率统计（不包括开空仓，本策略只做多）
                # 注意：由于 backtrader 的 position 在 notify_order 时尚未更新为最新，需要在这里用 executed.size 判断
                # 我们采用 trade analyzer 作为最终统计，但保留简单统计
                if self.position.size == 0:
                    self.trade_count += 1
                    if order.executed.price > self.entry_price:
                        self.win_count += 1

        elif order.status in [order.Canceled, order.Margin, order.Rejected]:
            # 可选打印订单被取消/拒绝
            # self.log(f'⚠️ 订单被取消/拒绝: {order.getstatusname()}')
            pass

        # 订单完成后重置引用（如果是我们曾挂的止损单）
        if order.status in [order.Completed, order.Canceled, order.Margin, order.Rejected]:
            if self.stop_order and hasattr(self.stop_order, 'ref') and order.ref == self.stop_order.ref:
                # 如果止损单被触发或取消，清除引用
                self.stop_order = None

    # ===========================
    #   计算仓位大小（risk-based）
    # ===========================
    def calculate_risk_size(self):
        """
        根据 ATR 计算风险仓位：
        - 每笔交易风险 = 账户总权益 * risk_pct
        - 单位风险 = ATR * atr_stop_mult
        - 仓位 = 每笔风险 / 单位风险
        - 同时受 max_pos_size 限制（占总资产比例）
        """
        try:
            account_value = self.broker.get_value()  # 使用总权益更稳妥
            close = self.data.close[0]
            atr = self.atr[0]
        except Exception:
            return 0

        # 数据不足，或 ATR 无效，直接不下单
        if atr is None or atr <= 0 or close is None or close <= 0:
            return 0

        # 每笔交易最大可承受亏损金额
        risk_money = account_value * self.params.risk_pct

        # 每股风险金额（用 ATR * multiplier 作为止损距离）
        per_share_risk = atr * self.params.atr_stop_mult

        if per_share_risk <= 0:
            return 0

        target_size = int(risk_money / per_share_risk)

        # 限制最大仓位（按资金比例）
        max_shares = int((account_value * self.params.max_pos_size) / close)
        if max_shares < 0:
            max_shares = 0

        size = min(target_size, max_shares)
        if size < 0:
            size = 0
        return size

    def next(self):
        # 确保有足够数据
        if len(self.data) < max(self.params.trend_period, self.params.slow_period) + 2:
            return

        # --- 1. 信号生成 (使用当前 [0] 数据) ---

        # 趋势条件：价格在长期EMA之上
        trend_ok = self.data.close[0] > self.trend_ma[0]

        # RSI条件：趋势策略只看是否处于多头区域 (>50)
        rsi_ok = True
        if self.params.use_rsi_filter:
            rsi_ok = self.rsi[0] > 50

        # 成交量条件：当前量 > 均量 * 0.8
        vol_ok = True
        if self.params.use_vol_filter:
            # 防止 vol_ma 为 nan
            try:
                vol_ok = self.data.volume[0] > (self.vol_ma[0] * 0.8)
            except Exception:
                vol_ok = True

        # ADX 趋势强度过滤
        adx_ok = True
        if self.params.use_adx_filter:
            try:
                adx_ok = self.adx[0] > self.params.adx_threshold
            except Exception:
                adx_ok = True

        # 综合买入信号
        buy_signal = (self.crossover > 0) and trend_ok and rsi_ok and vol_ok and adx_ok

        # 综合卖出信号 (死叉)
        sell_signal = self.crossover < 0

        # --- 2. 持仓逻辑 ---

        if not self.position:
            # 空仓时检查买入
            if buy_signal:
                size = self.calculate_risk_size()
                if size > 0:
                    self.log(f'📈 金叉买入信号 | ATR: {self.atr[0]:.2f} | 计划仓位: {size}')
                    buyord = self.buy(size=size)

                    # 设置初始止损 (价格 - N*ATR)
                    stop_price = self.data.close[0] - (self.atr[0] * self.params.atr_stop_mult)
                    # 挂止损单（卖出止损）
                    try:
                        self.stop_order = self.sell(size=size, exectype=bt.Order.Stop, price=stop_price)
                        self.last_stop_price = stop_price
                        self.initial_stop = stop_price
                        self.break_even_active = False
                        self.log(f'🛡️ 初始止损设置: {stop_price:.2f}')
                    except Exception as e:
                        # 如果止损单挂单失败，记录日志但不阻止策略继续
                        self.log(f'⚠️ 初始止损挂单失败: {e}')

        else:
            # 持仓时逻辑
            cur_price = self.data.close[0]

            # A. 保本止损逻辑（只要有浮盈，就尽量不让它变亏损）
            # 触发条件：价格相对于开仓价上涨超过初始风险的一定比例（这里取60%）
            if not self.break_even_active and self.entry_price and self.initial_stop:
                try:
                    initial_risk = self.entry_price - self.initial_stop
                    # 如果 initial_risk 非常小（价格几乎没有差距），避免无限触发
                    if initial_risk > 0 and (cur_price - self.entry_price) > (initial_risk * 0.6):
                        # new stop 设置为开仓价 + 0.1%（避免被常见跳空/穿刺带走）
                        new_stop = self.entry_price * 1.001
                        # 只有在 new_stop 高于当前 last_stop_price 时才更新
                        if not self.stop_order or new_stop > self.last_stop_price:
                            if self.stop_order:
                                try:
                                    self.cancel(self.stop_order)
                                except Exception:
                                    pass
                            try:
                                self.stop_order = self.sell(size=self.position.size, exectype=bt.Order.Stop, price=new_stop)
                                self.last_stop_price = new_stop
                                self.break_even_active = True
                                self.log(f'🟩 保本止损生效 → {new_stop:.2f}')
                            except Exception as e:
                                self.log(f'⚠️ 保本止损下单失败: {e}')
                except Exception:
                    pass

            # B. 智能移动止损 (Trailing Stop) — 仍然保留，但不会把止损下移
            try:
                dynamic_stop = cur_price - (self.atr[0] * self.params.atr_stop_mult)
            except Exception:
                dynamic_stop = None

            if dynamic_stop:
                # 只有当新止损价 高于 旧止损价 且超过阈值时，才更新 (防止 Order Spam)
                try:
                    if self.position.size > 0 and self.stop_order:
                        if dynamic_stop > self.last_stop_price * (1 + self.params.trail_trigger):
                            # 不允许把止损下移（保证保本原则）
                            if dynamic_stop > self.last_stop_price:
                                try:
                                    self.log(f'🔄 移动止损上移: {self.last_stop_price:.2f} -> {dynamic_stop:.2f}')
                                    self.cancel(self.stop_order)
                                    self.stop_order = self.sell(size=self.position.size, exectype=bt.Order.Stop, price=dynamic_stop)
                                    self.last_stop_price = dynamic_stop
                                except Exception as e:
                                    self.log(f'⚠️ 移动止损改单失败: {e}')
                except Exception:
                    pass

            # C. 死叉部分减仓
            if sell_signal:
                current_pos = self.position.size
                retain_size = int(current_pos * self.params.retain_pct)
                sell_size = current_pos - retain_size

                if sell_size > 0:
                    try:
                        self.log(f'📉 死叉减仓: 卖出 {sell_size}, 保留 {retain_size} (底仓)')
                        self.sell(size=sell_size)
                    except Exception as e:
                        self.log(f'⚠️ 减仓下单失败: {e}')

                    # 重要：减仓后，必须更新止损单的数量（取消旧单，挂新单）
                    if self.stop_order:
                        try:
                            self.cancel(self.stop_order)
                        except Exception:
                            pass

                    if retain_size > 0:
                        try:
                            new_stop_price = max(self.last_stop_price, self.data.low[0] - self.atr[0])
                            self.stop_order = self.sell(size=retain_size, exectype=bt.Order.Stop, price=new_stop_price)
                            self.last_stop_price = new_stop_price
                        except Exception as e:
                            self.log(f'⚠️ 死叉后挂新止损失败: {e}')


class OptimizedBacktest:
    """优化版回测引擎"""

    def __init__(self, data_dir='correct_processed_data'):
        self.data_dir = data_dir
        self.target_win_rate = 0.5
        self.target_return = 5.0  # 提高一点目标

        # 基础参数字典 (默认值)
        self.base_strategy_params = dict(
            fast_period=10,
            slow_period=30,
            trend_period=60,
            risk_pct=0.02,
            atr_stop_mult=2.0,
            retain_pct=0.15,
            printlog=True,
        )
        self.param_grid = self.build_param_grid()

    def build_param_grid(self):
        """
        构建参数网格
        注意：这里的参数名必须与 Strategy 类的 params 匹配
        """
        # 均线组合
        ma_combinations = [
            (5, 20), (10, 30), (10, 60)
        ]
        trend_periods = [60, 90]

        # 风险偏好 (激进 vs 稳健)
        risk_profiles = [
            {'atr_stop_mult': 2.0, 'retain_pct': 0.15},  # 紧凑止损，保留少
            {'atr_stop_mult': 3.0, 'retain_pct': 0.20},  # 宽幅止损，保留多
        ]

        grid = []
        for fast, slow in ma_combinations:
            for trend in trend_periods:
                for risk in risk_profiles:
                    params = {
                        'fast_period': fast,
                        'slow_period': slow,
                        'trend_period': trend,
                    }
                    params.update(risk)
                    grid.append(params)
        return grid

    def _prepare_dataframe(self, filepath):
        try:
            df = pd.read_csv(filepath)
            df['date'] = pd.to_datetime(df['date'])
            df.set_index('date', inplace=True)
            df.sort_index(inplace=True)
            return df
        except Exception as e:
            print(f"❌ 数据加载失败: {e}")
            return None

    def _setup_cerebro(self, initial_cash, df, strategy_params):
        cerebro = bt.Cerebro()
        cerebro.broker.setcash(initial_cash)
        cerebro.broker.setcommission(commission=0.0003)  # 万3手续费

        data = bt.feeds.PandasData(
            dataname=df.copy(),
            datetime=None,
            open='open', high='high', low='low', close='close', volume='volume',
            openinterest=-1
        )
        cerebro.adddata(data)
        cerebro.addstrategy(ProfessionalDoubleMAStrategy, **strategy_params)

        # 分析器
        cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name='sharpe')
        cerebro.addanalyzer(bt.analyzers.DrawDown, _name='drawdown')
        cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name='trades')

        return cerebro

    def optimize_strategy(self, df, initial_cash):
        if not self.param_grid: return None
        print("\n🧠 启动参数优化 (ATR风控模式)...")

        best_result = None

        for i, candidate in enumerate(self.param_grid):
            # 复制参数并关闭日志
            strategy_params = dict(self.base_strategy_params)
            strategy_params.update(candidate)
            strategy_params['printlog'] = False

            cerebro = self._setup_cerebro(initial_cash, df, strategy_params)

            try:
                results = cerebro.run()
                strat = results[0]
            except Exception:
                continue

            final_value = cerebro.broker.getvalue()
            profit_pct = (final_value / initial_cash - 1) * 100

            # 简单的评分标准：收益优先，但要求至少有交易
            if strat.trade_count > 0:
                if best_result is None or profit_pct > best_result['profit_pct']:
                    best_result = {
                        'params': candidate,
                        'profit_pct': profit_pct,
                        'win_rate': (strat.win_count / strat.trade_count) if strat.trade_count else 0
                    }
                    # 进度条效果
                    print(f"\r🔍 扫描中 [{i + 1}/{len(self.param_grid)}] 当前最佳: {profit_pct:.2f}%", end="")

        print(f"\n✅ 优化完成. 最佳收益: {best_result['profit_pct']:.2f}%" if best_result else "\n⚠️ 优化失败")
        return best_result

    def run_single_backtest(self, filename, initial_cash=100000.0, optimize=True):
        print(f"\n🎯 开始回测: {filename}")

        filepath = os.path.join(self.data_dir, filename)
        df = self._prepare_dataframe(filepath)
        if df is None: return

        strategy_params = dict(self.base_strategy_params)

        if optimize:
            opt_res = self.optimize_strategy(df, initial_cash)
            if opt_res:
                strategy_params.update(opt_res['params'])
                print(f"⚙️ 采用最优参数: {opt_res['params']}")

        strategy_params['printlog'] = True
        cerebro = self._setup_cerebro(initial_cash, df, strategy_params)

        results = cerebro.run()
        strat = results[0]

        final_val = cerebro.broker.getvalue()
        ret_pct = (final_val / initial_cash - 1) * 100

        print(f"\n💰 最终资金: {final_val:.2f} (收益率: {ret_pct:+.2f}%)")

        # 打印分析
        self._print_analysis(strat)

        # 绘图
        print("📊 生成图表...")
        try:
            cerebro.plot(style='candlestick', volume=False)  # 关掉volume让图更清晰
        except Exception as e:
            print(f"⚠️ 绘图失败: {e}")

        return {'filename': filename, 'total_return': ret_pct, 'final_value': final_val}

    def _print_analysis(self, strat):
        print("-" * 40)
        print("📊 策略深度分析")

        # 回撤
        try:
            dd = strat.analyzers.drawdown.get_analysis()
            max_dd = dd.get('max', {}).get('drawdown', 0)
            print(f"📉 最大回撤: {max_dd:.2f}%")
        except Exception:
            print("📉 最大回撤: 无法计算")

        # 交易统计
        try:
            ta = strat.analyzers.trades.get_analysis()
            total_closed = ta.get('total', {}).get('closed', 0)
        except Exception:
            total_closed = 0

        if total_closed > 0:
            try:
                won = ta.get('won', {}).get('total', 0)
                lost = ta.get('lost', {}).get('total', 0)
                win_rate = won / total_closed * 100

                # 盈亏比计算
                avg_win = ta.get('won', {}).get('pnl', {}).get('average', 0)
                avg_loss = ta.get('lost', {}).get('pnl', {}).get('average', 0)
                ratio = abs(avg_win / avg_loss) if avg_loss != 0 else 0

                print(f"🔄 交易次数: {total_closed}")
                print(f"🎯 胜率: {win_rate:.1f}% ({won}胜/{lost}负)")
                print(f"⚖️ 盈亏比: {ratio:.2f}")
            except Exception:
                print("⚠️ 交易统计解析失败")
        else:
            print("⚠️ 无平仓交易记录")
        print("-" * 40)

    # --- 文件管理辅助函数 (保持原样) ---
    def get_available_files(self):
        pattern = os.path.join(self.data_dir, '*.csv')
        return sorted([os.path.basename(f) for f in glob.glob(pattern)])

    def main(self):
        if not os.path.exists(self.data_dir):
            print(f"❌ 目录不存在: {self.data_dir}");
            return

        files = self.get_available_files()
        if not files: print("❌ 无CSV文件"); return

        print("\n📁 文件列表:")
        for i, f in enumerate(files): print(f"{i + 1}. {f}")

        try:
            choice = int(input("\n请选择文件编号: ")) - 1
            if 0 <= choice < len(files):
                self.run_single_backtest(files[choice])
            else:
                print("❌ 无效编号")
        except ValueError:
            print("❌ 输入错误")


if __name__ == "__main__":
    # 确保 data_dir 指向你实际存放 CSV 的文件夹
    backtester = OptimizedBacktest(data_dir='correct_processed_data')
    backtester.main()
