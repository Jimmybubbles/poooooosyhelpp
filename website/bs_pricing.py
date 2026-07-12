"""
Black-Scholes option pricing — shared by the Options 101 demo page and the
dummy Options Picks paper-trading portfolio. Educational only: no dividend
yield, flat assumed volatility, no real options market data feed.
"""

import math


def _norm_cdf(x):
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _norm_pdf(x):
    return math.exp(-0.5 * x * x) / math.sqrt(2.0 * math.pi)


def bs_price_greeks(spot, strike, t_years, vol, r, kind='call'):
    """Black-Scholes price + delta/gamma/theta/vega for a European option (no dividend)."""
    if t_years <= 0 or vol <= 0:
        intrinsic = max(spot - strike, 0.0) if kind == 'call' else max(strike - spot, 0.0)
        delta = (1.0 if spot > strike else 0.0) if kind == 'call' else (-1.0 if spot < strike else 0.0)
        return {'price': intrinsic, 'delta': delta, 'gamma': 0.0, 'theta': 0.0, 'vega': 0.0}

    sqrt_t = math.sqrt(t_years)
    d1 = (math.log(spot / strike) + (r + 0.5 * vol * vol) * t_years) / (vol * sqrt_t)
    d2 = d1 - vol * sqrt_t

    if kind == 'call':
        price = spot * _norm_cdf(d1) - strike * math.exp(-r * t_years) * _norm_cdf(d2)
        delta = _norm_cdf(d1)
        theta = (-(spot * _norm_pdf(d1) * vol) / (2 * sqrt_t)
                 - r * strike * math.exp(-r * t_years) * _norm_cdf(d2)) / 365.0
    else:
        price = strike * math.exp(-r * t_years) * _norm_cdf(-d2) - spot * _norm_cdf(-d1)
        delta = _norm_cdf(d1) - 1.0
        theta = (-(spot * _norm_pdf(d1) * vol) / (2 * sqrt_t)
                 + r * strike * math.exp(-r * t_years) * _norm_cdf(-d2)) / 365.0

    gamma = _norm_pdf(d1) / (spot * vol * sqrt_t)
    vega = spot * _norm_pdf(d1) * sqrt_t / 100.0

    return {'price': price, 'delta': delta, 'gamma': gamma, 'theta': theta, 'vega': vega}


def assumed_iv_for_price(price):
    """Cheaper/smaller stocks tend to run hotter implied vol than mega-caps."""
    if price >= 60:
        return 0.35
    if price >= 25:
        return 0.45
    return 0.60


SKEW_K = 2.5          # how fast IV rises per unit of moneyness distance
MAX_EFFECTIVE_IV = 2.0  # hard cap so extremely deep strikes don't blow up


def effective_iv(base_iv, spot, strike):
    """
    Approximate volatility skew. A flat IV badly underprices strikes far from
    the money — real option chains price deep OTM/ITM strikes at meaningfully
    higher implied vol than an at-the-money base assumption (this is why a
    strike 25% out of the money still trades for a few cents days before
    expiry instead of pricing to ~$0 under a flat-vol model). This is a rough
    linear approximation of that skew, not a real chain's actual curve.
    """
    if not spot:
        return base_iv
    moneyness = abs(strike - spot) / spot
    return min(base_iv + SKEW_K * moneyness, MAX_EFFECTIVE_IV)


def strike_increment_for_price(price):
    """Real chains list tighter strike spacing on cheaper stocks."""
    if price < 10:
        return 0.5
    if price < 25:
        return 1.0
    if price < 50:
        return 2.5
    return 5.0
