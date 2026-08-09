// digits-tested: 5,4,3,2
// Generated from EA-IR 1a01be363f859c1526944a2dfbd4e64adfd8e1f7b7a280a48b512f5748b21a3c
#pragma once

enum VCKSignalMode { VCK_SIGNAL_NONE=0,VCK_SIGNAL_RSI,VCK_SIGNAL_RSI_REVERSAL,VCK_SIGNAL_CCI_REVERSAL,VCK_SIGNAL_STOCH_REVERSAL,VCK_SIGNAL_EMA_CROSS,VCK_SIGNAL_BB_REVERSION,VCK_SIGNAL_PINBAR,VCK_SIGNAL_ENGULFING,VCK_SIGNAL_PINBAR_ENGULFING,VCK_SIGNAL_MACD_CROSS,VCK_SIGNAL_MOMENTUM,VCK_SIGNAL_ATR_BREAKOUT,VCK_SIGNAL_SUPERTREND,VCK_SIGNAL_UTBOT,VCK_SIGNAL_ICHIMOKU_BREAK,VCK_SIGNAL_SMC_ALL_WITH,VCK_SIGNAL_SMC_ALL_AGAINST,VCK_SIGNAL_SMC_INTERNAL_WITH,VCK_SIGNAL_SMC_INTERNAL_AGAINST,VCK_SIGNAL_SMC_SWING_WITH,VCK_SIGNAL_SMC_SWING_AGAINST,VCK_SIGNAL_CANDLE_COLOR,VCK_SIGNAL_NO_CONDITION,VCK_SIGNAL_RANDOM,VCK_SIGNAL_EXTERNAL };
enum VCKDCAMode { VCK_DCA_STEP=0,VCK_DCA_STEP_TIMEFRAME,VCK_DCA_STEP_MULTIPLIER,VCK_DCA_SIGNAL,VCK_DCA_POSITIVE,VCK_DCA_BIDIRECTIONAL,VCK_DCA_SIGNAL_BIDIRECTIONAL,VCK_DCA_CLOSED_BAR };
enum VCKLotMode { VCK_LOT_MULTIPLY=0,VCK_LOT_ADD };
enum VCKTimeBasis { VCK_TIME_SERVER=0,VCK_TIME_LOCAL,VCK_TIME_UTC,VCK_TIME_FIXED_OFFSET };

input group "Identity and runtime"
sinput long InpMagic=915731;
sinput string InpTradeSymbol="XAUUSD";
sinput ENUM_TIMEFRAMES InpSignalTimeframe=PERIOD_M15;
sinput VCKSignalMode InpSignalMode=VCK_SIGNAL_ATR_BREAKOUT;
sinput VCKDCAMode InpDCAMode=VCK_DCA_STEP;
sinput int InpDCASwitchCount=0;
sinput VCKDCAMode InpDCASecondaryMode=VCK_DCA_STEP;
sinput bool InpAllowBuy=true;
sinput bool InpAllowSell=true;
sinput int InpMinSecondsBetweenEntries=2;
sinput int InpMinutesDelayAfterClear=0;
sinput bool InpAsyncExecution=false;
sinput int InpIntentUnknownTimeoutSeconds=30;
sinput int InpIntentHistoryLookbackSeconds=86400;

// Time and accounting policy sealed from EA-IR.
const VCKTimeBasis VCK_DAILY_TIME_BASIS=VCK_TIME_SERVER;
const VCKTimeBasis VCK_SESSION_TIME_BASIS=VCK_TIME_SERVER;
const int VCK_UTC_OFFSET_MINUTES=0;
const int VCK_DAY_BOUNDARY_MINUTES=0;
const bool VCK_HISTORY_SYNC_REQUIRED=false;
const bool VCK_EXCLUDE_CASHFLOWS=true;
const bool VCK_RECOVERY_OUTSIDE_SESSION=false;

input group "Execution and risk"
sinput double InpBaseLot=0.0100;
sinput double InpMaxLot=1.0000;
sinput double InpMaxSpreadPips=2.50;
sinput int InpMaxBuyPositions=4;
sinput int InpMaxSellPositions=4;
sinput int InpMaxLevelsBuy=4;
sinput int InpMaxLevelsSell=4;
sinput double InpFreezeDDPct=15.00;
sinput double InpMaxDDPct=20.00;
sinput int InpSLPips=0;
sinput int InpTPPips=0;
sinput double InpDailyTargetPct=0.00;
sinput double InpDailyLossPct=0.00;
sinput double InpDailyTargetMoney=0.00;
sinput double InpDailyLossMoney=0.00;
sinput int InpNewDayDelayMinutes=0;

