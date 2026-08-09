EA `{spec.name}` (scaffold **portfolio-basket / hedging**) là **starter scaffold** portfolio-basket cho tài khoản **hedging**
(có thể đồng thời Buy + Sell cùng symbol — phù hợp broker US-regulated NFA
hoặc broker hỗ trợ hedge mode rõ ràng).

Khác `portfolio-basket/netting`: mỗi position là 1 ticket riêng, không
netting. Cho phép strategy mở hedge protective (vd long EURUSD + short
GBPUSD cùng lúc; hoặc long EURUSD 0.1 lot + short EURUSD 0.05 lot làm
partial hedge).

Scaffold cung cấp infrastructure (CPipNormalizer, CRiskGuard, CMagicRegistry,
CSafeTradeManager) và **CỐ Ý CHƯA** chứa logic mở lệnh — dev fill in
theo basket strategy.

---

## Giai đoạn 1 — OnInit

Giống `portfolio-basket/netting`:

1. `pip.Init(_Symbol)` — pip math cho symbol gốc.
2. `risk.Init(InpDailyLossPct, InpMaxPositions, 0.10)` — DD cap
   {spec.risk.daily_loss_pct:pct} + {InpMaxPositions} lệnh đồng thời.
3. `registry.Reserve(InpMagic, "{spec.name}")` — magic chung cho basket.

**Khác biệt hedging:** dev có thể cần check broker hedge mode bằng
`AccountInfoInteger(ACCOUNT_MARGIN_MODE) == ACCOUNT_MARGIN_MODE_RETAIL_HEDGING`
ở OnInit; nếu là netting → cảnh báo / từ chối.

---

## Giai đoạn 2 — OnTick (chạy mỗi tick)

Skeleton mặc định:

```
┌─────────────────────────────────────────────────────────┐
│ 1. risk.OnTick() │
├─────────────────────────────────────────────────────────┤
│ 2. if !risk.CanOpenNewPosition() → return │
├─────────────────────────────────────────────────────────┤
│ 3. sl = pip.Pips(InpSlPips) │
│ lot = pip.LotForRisk(InpRiskMoney, InpSlPips) │
│ if lot ≤ 0 → log + return │
├─────────────────────────────────────────────────────────┤
│ 4. [DEV FILL] Compute basket signal │
├─────────────────────────────────────────────────────────┤
│ 5. [DEV FILL] Place orders │
│ Hedging riêng biệt mỗi leg là 1 ticket độc lập. │
│ Có thể đồng thời mở Buy + Sell cùng symbol. │
└─────────────────────────────────────────────────────────┘
```

---

## Patterns hedging đặc thù

### Pattern A — Pairs trade (long A / short B)

```
if cointegration_zscore > +threshold:
    trade.Sell(lot_A, symbol_A, ...)
    trade.Buy (lot_B, symbol_B, ...)
if cointegration_zscore < -threshold:
    trade.Buy (lot_A, ...)
    trade.Sell(lot_B, ...)
```

- 2 leg ngược chiều, ticket riêng → exit độc lập.

### Pattern B — Partial hedge (delta neutralize)

```
existing_long = 0.1 lot EURUSD
hedge_short = 0.05 lot EURUSD // partial hedge khi sự kiện rủi ro
trade.Sell(0.05, "EURUSD", ...)
```

- Cùng symbol, ngược chiều — chỉ hedging account cho phép.

### Pattern C — Multi-symbol portfolio (8 G10 pairs)

```
For each pair in G10_pairs:
    direction = signal[pair]
    lot = lot_for_pair(pair, weights[pair])
    if direction == BUY: trade.Buy(lot, pair, ...)
    if direction == SELL: trade.Sell(lot, pair, ...)
```

---

## Tính toán phối hợp input (đặc thù hedging)

```
┌──────────────────────────────────────────────────────────┐
│ Margin requirement │
│ ┌────────────────────────────────────────────────────┐ │
│ │ Hedge mode: margin = max(margin_long, margin_short)│ │
│ │ (KHÔNG net như netting account) │ │
│ │ Nhân lot up → margin tăng ngay, không offset. │ │
│ └────────────────────────────────────────────────────┘ │
│ │ │
│ ▼ │
│ InpMaxPositions thực sự đếm ticket │
│ ┌────────────────────────────────────────────────────┐ │
│ │ Hedge có 2 ticket long + 2 ticket short cùng │ │
│ │ symbol = 4 positions, không 0 net. │ │
│ │ Đặt InpMaxPositions = 2× số leg dự kiến. │ │
│ └────────────────────────────────────────────────────┘ │
│ │ │
│ ▼ │
│ InpRiskMoney áp dụng cho NET exposure │
│ ┌────────────────────────────────────────────────────┐ │
│ │ Nếu hedge offset 50% → effective risk ~ 50% of │ │
│ │ InpRiskMoney. Tính toán per-leg theo NET delta. │ │
│ └────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────┘
```

**Quy tắc tune hedging:**

- `InpMaxPositions` PHẢI cao gấp đôi vs basket netting cùng size, do mỗi
  hedge leg = 1 ticket riêng (không gộp như netting).
- Tổng margin cần cẩn thận — hedge mode KHÔNG offset margin như netting.
  Đặt margin level safe threshold (default 0.10 = 10%) đủ cao.

---

## Setup khuyến nghị

| Loại basket | Tham số đề xuất |
|---|---|
| Pairs trade 2-leg | `InpRiskMoney`=20, `InpMaxPositions`=4 (2 long + 2 short tối đa) |
| 8 G10 pairs (1-direction mỗi pair) | `InpRiskMoney`=80, `InpMaxPositions`=8 |
| Delta-neutral 4-leg | `InpRiskMoney`=40, `InpMaxPositions`=8 |

Trước live:
1. Verify broker là hedging-mode (`AccountInfoInteger(ACCOUNT_MARGIN_MODE)`).
2. Backtest với hedge-aware tester (`/Mode = "Every tick based on real ticks"`).
3. Stress test margin: account 1000 USD + 8 leg đồng thời với leverage 1:100
   → margin > 80 USD per leg, kiểm tra account còn buffer.
