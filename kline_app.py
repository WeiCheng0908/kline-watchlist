"""
kline_app.py
===========
Self-hosted K-line (candlestick) chart viewer with watchlist + technical indicators.

執行:
    streamlit run kline_app.py

依賴:
    streamlit, yfinance, plotly, pandas
"""

import json
import os
from datetime import datetime
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import yfinance as yf
from plotly.subplots import make_subplots

# ---------- 路徑設定 ----------
# 預設存在 app 目錄下的 .kline_data,Streamlit Cloud 上會跨重啟保留(同 deploy)
# 本機開發若想用 home dir,設環境變數 KLINE_DATA_DIR=~/.kline_app
_data_dir = os.environ.get("KLINE_DATA_DIR")
APP_DIR = Path(_data_dir).expanduser() if _data_dir else Path(__file__).parent / ".kline_data"
WATCHLIST_FILE = APP_DIR / "watchlist.json"
PRESET_FILE = APP_DIR / "indicator_preset.json"
APP_DIR.mkdir(parents=True, exist_ok=True)

# ---------- TradingView 風格色票 ----------
# 經典 TV dark 主題
TV_COLORS = {
    "bg":            "#131722",   # 圖表底色
    "pane_bg":       "#131722",   # 子圖底色(同 bg,TV 一致)
    "grid":          "#1e222d",   # 格線
    "grid_minor":    "#1a1e2a",   # 副格線
    "text":          "#d1d4dc",   # 主要文字
    "text_muted":    "#787b86",   # 標籤/座標軸
    "up":            "#26a69a",   # 漲綠
    "down":          "#ef5350",   # 跌紅
    "crosshair":     "#758696",   # 十字游標線
    "hover_bg":      "#363a45",   # hover label 背景
    "bb_fill":       "rgba(120,180,255,0.10)",
    "bb_line":       "#90caf9",
    "sma_palette":   ["#fdd835", "#42a5f5", "#ab47bc", "#66bb6a", "#ff7043", "#26c6da"],
    "font":          "-apple-system, BlinkMacSystemFont, 'Trebuchet MS', Roboto, Ubuntu, sans-serif",
}


def _apply_tv_layout(fig: go.Figure, n_subplots: int = 1) -> None:
    """套用 TradingView dark 主題的 layout/字型/十字游標/格線設定。"""
    C = TV_COLORS
    fig.update_layout(
        paper_bgcolor=C["bg"],
        plot_bgcolor=C["pane_bg"],
        font=dict(family=C["font"], color=C["text"], size=12),
        margin=dict(l=8, r=8, t=10, b=10),
        xaxis_rangeslider_visible=False,
        hovermode="x unified",
        hoverlabel=dict(
            bgcolor=C["hover_bg"],
            bordercolor=C["crosshair"],
            font=dict(family=C["font"], color=C["text"], size=12),
        ),
        legend=dict(
            orientation="h",
            yanchor="bottom", y=1.02,
            xanchor="right", x=1,
            bgcolor="rgba(0,0,0,0)",
            font=dict(size=11, color=C["text_muted"]),
        ),
        showlegend=True,
    )
    # 套用到所有 subplot 的 axes
    # plotly 會自動建 axis 1..n_subplots
    for i in range(1, n_subplots + 1):
        # xaxis
        xa = getattr(fig.layout, f"xaxis{i if i > 1 else ''}", None)
        suffix = "" if i == 1 else str(i)
        fig.update_xaxes(
            showgrid=True, gridcolor=C["grid"], gridwidth=0.5,
            showline=False, zeroline=False,
            color=C["text_muted"],
            tickfont=dict(family=C["font"], size=11, color=C["text_muted"]),
            showspikes=True, spikemode="across", spikesnap="cursor",
            spikecolor=C["crosshair"], spikethickness=1, spikedash="dot",
            row=i, col=1,
        )
        fig.update_yaxes(
            showgrid=True, gridcolor=C["grid"], gridwidth=0.5,
            showline=False, zeroline=False,
            color=C["text_muted"],
            tickfont=dict(family=C["font"], size=11, color=C["text_muted"]),
            showspikes=True, spikemode="across", spikesnap="cursor",
            spikecolor=C["crosshair"], spikethickness=1, spikedash="dot",
            side="right",
            row=i, col=1,
        )
    # 統一子圖間距
    fig.update_layout(hoverdistance=50)


