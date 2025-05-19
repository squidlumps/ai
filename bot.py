
import yfinance as yf
import requests
import pandas as pd
import schedule
import time
from datetime import datetime, timedelta

DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/your_webhook_here"

def send_discord_alert(content):
    data = {"content": content}
    requests.post(DISCORD_WEBHOOK_URL, json=data)

def get_top_stocks_by_market_cap(threshold=50e9):
    sp500 = yf.Ticker("^GSPC")
    tickers = pd.read_html("https://en.wikipedia.org/wiki/List_of_S%26P_500_companies")[0]['Symbol'].tolist()
    large_caps = []
    for ticker in tickers:
        try:
            info = yf.Ticker(ticker).info
            if info.get("marketCap", 0) >= threshold:
                large_caps.append(ticker)
        except:
            continue
    return large_caps

def calculate_indicators(df):
    df["EMA12"] = df["Close"].ewm(span=12, adjust=False).mean()
    df["EMA26"] = df["Close"].ewm(span=26, adjust=False).mean()
    df["MACD"] = df["EMA12"] - df["EMA26"]
    df["Signal"] = df["MACD"].ewm(span=9, adjust=False).mean()
    delta = df["Close"].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df["RSI"] = 100 - (100 / (1 + rs))
    return df

def analyze_stock(ticker):
    df = yf.download(ticker, period="3mo", interval="1d")
    if df.empty or len(df) < 30:
        return None
    df = calculate_indicators(df)
    latest = df.iloc[-1]
    previous = df.iloc[-2]
    # Buy signal: MACD crosses above signal and RSI below 30
    if previous["MACD"] < previous["Signal"] and latest["MACD"] > latest["Signal"] and latest["RSI"] < 30:
        return "CALL"
    # Sell signal: MACD crosses below signal and RSI above 70
    if previous["MACD"] > previous["Signal"] and latest["MACD"] < latest["Signal"] and latest["RSI"] > 70:
        return "PUT"
    return None

def get_option_details(ticker, direction):
    stock = yf.Ticker(ticker)
    expirations = stock.options
    if not expirations:
        return None
    try:
        target_expiry = expirations[min(1, len(expirations)-1)]  # Prefer 2nd soonest
        options = stock.option_chain(target_expiry)
        chain = options.calls if direction == "CALL" else options.puts
        current_price = stock.history(period="1d")["Close"][-1]
        chain["diff"] = abs(chain["strike"] - current_price)
        selected = chain.sort_values("diff").iloc[0]
        return {
            "strike": selected["strike"],
            "expiry": target_expiry,
            "lastPrice": selected["lastPrice"]
        }
    except:
        return None

def scan_market():
    print(f"Scanning market at {datetime.now()}")
    stocks = get_top_stocks_by_market_cap()
    for ticker in stocks:
        signal = analyze_stock(ticker)
        if signal:
            opt = get_option_details(ticker, signal)
            if opt:
                msg = f"📢 **{signal} ALERT**\nTicker: {ticker}\nStrike: ${opt['strike']}\nExpiry: {opt['expiry']}\nLast Price: ${opt['lastPrice']}"
                send_discord_alert(msg)

schedule.every(4).hours.do(scan_market)  # Run 6x/day on trading days

print("Bot started. Waiting for next scheduled scan...")
while True:
    schedule.run_pending()
    time.sleep(60)
