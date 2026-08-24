import re
import json

def parse_coinglass_legend(file_path):
    with open(file_path, "r", encoding="utf-8") as f:
        lines = [line.strip() for line in f if line.strip()]

    data = {}

    for i, line in enumerate(lines):
        # 1. EMAs
        if line.startswith("EMA"):
            # Example: "8 close 0 SMA 9" \n "79448.6"
            if i + 2 < len(lines) and "close" in lines[i+1]:
                val = lines[i+2]
                if "8" in lines[i+1]: data["EMA 8"] = val
                elif "21" in lines[i+1]: data["EMA 21"] = val
                elif "50" in lines[i+1]: data["EMA 50"] = val
                elif "200" in lines[i+1]: data["EMA 200"] = val
                elif "800" in lines[i+1]: data["EMA 800"] = val
        
        # 2. Volume SMA 9
        elif line == "Volume":
            if i + 2 < len(lines) and "SMA" in lines[i+1]:
                data["VOLUME"] = lines[i+2]

        # 3. Spot CVD
        elif "<CoinGlass> Aggregated Spot Cumulative Volume Delta (CVD)" in line:
            if i + 2 < len(lines):
                data["SPOT CVD"] = lines[i+2]
        
        # 4. Futures CVD
        elif "<CoinGlass> Aggregated Futures Cumulative Volume Delta (CVD)" in line:
            if i + 2 < len(lines):
                data["FUT CVD"] = lines[i+2]

        # 5. RSI
        elif line == "RSI":
            if i + 2 < len(lines) and "SMA" in lines[i+1]:
                data["RSI (14)"] = lines[i+2]

        # 6. Funding Rates
        elif "<CoinGlass> Funding Rates" in line:
            # open No Filter \n 0.003609 \n 0.003609 \n 0.003210 \n 0.003452
            if i + 5 < len(lines) and "open No Filter" in lines[i+1]:
                # We usually want the main funding rate (maybe the first one?)
                data["FUNDING %"] = lines[i+2]

        # 7. Liquidations
        elif "<CoinGlass> Symbol Liquidations" in line:
            if i + 3 < len(lines) and "Long" in lines[i+1]:
                data["LONG LIQ"] = lines[i+2]
                data["SHORT LIQ"] = lines[i+3]

        # 8. L/S GLOBAL
        elif "<CoinGlass> Long/Short Ratio" in line:
            if i + 2 < len(lines):
                data["L/S GLOBAL"] = lines[i+2]

        # 9. Open Interest
        elif "<CoinGlass> Aggregated Open Interest" in line:
            if i + 2 < len(lines):
                data["OPEN INT"] = lines[i+2]

        # 10. Whale Index
        elif "<CoinGlass> Whale Index" in line:
            if i + 2 < len(lines):
                data["WHALE IDX"] = lines[i+2]

        # 11. Taker Buy/Sell
        elif "<CoinGlass> Taker Buy/Sell Count" in line:
            if i + 3 < len(lines):
                data["TAKER BUY"] = lines[i+2]
                data["TAKER SELL"] = lines[i+3]

        # 12. Bid / Ask Coins
        elif "<CoinGlass> Aggregated Futures Bid & Ask" in line and "Coins" in lines[i+1]:
            if i + 3 < len(lines):
                data["BID COIN"] = lines[i+2]
                data["ASK COIN"] = lines[i+3]

        # 13. Bid / Ask Dollars
        elif "<CoinGlass> Aggregated Futures Bid & Ask" in line and "Dollars" in lines[i+1]:
            if i + 3 < len(lines):
                data["BID DOLLAR"] = lines[i+2]
                data["ASK DOLLAR"] = lines[i+3]

        # 14. ATR
        elif line == "ATR":
            if i + 2 < len(lines):
                if lines[i+1] == "14": data["ATR 14"] = lines[i+2]
                elif lines[i+1] == "100": data["ATR 100"] = lines[i+2]

    # For ASSET, PRICE
    # Usually line 1: BTCUSDT, line 2: 15, line 3: Binance, line 4: O...H...L...C...
    if len(lines) > 5 and lines[1] == "BTCUSDT":
        data["ASSET"] = lines[1]
        c_match = re.search(r'C([\d\.]+)', lines[4])
        if c_match:
            data["PRICE"] = c_match.group(1)

    print(json.dumps(data, indent=2))

if __name__ == "__main__":
    parse_coinglass_legend("frame_1_text.txt")
