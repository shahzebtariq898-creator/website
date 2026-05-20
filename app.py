import os
from datetime import datetime, timedelta, timezone
from functools import wraps

import joblib
import numpy as np
import pandas as pd
import yfinance as yf
from flask import (
    Flask,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "gold-forecast-dev-key-change-in-prod")

VALID_EMAIL = "shahzeb2003@gmail.com"
VALID_PASSWORD = "12340000"

MODEL_PATH = os.path.join(os.path.dirname(__file__), "gold_price_model.pkl")
GOLD_TICKER = "GC=F"

_display_scale = None


def get_display_scale() -> float:
    """Map USD/oz to the scale the pickled model was trained on (~49)."""
    global _display_scale
    if _display_scale is not None:
        return _display_scale
    env = os.environ.get("GOLD_DISPLAY_SCALE")
    if env:
        _display_scale = float(env)
        return _display_scale
    scaler = get_model().named_steps["scaler"]
    train_anchor = float(scaler.mean_[0])
    try:
        end = datetime.now(timezone.utc)
        start = end - timedelta(days=5)
        df = yf.download(GOLD_TICKER, start=start, end=end, progress=False, auto_adjust=True)
        if not df.empty:
            if isinstance(df.columns, pd.MultiIndex):
                close = float(df["Close"].iloc[-1].squeeze())
            else:
                close = float(df["Close"].iloc[-1])
            _display_scale = close / train_anchor
            return _display_scale
    except Exception:
        pass
    _display_scale = 91.0
    return _display_scale

LAG_COLS = [f"lag_{i}" for i in range(1, 13)]

_model = None


def get_model():
    global _model
    if _model is None:
        _model = joblib.load(MODEL_PATH)
    return _model


def login_required(f):
    @wraps(f)
    def wrapped(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect(url_for("login"))
        return f(*args, **kwargs)

    return wrapped


def to_model_scale(price_display: float) -> float:
    return price_display / get_display_scale()


def to_display_scale(price_model: float) -> float:
    return price_model * get_display_scale()


def lags_from_single_price(price_model: float) -> list[float]:
    """Build 12 lags from one price using training mean ratios."""
    scaler = get_model().named_steps["scaler"]
    means = scaler.mean_
    ratio = price_model / means[0]
    return [float(means[i] * ratio) for i in range(12)]


def predict_one(lags: list[float]) -> float:
    model = get_model()
    row = pd.DataFrame([dict(zip(LAG_COLS, lags))])
    return float(model.predict(row)[0])


def forecast_days(initial_lags: list[float], days: int = 7) -> list[float]:
    lags = list(initial_lags)
    out = []
    for _ in range(days):
        pred = predict_one(lags)
        out.append(pred)
        lags = [pred] + lags[:11]
    return out


def fetch_gold_history(days: int = 90) -> pd.DataFrame:
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=days + 30)
    df = yf.download(GOLD_TICKER, start=start, end=end, progress=False, auto_adjust=True)
    if df.empty:
        return pd.DataFrame(columns=["date", "actual_model"])
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    close = df["Close"].dropna()
    result = pd.DataFrame(
        {
            "date": close.index.strftime("%Y-%m-%d"),
            "actual_model": (close.values.astype(float) / get_display_scale()).flatten(),
        }
    )
    return result.tail(days + 15).reset_index(drop=True)


def build_actual_vs_predicted(history_df: pd.DataFrame) -> dict:
    dates, actuals, predicted = [], [], []
    prices = history_df["actual_model"].tolist()
    date_labels = history_df["date"].tolist()

    for i in range(12, len(prices)):
        lags = prices[i - 12 : i][::-1]  # lag_1 = most recent
        pred = predict_one(lags)
        dates.append(date_labels[i])
        actuals.append(round(to_display_scale(prices[i]), 2))
        predicted.append(round(to_display_scale(pred), 2))

    return {"dates": dates, "actual": actuals, "predicted": predicted}


@app.route("/")
def index():
    if session.get("logged_in"):
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""
        if email == VALID_EMAIL.lower() and password == VALID_PASSWORD:
            session["logged_in"] = True
            session["user_email"] = email
            return redirect(url_for("dashboard"))
        error = "Invalid email or password."
    return render_template("login.html", error=error)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/dashboard")
@login_required
def dashboard():
    return render_template("dashboard.html", user_email=session.get("user_email", ""))


@app.route("/api/history")
@login_required
def api_history():
    try:
        df = fetch_gold_history(days=60)
        if len(df) < 14:
            return jsonify({"error": "Not enough market data. Try again later."}), 503
        chart = build_actual_vs_predicted(df)
        return jsonify(chart)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/forecast", methods=["POST"])
@login_required
def api_forecast():
    data = request.get_json(silent=True) or {}
    try:
        price = float(data.get("price", 0))
    except (TypeError, ValueError):
        return jsonify({"error": "Please enter a valid gold price."}), 400

    if price <= 0:
        return jsonify({"error": "Price must be greater than zero."}), 400

    price_model = to_model_scale(price)
    lags = lags_from_single_price(price_model)
    preds_model = forecast_days(lags, days=7)

    today = datetime.now(timezone.utc).date()
    days_out = []
    for i, p in enumerate(preds_model, start=1):
        d = today + timedelta(days=i)
        days_out.append(
            {
                "day": i,
                "date": d.strftime("%Y-%m-%d"),
                "price": round(to_display_scale(p), 2),
            }
        )

    return jsonify(
        {
            "input_price": round(price, 2),
            "forecast": days_out,
            "chart": {
                "labels": ["Today"] + [f"Day {x['day']}" for x in days_out],
                "values": [round(price, 2)] + [x["price"] for x in days_out],
            },
        }
    )


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
