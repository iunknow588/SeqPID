# -*- coding: utf-8 -*-
"""
@desc: 行情相关的数据
@author: 1nchaos
@time: 2023/3/29
@log: change log
"""
from adata.stock.market.capital_flow import StockCapitalFlow
from adata.stock.market.concept_capital_flow import ConceptCapitalFlow
from adata.stock.market.concepth_market import StockMarketConcept
from adata.stock.market.daily_market_view import DailyMarketViewBuilder
from adata.stock.market.index_market import StockMarketIndex
from adata.stock.market.stock_dividend import StockDividend
from adata.stock.market.stock_market import StockMarket


class Market(StockCapitalFlow, ConceptCapitalFlow, StockMarket, StockMarketConcept, StockDividend, StockMarketIndex):

    def __init__(self) -> None:
        super().__init__()

    def daily_view(self, model_output_dir=None):
        return DailyMarketViewBuilder(model_output_dir=model_output_dir, market_client=self)


market = Market()
