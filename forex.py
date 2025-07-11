# region imports
from AlgorithmImports import *
from tensorflow.keras.models import Sequential
import json
# endregion

class HyperActiveRedChinchilla(QCAlgorithm):

    def initialize(self):
        self.set_start_date(2022, 1, 1)
        self.set_cash(100000)

        model_key = 'forex_price_predictor'
        if self.ObjectStore.ContainsKey(model_key):
            model_str = self.ObjectStore.Read(model_key)
            config = json.loads(model_str)['config']
            self.model = Sequential.from_config(config)

        self.rolling_window = RollingWindow[QuoteBar](40)

        self.pair = self.add_forex("GBPUSD", Resolution.MINUTE, Market.OANDA).symbol
        self.bb = self.BB(self.pair, 20, 2)
        self.rsi = self.RSI(self.pair, 20)
        self.adx = self.ADX(self.pair, 20)

        # operates on a 30 min time frame
        self.consolidate("GBPUSD", timedelta(minutes=30), self.on_30_data)

        self.consolidate("GBPUSD", Resolution.MINUTE, self.on_minute_data)

        # creates a stop loss
        self.exit_price = None
        self.percentage_risk = 0.02

        # enable trading 40 mins after market open
        self.Schedule.On(
            self.DateRules.EveryDay(self.pair),
            self.TimeRules.after_market_open(self.pair, 40),
            self.enable_trading
        )

        # disable trading 5 mins before market closes
        self.Schedule.On(
            self.DateRules.EveryDay(self.pair),
            self.TimeRules.before_market_close(self.pair, 5),
            self.disable_trading
        )

        self.is_trading_enabled = False

        # creates plot of portfolio activity 
        stock_plot = Chart("Trade Plot")
        stock_plot.add_series(Series("Buy", SeriesType.SCATTER, "$", 
        Color.Green, ScatterMarkerSymbol.TRIANGLE))
        stock_plot.add_series(Series("Sell", SeriesType.SCATTER, "$", 
        Color.Green, ScatterMarkerSymbol.TRIANGLE_DOWN))
        stock_plot.add_series(Series("Liquidate", SeriesType.SCATTER, "$", 
        Color.Green, ScatterMarkerSymbol.DIAMOND))

        self.set_benchmark("SPY")

        self.add_chart(stock_plot)
    
    def on_minute_data(self, bar):
        self.rolling_window.add(bar)

    def on_30_data(self, bar):
        if not self.bb.is_ready or not self.rsi.is_ready or not self.adx.is_ready or not self.is_trading_enabled:
            return

        price = bar.close

        self.plot("Trade Plot", "Price", price)
        self.plot("Trade Plot", "MiddleBand", self.bb.middle_band.current.value)
        self.plot("Trade Plot", "UpperBand", self.bb.upper_band.current.value)
        self.plot("Trade Plot", "LowerBand", self.bb.lower_band.current.value)

        if not self.portfolio.invested:
            if self.bb.lower_band.current.value > price and self.rsi.current.value < 30 and self.adx.current.value > 20 and self.get_prediction() == "Up":
                self.set_holdings(self.pair, 1)
                self.plot("Trade Plot", "Buy", price)
                self.exit_price = (1 - self.percentage_risk) * price
            elif self.bb.upper_band.current.value < price and self.rsi.current.Value < 70 and self.adx.current.value > 20 and self.get_prediction() == "Down":
                self.set_holdings(self.pair, -1)
                self.plot("Trade Plot", "Sell", price)
                self.exit_price = (1 + self.percentage_risk) * price
        else:
            if self.portfolio[self.pair].is_long:
                if self.bb.middle_band.current.value <= price:
                    self.liquidate()
                    self.plot("Trade Plot", "Liquidate", price)
                    self.exit_price = None
            elif self.bb.middle_band.current.value >= price:
                    self.liquidate()
                    self.plot("Trade Plot", "Liquidate", price)
                    self.exit_price = None
            

    def on_data(self, data: Slice):
        if self.exit_price:
            price = data[self.pair].price

            if self.portfolio[self.pair].is_long:
                if price < self.exit_price:
                    self.liquidate()
                    self.exit_price = None
                    
            else:
                if price > self.exit_price:
                    self.liquidate()
                    self.exit_price = None
                
        


    def get_prediction(self):
        data = [{
            'open': bar.Open,
            'high': bar.High,
            'low': bar.Low,
            'close': bar.Close
        } for bar in self.rolling_window]

        df = pd.DataFrame(data)
        df_change = df[["open", "high", "low", "close"]].pct_change().dropna()
        model_input = []
        for index, row in df_change.tail(30).iterrows():
            model_input.append(np.array(row))
        model_input = np.array([model_input])

        if round(self.model.predict(model_input)[0][0]) == 0:
            return "Down"
        else:
            return "Up"

    def enable_trading(self):
        self.is_trading_enabled = True

    def disable_trading(self):
        self.is_trading_enabled = False