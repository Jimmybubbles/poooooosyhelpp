"""
Future Features — Ready to integrate into flask_app.py
=======================================================
Each section is self-contained. Instructions for wiring into the main app
are included as comments above each block.

1. Target Price Alert Emails
2. Weekly Performance Summary (auto after Friday scan)
3. Subscriber-Only Picks (paywall tier)
"""

# ══════════════════════════════════════════════════════════════════════════════
# 1. TARGET PRICE ALERT EMAILS
# ══════════════════════════════════════════════════════════════════════════════
#
# HOW TO WIRE IN:
#   - Set ALERT_EMAIL / SMTP settings in db_config.py (or as env vars)
#   - Call check_target_alerts() at the END of your daily price download job
#     (_run_download_job and _run_asx_download_job) after prices are saved.
#   - Install: pip install secure-smtplib  (or just use smtplib, already stdlib)
#
# In db_config.py add:
#   ALERT_EMAIL    = 'james@yourdomain.com'
#   SMTP_HOST      = 'smtp.gmail.com'
#   SMTP_PORT      = 587
#   SMTP_USER      = 'your@gmail.com'
#   SMTP_PASSWORD  = 'your-app-password'   # use Gmail App Password, not real password

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart


def send_email(subject, html_body, to_email, smtp_host, smtp_port, smtp_user, smtp_password):
    msg = MIMEMultipart('alternative')
    msg['Subject'] = subject
    msg['From']    = smtp_user
    msg['To']      = to_email
    msg.attach(MIMEText(html_body, 'html'))
    with smtplib.SMTP(smtp_host, smtp_port) as server:
        server.starttls()
        server.login(smtp_user, smtp_password)
        server.sendmail(smtp_user, to_email, msg.as_string())


def check_target_alerts(positions, currency='$', smtp_cfg=None):
    """
    Call after daily price download. Sends one email listing every open
    position that has reached or exceeded its target price.

    positions   — list of dicts from get_positions() or get_asx_picks()
    currency    — '$' for US, 'A$' for ASX
    smtp_cfg    — dict with keys: host, port, user, password, to_email
    """
    hits = [
        p for p in positions
        if p.get('target_price') and p['current_price'] >= p['target_price']
    ]
    if not hits or not smtp_cfg:
        return

    rows = ''.join(f"""
        <tr>
          <td style="padding:8px 12px;font-weight:700;color:#60a5fa">{p['ticker']}</td>
          <td style="padding:8px 12px">{currency}{p['current_price']:.4f}</td>
          <td style="padding:8px 12px;color:#22c55e">{currency}{p['target_price']:.4f}</td>
          <td style="padding:8px 12px;color:#22c55e">+{(p['current_price']-p['target_price'])/p['target_price']*100:.1f}%</td>
        </tr>""" for p in hits)

    html = f"""
    <div style="font-family:sans-serif;background:#0a0c14;color:#e0e0e0;padding:24px;border-radius:12px">
      <h2 style="color:#22c55e">Target Price Alert — {len(hits)} position{'s' if len(hits)>1 else ''} hit!</h2>
      <table style="border-collapse:collapse;width:100%">
        <tr style="color:#555;font-size:.85rem">
          <th style="text-align:left;padding:8px 12px">Ticker</th>
          <th style="text-align:left;padding:8px 12px">Current</th>
          <th style="text-align:left;padding:8px 12px">Target</th>
          <th style="text-align:left;padding:8px 12px">Over Target</th>
        </tr>
        {rows}
      </table>
      <p style="color:#555;font-size:.8rem;margin-top:16px">Jimmy's Stock Scanner — daily alert</p>
    </div>"""

    send_email(
        subject=f"Target Hit: {', '.join(p['ticker'] for p in hits)}",
        html_body=html,
        to_email=smtp_cfg['to_email'],
        smtp_host=smtp_cfg['host'],
        smtp_port=smtp_cfg['port'],
        smtp_user=smtp_cfg['user'],
        smtp_password=smtp_cfg['password'],
    )


# ══════════════════════════════════════════════════════════════════════════════
# 2. WEEKLY PERFORMANCE SUMMARY
# ══════════════════════════════════════════════════════════════════════════════
#
# HOW TO WIRE IN:
#   - At the end of _run_download_job(), after prices are saved, add:
#       from future_features import maybe_send_weekly_summary
#       maybe_send_weekly_summary(smtp_cfg)
#   - It checks if today is Friday — only fires once a week.
#   - Uses get_positions() + get_history() from db_picks so no new DB tables needed.

from datetime import datetime, timedelta


