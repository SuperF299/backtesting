# main.py
"""
高级多策略回测系统 - 主程序
修复策略返回结果的问题
"""

import os
import glob
import pandas as pd
import backtrader as bt
from datetime import datetime

# 导入策略模块
from trend_strategy import TrendBacktest
from mean_reversion_strategy import MeanReversionBacktest
from breakout_strategy import BreakoutBacktest
from ml_strategy import MLBacktest


class AdvancedMultiStrategyBacktest:
    """高级多策略回测系统"""

    def __init__(self, data_dir='correct_processed_data'):
        self.data_dir = data_dir
        self.strategies = {
            '1': {
                'name': '高级趋势跟踪策略',
                'backtester': TrendBacktest(data_dir),
                'description': '多时间框架趋势跟踪，适合趋势明显的市场'
            },
            '2': {
                'name': '高级均值回归策略',
                'backtester': MeanReversionBacktest(data_dir),
                'description': '统计套利策略，适合震荡市场'
            },
            '3': {
                'name': '高级突破策略',
                'backtester': BreakoutBacktest(data_dir),
                'description': '波动率压缩突破，适合整理后的突破行情'
            },
            '4': {
                'name': '高级机器学习策略',
                'backtester': MLBacktest(data_dir),
                'description': '多因子机器学习模型，自适应市场变化'
            }
        }

    def get_available_files(self):
        """获取可用数据文件"""
        pattern = os.path.join(self.data_dir, '*.csv')
        files = sorted([os.path.basename(f) for f in glob.glob(pattern)])
        return files

    def display_file_menu(self, files):
        """显示文件菜单"""
        print("\n" + "=" * 80)
        print("📁 可用的数据文件")
        print("=" * 80)

        for i, file in enumerate(files, 1):
            file_path = os.path.join(self.data_dir, file)
            try:
                df = pd.read_csv(file_path)
                date_range = f"{df['date'].iloc[0]} 到 {df['date'].iloc[-1]}"
                print(f"{i:2d}. {file:25} | 数据: {len(df):4d}条 | {date_range}")
            except Exception as e:
                print(f"{i:2d}. {file:25} | 信息获取失败: {e}")

    def display_strategy_menu(self):
        """显示策略菜单"""
        print("\n" + "=" * 80)
        print("🎯 可用的交易策略")
        print("=" * 80)

        for key, strategy in self.strategies.items():
            print(f"{key}. {strategy['name']}")
            print(f"   描述: {strategy['description']}")
            print()

    def choose_file(self, files):
        """选择数据文件"""
        while True:
            try:
                choice = input(f"\n请选择文件编号 (1-{len(files)}): ").strip()
                idx = int(choice) - 1
                if 0 <= idx < len(files):
                    return files[idx]
                print(f"❌ 请输入 1-{len(files)} 之间的数字")
            except ValueError:
                print("❌ 请输入有效数字")

    def choose_strategy(self):
        """选择策略"""
        while True:
            choice = input("\n请选择策略编号 (1-4): ").strip()
            if choice in self.strategies:
                return choice
            print("❌ 无效选择，请输入 1-4")

    def run_multi_strategy_comparison(self):
        """运行多策略对比回测 - 修复版"""
        files = self.get_available_files()
        if not files:
            print("❌ 没有找到数据文件")
            return

        self.display_file_menu(files)
        selected_file = self.choose_file(files)

        print(f"\n🔄 开始多策略对比回测...")
        print(f"📁 数据文件: {selected_file}")
        print("=" * 80)

        results = {}
        for strategy_id, strategy_info in self.strategies.items():
            print(f"\n📊 测试策略: {strategy_info['name']}")
            print("-" * 50)

            try:
                # 直接运行回测，不处理返回的strategy对象
                initial_cash = 100000.0
                cerebro = bt.Cerebro()
                cerebro.broker.setcash(initial_cash)
                cerebro.broker.setcommission(commission=0.0003)

                # 根据策略ID选择对应的策略类
                if strategy_id == '1':
                    from trend_strategy import AdvancedTrendFollowingStrategy
                    cerebro.addstrategy(AdvancedTrendFollowingStrategy)
                elif strategy_id == '2':
                    from mean_reversion_strategy import AdvancedMeanReversionStrategy
                    cerebro.addstrategy(AdvancedMeanReversionStrategy)
                elif strategy_id == '3':
                    from breakout_strategy import AdvancedBreakoutStrategy
                    cerebro.addstrategy(AdvancedBreakoutStrategy)
                elif strategy_id == '4':
                    from ml_strategy import AdvancedMachineLearningStrategy
                    cerebro.addstrategy(AdvancedMachineLearningStrategy)

                # 加载数据
                filepath = f"{self.data_dir}/{selected_file}"
                df = pd.read_csv(filepath)
                df['date'] = pd.to_datetime(df['date'])
                df.set_index('date', inplace=True)
                df.sort_index(inplace=True)

                data = bt.feeds.PandasData(
                    dataname=df,
                    open='open',
                    high='high',
                    low='low',
                    close='close',
                    volume='volume'
                )
                cerebro.adddata(data)

                # 添加分析器
                cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name='trades')

                # 运行回测
                print(f"💰 初始资金: {initial_cash:,.2f}")
                result = cerebro.run()
                strat = result[0]

                # 获取最终资金
                final_value = cerebro.broker.getvalue()
                total_return = (final_value / initial_cash - 1) * 100

                # 获取交易统计
                trade_analysis = strat.analyzers.trades.get_analysis()
                total_trades = trade_analysis.total.total if hasattr(trade_analysis, 'total') else 0
                won_trades = trade_analysis.won.total if hasattr(trade_analysis, 'won') else 0
                win_rate = (won_trades / total_trades * 100) if total_trades > 0 else 0

                results[strategy_info['name']] = {
                    'final_value': final_value,
                    'total_return': total_return,
                    'total_trades': total_trades,
                    'win_rate': win_rate
                }

                print(f"💰 最终资金: {final_value:,.2f}")
                print(f"📈 总收益率: {total_return:+.2f}%")
                print(f"🔄 总交易次数: {total_trades}")
                print(f"✅ 胜率: {win_rate:.2f}%")

            except Exception as e:
                print(f"❌ 策略回测失败: {e}")
                # 即使失败也记录一个默认结果
                results[strategy_info['name']] = {
                    'final_value': 100000,
                    'total_return': 0,
                    'total_trades': 0,
                    'win_rate': 0
                }

        # 显示对比结果
        self.print_comparison_results(results)

    def print_comparison_results(self, results):
        """打印对比结果"""
        if not results:
            print("❌ 没有有效的回测结果")
            return

        print("\n" + "=" * 80)
        print("📊 多策略对比结果")
        print("=" * 80)

        # 按总收益率排序
        sorted_results = sorted(results.items(), key=lambda x: x[1]['total_return'], reverse=True)

        print(f"{'策略名称':<20} {'最终资金':<12} {'收益率':<10} {'排名':<6} {'交易次数':<8} {'胜率':<8}")
        print("-" * 80)

        for i, (strategy_name, result) in enumerate(sorted_results, 1):
            symbol = "🟢" if result['total_return'] > 0 else "🔴"
            print(f"{strategy_name:<20} {result['final_value']:>11.2f} "
                  f"{symbol}{result['total_return']:>8.2f}% "
                  f"{i:>5} "
                  f"{result['total_trades']:>8} "
                  f"{result['win_rate']:>7.1f}%")

    def run_single_strategy(self):
        """运行单策略回测 - 修复版"""
        files = self.get_available_files()
        if not files:
            print("❌ 没有找到数据文件")
            return

        self.display_file_menu(files)
        selected_file = self.choose_file(files)

        self.display_strategy_menu()
        strategy_choice = self.choose_strategy()

        strategy_info = self.strategies[strategy_choice]
        print(f"\n🚀 开始回测: {strategy_info['name']}")
        print(f"📁 数据文件: {selected_file}")

        # 直接运行回测
        initial_cash = 100000.0
        cerebro = bt.Cerebro()
        cerebro.broker.setcash(initial_cash)
        cerebro.broker.setcommission(commission=0.0003)

        # 根据策略选择添加对应的策略
        if strategy_choice == '1':
            from trend_strategy import AdvancedTrendFollowingStrategy
            cerebro.addstrategy(AdvancedTrendFollowingStrategy)
        elif strategy_choice == '2':
            from mean_reversion_strategy import AdvancedMeanReversionStrategy
            cerebro.addstrategy(AdvancedMeanReversionStrategy)
        elif strategy_choice == '3':
            from breakout_strategy import AdvancedBreakoutStrategy
            cerebro.addstrategy(AdvancedBreakoutStrategy)
        elif strategy_choice == '4':
            from ml_strategy import AdvancedMachineLearningStrategy
            cerebro.addstrategy(AdvancedMachineLearningStrategy)

        # 加载数据
        filepath = f"{self.data_dir}/{selected_file}"
        df = pd.read_csv(filepath)
        df['date'] = pd.to_datetime(df['date'])
        df.set_index('date', inplace=True)
        df.sort_index(inplace=True)

        data = bt.feeds.PandasData(
            dataname=df,
            open='open',
            high='high',
            low='low',
            close='close',
            volume='volume'
        )
        cerebro.adddata(data)

        # 添加分析器
        cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name='trades')

        print(f"💰 初始资金: {initial_cash:,.2f}")
        print("=" * 60)

        # 运行回测
        try:
            results = cerebro.run()
            strat = results[0]

            # 获取结果
            final_value = cerebro.broker.getvalue()
            total_return = (final_value / initial_cash - 1) * 100

            # 交易统计
            trade_analysis = strat.analyzers.trades.get_analysis()
            total_trades = trade_analysis.total.total if hasattr(trade_analysis, 'total') else 0
            won_trades = trade_analysis.won.total if hasattr(trade_analysis, 'won') else 0
            win_rate = (won_trades / total_trades * 100) if total_trades > 0 else 0

            print(f"💰 最终资金: {final_value:,.2f}")
            print(f"📈 总收益率: {total_return:+.2f}%")
            print(f"🔄 总交易次数: {total_trades}")
            print(f"✅ 胜率: {win_rate:.2f}%")

        except Exception as e:
            print(f"❌ 回测失败: {e}")

    def main(self):
        """主函数"""
        print("\n" + "=" * 80)
        print("🚀 高级多策略回测系统 - 修复版")
        print("=" * 80)

        # 检查数据目录
        if not os.path.exists(self.data_dir):
            print(f"❌ 数据目录 '{self.data_dir}' 不存在")
            return

        files = self.get_available_files()
        if not files:
            print(f"❌ 在 '{self.data_dir}' 中没有找到CSV文件")
            return

        while True:
            print(f"\n📊 系统状态: 找到 {len(files)} 个数据文件")
            print("\n请选择操作:")
            print("1. 单策略回测")
            print("2. 多策略对比")
            print("3. 退出系统")

            choice = input("\n请输入选择 (1-3): ").strip()

            if choice == '1':
                self.run_single_strategy()
            elif choice == '2':
                self.run_multi_strategy_comparison()
            elif choice == '3':
                print("\n👋 感谢使用高级多策略回测系统！")
                break
            else:
                print("❌ 无效选择，请输入 1-3")


if __name__ == "__main__":
    # 创建数据目录（如果不存在）
    os.makedirs('correct_processed_data', exist_ok=True)

    # 检查是否有数据文件
    data_files = glob.glob('correct_processed_data/*.csv')

    if not data_files:
        print("⚠️  提示: 数据目录 'correct_processed_data' 为空")
        print("请将CSV格式的股票数据文件放入该目录")
    else:
        # 运行完整系统
        system = AdvancedMultiStrategyBacktest(data_dir='correct_processed_data')
        system.main()