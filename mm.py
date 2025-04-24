import tkinter as tk
from tkinter import ttk, simpledialog, messagebox, scrolledtext
import threading
import time
import random
from requests.exceptions import HTTPError
import mexc_spot_v3 
from time import sleep

# Stub ExchangeClient for demonstration
class ExchangeClient:
    def __init__(self, api_key: str, api_secret: str, exchange: str):
        self.api_key = api_key
        self.api_secret = api_secret
        self.exchange = exchange

    def buy(self, symbol: str, price: float, quantity: float, order_type: str):
        """Place a new order and return its details."""
        params = {
            "symbol": symbol.upper(),
            "side": "BUY",
            "type": order_type.upper(),
            "price": price,
            "quantity": quantity
        }
        response = mexc_spot_v3.mexc_trade().post_order(params)
        if 'orderId' in response:
            return f"Buy {quantity} {symbol} @ {price} ({order_type})"
        else:
            return f"Order not executed: {response}"

    def sell(self, symbol: str, price: float, quantity: float, order_type: str):
        """Place a new order and return its details."""
        params = {
            "symbol": symbol.upper(),
            "side": "SELL",
            "type": order_type.upper(),
            "price": price,
            "quantity": quantity
        }
        response = mexc_spot_v3.mexc_trade().post_order(params)
        if 'orderId' in response:
            return f"Sell {quantity} {symbol} @ {price} ({order_type})"
        else:
            return f"Order not executed: {response}"

    def cancel_all(self, symbol: str):
        """Place cancel all open orders request"""
        params = { "symbol": symbol.upper() }
        response = mexc_spot_v3.mexc_trade().delete_openorders( params )
        return f"Cancelled all open orders: {len(response)}"

    def get_avgprice(self, symbol: str) -> dict:
        """Return float"""
        response = mexc_spot_v3.mexc_market().get_avgprice({ "symbol": symbol} )
        
        if type(response) == dict:
            if 'price' in response:
                return float( response['price'] )

        return 0
        
    def start_market_maker(self, symbol: str, spread: float, coin_budget: float, usdt_budget: float, interval: float):
        #Get the current price.
        avg_price = self.get_avgprice( symbol )

         #compute parameters to place the trade
        trade_domain = avg_price*(spread/100)
        
        #Set number of trades for buy/sell orders. Total number of orders is twice this number
        points_on_domain = 10
        min_budget = min( [ coin_budget*avg_price, usdt_budget] )

        if min_budget < 1:
            return f'No orders were placed. Minimum budget is 1 USDT in value for coin and 1 USDT.'
        elif int( min_budget ) <= 2:
            points_on_domain = 1
        elif min_budget < 11:
            points_on_domain =  int(min_budget) - 1
        elif min_budget < 50:
            points_on_domain = 15
        elif min_budget < 100:
            points_on_domain = 20
        elif min_budget < 500:
            points_on_domain = 30
        elif min_budget < 1000:
            points_on_domain = 40
        else:
            points_on_domain = 50
        
        #Sanity checkks
        smallest_price_step = 0.01

        if ( (trade_domain/points_on_domain) < smallest_price_step) :
            self.log_message(f'spread: {trade_domain} units. Minimum unit is 0.01. MM aborted. [Increase spread %].')
            return False

        # Compute a small random number of points within the trading range to buy and sell.
        # Here is the domain, or x axis, are the price of the coin.
        trade_sell_domain = [random.uniform(avg_price, avg_price + trade_domain) for _ in range(points_on_domain)]
        trade_buys_domain = [ avg_price + (avg_price - val) for val in trade_sell_domain ]

        ###########################################################################################################
        # Now determine how much coin to place on each sell/buy order.
        # Here is the range, or y axiso or f(x), that are the amount of coins.
        # When we integrate the f(x) over the discrete points of the domain we should get the budget for eah one.
        ###########################################################################################################
        #First determine minium trade amount at each price point
        buys_units = [ round( 1/buys_price, 5) for buys_price in trade_buys_domain ] 
        sell_units = [ round( 1/sell_price, 5) for sell_price in trade_sell_domain ] 

        #Now that high level of precision is not needed, round to smallest exchange tick of 2 decimals
        trade_buys_domain = [ round(a,2) for a in trade_buys_domain ] 
        trade_sell_domain = [ round(a,2) for a in trade_sell_domain ]
        
        #Now compute how many minimum amount orders we could place.
        #First compute coin value of all the orders together
        cumsum_buys = sum(buys_units)
        cumsum_sell = sum(sell_units)

        #Now compute how many such orders we need to place to consume budget
        buys_multiplier = usdt_budget/(cumsum_buys*avg_price)
        sell_multiplier = coin_budget/cumsum_sell

        #Now compute actual coin value of trades
        trade_buys_range = [ round( buys_unit*buys_multiplier, 2)  for buys_unit in buys_units ] 
        trade_sell_range = [ round( sell_unit*sell_multiplier, 2)  for sell_unit in sell_units ] 

        #Now create the sell/buy orders
        sell_order = [  {"symbol": symbol.upper(), "side": "SELL", "type": "LIMIT", "price": sell_price, "quantity": sell_amount }
                      for sell_price, sell_amount in zip( trade_sell_domain, trade_sell_range ) ]

        buys_order = [  {"symbol": symbol.upper(), "side": "BUY", "type": "LIMIT", "price": buys_price, "quantity": buys_amount }
                      for buys_price, buys_amount in zip( trade_buys_domain, trade_buys_range ) ]

        #Now place the order
        self.cancel_all(symbol)
        sleep(0.1)
        SELL = mexc_spot_v3.mexc_trade().post_batchorders( sell_order )
        BUYS = mexc_spot_v3.mexc_trade().post_batchorders( buys_order )

        string_s = []
        
        for index, sell in enumerate(SELL):
            if "code" in sell:
                string_s.append( str(SELL.pop(index)) )
                

        for index, buy in enumerate(BUYS):
            if "code" in buy:
                string_s.append( str(BUYS.pop(index)) )
        
        for buy in BUYS:
            buy = f"symbol: {buy['symbol']} type: {buy['type']} side: {buy['side']} price: {buy['price']} Quantity: {buy['origQty']} "
            string_s.append( buy )

        for sell in SELL:
            sell = f"symbol: {sell['symbol']} type: {sell['type']} side: {sell['side']} price: {sell['price']} Quantity: {sell['origQty']}"
            string_s.append( sell )

        string_s.append( f"Market maker started on {symbol} spread {spread} coin_budget {coin_budget} usdt_budget {usdt_budget} interval {interval}" )
        S = "\n"+ "\n".join( string_s )
        
        return S 

    def stop_market_maker(self):
        return "Market maker stopped"

