import os
from datetime import datetime, timedelta, timezone
from functools import wraps
from pathlib import Path

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

from database import (
    authenticate,
    create_password_otp,
    create_user,
    get_user_by_email,
    get_user_by_id,
    init_db,
    verify_otp_and_reset_password,
)
from email_service import send_otp_email, smtp_configured

try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).parent / ".env")
except ImportError:
    pass

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "gold-forecast-dev-key-change-in-prod")

if os.environ.get("VERCEL") or os.environ.get("VERCEL_ENV"):
    app.config["SESSION_COOKIE_SECURE"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

init_db()

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


def set_user_session(user):
    session["logged_in"] = True
    session["user_id"] = user["id"]
    session["user_email"] = user["email"]
    session["user_name"] = user["name"]


@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    success = None
    if request.args.get("reset_ok"):
        success = "Password updated. Sign in with your new password."
    if request.method == "POST":
        email = request.form.get("email") or ""
        password = request.form.get("password") or ""
        user = authenticate(email, password)
        if user:
            set_user_session(user)
            return redirect(url_for("dashboard"))
        error = "Invalid email or password."
    return render_template("login.html", error=error, success=success)


@app.route("/signup", methods=["GET", "POST"])
def signup():
    error = None
    success = None
    form = {}
    if request.method == "POST":
        form = {
            "name": request.form.get("name"),
            "email": request.form.get("email"),
            "phone": request.form.get("phone"),
        }
        ok, msg = create_user(
            form["name"],
            form["email"],
            form["phone"],
            request.form.get("password"),
            request.form.get("confirm_password"),
        )
        if ok:
            success = "Account created. You can sign in now."
            form = {}
        else:
            error = msg
    return render_template("signup.html", error=error, success=success, form=form)


def _send_otp_to_email(email: str):
    ok, err, otp = create_password_otp(email)
    if not ok:
        return False, err
    user = get_user_by_email(email)
    sent, send_msg = send_otp_email(email, otp, user.get("name", "") if user else "")
    if not sent:
        return False, send_msg
    return True, send_msg


@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    error = None
    success = None
    form = {}
    if request.method == "POST":
        email = request.form.get("email") or ""
        form = {"email": email}
        if not smtp_configured():
            error = (
                "Email OTP is not set up yet. Copy .env.example to .env and add your "
                "Gmail App Password (MAIL_USERNAME, MAIL_PASSWORD)."
            )
        else:
            ok, msg = _send_otp_to_email(email)
            if ok:
                session["reset_email"] = email.strip().lower()
                return redirect(url_for("forgot_password_verify"))
            error = msg
    return render_template("forgot_password.html", error=error, success=success, form=form)


@app.route("/forgot-password/verify", methods=["GET", "POST"])
def forgot_password_verify():
    email = session.get("reset_email")
    if not email:
        return redirect(url_for("forgot_password"))

    error = None
    success = None
    if request.method == "POST":
        ok, msg = verify_otp_and_reset_password(
            email,
            request.form.get("otp"),
            request.form.get("password"),
            request.form.get("confirm_password"),
        )
        if ok:
            session.pop("reset_email", None)
            return redirect(url_for("login", reset_ok=1))
        error = msg

    return render_template(
        "forgot_password_verify.html", email=email, error=error, success=success
    )


@app.route("/forgot-password/resend", methods=["POST"])
def forgot_password_resend():
    email = session.get("reset_email")
    if not email:
        return redirect(url_for("forgot_password"))

    if not smtp_configured():
        return render_template(
            "forgot_password_verify.html",
            email=email,
            error="Email is not configured. Add MAIL_* settings to .env file.",
        )

    ok, msg = _send_otp_to_email(email)
    return render_template(
        "forgot_password_verify.html",
        email=email,
        success=msg if ok else None,
        error=None if ok else msg,
    )


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/dashboard")
@login_required
def dashboard():
    user = get_user_by_id(session.get("user_id")) or {}
    return render_template(
        "dashboard.html",
        user_email=session.get("user_email", ""),
        user_name=user.get("name") or session.get("user_name", ""),
        user_phone=user.get("phone", ""),
    )


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
