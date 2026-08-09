# hft-async / netting

OrderSendAsync HFT scaffold. Submits orders without waiting for the
trade server, then reconciles each `request_id` inside
`OnTradeTransaction()`.

## v2 features

- **Async open + close** — `SendBuyAsync`, `SendSellAsync`,
  `SendCloseAsync(ticket)`, `CloseAllAsync(symbol)`
- **Auto filling mode** — detects FOK/IOC/RETURN per symbol
- **Stale cleanup** — `CleanupStale()` in OnTick removes timed-out pending
- **Retry on reject** — requote/reject auto-retry with fresh price
- **Partial fill** — tracks filled volume, retries remainder
- **Stats** — `PrintStats()` in OnDeinit logs latency + counters
- **O(1) removal** — swap-with-last for pending queue

**AP-18 contract:** every `OrderSendAsync()` site must be paired with an
`OnTradeTransaction()` handler. The kit enforces this via
`vibecodekit_mql5.lint` and via `vibecodekit_mql5.async_build` (which
only renders this scaffold; never the bare stdlib path).

Render via:

```bash
python -m vibecodekit_mql5.async_build \
    --name MyHftEA --symbol EURUSD --tf M1 --output ./out
```

Tester notes:
- Run on a *real* MetaTrader 5 build ≥ 4620 (Oct 2024). Older builds do
  not surface `MqlTradeTransaction.request_id`.
- `result.request_id` correlates the OrderSendAsync return value with the
  later `TRADE_TRANSACTION_REQUEST` callback — see
  `Include/CAsyncTradeManager.mqh`.