input group "DCA and lot progression"
sinput double InpDCAStepPips=25.00;
sinput double InpDCAStepMultiplier=1.2000;
sinput VCKLotMode InpLotMode=VCK_LOT_MULTIPLY;
sinput double InpLotMultiplier=1.2000;
sinput double InpLotAdditive=0.0100;
sinput int InpTrendFilterAfterPositions=0;
sinput bool InpDCAOutsideSession=true;
sinput int InpLotStage1Count=0;
sinput double InpLotStage1Multiplier=1.0000;
sinput int InpLotStage2Count=0;
sinput double InpLotStage2Multiplier=1.0000;
sinput int InpLotStage3Count=0;
sinput double InpLotStage3Multiplier=1.0000;
sinput int InpLotStage4Count=0;
sinput double InpLotStage4Multiplier=1.0000;
sinput int InpLotStage5Count=0;
sinput double InpLotStage5Multiplier=1.0000;
sinput int InpDistanceStage1Count=0;
sinput double InpDistanceStage1Pips=0.00;
sinput int InpDistanceStage2Count=0;
sinput double InpDistanceStage2Pips=0.00;
sinput int InpDistanceStage3Count=0;
sinput double InpDistanceStage3Pips=0.00;
sinput int InpDistanceStage4Count=0;
sinput double InpDistanceStage4Pips=0.00;

input group "Basket, money exits and trailing"
sinput double InpBasketTargetMoney=0.00;
sinput double InpBasketStopMoney=0.00;
sinput double InpBasketTPPips=0.00;
sinput double InpAdaptiveTPLossPct=0.00;
sinput double InpAdaptiveTPLossMoney=0.00;
sinput double InpAdaptiveBasketTPPips=0.00;
sinput double InpAccountTPMoney=0.00;
sinput double InpAccountSLMoney=0.00;
sinput bool InpAllowAccountWideClose=false;
sinput double InpBuyTPMoney=0.00;
sinput double InpBuySLMoney=0.00;
sinput double InpSellTPMoney=0.00;
sinput double InpSellSLMoney=0.00;
sinput double InpSteppedTargetMoney=0.00;
sinput int InpSteppedTargetDelayMinutes=0;
sinput double InpBalanceDifferencePct=0.00;
sinput double InpTrailingStartPips=0.00;
sinput double InpTrailingDistancePips=0.00;

input group "Sniper and partial recovery"
sinput int InpSniperTriggerPositions=0;
sinput int InpSniperHeadCount=1;
sinput int InpSniperTailMaxCount=1;
sinput double InpSniperTargetMoney=0.00;
sinput double InpPartialClosePct=0.00;
sinput int InpCrossSniperTriggerPositions=0;
sinput double InpCrossSniperTargetMoney=0.00;
sinput bool InpCrossSniperMagicPairOnly=true;

input group "Hedge, hedge zone and balancing"
sinput int InpHedgeTriggerPositions=0;
sinput double InpHedgeTriggerLossPct=0.00;
sinput bool InpHedgeUseDCALot=false;
sinput double InpHedgeLotPct=0.00;
sinput double InpHedgeTPPips=0.00;
sinput double InpHedgeExitMoney=0.00;
sinput bool InpStopSniperDuringHedge=true;
sinput int InpHedgeZoneTriggerPositions=0;
sinput double InpHedgeZoneLotMultiplier=1.00;
sinput double InpHedgeZoneDistancePips=0.00;
sinput double InpHedgeZoneTargetMoney=0.00;
sinput double InpHedgeZoneTargetPips=0.00;
sinput int InpHedgeZoneNewTargetCount=0;
sinput double InpHedgeZoneNewTargetMoney=0.00;
sinput double InpHedgeZoneMaxLot=1.0000;
sinput int InpReverseTriggerPositions=0;
sinput double InpReverseLotPct=0.00;
sinput double InpReverseFixedLot=0.0000;
sinput double InpBalanceTriggerLots=0.0000;
sinput double InpBalanceStopLots=0.0000;
sinput double InpBalanceAddLot=0.0000;
sinput int InpBalanceDelaySeconds=30;

input group "Lottery after SL and manual reset"
sinput double InpLotterySLMultiplier=1.0000;
sinput int InpLotteryDelayMinutes=0;
sinput double InpLotteryResetLossMoney=0.00;
sinput double InpResetLot=0.0100;
sinput double InpResetMultiplier=1.0000;
sinput double InpResetBasketTPPips=0.00;

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
sinput double InpMinCandlePips=0.00;
sinput bool InpEngulfFullWick=true;
sinput int InpUnconditionalDirection=1;
sinput string InpExternalIndicator="";
sinput int InpExternalBuyBuffer=0;
sinput int InpExternalSellBuffer=1;

input group "Filters and zone cycle"
sinput bool InpUseEMAFilter=false;
sinput bool InpUseMACDFilter=false;
sinput bool InpUseRSIFilter=false;
sinput double InpEMAMaxPriceDistancePips=0.00;
sinput double InpEMAMinSeparationPips=0.00;
sinput double InpZoneCycleUpper=0.00000;
sinput double InpZoneCycleLower=0.00000;