def maybe_send_weekly_summary(smtp_cfg, currency='$', mode='us'):
    """Only sends on Fridays. Call at end of daily scan job."""
    if datetime.now().weekday() != 4:   # 4 = Friday
        return

    if mode == 'us':
        from db_picks import get_positions, get_account, get_portfolio_value, get_history
        positions = get_positions()
        cash      = get_account()
    else:
        from db_asx import get_asx_picks, get_asx_account, get_asx_portfolio_value, get_asx_history
        positions = get_asx_picks()
        cash      = get_asx_account()
        get_history = get_asx_history

    port_val  = sum(p['value'] for p in positions)
    total_val = cash + port_val
    total_pnl = total_val - 100_000.0
    pnl_sign  = '+' if total_pnl >= 0 else ''
    pnl_color = '#22c55e' if total_pnl >= 0 else '#ef4444'

    # Best and worst position this week
    sorted_pos = sorted(positions, key=lambda p: p['pnl_pct'], reverse=True)
    best  = sorted_pos[0]  if sorted_pos else None
    worst = sorted_pos[-1] if len(sorted_pos) > 1 else None

    best_html  = f"<p>Best: <strong style='color:#22c55e'>{best['ticker']}</strong> {best['pnl_pct']:+.1f}%</p>"  if best  else ''
    worst_html = f"<p>Worst: <strong style='color:#ef4444'>{worst['ticker']}</strong> {worst['pnl_pct']:+.1f}%</p>" if worst else ''

    html = f"""
    <div style="font-family:sans-serif;background:#0a0c14;color:#e0e0e0;padding:24px;border-radius:12px">
      <h2 style="color:#60a5fa">Weekly Portfolio Summary</h2>
      <p style="font-size:1.4rem;font-weight:700;color:{pnl_color}">{pnl_sign}{currency}{total_pnl:,.2f} total P&L</p>
      <p>Portfolio value: <strong>{currency}{total_val:,.2f}</strong></p>
      <p>Open positions: <strong>{len(positions)}</strong></p>
      {best_html}
      {worst_html}
      <p style="color:#555;font-size:.8rem;margin-top:16px">Week ending {datetime.now().strftime('%d %b %Y')} — Jimmy's Stock Scanner</p>
    </div>"""

    send_email(
        subject=f"Weekly Summary: {pnl_sign}{currency}{total_pnl:,.2f}",
        html_body=html,
        to_email=smtp_cfg['to_email'],
        smtp_host=smtp_cfg['host'],
        smtp_port=smtp_cfg['port'],
        smtp_user=smtp_cfg['user'],
        smtp_password=smtp_cfg['password'],
    )


# ══════════════════════════════════════════════════════════════════════════════
# 3. SUBSCRIBER-ONLY PICKS (PAYWALL TIER)
# ══════════════════════════════════════════════════════════════════════════════
#
# HOW TO WIRE IN:
#   - Add a 'tier' column to ask_users table:
#       ALTER TABLE ask_users ADD COLUMN tier VARCHAR(20) DEFAULT 'free';
#   - Add a Stripe/payment webhook route that sets tier='pro' on payment success.
#   - In flask_app.py picks_page(), wrap position cards:
#       if is_pro_user() or is_admin():
#           [show full card with buy price, reason, chart]
#       else:
#           [show blurred/teaser card with upgrade prompt]
#   - Add the /upgrade route below to flask_app.py

# --- Add to db_ask.py ---

def set_user_tier(user_id, tier):
    """Set a user's subscription tier. tier = 'free' | 'pro'"""
    from db_ask import get_connection
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("UPDATE ask_users SET tier = %s WHERE id = %s", (tier, user_id))
        conn.commit()
    finally:
        conn.close()


def get_user_tier(user_id):
    """Returns 'free' or 'pro'."""
    from db_ask import get_connection
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute("SELECT tier FROM ask_users WHERE id = %s", (user_id,))
        row = cur.fetchone()
    conn.close()
    return row[0] if row else 'free'


# --- Add to flask_app.py ---

def is_pro_user():
    """Check if current session user has pro tier."""
    uid = session.get('user_id')
    if not uid:
        return False
    return get_user_tier(uid) == 'pro'


def picks_pro_teaser(ticker, bought_date):
    """Blurred card shown to free users instead of full pick details."""
    return f"""
    <div class="card" style="margin-bottom:16px;position:relative;overflow:hidden">
      <div style="filter:blur(4px);pointer-events:none;user-select:none">
        <div style="font-size:1.3rem;font-weight:700;color:#60a5fa">{ticker}</div>
        <div style="color:#555;font-size:.78rem">bought {bought_date}</div>
        <div style="margin-top:8px;color:#22c55e;font-size:1.1rem">+$███.██ (+██.█%)</div>
        <div style="margin-top:8px;font-size:.83rem;color:#aaa">Buy at $██.██ · Target $██.██ · ████ shares</div>
      </div>
      <div style="position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;
                  justify-content:center;background:rgba(10,12,20,0.7);border-radius:12px">
        <div style="font-size:.95rem;font-weight:700;color:#fff;margin-bottom:10px">Pro subscribers only</div>
        <a href="/upgrade" class="btn btn-green" style="padding:8px 20px">Upgrade to Pro</a>
      </div>
    </div>"""


# Upgrade page route — paste into flask_app.py
MONTHLY_PRICE = 29   # USD — change to whatever you want

def upgrade_page_html():
    """Simple upgrade/paywall page. Wire up Stripe payment link separately."""
    return f"""
    <div style="max-width:480px;margin:60px auto;text-align:center">
      <div class="card" style="padding:36px">
        <div style="font-size:2rem;margin-bottom:8px">Pro Membership</div>
        <div style="font-size:3rem;font-weight:800;color:#22c55e;margin-bottom:4px">${MONTHLY_PRICE}<span style="font-size:1rem;color:#555">/mo</span></div>
        <ul style="text-align:left;margin:20px 0;color:#aaa;line-height:2;list-style:none;padding:0">
          <li>✅ Full Jimmy's Picks — entry price, target, reason</li>
          <li>✅ ASX Picks portfolio</li>
          <li>✅ Daily P&L alerts</li>
          <li>✅ Ask Jimmy — unlimited questions</li>
          <li>✅ Range Level + Channel scanner results</li>
        </ul>
        <!-- Replace href with your Stripe payment link -->
        <a href="https://buy.stripe.com/YOUR_LINK" class="btn btn-green"
           style="display:block;padding:14px;font-size:1rem;text-align:center">
          Subscribe Now
        </a>
        <div style="color:#555;font-size:.78rem;margin-top:12px">Cancel anytime. Billed monthly.</div>
      </div>
    </div>"""
