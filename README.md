# Gold Price Forecast

Login-protected dashboard for gold price **actual vs predicted** charts and **7-day forecasts** using `gold_price_model.pkl`.

## Live on Vercel

Import this repo on [Vercel](https://vercel.com) → connect GitHub `shahzebtariq898-creator/website` → add env vars from `.env.example` → Deploy.

See [DEPLOY.md](DEPLOY.md) for step-by-step instructions.

## Run locally

```bash
pip install -r requirements.txt
python app.py
```

Open http://127.0.0.1:5000

## Login

- **Sign up** — name, email, phone, password (stored in local SQLite `users.db`)
- **Forgot password** — email → 6-digit OTP → new password (OTP sent via Gmail SMTP; see `.env.example`)
- Default demo account: `shahzeb2003@gmail.com` / `12340000` (phone: `03000000000` for reset)  

## Features

- **Actual vs predicted** — Chart from recent COMEX gold (GC=F) vs model output  
- **7-day forecast** — Enter current gold price (USD/oz); see numbers + graph for next 7 days  

## Notes

- Prices are shown in **USD/oz** (scaled to match the trained model).  
- Display scale auto-calibrates from live gold vs model training mean; override with `GOLD_DISPLAY_SCALE` if needed.
