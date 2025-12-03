# free_data_fetcher.py
"""
免费数据获取模块
使用AKShare、Tushare等免费数据源获取股票数据
"""

import pandas as pd
import akshare as ak
import os
from datetime import datetime, timedelta
import logging
import time

# 设置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class FreeDataFetcher:
    """免费数据获取类"""

    def __init__(self):
        """初始化数据获取器"""
        logger.info("初始化免费数据获取器")

    def get_stock_data_akshare(self, symbol, start_date, end_date, adjust="hfq"):
        """
        使用AKShare获取股票数据

        参数:
        symbol: 股票代码，如 '000001'
        start_date: 开始日期 'YYYYMMDD'
        end_date: 结束日期 'YYYYMMDD'
        adjust: 复权类型 "hfq"-后复权, "qfq"-前复权, ""-不复权
        """
        try:
            logger.info(f"使用AKShare获取数据: {symbol} [{start_date} 到 {end_date}]")

            # 获取股票数据
            stock_data = ak.stock_zh_a_hist(
                symbol=symbol,
                period="daily",
                start_date=start_date,
                end_date=end_date,
                adjust=adjust
            )

            if stock_data.empty:
                raise Exception(f"未获取到 {symbol} 的数据")

            # 重命名列以匹配backtrader格式
            stock_data = stock_data.rename(columns={
                '日期': 'date',
                '开盘': 'open',
                '最高': 'high',
                '最低': 'low',
                '收盘': 'close',
                '成交量': 'volume'
            })

            # 设置日期索引
            stock_data['date'] = pd.to_datetime(stock_data['date'])
            stock_data.set_index('date', inplace=True)

            # 只保留需要的列
            stock_data = stock_data[['open', 'high', 'low', 'close', 'volume']]

            logger.info(f"成功获取数据: {len(stock_data)} 条记录")
            return stock_data

        except Exception as e:
            logger.error(f"AKShare获取数据失败: {e}")
            raise

    def get_stock_data_tushare(self, symbol, start_date, end_date):
        """
        使用Tushare获取股票数据（需要token）
        """
        try:
            import tushare as ts
            logger.info(f"使用Tushare获取数据: {symbol} [{start_date} 到 {end_date}]")

            # 设置token（需要先注册tushare账号获取token）
            # ts.set_token('您的token')

            pro = ts.pro_api()

            # 获取数据
            df = pro.daily(ts_code=f"{symbol}.SZ", start_date=start_date, end_date=end_date)

            if df.empty:
                raise Exception(f"未获取到 {symbol} 的数据")

            # 处理数据格式
            df['trade_date'] = pd.to_datetime(df['trade_date'])
            df.set_index('trade_date', inplace=True)
            df.sort_index(inplace=True)

            # 重命名列
            df = df.rename(columns={
                'open': 'open',
                'high': 'high',
                'low': 'low',
                'close': 'close',
                'vol': 'volume'
            })

            return df[['open', 'high', 'low', 'close', 'volume']]

        except ImportError:
            logger.warning("Tushare未安装，跳过")
            return None
        except Exception as e:
            logger.error(f"Tushare获取数据失败: {e}")
            return None

    def get_index_data(self, symbol, start_date, end_date):
        """获取指数数据"""
        try:
            logger.info(f"获取指数数据: {symbol}")

            # 获取指数数据
            index_data = ak.index_zh_a_hist(
                symbol=symbol,
                period="daily",
                start_date=start_date,
                end_date=end_date
            )

            if index_data.empty:
                raise Exception(f"未获取到 {symbol} 的数据")

            # 处理数据格式
            index_data = index_data.rename(columns={
                '日期': 'date',
                '开盘': 'open',
                '最高': 'high',
                '最低': 'low',
                '收盘': 'close',
                '成交量': 'volume'
            })

            index_data['date'] = pd.to_datetime(index_data['date'])
            index_data.set_index('date', inplace=True)

            return index_data[['open', 'high', 'low', 'close', 'volume']]

        except Exception as e:
            logger.error(f"获取指数数据失败: {e}")
            raise

    def save_data_to_csv(self, data, symbol, output_dir='data'):
        """保存数据到CSV文件"""
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)

        # 清理股票代码
        clean_symbol = symbol.replace('.', '_')
        filename = f"{clean_symbol}.csv"
        filepath = os.path.join(output_dir, filename)

        # 重置索引保存
        data_to_save = data.reset_index()
        data_to_save.to_csv(filepath, index=False)

        logger.info(f"数据已保存: {filepath}")
        return filepath


def main():
    """主函数 - 数据获取示例"""
    # 安装AKShare: pip install akshare

    fetcher = FreeDataFetcher()

    # 定义要获取的股票列表
    stocks = [
        {'symbol': '000001', 'name': '平安银行'},
        {'symbol': '000002', 'name': '万科A'},
        {'symbol': '000858', 'name': '五粮液'},
        {'symbol': '600000', 'name': '浦发银行'},
        {'symbol': '600036', 'name': '招商银行'},
    ]

    # 日期范围
    start_date = '20200101'
    end_date = '20231231'

    print("开始获取股票数据...")

    for stock in stocks:
        try:
            symbol = stock['symbol']
            name = stock['name']

            print(f"\n正在获取 {symbol} {name} 的数据...")

            # 获取数据
            data = fetcher.get_stock_data_akshare(symbol, start_date, end_date)

            # 保存数据
            csv_path = fetcher.save_data_to_csv(data, symbol)

            # 显示基本信息
            print(f"✅ 成功: {len(data)} 条数据")
            print(f"   时间范围: {data.index[0].date()} 到 {data.index[-1].date()}")
            print(f"   最新收盘价: {data['close'].iloc[-1]:.2f}")
            print(f"   保存路径: {csv_path}")

            # 避免请求过于频繁
            time.sleep(1)

        except Exception as e:
            print(f"❌ 失败: {e}")
            continue

    print(f"\n数据获取完成！数据保存在 'data' 文件夹中")


if __name__ == "__main__":
    main()