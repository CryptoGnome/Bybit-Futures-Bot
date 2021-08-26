import ccxt
import requests
from datetime import datetime
from time import sleep
import time
import json
import logging
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

def load_symbols(coins):
    symbols = []
    for coin in coins:
        symbols.append(coin['symbol'])
    return symbols

def check_positions(symbol):
    positions = client.LinearPositions.LinearPositions_myPosition(symbol=symbol+"USDT").result()
    if positions[0]['ret_msg'] == 'OK':
        for position in positions[0]['result']:
            if position['entry_price'] > 0:
                print("Position found for ", symbol, " entry price of ", position['entry_price'])
                return position
            else:
                pass

    else:
        print("API NOT RESPONSIVE AT CHECK ORDER")
        sleep(5)

def fetch_ticker(symbol):
    tickerDump = binance.fetch_ticker(symbol + '/USDT')
    ticker = float(tickerDump['last'])
    return ticker

def fetch_price(symbol, side):
    ticker = fetch_ticker(symbol)
    for coin in coins:
        if coin['symbol'] == symbol:
            if side == 'Buy':
                price = round(ticker + (ticker * (coin['take_profit_percent'] / 100)), 3)
                side = 'Sell'
                return price, side
            else:
                side = 'Buy'
                price = round(ticker - (ticker * (coin['take_profit_percent'] / 100)), 3)
                return price, side
        else:
            pass

def fetch_stop_price(symbol, side):
    ticker = fetch_ticker(symbol)
    for coin in coins:
        if coin['symbol'] == symbol:
            if side == 'Buy':
                price = round(ticker - (ticker * (coin['stop_loss_percent'] / 100)), 3)
                side = 'Sell'
                return price, side, price
            else:
                side = 'Buy'
                price = round(ticker + (ticker * (coin['stop_loss_percent'] / 100)), 3)
                return price, side, ticker
        else:
            pass

def cancel_orders(symbol, size, side):
    orders = client.LinearOrder.LinearOrder_getOrders(symbol=symbol+"USDT", limit='5').result()
    try:
        for order in orders[0]['result']['data']:
            if order['order_status'] != 'Filled' and order['order_status'] != 'Cancelled':
                prices = fetch_price(symbol, side)
                if size != order['qty']:
                    #print("Canceling Open Orders ", symbol)
                    cancel = client.LinearOrder.LinearOrder_cancel(symbol=symbol+"USDT", order_id=order['order_id']).result()
                    sleep(0.25)
                else:
                    pass
                    #print("No Changes needed for ", symbol, " Take Profit")
            else:
                pass

    except TypeError:
        pass

def cancel_stops(symbol, size, side):
    orders = client.LinearConditional.LinearConditional_getOrders(symbol=symbol+"USDT", limit='5').result()
    try:
        for order in orders[0]['result']['data']:
            #pprint(order)
            if order['order_status'] != 'Deactivated':
                #print("Canceling Open Stop Orders ", symbol)
                cancel = client.LinearConditional.LinearConditional_cancel(symbol=symbol+"USDT", stop_order_id=order['stop_order_id']).result()
                #pprint(cancel)
            else:
                pass

    except TypeError:
        pass


def set_tp(symbol, size, side):
    prices = fetch_price(symbol, side)
    order = client.LinearOrder.LinearOrder_new(side=prices[1], symbol=symbol + "USDT", order_type="Limit", qty=size,
                                       price=prices[0], time_in_force="GoodTillCancel",
                                       reduce_only=True, close_on_trigger=False).result()

def set_sl(symbol, size, side):
    prices = fetch_stop_price(symbol, side)
    orders = client.LinearConditional.LinearConditional_getOrders(symbol=symbol + "USDT", limit='5').result()
    cancel_stops(symbol, size, side)
    #print("Setting Stop Loss ", symbol)
    order = client.LinearConditional.LinearConditional_new(order_type="Limit", side=prices[1], symbol=symbol+"USDT", qty=size, price=prices[0],
                                                   base_price=prices[2], stop_px=prices[0], time_in_force="GoodTillCancel",
                                                   reduce_only=False, trigger_by='LastPrice',
                                                   close_on_trigger=False).result()

    #pprint(order)
def fetch_positions():

    for coin in coins:
        symbol = coin['symbol']

        position = check_positions(symbol)

        if position != None:
            cancel_orders(symbol, position['size'], position['side'])
            set_tp(symbol, position['size'], position['side'])
            set_sl(symbol, position['size'], position['side'])
        else:
            cancel_stops(symbol, 1, 'Buy')


load_jsons()

print("Starting Take Profit & Order Manager")
while True:
    print("Checking for Positions.........")
    fetch_positions()
    sleep(settings['cooldown'])