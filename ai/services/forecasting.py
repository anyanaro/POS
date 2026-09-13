import pandas as pd
from datetime import timedelta, date
from django.db.models import Sum
from django.utils import timezone
from decimal import Decimal

from ai.models import Forecast
from accounts.models.sales import SalesHeader, SalesLine
from accounts.models.product import Product
from accounts.models.org import Branch

def _timeseries_for(branch_id, product_id, days=365):
    """
    Returns daily units sold df with columns ['ds','y'].
    """
    since = timezone.now().date() - timedelta(days=days)
    qs = (
        SalesLine.objects
        .filter(product_id=product_id,
                header__branch_id=branch_id,
                header__created_at__date__gte=since)
        .values('header__created_at__date')
        .annotate(units=Sum('qty'))
        .order_by('header__created_at__date')
    )
    df = pd.DataFrame(list(qs))
    if df.empty:
        return pd.DataFrame(columns=["ds", "y"])
    df = df.rename(columns={"header__created_at__date": "ds", "units": "y"})
    # Ensure numeric float
    df["y"] = df["y"].astype(float)
    return df

def _seasonal_naive(df: pd.DataFrame, horizon_days=28, season=7):
    """
    Simple fast baseline: repeats last 'season' values.
    """
    from datetime import datetime
    if df.empty:
        return []
    df = df.sort_values("ds")
    hist = df["y"].values
    if len(hist) < 1:
        return []
    last_date = df["ds"].iloc[-1]
    preds = []
    for i in range(1, horizon_days + 1):
        yhat = hist[-season:][(i-1) % min(season, len(hist))]
        d = last_date + timedelta(days=i)
        preds.append({"ds": d, "yhat": float(yhat), "yhat_lower": float(max(0.0, yhat*0.8)), "yhat_upper": float(yhat*1.2)})
    return preds

def _prophet(df: pd.DataFrame, horizon_days=28):
    """
    Prophet model; if import fails, caller should fallback.
    """
    from prophet import Prophet
    m = Prophet(weekly_seasonality=True, yearly_seasonality=True)
    # m.add_country_holidays('IT')  # optional
    m.fit(df.rename(columns={"ds": "ds", "y": "y"}))
    future = m.make_future_dataframe(periods=horizon_days)
    fc = m.predict(future)[["ds", "yhat", "yhat_lower", "yhat_upper"]]
    return fc.tail(horizon_days).to_dict(orient="records")

def forecast_sku_branch(branch_id: int, product_id: int, horizon_days=28, prefer_prophet=True):
    df = _timeseries_for(branch_id, product_id)
    if df.empty or len(df) < 7:
        return [], "insufficient-history"

    if prefer_prophet:
        try:
            preds = _prophet(df, horizon_days=horizon_days)
            return preds, "prophet-v1"
        except Exception:
            pass  # fallback below

    preds = _seasonal_naive(df, horizon_days=horizon_days, season=7)
    return preds, "seasonal-naive-v1"

def persist_forecasts(branch_id, product_id, preds, model_version):
    saved = 0
    for r in preds:
        d = r["ds"].date() if hasattr(r["ds"], "date") else r["ds"]
        _, created = Forecast.objects.update_or_create(
            date=d,
            branch_id=branch_id,
            product_id=product_id,
            model_version=model_version,
            defaults={
                "yhat": float(r["yhat"]),
                "yhat_lower": float(r.get("yhat_lower", r["yhat"])),
                "yhat_upper": float(r.get("yhat_upper", r["yhat"])),
            },
        )
        saved += 1
    return saved