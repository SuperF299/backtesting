# correct_data_processor.py
"""
正确的数据处理 - 只保留交易日，移除非交易日
"""

import pandas as pd
import os
import akshare as ak
from datetime import datetime
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class CorrectDataProcessor:
    """正确的数据处理器 - 只处理交易日"""

    def __init__(self, data_dir='data', processed_dir='correct_processed_data'):
        self.data_dir = data_dir
        self.processed_dir = processed_dir

        if not os.path.exists(self.processed_dir):
            os.makedirs(self.processed_dir)

    def get_trading_days_only(self, symbol, start_date, end_date):
        """
        获取只包含交易日的数据（不填充非交易日）
        """
        try:
            logger.info(f"获取{symbol}交易日数据")

            # 从AKShare获取股票数据（自动只包含交易日）
            stock_data = ak.stock_zh_a_hist(
                symbol=symbol,
                period="daily",
                start_date=start_date,
                end_date=end_date,
                adjust="hfq"  # 后复权
            )

            if stock_data.empty:
                raise Exception(f"未获取到{symbol}数据")

            # 重命名列
            stock_data = stock_data.rename(columns={
                '日期': 'date',
                '开盘': 'open',
                '最高': 'high',
                '最低': 'low',
                '收盘': 'close',
                '成交量': 'volume'
            })

            # 转换日期格式
            stock_data['date'] = pd.to_datetime(stock_data['date'])

            # 按日期排序
            stock_data = stock_data.sort_values('date')

            # 重置索引（不使用日期作为索引，避免非交易日问题）
            stock_data = stock_data.reset_index(drop=True)

            logger.info(f"获取{symbol}数据成功: {len(stock_data)}个交易日")
            return stock_data

        except Exception as e:
            logger.error(f"获取数据失败: {e}")
            raise

    def validate_trading_days(self, data):
        """
        验证交易日数据
        """
        logger.info("验证交易日数据...")

        # 检查日期是否连续（应该不连续，因为有非交易日）
        date_diff = data['date'].diff().dt.days
        gaps = date_diff[date_diff > 1]  # 找到间隔大于1天的

        if not gaps.empty:
            logger.info(f"发现 {len(gaps)} 个非交易日间隔，这是正常的")

        # 检查数据完整性
        required_columns = ['date', 'open', 'high', 'low', 'close', 'volume']
        missing_columns = [col for col in required_columns if col not in data.columns]

        if missing_columns:
            raise ValueError(f"缺少必要列: {missing_columns}")

        # 检查价格逻辑
        self._validate_price_logic(data)

        return data

    def _validate_price_logic(self, data):
        """验证价格逻辑"""
        # 检查高价 >= 开盘、收盘、低价
        high_issues = data[data['high'] < data[['open', 'close', 'low']].max(axis=1)]
        low_issues = data[data['low'] > data[['open', 'close', 'high']].min(axis=1)]

        if not high_issues.empty or not low_issues.empty:
            logger.warning(f"发现 {len(high_issues)} 个高价问题, {len(low_issues)} 个低价问题")

            # 自动修正
            data['high'] = data[['open', 'high', 'close']].max(axis=1)
            data['low'] = data[['open', 'low', 'close']].min(axis=1)

        # 检查零或负值
        for col in ['open', 'high', 'low', 'close']:
            if (data[col] <= 0).any():
                raise ValueError(f"发现{col}列有零或负值")

    def save_correct_data(self, data, symbol):
        """保存正确的数据"""
        filename = f"{symbol}_correct.csv"
        filepath = os.path.join(self.processed_dir, filename)

        data.to_csv(filepath, index=False)
        logger.info(f"数据已保存: {filepath}")

        return filepath


def main():
    """主函数 - 生成正确的数据"""
    processor = CorrectDataProcessor()

    symbols = ['000001', '000002', '000858','600000','600036']
    start_date = '20200101'
    end_date = '20231231'

    for symbol in symbols:
        try:
            print(f"\n处理 {symbol}:")

            # 获取只包含交易日的数据
            data = processor.get_trading_days_only(symbol, start_date, end_date)

            # 验证数据
            data = processor.validate_trading_days(data)

            # 保存数据
            processor.save_correct_data(data, symbol)

            print(f"✅ {symbol} 处理完成: {len(data)} 个交易日")
            print(f"   时间范围: {data['date'].iloc[0].date()} 到 {data['date'].iloc[-1].date()}")

        except Exception as e:
            print(f"❌ {symbol} 处理失败: {e}")
            continue


if __name__ == "__main__":
    main()