input group "Trading sessions"
sinput bool InpSession1Enabled=false;
sinput string InpSession1Start="00:00";
sinput string InpSession1End="00:00";
sinput bool InpSession2Enabled=false;
sinput string InpSession2Start="00:00";
sinput string InpSession2End="00:00";
sinput bool InpSession3Enabled=false;
sinput string InpSession3Start="00:00";
sinput string InpSession3End="00:00";
sinput bool InpSession4Enabled=false;
sinput string InpSession4Start="00:00";
sinput string InpSession4End="00:00";

// Cross-feature semantic contracts (sealed from EA-IR).
const bool VCK_HEDGE_ZONE_EXCLUSIVE=true;
const bool VCK_HZ_ALLOW_HEDGE=false;
const bool VCK_HZ_ALLOW_REVERSE=false;
const bool VCK_HZ_ALLOW_BALANCE=false;
const bool VCK_SNIPER_PAUSE_HEDGE_ORIGIN_ONLY=true;
const bool VCK_ACCOUNT_WIDE_APPROVED=false;
const bool VCK_RECONCILE_BEFORE_RETRY=true;
const bool VCK_BLOCK_UNKNOWN_OUTCOME=true;

// Feature contract emitted by the capability plan.
// VCK-FEATURE:strategy.dca.enabled
const bool VCK_USE_DCA=false;
// VCK-FEATURE:strategy.dca.step_multiplier
const bool VCK_USE_STEP_MULTIPLIER=false;
// VCK-FEATURE:strategy.sizing.martingale
const bool VCK_USE_LOT_MULTIPLIER=false;
// VCK-FEATURE:strategy.sizing.additive
const bool VCK_USE_LOT_ADDITIVE=false;
// VCK-FEATURE:strategy.lottery.after_sl
const bool VCK_USE_LOTTERY=false;
// VCK-FEATURE:strategy.hedge.standard
const bool VCK_USE_HEDGE=false;
// VCK-FEATURE:strategy.hedge.zone
const bool VCK_USE_HEDGE_ZONE=false;
// VCK-FEATURE:strategy.reverse_entry
const bool VCK_USE_REVERSE_ENTRY=false;
// VCK-FEATURE:strategy.lot_balance
const bool VCK_USE_LOT_BALANCE=false;
// VCK-FEATURE:strategy.exit.basket_tp
const bool VCK_USE_BASKET_TP=false;
// VCK-FEATURE:strategy.exit.adaptive_basket_tp
const bool VCK_USE_ADAPTIVE_TP=false;
// VCK-FEATURE:strategy.exit.money
const bool VCK_USE_MONEY_EXIT=false;
// VCK-FEATURE:strategy.exit.account_money
const bool VCK_USE_ACCOUNT_MONEY_EXIT=false;
// VCK-FEATURE:strategy.exit.side_money
const bool VCK_USE_SIDE_MONEY_EXIT=false;
// VCK-FEATURE:strategy.exit.daily_target
const bool VCK_USE_DAILY_GUARD=false;
// VCK-FEATURE:strategy.exit.stepped_target
const bool VCK_USE_STEPPED_TARGET=false;
// VCK-FEATURE:strategy.exit.trailing
const bool VCK_USE_TRAILING=false;
// VCK-FEATURE:strategy.exit.trend_reversal
const bool VCK_USE_TREND_REVERSAL_EXIT=false;
// VCK-FEATURE:strategy.exit.balance_difference
const bool VCK_USE_BALANCE_DIFFERENCE_EXIT=false;
// VCK-FEATURE:strategy.sniper.same_chain
const bool VCK_USE_SNIPER=false;
// VCK-FEATURE:strategy.sniper.partial
const bool VCK_USE_PARTIAL_SNIPER=false;
// VCK-FEATURE:strategy.sniper.cross_chain
const bool VCK_USE_CROSS_SNIPER=false;
// VCK-FEATURE:strategy.time.sessions
const bool VCK_USE_SESSIONS=false;
// VCK-FEATURE:strategy.filter.zone_cycle
const bool VCK_USE_ZONE_CYCLE=false;
// VCK-FEATURE:controls.pending_order_remote
const bool VCK_USE_REMOTE=false;
// VCK-FEATURE:controls.chart_panel
const bool VCK_USE_PANEL=false;
// VCK-FEATURE:controls.reset_lots
const bool VCK_USE_RESET_LOTS=false;

// Complete planned feature trace markers.
// VCK-IMPLEMENTED:risk.max_lot
// VCK-IMPLEMENTED:risk.max_positions
// VCK-IMPLEMENTED:risk.max_spread
// VCK-IMPLEMENTED:strategy.entry.breakout
// VCK-IMPLEMENTED:strategy.entry.signals.atr_break