# ---------- 週期對照表 ----------
PERIODS = {
    "1 個月": ("1mo", "1d"),
    "3 個月": ("3mo", "1d"),
    "6 個月": ("6mo", "1d"),
    "1 年": ("1y", "1d"),
    "2 年": ("2y", "1d"),
    "5 年": ("5y", "1wk"),
    "10 年": ("10y", "1wk"),
    "今年至今": ("ytd", "1d"),
    "最大範圍": ("max", "1mo"),
}

# ---------- 指標定義 ----------
# type: overlay=疊在主圖 / oscillator=獨立下方面板 / volume=疊在成交量
INDICATOR_DEFAULTS = {
    "bb": {
        "label": "布林通道 BB",
        "group": "主圖疊加",
        "type": "overlay",
        "params": {"period": 20, "std": 2.0},
    },
    "sma": {
        "label": "簡單均線 SMA",
        "group": "主圖疊加",
        "type": "overlay",
        "params": {"periods": [5, 20, 60]},
    },
    "ema": {
        "label": "指數均線 EMA",
        "group": "主圖疊加",
        "type": "overlay",
        "params": {"periods": [12, 26]},
    },
    "vol_ma": {
        "label": "成交量均線",
        "group": "成交量",
        "type": "volume",
        "params": {"period": 20},
    },
    "rsi": {
        "label": "RSI 相對強弱",
        "group": "震盪指標",
        "type": "oscillator",
        "params": {"period": 14, "overbought": 70, "oversold": 30},
    },
    "macd": {
        "label": "MACD",
        "group": "震盪指標",
        "type": "oscillator",
        "params": {"fast": 12, "slow": 26, "signal": 9},
    },
    "kd": {
        "label": "KD 隨機指標",
        "group": "震盪指標",
        "type": "oscillator",
        "params": {"k_period": 9, "d_period": 3},
    },
}


