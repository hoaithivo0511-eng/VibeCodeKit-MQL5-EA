"""Multilingual EA-domain ontology used by deterministic intake."""
from __future__ import annotations

# Component path -> expressions. Patterns are context-aware enough to avoid
# reducing e.g. "trend filter for DCA" to a trend-following strategy.
COMPONENT_PATTERNS: dict[str, tuple[str, ...]] = {
    "strategy.entry.signal_selectable": (
        r"nhiều tín hiệu", r"đa dạng tín hiệu", r"selectable signals?",
        r"chọn tín hiệu\s+mở lệnh",
    ),
    "strategy.entry.trend_following": (
        r"\btrend[\s-]?follow(?:ing)?\b", r"chiến lược\s+bám\s+xu hướng",
    ),
    "strategy.entry.mean_reversion": (
        r"mean[\s-]?revers", r"hồi quy về trung bình", r"đảo chiều về trung bình",
    ),
    "strategy.entry.breakout": (r"\bbreak[\s-]?out\b", r"phá vỡ"),
    "strategy.dca.enabled": (r"\bdca\b", r"nhồi lệnh", r"trung bình giá"),
    "strategy.dca.step": (
        r"\bDCA\s+Step\b(?!\s+Multiplier)",
        r"(?:DCA|nhồi lệnh)[^\n]{0,80}khoảng cách cố định",
    ),
    "strategy.dca.step_timeframe": (r"Step\s*\+\s*TF", r"mỗi nến nhồi"),
    "strategy.dca.step_multiplier": (r"Step\s+Multiplier", r"khoảng cách nhân dần"),
    "strategy.dca.signal": (r"Signal\s+DCA", r"nhồi theo tín hiệu"),
    "strategy.dca.positive": (r"nhồi dương",),
    "strategy.dca.bidirectional": (r"nhồi âm dương",),
    "strategy.dca.closed_bar": (r"Step\s*\+\s*Đóng nến", r"step\s*\+\s*closed bar"),
    "strategy.sizing.martingale": (r"martingale", r"hệ số nhân.*lots", r"nhân lots"),
    "strategy.sizing.additive": (r"hệ số cộng", r"additive lot"),
    "strategy.sniper.same_chain": (r"tỉa lệnh cùng chuỗi", r"same[\s-]?chain sniper"),
    "strategy.sniper.cross_chain": (r"tỉa lệnh khác chuỗi", r"cross[\s-]?chain sniper"),
    "strategy.sniper.partial": (r"tỉa lệnh 1 phần", r"partial sniper"),
    "strategy.hedge.standard": (r"hedging \(phòng hộ thường\)", r"sử dụng hedging", r"standard hedge"),
    "strategy.hedge.zone": (r"hedging zone", r"vùng phòng hộ"),
    "strategy.reverse_entry": (r"mở lệnh ngược chiều", r"reverse entry"),
    "strategy.lot_balance": (r"cân lots", r"lot balancing"),
    "strategy.lottery.after_sl": (
        r"chế độ xổ số", r"martingale kiểu [\"']?xổ số", r"lottery after SL",
    ),
    "strategy.exit.basket_tp": (r"TP chuỗi", r"basket TP", r"chốt tổng"),
    "strategy.exit.money": (r"Money TP", r"Money SL", r"đóng lệnh.*\$"),
    "strategy.exit.daily_target": (r"target lợi nhuận ngày", r"daily target"),
    "strategy.exit.trailing": (r"\btrailing\b", r"trailing stop"),
    "strategy.exit.single_tp": (r"TP đơn lệnh", r"single TP"),
    "strategy.exit.adaptive_basket_tp": (r"điều chỉnh TP chuỗi khi âm", r"adaptive basket TP"),
    "strategy.exit.account_money": (
        r"Money TP All account", r"Money SL All account", r"account-wide money exit",
    ),
    "strategy.exit.side_money": (
        r"Money TP Buy", r"Money SL Buy", r"Money TP Sell", r"Money SL Sell",
        r"side money exit",
    ),
    "strategy.exit.stepped_target": (r"mục tiêu lợi nhuận bậc thang", r"stepped profit target"),
    "strategy.exit.trend_reversal": (r"đóng lệnh khi đảo trend", r"close on trend reversal"),
    "strategy.exit.balance_difference": (
        r"% lãi/lỗ giữa buy và sell", r"buy.*sell.*close all", r"side profit difference",
    ),
    "strategy.time.sessions": (r"giới hạn thời gian", r"khung giờ giao dịch", r"trading sessions?"),
    "strategy.filter.trend": (r"bộ lọc xu hướng", r"trend filter"),
    "strategy.filter.ema": (
        r"(?:bộ lọc|filter)[^\n]{0,100}\bEMA\b",
        r"\bEMA\b[^\n]{0,100}(?:bộ lọc|filter)",
    ),
    "strategy.filter.macd": (
        r"(?:bộ lọc|filter)[^\n]{0,100}\bMACD\b",
        r"\bMACD\b[^\n]{0,100}(?:bộ lọc|filter)",
    ),
    "strategy.filter.zone_cycle": (r"Zone Cycle", r"bộ lọc vùng giá"),
    "strategy.filter.rsi": (
        r"(?:bộ lọc|filter)[^\n]{0,100}\bRSI\b",
        r"\bRSI\b[^\n]{0,100}(?:bộ lọc|filter)",
    ),
    "controls.pending_order_remote": (r"Mobile Control", r"lệnh chờ điều khiển", r"pending order.*control"),
    "controls.chart_panel": (r"nút bấm.*biểu đồ", r"chart buttons?", r"chart panel"),
    "controls.new_cycle": (r"New Cycle",),
    "controls.reset_lots": (r"Reset lots", r"reset lots chuỗi"),
    "risk.max_spread": (r"spread tối đa", r"max spread"),
    "risk.max_lot": (r"lots? tối đa", r"max lots?"),
    "risk.max_positions": (r"số lệnh .* tối đa", r"max .* positions?"),
    "risk.daily_loss": (r"daily loss", r"lỗ.*ngày", r"thua lỗ.*ngày"),
}

