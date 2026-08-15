# Pradeep Momentum Burst Screener

A Python live screener for the Indian (NSE) market implementing the
**pattern-based momentum-burst strategy** taught in a Stockbee-methodology
trading bootcamp (referred to in this repo as "the webinar"). It scans the
Nifty 500 on a schedule, finds stocks matching four specific chart/volume
patterns, and pushes them to Telegram — nothing more. It does **not** place
orders, size positions, or manage exits for you; those decisions stay with
the trader, using the rules documented below.

> **Not financial advice.** This is a personal screening tool built from
> one trader's teaching material. Past patterns matching does not mean a
> trade will work. Use your own judgment, risk only what you can afford to
> lose, and treat every signal here as a candidate to research, not an
> instruction to buy.

---

## Table of contents

1. [What it screens for](#what-it-screens-for)
2. [Quick start](#quick-start)
3. [How to use the signals properly](#how-to-use-the-signals-properly)
4. [Exit logic — per the webinar](#exit-logic--per-the-webinar)
5. [Telegram bot](#telegram-bot)
6. [Output files](#output-files)
7. [Architecture](#architecture)
8. [Universe](#universe)
9. [Known approximations](#known-approximations)

---

## What it screens for

The webinar's core idea: stocks move in short, sharp **momentum bursts** —
3-5 day moves of roughly 8-20% — driven by informed buyers moving first and
"follower" traders piling in over the next few days. Four setups catch this
pattern at different points:

| # | Setup | What it looks like | Typical hold |
|---|---|---|---|
| 1 | **Bottom Bounce** | A stock at a multi-month low suddenly reverses hard on a range-expansion day, while the broad market itself is oversold. | 3-5 days (sometimes longer) |
| 2 | **Consolidation Breakout** | A stock that already rallied goes sideways for weeks/months, then breaks out on a huge volume spike (3x+ average). | Several days to weeks |
| 3 | **Continuation ("2Lynch")** | The bread-and-butter setup: a first leg up, a brief 3-7 day pullback that doesn't give back much, then another breakout. | 3-5 days |
| 4 | **Anticipation** | Advanced/pre-emptive: a stock with an established uptrend goes very quiet (±0.4% day) — entering *before* the breakout, betting it goes the next session. | 3-5 days, or a same/next-day scratch |

All four are **long-only** — no shorting, since Zerodha and other Indian
brokers don't allow overnight short-selling in the cash segment. Two other
setups from the same strategy (Weak Structure Short, Parabolic Short) are
short-only and out of scope here; a third (Episodic Pivot / EP-9-Million)
needs fundamentals and news data, not price/volume, so it's also out of
scope for a pure OHLCV screener.

---

## Quick start

```bash
git clone <this repo>
cd Pradeep-Momentum-Burst-Screener
pip install -r requirements.txt

# Optional but recommended: get results pushed to Telegram — see below.
cp .env.example .env
# ... fill in TELEGRAM_BOT_TOKEN / ADMIN_USER_ID in .env ...

python run_scheduler.py
```

That's it — `run_scheduler.py` handles everything else: waiting for market
open if you start it early, scanning all four setups every 15 minutes
during the trading session, and (if Telegram is configured) staying
reachable so you can ask it questions at any time. See
[Telegram bot](#telegram-bot) and [Output files](#output-files) for where
results actually land.

If you'd rather run it by hand instead of leaving a process running:

```bash
# Every setup, once, right now
python run_all_live_screens.py

# Or one setup at a time (all still write to the same output file)
python -m Algorithms.bottom_bounce.live_screen
python -m Algorithms.consolidation_breakout.live_screen
python -m Algorithms.continuation.live_screen
python -m Algorithms.anticipation.live_screen
```

---

## How to use the signals properly

### Reading a row

Every hit — whether in `output/live_signals.csv` or a Telegram push — has:

| field | meaning |
|---|---|
| `setup` | which of the 4 patterns matched |
| `symbol` | NSE symbol |
| `trigger_date` | the **daily bar** whose close satisfied the setup's rules |
| `trigger_close` | that bar's closing price |
| `note` | when/how to enter, specific to that setup (see below) |
| `times_seen` | how many scans today still found this stock matching (CSV only — see [Output files](#output-files)) |

A signal is not a price target and not a guaranteed mover — it means *the
stock's daily bar satisfies the mechanical pattern rules right now*. You
still look at the chart before acting.

### Entry timing, per setup

The webinar's governing rule for entry across all four setups:
**whichever qualifying setup you see first, you act on it — no comparing
multiple candidates and waiting for the "best" one.** Speed matters more
than optimizing the choice.

- **Bottom Bounce / Consolidation Breakout / Continuation** — enter as
  close to the trigger as possible: same-day, as early as you can confirm
  it, or the next session's open if you're checking after close. A next-day
  entry is a real (if smaller) degradation of the edge — don't chase it
  past day 2.
- **Anticipation** — this one is different by design: you're meant to enter
  **before** the breakout confirms, in the last 30-40 minutes of the
  session the "quiet day" itself shows up (~2:50-3:30 PM IST). If you only
  see the signal after that day has closed, the setup has already passed —
  treat it as informational, not an entry cue. If the very next session
  doesn't make a new high above the trigger day's high, the standard
  response is to scratch (exit for a small loss/breakeven) immediately, not
  wait around hoping.

### Position sizing

Per the webinar's own rules (not something this screener enforces):

- Normal trade: **10-25% of trading capital** per position, 20% is the
  number used most often.
- Never risk more than **~2.5% of total capital across everything you're
  holding at once** — this is what ties position size to the stop-loss
  percentage below.
- The "reverse pyramiding" technique (sizing up to 80-100% on your
  highest-conviction Continuation setups, then selling 80% once up 8-10%
  and letting the rest run risk-free) is explicitly described as an
  **advanced, experienced-traders-only** technique — not a starting point.

### Setup-specific things worth knowing

- **Bottom Bounce** only fires when the *broader market* is oversold (this
  screener's own T2108-equivalent breadth calculation — see
  [Architecture](#architecture)) — so it will often produce nothing for
  long stretches. That's expected, not a bug: the webinar itself says "if
  you only trade Bottom Bounce, you'll wait 2-3 years between real
  opportunities."
- **Consolidation Breakout**'s defining ingredient is the volume spike, not
  a clean-looking base — a messy consolidation can still qualify if the
  breakout volume is big enough.
- **Continuation** is the setup you should expect to see most often, and
  the one the webinar calls its true bread-and-butter. Ideally you're
  catching the 2nd or 3rd leg of a move, not the 1st (unproven) or the
  4th/5th (statistically weaker) — this screener does not attempt to count
  legs (see [Known approximations](#known-approximations)), so use your own
  eyes on the chart before entering.
- **Anticipation** is explicitly **not a beginner setup** — learn the other
  three first. It also should only be used in a rising market (this
  screener enforces that with its own bull-regime breadth gate) and never
  on low-priced/thin stocks, since the whole edge depends on a very tight
  stop that only makes sense when a stock's daily range is already small.

---

## Exit logic — per the webinar

**This screener does not manage exits for you.** It is deliberately
scope-limited to entry detection (see [Architecture](#architecture)) — once
a symbol shows up, everything from here is manual, using the rules below,
which are the webinar's own stated exit framework, not this project's
invention.

### The shared exit framework (Bottom Bounce, Consolidation Breakout, Continuation)

The webinar explicitly treats these three setups as sharing **one** exit
framework, not three separate ones:

1. **Stop-loss: 2.5% below entry**, occasionally up to 4% max — 2.5% is
   described as correct "95% of the time." An alternative method: half of
   the trigger day's own price range (e.g. a ₹30 high-low range → stop ₹15
   below your entry).
2. **3-day time-stop**: if the trade hasn't moved meaningfully in your
   favor within 3 trading days, close it — even if the stop-loss hasn't
   been hit. The whole thesis is an *immediate* follow-through; a stock
   that's just sitting there has invalidated that thesis.
3. **5-day maximum hold**: exit by day 5 regardless, or at your profit
   target, whichever comes first.
4. **Profit protection once up ~8%** — and this is the part most traders
   get wrong: **do NOT simply move your stop to breakeven.** The webinar
   calls that a classic beginner mistake, because it means you'd give back
   the *entire* gain on a small pullback. Instead: decide how much of the
   *current* profit you're willing to give back (a simple starting rule —
   once up 8%, protect so your worst case becomes roughly +6%, not
   breakeven), and keep sliding that protective floor up as the trade
   extends further. Give more room in a strong market, protect tighter in
   a choppy one.
5. **Target range: 8-20%** over the typical 3-5 day hold for these three
   setups. There's no single fixed take-profit price — the profit-ratchet
   rule above is how you actually let a winner run without giving it all
   back.

### Anticipation's exit (different, and much tighter)

Because Anticipation enters *before* the breakout confirms, its risk
management is deliberately different from the other three:

1. **Very tight stop** — often well under 0.5% risk, since the whole
   trigger day's range was already tiny by definition of the setup.
2. **Scratch immediately if there's no follow-through**: if the position
   doesn't break out within the first 5-20 minutes of the next session,
   exit for a small loss/scratch right away — don't wait around hoping it
   turns into something.
3. Once a genuine breakout does confirm, manage the rest of the trade like
   a normal Continuation trade — same +8% profit-protection idea as above.

### Summary table

| Setup(s) | Stop | Time-stop | Max hold | Target |
|---|---|---|---|---|
| Bottom Bounce, Consolidation Breakout, Continuation | 2.5% (up to 4%) | 3 days, no meaningful move | 5 days | 8-20% |
| Anticipation | <0.5%, or scratch next session | — | 3-5 days once confirmed | 8-20% once confirmed |

---

## Telegram bot

Send results straight to Telegram instead of watching a terminal. Same
access-control model as this project's sibling `PROJECT_TRADE_BOT` — one
admin id, an optional allowlist, admin-managed via bot commands.

**Setup:**

1. Create a bot via [@BotFather](https://t.me/BotFather), copy the token.
2. Get your numeric Telegram user id from [@userinfobot](https://t.me/userinfobot).
3. Copy `.env.example` to `.env`, fill in `TELEGRAM_BOT_TOKEN` and
   `ADMIN_USER_ID` (and optionally `ALLOWED_USER_IDS`, comma-separated —
   leave blank and the bot is open to anyone who finds it).
4. `python run_scheduler.py`.

**What it does:**

- **Live progress** — while any scan runs (scheduled or `/run_now`), you
  get a message that's edited in place with fetch/scan progress, then a
  "Scan complete" summary.
- **Automatic push, once per stock per day** — the first time a
  (setup, symbol) pair matches, you get a message with the symbol, setup
  name, and note. If it keeps matching on later scans the same day, it's
  **not** re-sent — the CSV's `times_seen` still counts it, but you only
  get notified once.
- **`/next_schedule`** — when the next scan runs.
- **`/today_signals`** — sends today's `live_signals.csv` as a file.
- **`/run_now`** — trigger a scan immediately, outside the 15-minute
  schedule. Always replies, even with "no signals right now."
- **`/admin_add <user_id>` / `/admin_remove <user_id>` / `/admin_list`**
  (admin only) — manage who else can use the bot.

Leave `TELEGRAM_BOT_TOKEN` blank and none of this activates —
`run_scheduler.py` falls back to a plain loop with no Telegram calls,
running once from whenever you start it until market close.

---

## Output files

Everything lands in `output/` (gitignored — regenerate by running the
screener):

- **`live_signals.csv`** — every setup writes into this **one** file.
  Re-running through the day does not duplicate a row for a stock still
  matching — it bumps `times_seen` and refreshes the trigger/close/time
  fields instead.
- **`archive/live_signals_<date>.csv`** — the previous day's file, moved
  here automatically the first time you run the screener on a new calendar
  day (lazy — happens on your next run, not on a schedule of its own).
- **`scheduler.log`** — a structured record of every run (fetch counts,
  hits per setup, timing, warnings).

---

## Architecture

- Each setup is one entry-detection module, `Algorithms/<setup>/signals.py`
  — a pure function over one symbol's OHLCV returning True/False per day.
- Each `Algorithms/<setup>/runner.py` exposes `scan(universe_ohlcv)` (pure —
  no fetching) separately from `run_live_screen()` (fetch + scan + merge,
  for running that one setup standalone). `run_all_live_screens.py` fetches
  the whole universe **once** via `common/universe_data.py` and calls all 4
  `scan()` functions against that same fetched data — no per-setup
  re-fetching when running all 4 together.
- `common/signal_store.py` owns the single consolidated CSV: merging new
  hits, incrementing `times_seen`, and the day-rollover archive.
- `common/breadth.py` computes a T2108-equivalent (% of the universe above
  its 40-day MA) plus advance/decline breadth directly from the universe's
  own OHLCV — no external breadth feed needed:
  - **Bottom Bounce**: an oversold gate (`pct_above_ma < 20`, confirmed by
    a rolling share of the universe actively declining).
  - **Anticipation**: the opposite-direction "only in a bull market" gate
    (`pct_above_ma >= 50`).
- `data_fetcher/` (Moneycontrol + yfinance NSE/BSE fallback) and
  `notifications/` (optional SMTP alert) are shared utility modules;
  credentials are read from `.env` only, no hardcoded fallback values.
- Progress: fetching Nifty 500 and scanning it takes tens of seconds, so
  every run shows a live tqdm progress bar in the terminal, and — if
  Telegram is configured — the same progress mirrored into a chat message
  that gets edited in place.

## Universe

All 4 setups scan **Nifty 500** (`input/NIFTY500.csv`), NSE's own published
index-constituent list. Re-download periodically — index membership changes
at each periodic NSE reshuffle. (`input/NIFTY200.csv` is also included,
unused by default — Bottom Bounce originally used it as a narrower
"quality index" restriction per the source material, dropped in favor of
one shared fetch across all 4 setups.)

## Known approximations

By design, not oversights:

- **Continuation leg-counting** (2nd/3rd leg vs. 4th/5th) is explicitly
  called visual/manual in the source material. This screener mechanizes the
  parts that ARE precisely quantified (leg size, persistence, pullback
  discipline, breakout-day quality) and does not attempt to count legs —
  use your own chart read for that part.
- **Anticipation's "skip pending buyout/merger targets"** rule is a
  news-based judgment call, not something OHLCV can detect.
- A "trigger" fires when a setup's conditions are true on the **most
  recent completed daily bar**. Run the screener after each session's close
  for a settled read, or intraday for an early (not-yet-final) read of
  today's still-forming bar.
