# 📈 K-Line Watchlist

自架看 K 線網站,TradingView 風格。資料來源:Yahoo Finance (yfinance)。

![demo](https://raw.githubusercontent.com/yourname/kline-watchlist/main/preview.png)

## 功能

- 🚀 快速匯入自選股(貼上股號,逗號/換行分隔)
- 📊 多時間區間(1M / 3M / 6M / 1Y / 2Y / 5Y / 10Y / YTD / Max)
- 🎨 **TradingView 風格深色主題** — 十字游標 / 右側價格軸 / 漲綠跌紅
- 🔧 7 種技術指標 + 可調參數:
  - 布林通道 BB(週期、標準差)
  - SMA / EMA(多週期)
  - RSI(週期、超買超賣門檻)
  - MACD(快慢線、信號線)
  - KD 隨機指標
  - 成交量均線
- 💾 watchlist 存 JSON,可下載/上傳同步多裝置
- 🌐 支援美股 / 台股 / 港股

## 在 Streamlit Community Cloud 部署

### 1. Push 到 GitHub

```bash
git init
git add .
git commit -m "init kline watchlist"
git branch -M main
git remote add origin https://github.com/<你的帳號>/kline-watchlist.git
git push -u origin main
```

### 2. 連結 Streamlit Cloud

1. 到 [share.streamlit.io](https://share.streamlit.io/) 用 GitHub 帳號登入
2. 點 **「New app」**
3. 填寫:
   - **Repository**: `你的帳號/kline-watchlist`
   - **Branch**: `main`
   - **Main file path**: `kline_app.py`
   - **App URL**: 選一個 subdomain(像 `my-kline.streamlit.app`)
4. 點 **Deploy!**

第一次部署會花 1-2 分鐘裝套件,之後冷啟動約 10-20 秒。

### 3. 之後更新

`git push` 完 Streamlit Cloud 會自動重新部署(預設 1-2 分鐘)。

### ⚠️ watchlist 持久化

watchlist 跟指標預設存到 `app 目錄下的 .kline_data/`(會跨重啟保留,但**重新 deploy 會清空**)。
若想放別處,設環境變數 `KLINE_DATA_DIR`(在 Streamlit Cloud 的 Secrets 裡加):

```toml
KLINE_DATA_DIR = "/tmp/.kline_app"
```

如果 watchlist 真的掉了,左下角「從 JSON 匯入」按鈕可以還原。

## 本機跑

```bash
pip install -r requirements.txt
streamlit run kline_app.py
```

開 http://localhost:8501

## 檔案結構

```
.
├── kline_app.py          # 主程式
├── requirements.txt      # Python 依賴
├── .streamlit/
│   └── config.toml       # 主題設定(深色)
├── .gitignore
└── README.md
```

## 注意

- yfinance 對台股盤中資料有 15 分鐘延遲(從 Yahoo 取得的就是這樣)
- 短時間大量 request 會被 Yahoo 限流,內建 `@st.cache_data(ttl=300)` 緩解
- 免費 Streamlit Cloud 資源有限(1GB RAM),個股數量不要太多就好

## License

MIT
