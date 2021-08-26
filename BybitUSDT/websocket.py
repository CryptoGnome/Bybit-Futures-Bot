import ccxt
import requests
from datetime import datetime
from time import sleep
import time
from ccxt.base.errors import ExchangeError
import json
import logging
from unicorn_binance_websocket_api.unicorn_binance_websocket_api_manager import BinanceWebSocketApiManager
from prettyprinter import pprint
import bybitwrapper

with open('../settings.json', 'r') as fp:
    settings = json.load(fp)
fp.close()
with open('../coins.json', 'r') as fp:
    coins = json.load(fp)
fp.close()


exchange_id = 'binance'
exchange_class = getattr(ccxt, exchange_id)
binance = exchange_class({
    'apiKey': None,
    'secret': None,
    'timeout': 30000,
    'enableRateLimit': True,
    'options': {'defaultType': 'future'},
})
binance.load_markets()

client = bybitwrapper.bybit(test=False, api_key=settings['key'], api_secret=settings['secret'])


def load_jsons():
    #print("Checking Settings")
    with open('../coins.json', 'r') as fp:
        coins = json.load(fp)
    fp.close()
    with open('../settings.json', 'r') as fp:
        settings = json.load(fp)
    fp.close()

def fetch_vwap(symbol):
    global longwap, shortwap
    tickerSymbol = symbol + '/USDT'
    tickerDump = binance.fetch_ticker(tickerSymbol)
    vwap = tickerDump['vwap']
    for coin in coins:
        if coin['symbol'] == symbol:
            longwap = round(vwap - (vwap * (coin['long_vwap_offset'] / 100)), 4)
            shortwap = round(vwap + (vwap * (coin['short_vwap_offset'] / 100)), 4)
        else:
            pass

    return vwap, longwap, shortwap

def load_symbols(coins):
    symbols = []
    for coin in coins:
        symbols.append(coin['symbol'])
    return symbols

def load_multipliers(coins, symbol):
    multipliers = []
    for coin in coins:
        if coin['symbol'] == symbol:
            multipliers.append(coin['dca_max_buy_level_1'])
            multipliers.append(coin['dca_max_buy_level_2'])
            multipliers.append(coin['dca_max_buy_level_3'])
            multipliers.append(coin['dca_max_buy_level_4'])
    return multipliers

def load_dca(coins, symbol):
    dca = []
    for coin in coins:
        if coin['symbol'] == symbol:
            dca.append(coin['dca_drawdown_percent_1'])
            dca.append(coin['dca_drawdown_percent_2'])
            dca.append(coin['dca_drawdown_percent_3'])
            dca.append(coin['dca_drawdown_percent_4'])
    return dca

def load_dca_values(coins, symbol):
    dca_values = []
    for coin in coins:
        if coin['symbol'] == symbol:
            dca_values.append(coin['dca_size_multiplier_1'])
            dca_values.append(coin['dca_size_multiplier_2'])
            dca_values.append(coin['dca_size_multiplier_3'])
            dca_values.append(coin['dca_size_multiplier_4'])
    return dca_values

def check_positions(symbol):
    positions = client.LinearPositions.LinearPositions_myPosition(symbol=symbol+"USDT").result()
    if positions[0]['ret_msg'] == 'OK':
        for position in positions[0]['result']:
            if position['entry_price'] > 0:
                print("Position found for ", symbol, " entry price of ", position['entry_price'])
                return True, position
            else:
                pass

    else:
        print("API NOT RESPONSIVE AT CHECK ORDER")
        sleep(5)

def fetch_ticker(symbol):
    tickerDump = binance.fetch_ticker(symbol + '/USDT')
    ticker = float(tickerDump['last'])
    return ticker

def fetch_order_size(symbol):
    global qty
    wallet_info = client.Wallet.Wallet_getBalance(coin="USDT").result()
    balance = wallet_info[0]['result']['USDT']['wallet_balance']
    ticker = fetch_ticker(symbol)
    for coin in coins:
        if coin['symbol'] == symbol:
            qtycalc = (balance / ticker) * coin['leverage']
            qty = qtycalc * (coin['order_size_percent_balance'] / 100)
        else:
            pass

    return qty

def set_leverage(symbol):
    for coin in coins:
        if coin['symbol'] == symbol:
            set = client.LinearPositions.LinearPositions_saveLeverage(symbol=symbol+"USDT", buy_leverage=coin['leverage'], sell_leverage=coin['leverage']).result()
        else:
            pass


def place_order(symbol, side, ticker, size):
    print('*****************************************************')
    print(symbol, side, " Entry Found!! Placing new order!!")
    print('*****************************************************')

    with open('../ordersize.json', 'r') as fp:
        ordersize = json.load(fp)
    fp.close()

    for coin in ordersize:
        if size < coin[symbol]:
            size = coin[symbol]
        else:
            size = round(size, 3)

    order = client.LinearOrder.LinearOrder_new(side=side, symbol=symbol+"USDT", order_type="Market", qty=size,
                                       time_in_force="GoodTillCancel", reduce_only=False,
                                       close_on_trigger=False).result()

    #pprint(order)


