# {{NAME}} — wizard-composable / netting

Single-position netting EA scaffold. Suitable for FxPro, IC, and most
non-US brokers (account_type = NETTING).

## Wiring

- `CPipNormalizer pip` — cross-broker pip math (truth table per digits)
- `CRiskGuard risk` — daily-loss + max-positions enforcement
- `CMagicRegistry registry` — magic reservation across kit

## Next steps

1. Fill in the strategy in `OnTick` (signal → `CTrade.Buy/Sell`).
2. Run `mql5-lint {{NAME}}.mq5` — must clear 8 critical AP.
3. Run `mql5-compile {{NAME}}.mq5` — must compile 0 errors.