class ConfigDialog(simpledialog.Dialog):
    def body(self, master):
        ttk.Label(master, text="Exchange:").grid(row=0, column=0, sticky='e')
        self.exchange_var = tk.StringVar(value="")
        ttk.Entry(master, textvariable=self.exchange_var).grid(row=0, column=1)

        ttk.Label(master, text="API Key:").grid(row=1, column=0, sticky='e')
        self.key_var = tk.StringVar(value="")
        ttk.Entry(master, textvariable=self.key_var).grid(row=1, column=1)

        ttk.Label(master, text="API Secret:").grid(row=2, column=0, sticky='e')
        self.secret_var = tk.StringVar(value="")
        ttk.Entry(master, textvariable=self.secret_var, show="*").grid(row=2, column=1)

        return None

    def apply(self):
        self.result = (
            self.exchange_var.get(),
            self.key_var.get(),
            self.secret_var.get()
        )

class CryptoGUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Crypto Trading & Market Maker")
        self.geometry("800x600")
        self.client = None

        # Menu
        menubar = tk.Menu(self)
        config_menu = tk.Menu(menubar, tearoff=0)
        config_menu.add_command(label="Config", command=self.open_config)
        menubar.add_cascade(label="Settings", menu=config_menu)
        self.config(menu=menubar)

        # Trading Frame
        trade_frame = ttk.LabelFrame(self, text="Trade", padding=10)
        trade_frame.pack(padx=10, pady=5)
        for i, label in enumerate(["Symbol","Price","Quantity","Order Type"]):
            ttk.Label(trade_frame, text=label).grid(row=i, column=0, sticky='e', pady=2)
        self.trade_symbol = ttk.Entry(trade_frame)
        self.trade_symbol.grid(row=0, column=1)
        self.trade_price  = ttk.Entry(trade_frame)
        self.trade_price.grid(row=1, column=1)
        self.trade_qty    = ttk.Entry(trade_frame)
        self.trade_qty.grid(row=2, column=1)
        self.trade_type   = ttk.Combobox(trade_frame, values=["limit","market"])
        self.trade_type.current(0)
        self.trade_type.grid(row=3, column=1)
        buy_btn = ttk.Button(trade_frame, text="Buy", command=self.do_buy)
        sell_btn = ttk.Button(trade_frame, text="Sell", command=self.do_sell)
        buy_btn.grid(row=0, column=2, padx=5)
        sell_btn.grid(row=1, column=2, padx=5)

        # Market Maker Frame
        mm_frame = ttk.LabelFrame(self, text="Market Maker", padding=10)
        mm_frame.pack(padx=10, pady=5)
        ttk.Label(mm_frame, text="Symbol").grid(row=0, column=0, sticky='e', pady=2)
        ttk.Label(mm_frame, text="Spread (%)").grid(row=1, column=0, sticky='e', pady=2)
        ttk.Label(mm_frame, text="Coin Budget").grid(row=2, column=0, sticky='e', pady=2)
        ttk.Label(mm_frame, text="USDT Budget").grid(row=3, column=0, sticky='e', pady=2)
        ttk.Label(mm_frame, text="Interval (s)").grid(row=4, column=0, sticky='e', pady=2)
        self.mm_symbol = ttk.Entry(mm_frame)
        self.mm_symbol.grid(row=0, column=1)
        self.mm_spread = ttk.Entry(mm_frame)
        self.mm_spread.grid(row=1, column=1)
        self.mm_coin_budget = ttk.Entry(mm_frame)
        self.mm_coin_budget.grid(row=2, column=1)
        self.mm_usdt_budget = ttk.Entry(mm_frame)
        self.mm_usdt_budget.grid(row=3, column=1)
        self.mm_interval = ttk.Entry(mm_frame)
        self.mm_interval.grid(row=4, column=1)
        start_btn = ttk.Button(mm_frame, text="Start MM", command=self.start_mm)
        start_btn.grid(row=0, column=2, padx=5)
        stop_btn = ttk.Button(mm_frame, text="Stop MM", command=self.stop_mm)
        stop_btn.grid(row=1, column=2, padx=5)

        # Log
        log_frame = ttk.LabelFrame(self, text="Log", padding=10)
        log_frame.pack(fill='both', expand=True, padx=10, pady=5)
        self.log = scrolledtext.ScrolledText(log_frame, state='disabled')
        self.log.pack(fill='both', expand=True)

        self.mm_running = False
        self.mm_thread = None

    def open_config(self):
        dlg = ConfigDialog(self, title="Configure Exchange")
        if dlg.result:
            exch, key, secret = dlg.result
            self.client = ExchangeClient(key, secret, exch)
            self.log_message(f"Configured client for {exch}")

    def log_message(self, msg):
        self.log.configure(state='normal')
        self.log.insert('end', f"{time.strftime('%H:%M:%S')} {msg}\n")
        self.log.configure(state='disabled')
        self.log.yview('end')

    def do_buy(self):
        if not self.client:
            messagebox.showwarning("Not configured", "Set API keys first.")
            return
        sym = self.trade_symbol.get()
        price = float(self.trade_price.get())
        qty = float(self.trade_qty.get())
        t = self.trade_type.get()
        try:
            res = self.client.buy(sym, price, qty, t)
            self.log_message(res)
        except HTTPError as e:
            messagebox.showerror("Buy Failed", str(e))

    def do_sell(self):
        if not self.client:
            messagebox.showwarning("Not configured", "Set API keys first.")
            return
        sym = self.trade_symbol.get()
        price = float(self.trade_price.get())
        qty = float(self.trade_qty.get())
        t = self.trade_type.get()
        try:
            res = self.client.sell(sym, price, qty, t)
            self.log_message(res)
        except HTTPError as e:
            messagebox.showerror("Sell Failed", str(e))

    def mm_loop(self, symbol, spread, coin_budget, usdt_budget, interval):
        self.log_message("MM START")
        while self.mm_running:
            res = self.client.start_market_maker(symbol, spread, coin_budget, usdt_budget, interval)
            if res == False:
                return
                
            self.log_message(res)
            time.sleep(interval)

    def start_mm(self):
        if not self.client:
            messagebox.showwarning("Not configured", "Set API keys first.")
            return
        sym = self.mm_symbol.get()
        spr = float(self.mm_spread.get())
        cb = float(self.mm_coin_budget.get())
        ub = float(self.mm_usdt_budget.get())
        iv = float(self.mm_interval.get())
        self.mm_running = True
        self.mm_thread = threading.Thread(target=self.mm_loop, args=(sym, spr, cb, ub, iv), daemon=True)
        self.mm_thread.start()

    def stop_mm(self):
        """Stop the market maker thread."""
        if self.mm_running:
            self.mm_running = False
            if self.mm_thread:
                self.mm_thread.join(timeout=1)
            if self.client:
                sleep(0.75)
                res = self.client.stop_market_maker()
                self.log_message(res)
        self.log_message("MM STOP")

# --- Main Entry Point ---
if __name__ == '__main__':
    app = CryptoGUI()
    app.mainloop()