def calculate_order(symbol, side):
    position = check_positions(symbol)
    if position != None:
        if position[0] == True:
            position = position[1]
            pnl = float(position['unrealised_pnl'])

            if pnl > 0:
                ticker = fetch_ticker(symbol)
                percent_change = ticker - float(position['entry_price'])
                pnl = (percent_change / ticker) * -100
                print("PNL %", symbol, (-1 * pnl))
                min_order = fetch_order_size(symbol)

                multipliers = load_multipliers(coins, symbol)
                size1 = (min_order * multipliers[0])
                size2 = (min_order * multipliers[1])
                size3 = (min_order * multipliers[2])
                size4 = (min_order * multipliers[3])

                dca = load_dca(coins, symbol)
                modifiers = load_dca_values(coins, symbol)
                print(min_order)

                print("Current Position Size for ", symbol, " = ", position['size'])
                if position['size'] <= size1:
                    size = min_order
                    place_order(symbol, side, ticker, size)
                elif size1 < position['size'] <= size2 and pnl > dca[0]:
                    size = min_order * modifiers[1]
                    place_order(symbol, side, ticker, size)
                elif size2 < position['size'] <= size3 and pnl > dca[1]:
                    size = min_order * modifiers[2]
                    place_order(symbol, side, ticker, size)
                elif size3 < position['size'] <= size4 and pnl > dca[2]:
                    size = min_order * modifiers[3]
                    place_order(symbol, side, ticker, size)
                elif size4 < position['size'] and pnl > dca[3]:
                    size = min_order * modifiers[4]
                    place_order(symbol, side, ticker, size)
                else:
                    print("At Max Size for ", symbol, " Tier or Not Outside Drawdown Settings..")

            else:
                print(symbol, "Position is currently in profit so we wont do anything here    :D")

        else:
            print("SEARCH FOR ME THIS SHOULD NOT HAPPEN GNOME LOL")

    else:
        print("No Open Position Found Yet")
        ticker = fetch_ticker(symbol)
        min_order = fetch_order_size(symbol)
        place_order(symbol, side, ticker, min_order)

def check_liquidations():
    print("Launching Liquidation Websocket & Waiting for new Liquidations...")
    binance_websocket_api_manager = BinanceWebSocketApiManager(exchange="binance.com-futures")
    binance_websocket_api_manager.create_stream(['!forceOrder'], [{}])
    cycles = 5000000
    nonce = 0

    while True:
        lick_stream = binance_websocket_api_manager.pop_stream_data_from_stream_buffer()

        #settings update script
        nonce += 1
        if nonce > cycles:
            load_jsons()
            nonce = 0

        if lick_stream:
            data = json.loads(lick_stream)
            #pprint(data)
            try:
                #data = {'stream': '!forceOrder@arr', 'data': {'e': 'forceOrder', 'E': 1629656323555, 'o': {'s': 'BTCUSDT', 'S': 'BUY', 'o': 'LIMIT', 'f': 'IOC', 'q': '6', 'p': '73.2212', 'ap': '80000', 'X': 'FILLED', 'l': '6', 'z': '6', 'T': 1629656323549}}}
                symbol = data['data']['o']['s'][:-4]
                symbols = load_symbols(coins)

                if symbol in symbols:
                    #pprint(data)
                    last = data['data']['o']['ap']
                    side = data['data']['o']['S']
                    amount = data['data']['o']['q']
                    stamp = data['data']['E']
                    lick_size = float(last) * float(amount)
                    d1 = datetime.fromtimestamp(stamp / 1000)
                    now = datetime.now()
                    past = now - d1
                    duration = past.total_seconds()

                    if duration < 5:
                        print("---------------------------------------------------------------------------------")
                        print("Liquidation found for:", amount, "Contracts worth: $", lick_size, "on ", symbol)

                        vwaps = fetch_vwap(symbol)
                        ticker = fetch_ticker(symbol)

                        if ticker < vwaps[1] and side == 'SELL' and lick_size:
                            side = 'Buy'
                            calculate_order(symbol, side)
                        elif ticker > vwaps[2] and side == "BUY":
                            side = 'Sell'
                            calculate_order(symbol, side)
                        else:
                            print("Does not Meet VWAP or Size Requirements")

                    else:
                        pass
                        #print("Lick timestamp to far away")

                else:
                    pass

            except KeyError:
                pass


load_jsons()
if settings['check_leverage'].lower() == 'true':
    for coin in coins:
        print("Setting Leverage for ", coin['symbol']+'USDT', " before Starting Bot")
        set_leverage(coin['symbol'])

check_liquidations()