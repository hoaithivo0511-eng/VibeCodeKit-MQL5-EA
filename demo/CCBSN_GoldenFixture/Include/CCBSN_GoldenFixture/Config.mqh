// digits-tested: 5,4,3,2
// Generated from EA-IR 940e5167d1b0b65655caefe1e2644896da6c2e67b6a4ed02bd3c25dce2dd2a5b
#pragma once

enum VCKSignalMode { VCK_SIGNAL_NONE=0,VCK_SIGNAL_RSI,VCK_SIGNAL_RSI_REVERSAL,VCK_SIGNAL_CCI_REVERSAL,VCK_SIGNAL_STOCH_REVERSAL,VCK_SIGNAL_EMA_CROSS,VCK_SIGNAL_BB_REVERSION,VCK_SIGNAL_PINBAR,VCK_SIGNAL_ENGULFING,VCK_SIGNAL_PINBAR_ENGULFING,VCK_SIGNAL_MACD_CROSS,VCK_SIGNAL_MOMENTUM,VCK_SIGNAL_ATR_BREAKOUT,VCK_SIGNAL_SUPERTREND,VCK_SIGNAL_UTBOT,VCK_SIGNAL_ICHIMOKU_BREAK,VCK_SIGNAL_SMC_ALL_WITH,VCK_SIGNAL_SMC_ALL_AGAINST,VCK_SIGNAL_SMC_INTERNAL_WITH,VCK_SIGNAL_SMC_INTERNAL_AGAINST,VCK_SIGNAL_SMC_SWING_WITH,VCK_SIGNAL_SMC_SWING_AGAINST,VCK_SIGNAL_CANDLE_COLOR,VCK_SIGNAL_NO_CONDITION,VCK_SIGNAL_RANDOM,VCK_SIGNAL_EXTERNAL };
enum VCKDCAMode { VCK_DCA_STEP=0,VCK_DCA_STEP_TIMEFRAME,VCK_DCA_STEP_MULTIPLIER,VCK_DCA_SIGNAL,VCK_DCA_POSITIVE,VCK_DCA_BIDIRECTIONAL,VCK_DCA_SIGNAL_BIDIRECTIONAL,VCK_DCA_CLOSED_BAR };
enum VCKLotMode { VCK_LOT_MULTIPLY=0,VCK_LOT_ADD };
enum VCKTimeBasis { VCK_TIME_SERVER=0,VCK_TIME_LOCAL,VCK_TIME_UTC,VCK_TIME_FIXED_OFFSET };

input group "Identity and runtime"
sinput long InpMagic=929475;
sinput string InpTradeSymbol="";
sinput ENUM_TIMEFRAMES InpSignalTimeframe=PERIOD_CURRENT;
sinput VCKSignalMode InpSignalMode=VCK_SIGNAL_CCI_REVERSAL;
sinput VCKDCAMode InpDCAMode=VCK_DCA_STEP_MULTIPLIER;
sinput int InpDCASwitchCount=10;
sinput VCKDCAMode InpDCASecondaryMode=VCK_DCA_SIGNAL;
sinput bool InpAllowBuy=true;
sinput bool InpAllowSell=true;
sinput int InpMinSecondsBetweenEntries=2;
sinput int InpMinutesDelayAfterClear=5;
sinput bool InpAsyncExecution=false;
sinput int InpIntentUnknownTimeoutSeconds=30;
sinput int InpIntentHistoryLookbackSeconds=86400;

// Time and accounting policy sealed from EA-IR.
const VCKTimeBasis VCK_DAILY_TIME_BASIS=VCK_TIME_SERVER;
const VCKTimeBasis VCK_SESSION_TIME_BASIS=VCK_TIME_SERVER;
const int VCK_UTC_OFFSET_MINUTES=0;
const int VCK_DAY_BOUNDARY_MINUTES=0;
const bool VCK_HISTORY_SYNC_REQUIRED=true;
const bool VCK_EXCLUDE_CASHFLOWS=true;
const bool VCK_RECOVERY_OUTSIDE_SESSION=true;

