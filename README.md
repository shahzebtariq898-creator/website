# Gold Price Forecast

Login-protected dashboard for gold price **actual vs predicted** charts and **7-day forecasts** using `gold_price_model.pkl`.

## Run locally

```bash
pip install -r requirements.txt
python app.py
```

Open http://127.0.0.1:5000

## Login

- **Email:** shahzeb2003@gmail.com  
- **Password:** 12340000  

## Features

- **Actual vs predicted** — Chart from recent COMEX gold (GC=F) vs model output  
- **7-day forecast** — Enter current gold price (USD/oz); see numbers + graph for next 7 days  

## Notes

- Prices are shown in **USD/oz** (scaled to match the trained model).  
- Display scale auto-calibrates from live gold vs model training mean; override with `GOLD_DISPLAY_SCALE` if needed.