# ---------- watchlist 存取 ----------
def load_watchlist() -> list[dict]:
    if not WATCHLIST_FILE.exists():
        return []
    try:
        return json.loads(WATCHLIST_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []


def save_watchlist(items: list[dict]) -> None:
    WATCHLIST_FILE.write_text(
        json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def load_preset() -> dict | None:
    if not PRESET_FILE.exists():
        return None
    try:
        return json.loads(PRESET_FILE.read_text(encoding="utf-8"))
    except Exception:
        return None


def save_preset(ind: dict) -> None:
    PRESET_FILE.write_text(
        json.dumps(ind, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def parse_tickers(raw: str) -> list[str]:
    if not raw:
        return []
    parts = [p.strip().upper() for p in raw.replace("\n", ",").replace(" ", ",").split(",")]
    return [p for p in parts if p]


# ---------- 抓資料 ----------
@st.cache_data(ttl=300, show_spinner=False)
def fetch_history(ticker: str, period: str, interval: str) -> pd.DataFrame:
    df = yf.Ticker(ticker).history(period=period, interval=interval, auto_adjust=False)
    if df is None or df.empty:
        return pd.DataFrame()
    df = df.rename_axis("Date").reset_index()
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [c[0] for c in df.columns]
    return df


@st.cache_data(ttl=600, show_spinner=False)
def fetch_quote(ticker: str) -> dict:
    try:
        info = yf.Ticker(ticker).fast_info
        return {
            "price": getattr(info, "last_price", None),
            "prev_close": getattr(info, "previous_close", None),
            "currency": getattr(info, "currency", ""),
            "name": getattr(info, "short_name", "") or ticker,
        }
    except Exception:
        return {"price": None, "prev_close": None, "currency": "", "name": ticker}


# ---------- 指標計算 ----------
def _bb_bands(close: pd.Series, period: int, n_std: float):
    mid = close.rolling(period).mean()
    sd = close.rolling(period).std(ddof=0)
    return mid + n_std * sd, mid, mid - n_std * sd


def _ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False).mean()


def _rsi(close: pd.Series, n: int) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    rs = gain / loss.replace(0, 1e-12)
    return 100 - 100 / (1 + rs)


def _macd(close: pd.Series, f: int, s: int, sig: int):
    macd = _ema(close, f) - _ema(close, s)
    signal = _ema(macd, sig)
    return macd, signal, macd - signal


def _kd(high: pd.Series, low: pd.Series, close: pd.Series, kp: int, dp: int):
    low_n = low.rolling(kp).min()
    high_n = high.rolling(kp).max()
    rsv = (close - low_n) / (high_n - low_n).replace(0, 1e-12) * 100
    k = rsv.ewm(alpha=1 / dp, adjust=False).mean()
    d = k.ewm(alpha=1 / dp, adjust=False).mean()
    return k, d


# ---------- 繪圖 ----------
def make_chart(df: pd.DataFrame, ticker: str, ind: dict) -> go.Figure:
    C = TV_COLORS
    # 動態決定面板數量與高度
    rows_def = [("price", 0.62), ("volume", 0.16)]
    if ind["rsi"]["enabled"]:
        rows_def.append(("rsi", 0.10))
    if ind["macd"]["enabled"]:
        rows_def.append(("macd", 0.12))
    if ind["kd"]["enabled"]:
        rows_def.append(("kd", 0.10))

    fig = make_subplots(
        rows=len(rows_def), cols=1, shared_xaxes=True,
        vertical_spacing=0.02,
        row_heights=[r[1] for r in rows_def],
    )
    rmap = {name: i + 1 for i, (name, _) in enumerate(rows_def)}

    # 主圖:K 線(TV 風格:無邊框、實心填色)
    fig.add_trace(
        go.Candlestick(
            x=df["Date"], open=df["Open"], high=df["High"],
            low=df["Low"], close=df["Close"], name=ticker,
            increasing_line_color=C["up"], increasing_fillcolor=C["up"],
            decreasing_line_color=C["down"], decreasing_fillcolor=C["down"],
            line=dict(width=1),
            whiskerwidth=0,
        ),
        row=rmap["price"], col=1,
    )

    # BB
    if ind["bb"]["enabled"]:
        p, s = ind["bb"]["period"], ind["bb"]["std"]
        upper, mid, lower = _bb_bands(df["Close"], p, s)
        # 上軌(隱形,給 fill 參考)
        fig.add_trace(go.Scatter(
            x=df["Date"], y=upper, mode="lines",
            line=dict(width=0), showlegend=False, hoverinfo="skip",
        ), row=rmap["price"], col=1)
        # 下軌 + 填色
        fig.add_trace(go.Scatter(
            x=df["Date"], y=lower, mode="lines",
            line=dict(width=0), fill="tonexty",
            fillcolor=C["bb_fill"],
            showlegend=False, hoverinfo="skip",
        ), row=rmap["price"], col=1)
        # 中軌(顯示在圖例)
        fig.add_trace(go.Scatter(
            x=df["Date"], y=mid, mode="lines",
            name=f"BB({p},{s})", line=dict(color=C["bb_line"], width=1),
        ), row=rmap["price"], col=1)

    palette = C["sma_palette"]

    # SMA
    if ind["sma"]["enabled"]:
        for i, p in enumerate(ind["sma"]["periods"]):
            ma = df["Close"].rolling(p).mean()
            fig.add_trace(go.Scatter(
                x=df["Date"], y=ma, mode="lines",
                name=f"SMA{p}", line=dict(width=1.3, color=palette[i % len(palette)]),
            ), row=rmap["price"], col=1)

    # EMA
    if ind["ema"]["enabled"]:
        for i, p in enumerate(ind["ema"]["periods"]):
            ma = _ema(df["Close"], p)
            fig.add_trace(go.Scatter(
                x=df["Date"], y=ma, mode="lines",
                name=f"EMA{p}", line=dict(width=1.3, color=palette[i % len(palette)], dash="dot"),
            ), row=rmap["price"], col=1)

    # 成交量(TV 風格:半透明同色)
    vol_colors_up = f"rgba(38,166,154,0.55)"   # C["up"] 半透明
    vol_colors_dn = f"rgba(239,83,80,0.55)"    # C["down"] 半透明
    colors_vol = [vol_colors_up if c >= o else vol_colors_dn for o, c in zip(df["Open"], df["Close"])]
    fig.add_trace(go.Bar(
        x=df["Date"], y=df["Volume"], name="Volume",
        marker=dict(color=colors_vol, line=dict(width=0)),
        showlegend=False,
    ), row=rmap["volume"], col=1)
    if ind["vol_ma"]["enabled"]:
        p = ind["vol_ma"]["period"]
        vma = df["Volume"].rolling(p).mean()
        fig.add_trace(go.Scatter(
            x=df["Date"], y=vma, mode="lines",
            name=f"VolMA{p}", line=dict(color="#FFFFFF", width=1.1),
        ), row=rmap["volume"], col=1)

    # RSI
    if ind["rsi"]["enabled"]:
        p, ob, os_ = ind["rsi"]["period"], ind["rsi"]["overbought"], ind["rsi"]["oversold"]
        rsi = _rsi(df["Close"], p)
        fig.add_trace(go.Scatter(
            x=df["Date"], y=rsi, mode="lines", name=f"RSI({p})",
            line=dict(color="#ce93d8", width=1.3),
        ), row=rmap["rsi"], col=1)
        for level, color, label in [(ob, C["down"], f"{ob}"), (os_, C["up"], f"{os_}"), (50, C["text_muted"], "50")]:
            fig.add_hline(y=level, line_dash="dash", line_color=color, line_width=0.6,
                          annotation_text=label, annotation_position="right",
                          annotation_font=dict(color=C["text_muted"], size=10),
                          row=rmap["rsi"], col=1)
        fig.update_yaxes(range=[0, 100], row=rmap["rsi"], col=1)

    # MACD
    if ind["macd"]["enabled"]:
        f, s, sig = ind["macd"]["fast"], ind["macd"]["slow"], ind["macd"]["signal"]
        macd, signal, hist = _macd(df["Close"], f, s, sig)
        colors_h = [C["up"] if h >= 0 else C["down"] for h in hist]
        fig.add_trace(go.Bar(
            x=df["Date"], y=hist, name="Hist",
            marker=dict(color=colors_h, line=dict(width=0)),
            showlegend=False,
        ), row=rmap["macd"], col=1)
        fig.add_trace(go.Scatter(
            x=df["Date"], y=macd, mode="lines", name="MACD",
            line=dict(color="#42a5f5", width=1.3),
        ), row=rmap["macd"], col=1)
        fig.add_trace(go.Scatter(
            x=df["Date"], y=signal, mode="lines", name="Signal",
            line=dict(color="#ffa726", width=1.3),
        ), row=rmap["macd"], col=1)
        fig.add_hline(y=0, line_color=C["text_muted"], line_width=0.5, row=rmap["macd"], col=1)

    # KD
    if ind["kd"]["enabled"]:
        kp, dp = ind["kd"]["k_period"], ind["kd"]["d_period"]
        k, d = _kd(df["High"], df["Low"], df["Close"], kp, dp)
        fig.add_trace(go.Scatter(
            x=df["Date"], y=k, mode="lines", name=f"K({kp})",
            line=dict(color="#42a5f5", width=1.3),
        ), row=rmap["kd"], col=1)
        fig.add_trace(go.Scatter(
            x=df["Date"], y=d, mode="lines", name=f"D({dp})",
            line=dict(color="#ffa726", width=1.3),
        ), row=rmap["kd"], col=1)
        for level, color, label in [(80, C["down"], "80"), (20, C["up"], "20")]:
            fig.add_hline(y=level, line_dash="dash", line_color=color, line_width=0.6,
                          annotation_text=label, annotation_position="right",
                          annotation_font=dict(color=C["text_muted"], size=10),
                          row=rmap["kd"], col=1)
        fig.update_yaxes(range=[0, 100], row=rmap["kd"], col=1)

    # 高度 & TV 風格 layout
    height = 620 + 110 * sum(1 for r in rows_def if r[0] != "price")
    _apply_tv_layout(fig, n_subplots=len(rows_def))
    fig.update_layout(height=height)
    return fig


# ---------- session_state 初始化 ----------
def _init_indicators():
    if "indicators" in st.session_state:
        return
    preset = load_preset()
    base = {k: {"enabled": False, **v["params"]} for k, v in INDICATOR_DEFAULTS.items()}
    if preset:
        for k, v in preset.items():
            if k in base:
                base[k].update(v)
    else:
        # 預設:BB + SMA 開
        base["bb"]["enabled"] = True
        base["sma"]["enabled"] = True
    st.session_state.indicators = base


_init_indicators()


# ---------- UI ----------
st.set_page_config(
    page_title="K-Line Watchlist",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={"About": "Self-hosted candlestick viewer · yfinance · plotly"},
)

# 用 markdown 注入最小化 CSS(深色配 TV 風)
st.markdown(
    """
    <style>
        .stApp { background-color: #131722; }
        section[data-testid="stSidebar"] { background-color: #1a1e2a; }
        h1, h2, h3, h4, h5, h6, p, span, label, .stMarkdown, .stCaption { color: #d1d4dc !important; }
        .stCaption { color: #787b86 !important; }
        div[data-testid="stMetricValue"] { color: #d1d4dc; }
        div[data-testid="stDataFrame"] { background-color: #1a1e2a; }
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("📈 自選股 K 線看盤")
st.caption("資料來源: Yahoo Finance via yfinance · TradingView-style dark theme")

watchlist = load_watchlist()

with st.sidebar:
    st.header("➕ 快速匯入")
    raw = st.text_area(
        "貼上股號(逗號/空白/換行分隔)",
        placeholder="AAPL, MSFT, NVDA\n2330.TW, 0050.TW",
        height=90,
    )
    col_a, col_b = st.columns(2)
    if col_a.button("加入", use_container_width=True):
        new = parse_tickers(raw)
        existing = {w["ticker"] for w in watchlist}
        added = []
        for t in new:
            if t not in existing:
                quote = fetch_quote(t)
                watchlist.append({
                    "ticker": t,
                    "name": quote["name"] or t,
                    "added_at": datetime.now().isoformat(timespec="seconds"),
                })
                added.append(t)
        if added:
            save_watchlist(watchlist)
            st.success(f"已加入: {', '.join(added)}")
            st.rerun()
        else:
            st.info("沒有新股號(可能已在清單中)")

    if col_b.button("清空輸入", use_container_width=True):
        st.rerun()

    st.divider()
    st.header("⚙️ 顯示設定")
    period_label = st.selectbox("時間區間", list(PERIODS.keys()), index=3)

    st.divider()
    st.header("📊 技術指標")

    # 群組分區顯示
    groups: dict[str, list[str]] = {}
    for k, v in INDICATOR_DEFAULTS.items():
        groups.setdefault(v["group"], []).append(k)

    for gname, keys in groups.items():
        st.caption(f"**{gname}**")
        for key in keys:
            meta = INDICATOR_DEFAULTS[key]
            cfg = st.session_state.indicators[key]
            cfg["enabled"] = st.checkbox(meta["label"], value=cfg["enabled"], key=f"en_{key}")
            if cfg["enabled"]:
                with st.container(border=True):
                    for pname, pval in meta["params"].items():
                        if isinstance(pval, list):
                            cur = ", ".join(str(x) for x in cfg[pname])
                            new = st.text_input(
                                f"{pname}(逗號分隔)",
                                value=cur,
                                key=f"p_{key}_{pname}",
                                help="例如: 5, 20, 60",
                            )
                            try:
                                cfg[pname] = [int(x.strip()) for x in new.split(",") if x.strip().isdigit()]
                            except Exception:
                                pass
                        elif isinstance(pval, float):
                            cfg[pname] = st.number_input(
                                pname, value=float(pval),
                                step=0.1, min_value=0.1, max_value=10.0,
                                key=f"p_{key}_{pname}",
                            )
                        else:
                            cfg[pname] = st.number_input(
                                pname, value=int(pval),
                                step=1, min_value=1, max_value=500,
                                key=f"p_{key}_{pname}",
                            )

    pc1, pc2 = st.columns(2)
    if pc1.button("💾 存為預設", use_container_width=True):
        save_preset(st.session_state.indicators)
        st.toast("已存到 ~/.kline_app/indicator_preset.json", icon="✅")
    if pc2.button("↩️ 重置預設", use_container_width=True):
        for k in st.session_state.indicators:
            st.session_state.indicators[k] = {"enabled": False, **INDICATOR_DEFAULTS[k]["params"]}
        st.session_state.indicators["bb"]["enabled"] = True
        st.session_state.indicators["sma"]["enabled"] = True
        st.rerun()

    st.divider()
    st.header("💾 watchlist 備份")
    st.download_button(
        "下載 JSON",
        data=json.dumps(watchlist, ensure_ascii=False, indent=2),
        file_name="watchlist.json",
        mime="application/json",
        use_container_width=True,
    )
    uploaded = st.file_uploader("從 JSON 匯入", type=["json"])
    if uploaded and st.button("合併匯入", use_container_width=True):
        try:
            incoming = json.loads(uploaded.read().decode("utf-8"))
            existing = {w["ticker"] for w in watchlist}
            merged = watchlist + [w for w in incoming if w.get("ticker") and w["ticker"] not in existing]
            save_watchlist(merged)
            st.success(f"合併完成,目前 {len(merged)} 檔")
            st.rerun()
        except Exception as e:
            st.error(f"匯入失敗: {e}")

# ---------- watchlist 主體 ----------
if not watchlist:
    st.info("👈 從左側貼上股號開始,例如 `AAPL, MSFT, 2330.TW`")
    st.stop()

rows = []
for w in watchlist:
    q = fetch_quote(w["ticker"])
    price = q["price"]
    prev = q["prev_close"]
    chg = ((price - prev) / prev * 100) if (price and prev) else None
    rows.append({
        "代碼": w["ticker"],
        "名稱": q["name"][:20],
        "現價": f"{price:.2f}" if price else "-",
        "漲跌%": (f"{chg:+.2f}%" if chg is not None else "-"),
        "幣別": q["currency"],
    })
df_watch = pd.DataFrame(rows)

st.subheader(f"自選股 ({len(watchlist)})")
st.dataframe(
    df_watch,
    use_container_width=True, hide_index=True,
)

st.subheader("K 線檢視")
tickers = [w["ticker"] for w in watchlist]
selected = st.selectbox("選擇股號", tickers)
to_remove = st.button("🗑️ 從 watchlist 移除此股")
if to_remove:
    watchlist = [w for w in watchlist if w["ticker"] != selected]
    save_watchlist(watchlist)
    st.rerun()

period, interval = PERIODS[period_label]
with st.spinner(f"抓取 {selected} {period_label} 資料..."):
    df = fetch_history(selected, period, interval)

if df.empty:
    st.error(f"抓不到 {selected} 的資料,請確認代號是否正確(美股直接代號,台股加 .TW,港股 .HK)")
    st.stop()

fig = make_chart(df, selected, st.session_state.indicators)
st.plotly_chart(fig, use_container_width=True)

c1, c2, c3, c4 = st.columns(4)
c1.metric("區間最高", f"{df['High'].max():.2f}")
c2.metric("區間最低", f"{df['Low'].min():.2f}")
c3.metric("區間均量", f"{int(df['Volume'].mean()):,}")
c4.metric("資料筆數", f"{len(df)}")

with st.expander("查看原始資料"):
    st.dataframe(df, use_container_width=True, hide_index=True)
    st.download_button(
        "下載此檔 CSV",
        data=df.to_csv(index=False).encode("utf-8"),
        file_name=f"{selected}_{period_label}.csv",
        mime="text/csv",
    )