input group "Execution and risk"
sinput double InpBaseLot=0.0100;
sinput double InpMaxLot=1.0000;
sinput double InpMaxSpreadPips=3.00;
sinput int InpMaxBuyPositions=50;
sinput int InpMaxSellPositions=50;
sinput int InpMaxLevelsBuy=50;
sinput int InpMaxLevelsSell=50;
sinput double InpFreezeDDPct=15.00;
sinput double InpMaxDDPct=20.00;
sinput int InpSLPips=100;
sinput int InpTPPips=20;
sinput double InpDailyTargetPct=2.00;
sinput double InpDailyLossPct=5.00;
sinput double InpDailyTargetMoney=0.00;
sinput double InpDailyLossMoney=-500.00;
sinput int InpNewDayDelayMinutes=30;

input group "DCA and lot progression"
sinput double InpDCAStepPips=25.00;
sinput double InpDCAStepMultiplier=1.2000;
sinput VCKLotMode InpLotMode=VCK_LOT_MULTIPLY;
sinput double InpLotMultiplier=1.2000;
sinput double InpLotAdditive=0.0100;
sinput int InpTrendFilterAfterPositions=3;
sinput bool InpDCAOutsideSession=true;
sinput int InpLotStage1Count=10;
sinput double InpLotStage1Multiplier=1.2000;
sinput int InpLotStage2Count=20;
sinput double InpLotStage2Multiplier=1.1000;
sinput int InpLotStage3Count=30;
sinput double InpLotStage3Multiplier=1.0500;
sinput int InpLotStage4Count=40;
sinput double InpLotStage4Multiplier=1.0600;
sinput int InpLotStage5Count=50;
sinput double InpLotStage5Multiplier=1.0300;
sinput int InpDistanceStage1Count=10;
sinput double InpDistanceStage1Pips=35.00;
sinput int InpDistanceStage2Count=20;
sinput double InpDistanceStage2Pips=50.00;
sinput int InpDistanceStage3Count=30;
sinput double InpDistanceStage3Pips=70.00;
sinput int InpDistanceStage4Count=40;
sinput double InpDistanceStage4Pips=100.00;

input group "Basket, money exits and trailing"
sinput double InpBasketTargetMoney=20.00;
sinput double InpBasketStopMoney=-1000.00;
sinput double InpBasketTPPips=10.00;
sinput double InpAdaptiveTPLossPct=-20.00;
sinput double InpAdaptiveTPLossMoney=-12000.00;
sinput double InpAdaptiveBasketTPPips=3.00;
sinput double InpAccountTPMoney=500.00;
sinput double InpAccountSLMoney=-1000.00;
sinput bool InpAllowAccountWideClose=false;
sinput double InpBuyTPMoney=100.00;
sinput double InpBuySLMoney=-500.00;
sinput double InpSellTPMoney=100.00;
sinput double InpSellSLMoney=-500.00;
sinput double InpSteppedTargetMoney=200.00;
sinput int InpSteppedTargetDelayMinutes=30;
sinput double InpBalanceDifferencePct=2.00;
sinput double InpTrailingStartPips=20.00;
sinput double InpTrailingDistancePips=10.00;

input group "Sniper and partial recovery"
sinput int InpSniperTriggerPositions=5;
sinput int InpSniperHeadCount=1;
sinput int InpSniperTailMaxCount=2;
sinput double InpSniperTargetMoney=1.00;
sinput double InpPartialClosePct=30.00;
sinput int InpCrossSniperTriggerPositions=8;
sinput double InpCrossSniperTargetMoney=2.00;
sinput bool InpCrossSniperMagicPairOnly=true;

input group "Hedge, hedge zone and balancing"
sinput int InpHedgeTriggerPositions=12;
sinput double InpHedgeTriggerLossPct=-25.00;
sinput bool InpHedgeUseDCALot=false;
sinput double InpHedgeLotPct=50.00;
sinput double InpHedgeTPPips=10.00;
sinput double InpHedgeExitMoney=10.00;
sinput bool InpStopSniperDuringHedge=true;
sinput int InpHedgeZoneTriggerPositions=15;
sinput double InpHedgeZoneLotMultiplier=1.00;
sinput double InpHedgeZoneDistancePips=30.00;
sinput double InpHedgeZoneTargetMoney=20.00;
sinput double InpHedgeZoneTargetPips=5.00;
sinput int InpHedgeZoneNewTargetCount=25;
sinput double InpHedgeZoneNewTargetMoney=10.00;
sinput double InpHedgeZoneMaxLot=1.0000;
sinput int InpReverseTriggerPositions=12;
sinput double InpReverseLotPct=25.00;
sinput double InpReverseFixedLot=0.0100;
sinput double InpBalanceTriggerLots=0.2000;
sinput double InpBalanceStopLots=0.0500;
sinput double InpBalanceAddLot=0.0100;
sinput int InpBalanceDelaySeconds=30;