SIGNAL_PATTERNS: dict[str, tuple[str, ...]] = {
    # More specific variants appear before their base indicator so the IR can
    # preserve the operator-visible menu without collapsing distinct modes.
    "cci_reversal": (r"CCI Reverse", r"CCI Reversal"),
    "stochastic_reversal": (r"Stoch Reverse", r"Stochastic Reversal"),
    "rsi_reversal": (r"RSI Reversal",),
    "pinbar_engulfing": (r"Pinbar\s*/\s*Engulfing", r"Pinbar[^\n]{0,30}Engulfing"),
    "candle_color": (r"Xanh đỏ", r"2 nến xanh/đỏ", r"two candle colo(?:u)?r"),
    "no_condition": (r"Không điều kiện", r"no condition"),
    "random": (r"\bRandom\b", r"ngẫu nhiên"),
    "external_indicator": (r"Indi ngoài", r"Indicator ngoài", r"external indicator"),
    "smc_all_with": (r"SMC All thuận",),
    "smc_all_against": (r"SMC All ngược",),
    "smc_internal_with": (r"SMC Internal thuận",),
    "smc_internal_against": (r"SMC Internal[^\n]{0,30}ngược",),
    "smc_swing_with": (r"SMC Swing thuận",),
    "smc_swing_against": (r"SMC Swing[^\n]{0,30}ngược",),
    "cci": (r"\bCCI\b",),
    "stochastic": (r"\bStoch(?:astic)?\b",),
    "momentum": (r"\bMomentum\b",),
    "supertrend": (r"\bSupertrend\b",),
    "utbot": (r"\bUTBOT\b", r"\bUT Bot\b"),
    "rsi": (r"\bRSI\b",),
    "ichimoku_kumo_break": (r"Break Kumo", r"Ichimoku break"),
    "smc": (r"\bSMC\b(?!\s+(?:All|Internal|Swing))", r"smart money concept"),
    "bollinger_bands": (r"\bBB\b", r"Bollinger"),
    "pinbar": (r"Pinbar", r"Pin Bar"),
    "engulfing": (r"Engulfing",),
    # MACD and EMA are frequently filters. Bare names are intentionally not
    # accepted as entry signals; an explicit signal/cross context is required.
    "macd": (r"MACD[\s-]?(?:cross|signal)", r"tín hiệu[^\n]{0,30}\bMACD\b"),
    "ema_cross": (r"EMA[\s-]?cross", r"MA[\s-]?cross"),
    "atr_break": (r"ATR[\s-]?break",),
}

TERM_ALIASES: dict[str, str] = {
    "nhồi lệnh": "dca",
    "nhồi dương": "dca_positive",
    "nhồi âm dương": "dca_bidirectional",
    "tỉa lệnh": "sniper",
    "cân lots": "lot_balancing",
    "mở lệnh ngược chiều": "reverse_entry",
    "phòng hộ": "hedging",
    "vùng phòng hộ": "hedge_zone",
    "chuỗi lệnh": "position_cycle",
}