input group "Lottery after SL and manual reset"
sinput double InpLotterySLMultiplier=1.5000;
sinput int InpLotteryDelayMinutes=5;
sinput double InpLotteryResetLossMoney=-1000.00;
sinput double InpResetLot=0.0100;
sinput double InpResetMultiplier=1.0000;
sinput double InpResetBasketTPPips=10.00;

input group "Signal parameters"
sinput int InpRSIPeriod=14;
sinput double InpRSIOversold=25.00;
sinput double InpRSIOverbought=75.00;
sinput int InpCCIPeriod=14;
sinput double InpCCIOversold=-100.00;
sinput double InpCCIOverbought=100.00;
sinput int InpStochK=5;
sinput int InpStochD=3;
sinput int InpStochSlowing=3;
sinput int InpMomentumPeriod=14;
sinput double InpMomentumBuyLevel=100.45;
sinput double InpMomentumSellLevel=99.45;
sinput int InpEMAFast=34;
sinput int InpEMASlow=89;
sinput int InpBBPeriod=20;
sinput double InpBBDeviation=2.00;
sinput int InpATRPeriod=10;
sinput double InpATRBreakMultiplier=1.00;
sinput int InpSupertrendPeriod=21;
sinput double InpSupertrendMultiplier=3.00;
sinput int InpUTBotPeriod=10;
sinput double InpUTBotSensitivity=1.00;
sinput int InpIchimokuTenkan=9;
sinput int InpIchimokuKijun=26;
sinput int InpIchimokuSenkou=52;
sinput int InpSMCInternalLookback=5;
sinput int InpSMCSwingLookback=20;
sinput double InpPinbarWickRatio=5.00;
sinput double InpPinbarOppositeRatio=6.00;
sinput double InpMinCandlePips=5.00;
sinput bool InpEngulfFullWick=true;
sinput int InpUnconditionalDirection=1;
sinput string InpExternalIndicator="";
sinput int InpExternalBuyBuffer=0;
sinput int InpExternalSellBuffer=1;

input group "Filters and zone cycle"
sinput bool InpUseEMAFilter=true;
sinput bool InpUseMACDFilter=true;
sinput bool InpUseRSIFilter=true;
sinput double InpEMAMaxPriceDistancePips=0.00;
sinput double InpEMAMinSeparationPips=0.00;
sinput double InpZoneCycleUpper=999999.00000;
sinput double InpZoneCycleLower=0.00001;

input group "Trading sessions"
sinput bool InpSession1Enabled=true;
sinput string InpSession1Start="00:00";
sinput string InpSession1End="23:59";
sinput bool InpSession2Enabled=false;
sinput string InpSession2Start="00:00";
sinput string InpSession2End="00:00";
sinput bool InpSession3Enabled=false;
sinput string InpSession3Start="00:00";
sinput string InpSession3End="00:00";
sinput bool InpSession4Enabled=false;
sinput string InpSession4Start="00:00";
sinput string InpSession4End="00:00";

input group "Remote controls"
sinput double InpCmd_DISABLE_NEW_CYCLE=888888.00000000;
const ENUM_ORDER_TYPE VCK_CMD_DISABLE_NEW_CYCLE_TYPE=ORDER_TYPE_BUY_STOP;
sinput double InpCmd_ENABLE_NEW_CYCLE=888888.00000000;
const ENUM_ORDER_TYPE VCK_CMD_ENABLE_NEW_CYCLE_TYPE=ORDER_TYPE_SELL_LIMIT;
sinput double InpCmd_START_EA=666666.00000000;
const ENUM_ORDER_TYPE VCK_CMD_START_EA_TYPE=ORDER_TYPE_BUY_STOP;
sinput double InpCmd_STOP_BUY=555555.00000000;
const ENUM_ORDER_TYPE VCK_CMD_STOP_BUY_TYPE=ORDER_TYPE_BUY_STOP;
sinput double InpCmd_STOP_EA=999999.00000000;
const ENUM_ORDER_TYPE VCK_CMD_STOP_EA_TYPE=ORDER_TYPE_BUY_STOP;
sinput double InpCmd_STOP_SELL=555555.00000000;
const ENUM_ORDER_TYPE VCK_CMD_STOP_SELL_TYPE=ORDER_TYPE_SELL_LIMIT;

// Cross-feature semantic contracts (sealed from EA-IR).
const bool VCK_HEDGE_ZONE_EXCLUSIVE=true;
const bool VCK_HZ_ALLOW_HEDGE=false;
const bool VCK_HZ_ALLOW_REVERSE=false;
const bool VCK_HZ_ALLOW_BALANCE=false;
const bool VCK_SNIPER_PAUSE_HEDGE_ORIGIN_ONLY=true;
const bool VCK_ACCOUNT_WIDE_APPROVED=true;
const bool VCK_RECONCILE_BEFORE_RETRY=true;
const bool VCK_BLOCK_UNKNOWN_OUTCOME=true;

// Feature contract emitted by the capability plan.
// VCK-FEATURE:strategy.dca.enabled
const bool VCK_USE_DCA=true;
// VCK-FEATURE:strategy.dca.step_multiplier
const bool VCK_USE_STEP_MULTIPLIER=true;
// VCK-FEATURE:strategy.sizing.martingale
const bool VCK_USE_LOT_MULTIPLIER=true;
// VCK-FEATURE:strategy.sizing.additive
const bool VCK_USE_LOT_ADDITIVE=true;
// VCK-FEATURE:strategy.lottery.after_sl
const bool VCK_USE_LOTTERY=true;
// VCK-FEATURE:strategy.hedge.standard
const bool VCK_USE_HEDGE=true;
// VCK-FEATURE:strategy.hedge.zone
const bool VCK_USE_HEDGE_ZONE=true;
// VCK-FEATURE:strategy.reverse_entry
const bool VCK_USE_REVERSE_ENTRY=true;
// VCK-FEATURE:strategy.lot_balance
const bool VCK_USE_LOT_BALANCE=true;
// VCK-FEATURE:strategy.exit.basket_tp
const bool VCK_USE_BASKET_TP=true;
// VCK-FEATURE:strategy.exit.adaptive_basket_tp
const bool VCK_USE_ADAPTIVE_TP=true;
// VCK-FEATURE:strategy.exit.money
const bool VCK_USE_MONEY_EXIT=true;
// VCK-FEATURE:strategy.exit.account_money
const bool VCK_USE_ACCOUNT_MONEY_EXIT=true;
// VCK-FEATURE:strategy.exit.side_money
const bool VCK_USE_SIDE_MONEY_EXIT=true;
// VCK-FEATURE:strategy.exit.daily_target
const bool VCK_USE_DAILY_GUARD=true;
// VCK-FEATURE:strategy.exit.stepped_target
const bool VCK_USE_STEPPED_TARGET=true;
// VCK-FEATURE:strategy.exit.trailing
const bool VCK_USE_TRAILING=true;
// VCK-FEATURE:strategy.exit.trend_reversal
const bool VCK_USE_TREND_REVERSAL_EXIT=true;
// VCK-FEATURE:strategy.exit.balance_difference
const bool VCK_USE_BALANCE_DIFFERENCE_EXIT=true;
// VCK-FEATURE:strategy.sniper.same_chain
const bool VCK_USE_SNIPER=true;
// VCK-FEATURE:strategy.sniper.partial
const bool VCK_USE_PARTIAL_SNIPER=true;
// VCK-FEATURE:strategy.sniper.cross_chain
const bool VCK_USE_CROSS_SNIPER=true;
// VCK-FEATURE:strategy.time.sessions
const bool VCK_USE_SESSIONS=true;
// VCK-FEATURE:strategy.filter.zone_cycle
const bool VCK_USE_ZONE_CYCLE=true;
// VCK-FEATURE:controls.pending_order_remote
const bool VCK_USE_REMOTE=true;
// VCK-FEATURE:controls.chart_panel
const bool VCK_USE_PANEL=true;
// VCK-FEATURE:controls.reset_lots
const bool VCK_USE_RESET_LOTS=true;

// Complete planned feature trace markers.
// VCK-IMPLEMENTED:controls.chart_panel
// VCK-IMPLEMENTED:controls.new_cycle
// VCK-IMPLEMENTED:controls.pending_order_remote
// VCK-IMPLEMENTED:controls.reset_lots
// VCK-IMPLEMENTED:risk.daily_loss
// VCK-IMPLEMENTED:risk.max_lot
// VCK-IMPLEMENTED:risk.max_positions
// VCK-IMPLEMENTED:risk.max_spread
// VCK-IMPLEMENTED:strategy.dca.bidirectional
// VCK-IMPLEMENTED:strategy.dca.closed_bar
// VCK-IMPLEMENTED:strategy.dca.enabled
// VCK-IMPLEMENTED:strategy.dca.positive
// VCK-IMPLEMENTED:strategy.dca.signal
// VCK-IMPLEMENTED:strategy.dca.step
// VCK-IMPLEMENTED:strategy.dca.step_multiplier
// VCK-IMPLEMENTED:strategy.dca.step_timeframe
// VCK-IMPLEMENTED:strategy.entry.signal_selectable
// VCK-IMPLEMENTED:strategy.entry.signals.bollinger_bands
// VCK-IMPLEMENTED:strategy.entry.signals.candle_color
// VCK-IMPLEMENTED:strategy.entry.signals.cci
// VCK-IMPLEMENTED:strategy.entry.signals.cci_reversal
// VCK-IMPLEMENTED:strategy.entry.signals.engulfing
// VCK-IMPLEMENTED:strategy.entry.signals.external_indicator
// VCK-IMPLEMENTED:strategy.entry.signals.ichimoku_kumo_break
// VCK-IMPLEMENTED:strategy.entry.signals.momentum
// VCK-IMPLEMENTED:strategy.entry.signals.no_condition
// VCK-IMPLEMENTED:strategy.entry.signals.pinbar
// VCK-IMPLEMENTED:strategy.entry.signals.pinbar_engulfing
// VCK-IMPLEMENTED:strategy.entry.signals.random
// VCK-IMPLEMENTED:strategy.entry.signals.rsi
// VCK-IMPLEMENTED:strategy.entry.signals.rsi_reversal
// VCK-IMPLEMENTED:strategy.entry.signals.smc
// VCK-IMPLEMENTED:strategy.entry.signals.smc_all_against
// VCK-IMPLEMENTED:strategy.entry.signals.smc_all_with
// VCK-IMPLEMENTED:strategy.entry.signals.smc_internal_against
// VCK-IMPLEMENTED:strategy.entry.signals.smc_internal_with
// VCK-IMPLEMENTED:strategy.entry.signals.smc_swing_against
// VCK-IMPLEMENTED:strategy.entry.signals.smc_swing_with
// VCK-IMPLEMENTED:strategy.entry.signals.stochastic
// VCK-IMPLEMENTED:strategy.entry.signals.stochastic_reversal
// VCK-IMPLEMENTED:strategy.entry.signals.supertrend
// VCK-IMPLEMENTED:strategy.entry.signals.utbot
// VCK-IMPLEMENTED:strategy.exit.account_money
// VCK-IMPLEMENTED:strategy.exit.adaptive_basket_tp
// VCK-IMPLEMENTED:strategy.exit.balance_difference
// VCK-IMPLEMENTED:strategy.exit.basket_tp
// VCK-IMPLEMENTED:strategy.exit.daily_target
// VCK-IMPLEMENTED:strategy.exit.money
// VCK-IMPLEMENTED:strategy.exit.side_money
// VCK-IMPLEMENTED:strategy.exit.single_tp
// VCK-IMPLEMENTED:strategy.exit.stepped_target
// VCK-IMPLEMENTED:strategy.exit.trailing
// VCK-IMPLEMENTED:strategy.exit.trend_reversal
// VCK-IMPLEMENTED:strategy.filter.ema
// VCK-IMPLEMENTED:strategy.filter.macd
// VCK-IMPLEMENTED:strategy.filter.rsi
// VCK-IMPLEMENTED:strategy.filter.trend
// VCK-IMPLEMENTED:strategy.filter.zone_cycle
// VCK-IMPLEMENTED:strategy.hedge.standard
// VCK-IMPLEMENTED:strategy.hedge.zone
// VCK-IMPLEMENTED:strategy.lot_balance
// VCK-IMPLEMENTED:strategy.lottery.after_sl
// VCK-IMPLEMENTED:strategy.reverse_entry
// VCK-IMPLEMENTED:strategy.sizing.additive
// VCK-IMPLEMENTED:strategy.sizing.martingale
// VCK-IMPLEMENTED:strategy.sniper.cross_chain
// VCK-IMPLEMENTED:strategy.sniper.partial
// VCK-IMPLEMENTED:strategy.sniper.same_chain
// VCK-IMPLEMENTED:strategy.time.sessions
