// digits-tested: 5,4,3,2
//+------------------------------------------------------------------+
//| CCBSN_GoldenFixture.mq5 | EA-IR 940e5167d1b0b65655caefe1e2644896da6c2e67b6a4ed02bd3c25dce2dd2a5b
//+------------------------------------------------------------------+
#property strict
#property version "3.30"
#include <CCBSN_GoldenFixture/Config.mqh>
#include <CCBSN_GoldenFixture/Core/AsyncTradeExecutor.mqh>
#include <CCBSN_GoldenFixture/Core/PositionBook.mqh>
#include <CCBSN_GoldenFixture/Core/TradeEventReducer.mqh>
#include <CCBSN_GoldenFixture/Signal/EntryEngine.mqh>
#include <CCBSN_GoldenFixture/Risk/GridRiskGuard.mqh>
#include <CCBSN_GoldenFixture/Exit/BasketCloseEngine.mqh>
#include <CCBSN_GoldenFixture/State/PersistentStateStore.mqh>
#include <CCBSN_GoldenFixture/Telemetry/StructuredLogger.mqh>
#include <CCBSN_GoldenFixture/Telemetry/MfeMaeLogger.mqh>
enum VCKLifecycleState { VCK_IDLE,VCK_ACTIVE_CYCLE,VCK_DCA_ACTIVE,VCK_HEDGE_ACTIVE,VCK_HEDGE_ZONE_ACTIVE,VCK_CLOSING,VCK_COOLDOWN,VCK_STOPPED };
enum VCKExposureSource { VCK_SRC_ENTRY,VCK_SRC_DCA,VCK_SRC_HEDGE,VCK_SRC_HEDGE_ZONE,VCK_SRC_REVERSE,VCK_SRC_BALANCE };
enum VCKZonePhase { VCK_ZONE_IDLE,VCK_ZONE_ACTIVE,VCK_ZONE_EXITING,VCK_ZONE_RECONCILING };
CAsyncTradeExecutor Trade; CTradeEventReducer EventReducer; CVCKPositionBook Book; CVCKEntryEngine Entry; CGridRiskGuard GridRisk; CBasketCloseEngine Basket; CPersistentStateStore StateStore; CStructuredLogger Log; CMfeMaeLogger MfeMae;
VCKLifecycleState g_state=VCK_IDLE; int g_zone_phase=VCK_ZONE_IDLE; string g_symbol=""; double g_pip=0; bool g_ea_enabled=true,g_new_cycle=true,g_stop_buy=false,g_stop_sell=false,g_hedge_zone=false,g_daily_history_ready=true; datetime g_last_entry=0,g_last_balance=0,g_last_clear=0,g_last_dca_bar=0,g_cooldown_until=0; double g_lottery_factor=1,g_buy_reset_lot=0,g_sell_reset_lot=0,g_zone_low=0,g_zone_high=0,g_day_start_balance=0,g_persisted_peak=0; int g_daily_halt_day=0,g_balance_day=0,g_zone_cycle_id=0,g_history_sync_confirmations=0; ulong g_zone_anchor_position_id=0;
const string VCKP_PREFIX="VCKP_"; bool g_close_armed=false; datetime g_close_armed_at=0;
void PersistState(){StateStore.Save(g_ea_enabled,g_new_cycle,g_stop_buy,g_stop_sell,g_lottery_factor);StateStore.SaveExtended(g_daily_halt_day,g_balance_day,g_day_start_balance,GridRisk.Peak(),g_hedge_zone,g_zone_phase,g_zone_cycle_id,g_zone_anchor_position_id,g_zone_low,g_zone_high,g_cooldown_until);}

double PipSize(){int d=(int)SymbolInfoInteger(g_symbol,SYMBOL_DIGITS);double p=SymbolInfoDouble(g_symbol,SYMBOL_POINT);return(d==3||d==5)?p*10:p;}
datetime ClockNow(const VCKTimeBasis basis){if(basis==VCK_TIME_LOCAL)return TimeLocal();if(basis==VCK_TIME_UTC)return TimeGMT();if(basis==VCK_TIME_FIXED_OFFSET)return TimeGMT()+VCK_UTC_OFFSET_MINUTES*60;return TimeCurrent();}
int DayKey(datetime when){MqlDateTime x;TimeToStruct(when,x);return x.year*10000+x.mon*100+x.day;}
datetime TradingDayStart(){datetime shifted=ClockNow(VCK_DAILY_TIME_BASIS)-VCK_DAY_BOUNDARY_MINUTES*60;MqlDateTime x;TimeToStruct(shifted,x);x.hour=0;x.min=0;x.sec=0;return StructToTime(x)+VCK_DAY_BOUNDARY_MINUTES*60;}
int CurrentTradingDayKey(){return DayKey(ClockNow(VCK_DAILY_TIME_BASIS)-VCK_DAY_BOUNDARY_MINUTES*60);}
bool EntryDelayPassed(){return g_last_entry==0||TimeCurrent()-g_last_entry>=InpMinSecondsBetweenEntries;}
bool NewBar(datetime &last){datetime t=iTime(g_symbol,InpSignalTimeframe,0);if(t==0||t==last)return false;last=t;return true;}
int HHMM(const string value){int p=StringFind(value,":");if(p<0)return -1;return (int)StringToInteger(StringSubstr(value,0,p))*60+(int)StringToInteger(StringSubstr(value,p+1));}
bool InWindow(const string start,const string finish){MqlDateTime x;TimeToStruct(ClockNow(VCK_SESSION_TIME_BASIS),x);int n=x.hour*60+x.min,a=HHMM(start),b=HHMM(finish);if(a<0||b<0)return false;if(a==b)return true;return a<b?(n>=a&&n<=b):(n>=a||n<=b);}
bool SessionAllowed(){if(!VCK_USE_SESSIONS)return true;return(InpSession1Enabled&&InWindow(InpSession1Start,InpSession1End))||(InpSession2Enabled&&InWindow(InpSession2Start,InpSession2End))||(InpSession3Enabled&&InWindow(InpSession3Start,InpSession3End))||(InpSession4Enabled&&InWindow(InpSession4Start,InpSession4End));}

double StageMultiplier(const int count){double m=InpLotMultiplier;if(InpLotStage1Count>0&&count>=InpLotStage1Count)m=InpLotStage1Multiplier;if(InpLotStage2Count>0&&count>=InpLotStage2Count)m=InpLotStage2Multiplier;if(InpLotStage3Count>0&&count>=InpLotStage3Count)m=InpLotStage3Multiplier;if(InpLotStage4Count>0&&count>=InpLotStage4Count)m=InpLotStage4Multiplier;if(InpLotStage5Count>0&&count>=InpLotStage5Count)m=InpLotStage5Multiplier;return m;}
double StageDistance(const int count){double p=InpDCAStepPips;if(InpDistanceStage1Count>0&&count>=InpDistanceStage1Count)p=InpDistanceStage1Pips;if(InpDistanceStage2Count>0&&count>=InpDistanceStage2Count)p=InpDistanceStage2Pips;if(InpDistanceStage3Count>0&&count>=InpDistanceStage3Count)p=InpDistanceStage3Pips;if(InpDistanceStage4Count>0&&count>=InpDistanceStage4Count)p=InpDistanceStage4Pips;return p;}
double NextLot(const int direction,const int count){double base=direction>0&&g_buy_reset_lot>0?g_buy_reset_lot:(direction<0&&g_sell_reset_lot>0?g_sell_reset_lot:InpBaseLot),lot=base;if(InpLotMode==VCK_LOT_MULTIPLY){double mult=((direction>0&&g_buy_reset_lot>0)||(direction<0&&g_sell_reset_lot>0))?InpResetMultiplier:StageMultiplier(count);lot=base*MathPow(mult,count);}else lot=base+InpLotAdditive*count;lot*=g_lottery_factor;return Trade.NormalizeVolume(g_symbol,lot,InpMaxLot);}
VCKDCAMode ActiveDCAMode(const int count){return InpDCASwitchCount>0&&count>=InpDCASwitchCount?InpDCASecondaryMode:InpDCAMode;}
double RequiredDistance(const int count){double p=StageDistance(count);if(ActiveDCAMode(count)==VCK_DCA_STEP_MULTIPLIER)p*=MathPow(InpDCAStepMultiplier,MathMax(count-1,0));return p*g_pip;}
bool SpreadAllowed(){MqlTick t;return SymbolInfoTick(g_symbol,t)&&(t.ask-t.bid)/g_pip<=InpMaxSpreadPips;}

bool ComputeDaySnapshot(const long magic_filter,double &trading_pnl,double &cashflow,double &day_start_balance){trading_pnl=0;cashflow=0;day_start_balance=0;if(!TerminalInfoInteger(TERMINAL_CONNECTED))return false;datetime from=TradingDayStart(),now=ClockNow(VCK_DAILY_TIME_BASIS);if(!HistorySelect(from,now))return false;double account_trading=0;for(int i=0;i<HistoryDealsTotal();i++){ulong d=HistoryDealGetTicket(i);if(d==0)continue;ENUM_DEAL_TYPE type=(ENUM_DEAL_TYPE)HistoryDealGetInteger(d,DEAL_TYPE);long magic=(long)HistoryDealGetInteger(d,DEAL_MAGIC);double value=HistoryDealGetDouble(d,DEAL_PROFIT)+HistoryDealGetDouble(d,DEAL_SWAP)+HistoryDealGetDouble(d,DEAL_COMMISSION);if(type==DEAL_TYPE_BUY||type==DEAL_TYPE_SELL){account_trading+=value;if(magic_filter<0||magic==magic_filter)trading_pnl+=value;}else cashflow+=value;}day_start_balance=AccountInfoDouble(ACCOUNT_BALANCE)-account_trading-cashflow;return true;}
double ClosedProfitToday(const long magic_filter){double trading=0,cashflow=0,baseline=0;if(!ComputeDaySnapshot(magic_filter,trading,cashflow,baseline))return 0;return trading+(VCK_EXCLUDE_CASHFLOWS?0:cashflow);}
double AccountFloating(){double x=0;for(int i=0;i<PositionsTotal();i++){ulong t=PositionGetTicket(i);if(t>0&&PositionSelectByTicket(t))x+=PositionGetDouble(POSITION_PROFIT)+PositionGetDouble(POSITION_SWAP);}return x;}

int LiveDirectionCount(const int d){VCKSideStats s;Book.Collect(g_symbol,InpMagic,d>0?POSITION_TYPE_BUY:POSITION_TYPE_SELL,s);return s.count;}
bool HedgeZoneAllowsSource(const VCKExposureSource source){if(source==VCK_SRC_HEDGE_ZONE)return true;if(VCK_HEDGE_ZONE_EXCLUSIVE)return false;if(source==VCK_SRC_HEDGE)return VCK_HZ_ALLOW_HEDGE;if(source==VCK_SRC_REVERSE)return VCK_HZ_ALLOW_REVERSE;if(source==VCK_SRC_BALANCE)return VCK_HZ_ALLOW_BALANCE;return false;}
bool DirectionPermissionAllowed(const int d){if(d>0)return InpAllowBuy&&!g_stop_buy;if(d<0)return InpAllowSell&&!g_stop_sell;return false;}
bool SourceTimingAllowed(const VCKExposureSource source){if(source==VCK_SRC_ENTRY)return g_new_cycle&&SessionAllowed()&&TimeCurrent()>=g_cooldown_until;if(source==VCK_SRC_DCA)return SessionAllowed()||InpDCAOutsideSession;if(source==VCK_SRC_HEDGE||source==VCK_SRC_HEDGE_ZONE||source==VCK_SRC_REVERSE||source==VCK_SRC_BALANCE)return SessionAllowed()||VCK_RECOVERY_OUTSIDE_SESSION;return true;}
bool DirectionCapacityAllowed(const int d){int count=LiveDirectionCount(d);if(d>0)return count<InpMaxBuyPositions;if(d<0)return count<InpMaxSellPositions;return false;}
bool ExposureAllowed(const int d,const VCKExposureSource source){if(!g_ea_enabled||g_daily_halt_day==CurrentTradingDayKey())return false;if(!DirectionPermissionAllowed(d))return false;if(g_hedge_zone&&!HedgeZoneAllowsSource(source))return false;if(!SourceTimingAllowed(source))return false;return DirectionCapacityAllowed(d);}
bool OpenLeg(const int d,const double lot,const string comment,const VCKExposureSource source,const double custom_tp_pips=0){if(!ExposureAllowed(d,source))return false;MqlTick t;if(!SymbolInfoTick(g_symbol,t))return false;double price=d>0?t.ask:t.bid,sl=0,tp=0;int digits=(int)SymbolInfoInteger(g_symbol,SYMBOL_DIGITS);if(InpSLPips>0)sl=NormalizeDouble(price-d*InpSLPips*g_pip,digits);double tp_pips=custom_tp_pips>0?custom_tp_pips:InpTPPips;if(tp_pips>0)tp=NormalizeDouble(price+d*tp_pips*g_pip,digits);if(Trade.Open(d,g_symbol,lot,InpMaxLot,sl,tp,comment,(int)source)){g_last_entry=TimeCurrent();return true;}return false;}
bool CloseTicket(const ulong t){return t>0&&Trade.Close(t);}
bool CloseMagicPositions(){g_state=VCK_CLOSING;bool acted=false;for(int i=PositionsTotal()-1;i>=0;i--){ulong t=PositionGetTicket(i);if(t==0||!PositionSelectByTicket(t))continue;if(PositionGetString(POSITION_SYMBOL)==g_symbol&&(long)PositionGetInteger(POSITION_MAGIC)==InpMagic)acted=CloseTicket(t)||acted;}if(acted)g_last_clear=TimeCurrent();return acted;}
bool CloseAccountPositions(){if(!VCK_ACCOUNT_WIDE_APPROVED)return false;g_state=VCK_CLOSING;bool acted=false;for(int i=PositionsTotal()-1;i>=0;i--){ulong t=PositionGetTicket(i);if(t==0||!PositionSelectByTicket(t))continue;acted=CloseTicket(t)||acted;}if(acted)g_last_clear=TimeCurrent();return acted;}
bool CloseSide(const ENUM_POSITION_TYPE side){bool acted=false;for(int i=PositionsTotal()-1;i>=0;i--){ulong t=PositionGetTicket(i);if(t==0||!PositionSelectByTicket(t))continue;if(PositionGetString(POSITION_SYMBOL)==g_symbol&&(long)PositionGetInteger(POSITION_MAGIC)==InpMagic&&(ENUM_POSITION_TYPE)PositionGetInteger(POSITION_TYPE)==side)acted=CloseTicket(t)||acted;}return acted;}

double AdaptiveBasketPips(const VCKSideStats &s){if((g_buy_reset_lot>0||g_sell_reset_lot>0)&&InpResetBasketTPPips>0)return InpResetBasketTPPips;if(!VCK_USE_ADAPTIVE_TP||InpAdaptiveBasketTPPips<=0)return InpBasketTPPips;double bal=AccountInfoDouble(ACCOUNT_BALANCE),pct=bal>0?s.profit/bal*100:0;if((InpAdaptiveTPLossPct<0&&pct<=InpAdaptiveTPLossPct)||(InpAdaptiveTPLossMoney<0&&s.profit<=InpAdaptiveTPLossMoney))return InpAdaptiveBasketTPPips;return InpBasketTPPips;}
bool RefreshDailySnapshot(double &trading,double &cashflow,double &baseline){bool ok=ComputeDaySnapshot(InpMagic,trading,cashflow,baseline);g_history_sync_confirmations=ok?MathMin(g_history_sync_confirmations+1,2):0;g_daily_history_ready=ok&&(!VCK_HISTORY_SYNC_REQUIRED||g_history_sync_confirmations>=2);return g_daily_history_ready||!VCK_HISTORY_SYNC_REQUIRED;}
void UpdateTradingDay(const int key,const double baseline){if(g_balance_day!=key){g_balance_day=key;g_day_start_balance=g_daily_history_ready?baseline:AccountInfoDouble(ACCOUNT_BALANCE);if(g_daily_halt_day!=key)g_daily_halt_day=0;PersistState();return;}if(g_daily_history_ready&&baseline>0)g_day_start_balance=baseline;}
bool NewDayDelayActive(){if(g_daily_halt_day==0||InpNewDayDelayMinutes<=0)return false;return ClockNow(VCK_DAILY_TIME_BASIS)-TradingDayStart()<InpNewDayDelayMinutes*60;}
bool DailyThresholdHit(const double total,const double balance){if(InpDailyTargetMoney>0&&total>=InpDailyTargetMoney)return true;if(InpDailyLossMoney<0&&total<=InpDailyLossMoney)return true;if(InpDailyTargetPct>0&&balance>0&&total/balance*100>=InpDailyTargetPct)return true;if(InpDailyLossPct>0&&balance>0&&total/balance*100<=-InpDailyLossPct)return true;return false;}
bool DailyAllowed(){int key=CurrentTradingDayKey();double trading=0,cashflow=0,baseline=0;if(!RefreshDailySnapshot(trading,cashflow,baseline))return false;UpdateTradingDay(key,baseline);if(g_daily_halt_day==key||NewDayDelayActive())return false;double closed=trading+(VCK_EXCLUDE_CASHFLOWS?0:cashflow),total=closed+Book.Floating(g_symbol,InpMagic),balance=g_day_start_balance>0?g_day_start_balance:baseline;if(!DailyThresholdHit(total,balance))return true;g_daily_halt_day=key;PersistState();return false;}
bool ManageAccountMoneyExit(){if(!VCK_USE_ACCOUNT_MONEY_EXIT||!InpAllowAccountWideClose||!VCK_ACCOUNT_WIDE_APPROVED)return false;double profit=AccountFloating();if(!Basket.MoneyHit(profit,InpAccountTPMoney,InpAccountSLMoney))return false;Log.Event("ACCOUNT_EXIT","money threshold",profit);CloseAccountPositions();return true;}
bool ManageManagedMoneyExit(const double managed){if(!VCK_USE_MONEY_EXIT||!Basket.MoneyHit(managed,InpBasketTargetMoney,InpBasketStopMoney))return false;Log.Event("BASKET_EXIT","managed money threshold",managed);CloseMagicPositions();return true;}
bool ManageSideMoneyExits(const VCKSideStats &buy,const VCKSideStats &sell){if(!VCK_USE_SIDE_MONEY_EXIT)return false;bool acted=false;if(Basket.MoneyHit(buy.profit,InpBuyTPMoney,InpBuySLMoney))acted=CloseSide(POSITION_TYPE_BUY)||acted;if(Basket.MoneyHit(sell.profit,InpSellTPMoney,InpSellSLMoney))acted=CloseSide(POSITION_TYPE_SELL)||acted;return acted;}
bool ManageSteppedTarget(const double managed){if(!VCK_USE_STEPPED_TARGET||InpSteppedTargetMoney<=0)return false;if(ClosedProfitToday(InpMagic)+managed<InpSteppedTargetMoney)return false;CloseMagicPositions();g_cooldown_until=TimeCurrent()+InpSteppedTargetDelayMinutes*60;return true;}
bool ManageBalanceDifferenceExit(const VCKSideStats &buy,const VCKSideStats &sell){if(!VCK_USE_BALANCE_DIFFERENCE_EXIT||InpBalanceDifferencePct<=0||buy.count==0||sell.count==0)return false;double good=MathMax(buy.profit,sell.profit),bad=MathMin(buy.profit,sell.profit);if(good<=0||bad>=0||good+bad*(1+InpBalanceDifferencePct/100.0)<0)return false;CloseMagicPositions();return true;}
bool ManageGlobalExits(const VCKSideStats &buy,const VCKSideStats &sell){double managed=buy.profit+sell.profit;if(ManageAccountMoneyExit())return true;if(ManageManagedMoneyExit(managed))return true;if(ManageSideMoneyExits(buy,sell))return true;if(ManageSteppedTarget(managed))return true;return ManageBalanceDifferenceExit(buy,sell);}
bool ManageBasketExit(const VCKSideStats &buy,const VCKSideStats &sell){MqlTick t;if(!SymbolInfoTick(g_symbol,t))return false;if(VCK_USE_BASKET_TP){double bp=AdaptiveBasketPips(buy),sp=AdaptiveBasketPips(sell);if(buy.count>0&&Basket.SidePipsHit(1,t.bid,buy.average_price,bp,g_pip)){Log.Event("BUY_BASKET_TP","pips target",bp);CloseSide(POSITION_TYPE_BUY);return true;}if(sell.count>0&&Basket.SidePipsHit(-1,t.ask,sell.average_price,sp,g_pip)){Log.Event("SELL_BASKET_TP","pips target",sp);CloseSide(POSITION_TYPE_SELL);return true;}}if(VCK_USE_HEDGE&&buy.count>0&&sell.count>0&&InpHedgeExitMoney>0&&buy.profit+sell.profit>=InpHedgeExitMoney){CloseMagicPositions();return true;}return false;}
bool ManageTrailing(){if(!VCK_USE_TRAILING||InpTrailingStartPips<=0||InpTrailingDistancePips<=0)return false;MqlTick t;if(!SymbolInfoTick(g_symbol,t))return false;int digits=(int)SymbolInfoInteger(g_symbol,SYMBOL_DIGITS);bool acted=false;for(int i=PositionsTotal()-1;i>=0;i--){ulong ticket=PositionGetTicket(i);if(ticket==0||!PositionSelectByTicket(ticket))continue;if(PositionGetString(POSITION_SYMBOL)!=g_symbol||(long)PositionGetInteger(POSITION_MAGIC)!=InpMagic)continue;ENUM_POSITION_TYPE type=(ENUM_POSITION_TYPE)PositionGetInteger(POSITION_TYPE);double open=PositionGetDouble(POSITION_PRICE_OPEN),old=PositionGetDouble(POSITION_SL),tp=PositionGetDouble(POSITION_TP),current=type==POSITION_TYPE_BUY?t.bid:t.ask,gain=type==POSITION_TYPE_BUY?(current-open)/g_pip:(open-current)/g_pip;if(gain<InpTrailingStartPips)continue;double sl=NormalizeDouble(type==POSITION_TYPE_BUY?current-InpTrailingDistancePips*g_pip:current+InpTrailingDistancePips*g_pip,digits);if(type==POSITION_TYPE_BUY?(old==0||sl>old):(old==0||sl<old))acted=Trade.Modify(ticket,sl,tp)||acted;}return acted;}
bool ManageTrendReversal(const VCKSideStats &buy,const VCKSideStats &sell){if(!VCK_USE_TREND_REVERSAL_EXIT)return false;int d=Entry.Direction();if(d<0&&buy.count>0&&Entry.FiltersAllow(-1))return CloseSide(POSITION_TYPE_BUY);if(d>0&&sell.count>0&&Entry.FiltersAllow(1))return CloseSide(POSITION_TYPE_SELL);return false;}
bool ManageSniper(VCKSideStats &s){if(!VCK_USE_SNIPER||InpSniperHeadCount<1||InpSniperTailMaxCount<1||s.count<InpSniperTriggerPositions||s.oldest_ticket==0||s.best_ticket==0||s.oldest_ticket==s.best_ticket)return false;if(s.oldest_profit+s.best_profit<InpSniperTargetMoney)return false;bool acted=false;if(VCK_USE_PARTIAL_SNIPER){double v=Trade.NormalizeVolume(g_symbol,s.oldest_volume*InpPartialClosePct/100,s.oldest_volume),lo=SymbolInfoDouble(g_symbol,SYMBOL_VOLUME_MIN);if(v>=lo&&v<s.oldest_volume)acted=Trade.ClosePartial(s.oldest_ticket,v);}else acted=CloseTicket(s.oldest_ticket);if(acted)CloseTicket(s.best_ticket);return acted;}
bool ManageCrossChainSniper(const VCKSideStats &buy,const VCKSideStats &sell){if(!VCK_USE_CROSS_SNIPER||buy.count+sell.count<InpCrossSniperTriggerPositions)return false;if(!InpCrossSniperMagicPairOnly){ulong worst=0,best=0;double worstp=DBL_MAX,bestp=-DBL_MAX;for(int i=0;i<PositionsTotal();i++){ulong t=PositionGetTicket(i);if(t==0||!PositionSelectByTicket(t))continue;double p=PositionGetDouble(POSITION_PROFIT)+PositionGetDouble(POSITION_SWAP);if(p<worstp){worstp=p;worst=t;}if(p>bestp){bestp=p;best=t;}}if(worst>0&&best>0&&worst!=best&&worstp+bestp>=InpCrossSniperTargetMoney){bool acted=CloseTicket(worst);if(acted)CloseTicket(best);return acted;}return false;}VCKSideStats loser,winner;if(buy.profit<sell.profit){loser=buy;winner=sell;}else{loser=sell;winner=buy;}if(loser.oldest_ticket>0&&winner.best_ticket>0&&loser.oldest_profit+winner.best_profit>=InpCrossSniperTargetMoney){bool acted=CloseTicket(loser.oldest_ticket);if(acted)CloseTicket(winner.best_ticket);return acted;}return false;}

bool ManageHedge(const VCKSideStats &buy,const VCKSideStats &sell){if(!VCK_USE_HEDGE||!EntryDelayPassed())return false;double bal=AccountInfoDouble(ACCOUNT_BALANCE),buy_loss=bal>0?buy.profit/bal*100:0,sell_loss=bal>0?sell.profit/bal*100:0;bool hb=buy.count>=InpHedgeTriggerPositions||(InpHedgeTriggerLossPct<0&&buy_loss<=InpHedgeTriggerLossPct),hs=sell.count>=InpHedgeTriggerPositions||(InpHedgeTriggerLossPct<0&&sell_loss<=InpHedgeTriggerLossPct);if(hb&&sell.count==0){double v=InpHedgeUseDCALot?NextLot(-1,buy.count):buy.lots*InpHedgeLotPct/100;return OpenLeg(-1,MathMax(InpBaseLot,v),"VCK-HEDGE-SELL",VCK_SRC_HEDGE,InpHedgeTPPips);}if(hs&&buy.count==0){double v=InpHedgeUseDCALot?NextLot(1,sell.count):sell.lots*InpHedgeLotPct/100;return OpenLeg(1,MathMax(InpBaseLot,v),"VCK-HEDGE-BUY",VCK_SRC_HEDGE,InpHedgeTPPips);}return false;}
bool ManageReverseEntry(const VCKSideStats &buy,const VCKSideStats &sell){if(!VCK_USE_REVERSE_ENTRY||!EntryDelayPassed())return false;int d=Entry.Direction();if(buy.count>=InpReverseTriggerPositions&&sell.count==0&&d<0){double v=InpReverseLotPct>0?buy.lots*InpReverseLotPct/100:InpReverseFixedLot;return OpenLeg(-1,v,"VCK-REVERSE-SELL",VCK_SRC_REVERSE);}if(sell.count>=InpReverseTriggerPositions&&buy.count==0&&d>0){double v=InpReverseLotPct>0?sell.lots*InpReverseLotPct/100:InpReverseFixedLot;return OpenLeg(1,v,"VCK-REVERSE-BUY",VCK_SRC_REVERSE);}return false;}
bool ManageLotBalance(const VCKSideStats &buy,const VCKSideStats &sell){if(!VCK_USE_LOT_BALANCE||TimeCurrent()-g_last_balance<InpBalanceDelaySeconds)return false;double diff=buy.lots-sell.lots;if(MathAbs(diff)<InpBalanceTriggerLots||MathAbs(diff)<=InpBalanceStopLots)return false;if(OpenLeg(diff>0?-1:1,InpBalanceAddLot,"VCK-BALANCE",VCK_SRC_BALANCE)){g_last_balance=TimeCurrent();return true;}return false;}
bool ManagedPositionExists(const ulong ticket){return ticket>0&&PositionSelectByTicket(ticket)&&PositionGetString(POSITION_SYMBOL)==g_symbol&&(long)PositionGetInteger(POSITION_MAGIC)==InpMagic;}
bool ManagedPositionIdentifierExists(const ulong position_id){for(int i=0;i<PositionsTotal();i++){ulong t=PositionGetTicket(i);if(t==0||!PositionSelectByTicket(t))continue;if(PositionGetString(POSITION_SYMBOL)==g_symbol&&(long)PositionGetInteger(POSITION_MAGIC)==InpMagic&&(ulong)PositionGetInteger(POSITION_IDENTIFIER)==position_id)return true;}return false;}
bool PositionRealizedSummary(const ulong position_id,double &realized,ENUM_DEAL_REASON &reason){realized=0;reason=DEAL_REASON_CLIENT;datetime from=TimeCurrent()-InpIntentHistoryLookbackSeconds;if(!HistorySelect(from,TimeCurrent()))return false;bool found=false;for(int i=0;i<HistoryDealsTotal();i++){ulong d=HistoryDealGetTicket(i);if(d==0||(ulong)HistoryDealGetInteger(d,DEAL_POSITION_ID)!=position_id)continue;ENUM_DEAL_ENTRY entry=(ENUM_DEAL_ENTRY)HistoryDealGetInteger(d,DEAL_ENTRY);if(entry!=DEAL_ENTRY_OUT&&entry!=DEAL_ENTRY_OUT_BY)continue;realized+=HistoryDealGetDouble(d,DEAL_PROFIT)+HistoryDealGetDouble(d,DEAL_SWAP)+HistoryDealGetDouble(d,DEAL_COMMISSION);reason=(ENUM_DEAL_REASON)HistoryDealGetInteger(d,DEAL_REASON);found=true;}return found;}
void ResetHedgeZoneState(const string reason){if(g_hedge_zone||g_zone_phase!=VCK_ZONE_IDLE)Log.Event("HEDGE_ZONE_RESET",reason);g_hedge_zone=false;g_zone_phase=VCK_ZONE_IDLE;g_zone_low=0;g_zone_high=0;g_zone_anchor_position_id=0;PersistState();}
void ReconcileHedgeZoneState(const VCKSideStats &buy,const VCKSideStats &sell){if(!VCK_USE_HEDGE_ZONE){if(g_hedge_zone)ResetHedgeZoneState("feature disabled");return;}int total=buy.count+sell.count;if(total==0){if(g_hedge_zone||g_zone_phase!=VCK_ZONE_IDLE)ResetHedgeZoneState("no managed positions");return;}if(!g_hedge_zone){if(g_zone_phase!=VCK_ZONE_IDLE)ResetHedgeZoneState("inactive flag mismatch");return;}if(g_zone_phase==VCK_ZONE_EXITING)return;bool invalid_bounds=g_zone_low<=0||g_zone_high<=g_zone_low;bool missing_anchor=g_zone_anchor_position_id>0&&!ManagedPositionIdentifierExists(g_zone_anchor_position_id);if(invalid_bounds||missing_anchor){g_zone_phase=VCK_ZONE_RECONCILING;double anchor=buy.count>=sell.count?buy.average_price:sell.average_price;g_zone_anchor_position_id=buy.count>=sell.count?buy.oldest_identifier:sell.oldest_identifier;g_zone_low=anchor-InpHedgeZoneDistancePips*g_pip;g_zone_high=anchor+InpHedgeZoneDistancePips*g_pip;g_zone_phase=VCK_ZONE_ACTIVE;Log.Event("HEDGE_ZONE_RECONCILE",missing_anchor?"anchor changed":"bounds rebuilt");PersistState();}}
bool ManageHedgeZone(const VCKSideStats &buy,const VCKSideStats &sell){if(!VCK_USE_HEDGE_ZONE)return false;int total=buy.count+sell.count;if(!g_hedge_zone&&MathMax(buy.count,sell.count)>=InpHedgeZoneTriggerPositions){g_hedge_zone=true;g_zone_phase=VCK_ZONE_ACTIVE;g_zone_cycle_id++;g_state=VCK_HEDGE_ZONE_ACTIVE;double anchor=buy.count>=sell.count?buy.average_price:sell.average_price;g_zone_anchor_position_id=buy.count>=sell.count?buy.oldest_identifier:sell.oldest_identifier;g_zone_low=anchor-InpHedgeZoneDistancePips*g_pip;g_zone_high=anchor+InpHedgeZoneDistancePips*g_pip;PersistState();}if(!g_hedge_zone||g_zone_phase==VCK_ZONE_EXITING)return false;double target=(InpHedgeZoneNewTargetCount>0&&total>=InpHedgeZoneNewTargetCount)?InpHedgeZoneNewTargetMoney:InpHedgeZoneTargetMoney;double pip_value=0,tick_value=SymbolInfoDouble(g_symbol,SYMBOL_TRADE_TICK_VALUE),tick_size=SymbolInfoDouble(g_symbol,SYMBOL_TRADE_TICK_SIZE);if(tick_size>0)pip_value=tick_value*g_pip/tick_size;double pip_money=MathAbs(buy.lots-sell.lots)*InpHedgeZoneTargetPips*pip_value;if((target>0&&buy.profit+sell.profit>=target)||(target<=0&&InpHedgeZoneTargetPips>0&&buy.profit+sell.profit>=pip_money)){g_zone_phase=VCK_ZONE_EXITING;PersistState();return CloseMagicPositions();}if(!EntryDelayPassed())return false;MqlTick t;if(!SymbolInfoTick(g_symbol,t))return false;double lot=Trade.NormalizeVolume(g_symbol,MathMax(buy.lots,sell.lots)*InpHedgeZoneLotMultiplier,InpHedgeZoneMaxLot);if(lot<=0)return false;if(t.ask>=g_zone_high&&buy.lots<=sell.lots)return OpenLeg(1,lot,"VCK-HZ-BUY",VCK_SRC_HEDGE_ZONE);if(t.bid<=g_zone_low&&sell.lots<=buy.lots)return OpenLeg(-1,lot,"VCK-HZ-SELL",VCK_SRC_HEDGE_ZONE);return false;}
bool DCACondition(const int direction,const VCKSideStats &side,const MqlTick &tick){if(side.count<=0||side.newest_price<=0)return false;VCKDCAMode mode=ActiveDCAMode(side.count);double distance=RequiredDistance(side.count);double current=direction>0?tick.ask:tick.bid;bool adverse=direction>0?(side.newest_price-current>=distance):(current-side.newest_price>=distance);bool favorable=direction>0?(current-side.newest_price>=distance):(side.newest_price-current>=distance);switch(mode){case VCK_DCA_STEP:case VCK_DCA_STEP_MULTIPLIER:return adverse;case VCK_DCA_STEP_TIMEFRAME:return adverse&&NewBar(g_last_dca_bar);case VCK_DCA_SIGNAL:return adverse&&Entry.Direction()==direction;case VCK_DCA_POSITIVE:return favorable;case VCK_DCA_BIDIRECTIONAL:return adverse||favorable;case VCK_DCA_SIGNAL_BIDIRECTIONAL:return(adverse||favorable)&&Entry.Direction()==direction;case VCK_DCA_CLOSED_BAR:return adverse&&NewBar(g_last_dca_bar);default:return false;}}
bool ManageDCA(const VCKSideStats &buy,const VCKSideStats &sell){if(!VCK_USE_DCA||!EntryDelayPassed()||g_hedge_zone)return false;if(!SessionAllowed()&&!InpDCAOutsideSession)return false;MqlTick t;if(!SymbolInfoTick(g_symbol,t))return false;if(buy.count>0&&buy.count<InpMaxBuyPositions&&GridRisk.LevelAllowed(buy.count,InpMaxLevelsBuy)&&DCACondition(1,buy,t)&&(!g_stop_buy)&&((buy.count<InpTrendFilterAfterPositions)||Entry.FiltersAllow(1))&&OpenLeg(1,NextLot(1,buy.count),"VCK-DCA-BUY",VCK_SRC_DCA))return true;if(sell.count>0&&sell.count<InpMaxSellPositions&&GridRisk.LevelAllowed(sell.count,InpMaxLevelsSell)&&DCACondition(-1,sell,t)&&(!g_stop_sell)&&((sell.count<InpTrendFilterAfterPositions)||Entry.FiltersAllow(-1))&&OpenLeg(-1,NextLot(-1,sell.count),"VCK-DCA-SELL",VCK_SRC_DCA))return true;return false;}
bool ManageInitialEntry(const VCKSideStats &buy,const VCKSideStats &sell){if(!g_new_cycle||!SessionAllowed()||!EntryDelayPassed()||buy.count+sell.count>0||TimeCurrent()<g_cooldown_until)return false;int d=Entry.Direction();if(d==0||!Entry.FiltersAllow(d)||(d>0&&g_stop_buy)||(d<0&&g_stop_sell))return false;if(OpenLeg(d,NextLot(d,0),"VCK-ENTRY",VCK_SRC_ENTRY)){g_state=VCK_ACTIVE_CYCLE;return true;}return false;}
void ManageZoneCycle(){if(!VCK_USE_ZONE_CYCLE||InpZoneCycleUpper<=InpZoneCycleLower)return;MqlTick t;if(SymbolInfoTick(g_symbol,t)&&(t.bid>InpZoneCycleUpper||t.ask<InpZoneCycleLower))g_new_cycle=false;}

bool ProcessRemoteCommands(){if(!VCK_USE_REMOTE)return false;double point=SymbolInfoDouble(g_symbol,SYMBOL_POINT);for(int i=OrdersTotal()-1;i>=0;i--){ulong ticket=OrderGetTicket(i);if(ticket==0||!OrderSelect(ticket)||OrderGetString(ORDER_SYMBOL)!=g_symbol)continue;ENUM_ORDER_TYPE type=(ENUM_ORDER_TYPE)OrderGetInteger(ORDER_TYPE);double p=OrderGetDouble(ORDER_PRICE_OPEN);bool used=false;if(type==VCK_CMD_DISABLE_NEW_CYCLE_TYPE&&MathAbs(p-InpCmd_DISABLE_NEW_CYCLE)<=point){g_new_cycle=false;used=true;}else if(type==VCK_CMD_ENABLE_NEW_CYCLE_TYPE&&MathAbs(p-InpCmd_ENABLE_NEW_CYCLE)<=point){g_new_cycle=true;used=true;}else if(type==VCK_CMD_START_EA_TYPE&&MathAbs(p-InpCmd_START_EA)<=point){g_ea_enabled=true;used=true;}else if(type==VCK_CMD_STOP_BUY_TYPE&&MathAbs(p-InpCmd_STOP_BUY)<=point){g_stop_buy=true;used=true;}else if(type==VCK_CMD_STOP_EA_TYPE&&MathAbs(p-InpCmd_STOP_EA)<=point){g_ea_enabled=false;used=true;}else if(type==VCK_CMD_STOP_SELL_TYPE&&MathAbs(p-InpCmd_STOP_SELL)<=point){g_stop_sell=true;used=true;}if(used){Trade.DeleteOrder(ticket);PersistState();return true;}}return false;}
void CreateButton(const string key,const string text,const int y){string n=VCKP_PREFIX+key;if(ObjectFind(0,n)>=0)return;if(!ObjectCreate(0,n,OBJ_BUTTON,0,0,0))return;ObjectSetInteger(0,n,OBJPROP_CORNER,CORNER_LEFT_UPPER);ObjectSetInteger(0,n,OBJPROP_XDISTANCE,10);ObjectSetInteger(0,n,OBJPROP_YDISTANCE,y);ObjectSetInteger(0,n,OBJPROP_XSIZE,145);ObjectSetInteger(0,n,OBJPROP_YSIZE,22);ObjectSetString(0,n,OBJPROP_TEXT,text);}
void CreatePanel(){if(!VCK_USE_PANEL)return;CreateButton("NEW","Toggle New Cycle",20);CreateButton("CLOSE_BUY","Close Buy",46);CreateButton("CLOSE_SELL","Close Sell",72);CreateButton("CLOSE_ALL","Close All (2-step)",98);CreateButton("STOP_BUY","Toggle Buy",124);CreateButton("STOP_SELL","Toggle Sell",150);if(VCK_USE_RESET_LOTS){CreateButton("RESET_BUY","Reset Lots Buy",176);CreateButton("RESET_SELL","Reset Lots Sell",202);}}
void OnChartEvent(const int id,const long &lparam,const double &dparam,const string &s){if(id!=CHARTEVENT_OBJECT_CLICK)return;if(s==VCKP_PREFIX+"NEW")g_new_cycle=!g_new_cycle;else if(s==VCKP_PREFIX+"CLOSE_BUY")CloseSide(POSITION_TYPE_BUY);else if(s==VCKP_PREFIX+"CLOSE_SELL")CloseSide(POSITION_TYPE_SELL);else if(s==VCKP_PREFIX+"STOP_BUY")g_stop_buy=!g_stop_buy;else if(s==VCKP_PREFIX+"STOP_SELL")g_stop_sell=!g_stop_sell;else if(s==VCKP_PREFIX+"RESET_BUY")g_buy_reset_lot=InpResetLot;else if(s==VCKP_PREFIX+"RESET_SELL")g_sell_reset_lot=InpResetLot;else if(s==VCKP_PREFIX+"CLOSE_ALL"){datetime n=TimeCurrent();if(!g_close_armed||n-g_close_armed_at>5){g_close_armed=true;g_close_armed_at=n;ObjectSetString(0,s,OBJPROP_TEXT,"Confirm Close All");return;}g_close_armed=false;ObjectSetString(0,s,OBJPROP_TEXT,"Close All (2-step)");CloseMagicPositions();}PersistState();}

int OnInit(){g_symbol=StringLen(InpTradeSymbol)>0?InpTradeSymbol:_Symbol;if(!SymbolSelect(g_symbol,true))return INIT_FAILED;if((VCK_USE_DCA||VCK_USE_HEDGE||VCK_USE_HEDGE_ZONE||VCK_USE_REVERSE_ENTRY||VCK_USE_LOT_BALANCE)&&(ENUM_ACCOUNT_MARGIN_MODE)AccountInfoInteger(ACCOUNT_MARGIN_MODE)!=ACCOUNT_MARGIN_MODE_RETAIL_HEDGING){Print("Composition requires MT5 hedging account");return INIT_FAILED;}g_pip=PipSize();if(g_pip<=0||!Entry.Init(g_symbol,InpSignalTimeframe))return INIT_FAILED;MathSrand((int)GetTickCount());Trade.Configure(InpMagic,g_symbol,InpSignalTimeframe,InpMaxSpreadPips,InpAsyncExecution);EventReducer.Configure(InpMagic,g_symbol);StateStore.Configure(InpMagic,g_symbol);StateStore.Load(g_ea_enabled,g_new_cycle,g_stop_buy,g_stop_sell,g_lottery_factor);StateStore.LoadExtended(g_daily_halt_day,g_balance_day,g_day_start_balance,g_persisted_peak,g_hedge_zone,g_zone_phase,g_zone_cycle_id,g_zone_anchor_position_id,g_zone_low,g_zone_high,g_cooldown_until);GridRisk.Init(g_persisted_peak);Log.Configure("CCBSN_GoldenFixture");MfeMae.Configure("CCBSN_GoldenFixture");Trade.Reconcile();VCKSideStats buy,sell;Book.Collect(g_symbol,InpMagic,POSITION_TYPE_BUY,buy);Book.Collect(g_symbol,InpMagic,POSITION_TYPE_SELL,sell);ReconcileHedgeZoneState(buy,sell);CreatePanel();Log.Event("INIT","EA initialized");return INIT_SUCCEEDED;}
void OnDeinit(const int reason){PersistState();Log.Event("DEINIT",IntegerToString(reason));Entry.Release();ObjectsDeleteAll(0,VCKP_PREFIX);}
bool TickAdmissionGate()
  {
   if(ProcessRemoteCommands()) return false;
   ManageZoneCycle();
   MfeMae.Sample(g_symbol,InpMagic);
   if(!g_ea_enabled){g_state=VCK_STOPPED;return false;}
   return SpreadAllowed();
  }

bool RiskMutationGate(const VCKSideStats &buy,const VCKSideStats &sell)
  {
   if(GridRisk.MustStop())
     {
      Log.Event("MAX_DD_STOP","hard drawdown stop",GridRisk.DD());
      CloseMagicPositions();
      g_ea_enabled=false;
      PersistState();
      return true;
     }
   if(!DailyAllowed())
     {
      if(!g_daily_history_ready){Log.Event("HISTORY_NOT_READY","daily accounting frozen");return true;}
      Log.Event("DAILY_HALT","daily target/loss");
      CloseMagicPositions();
      return true;
     }
   if(VCK_USE_LOTTERY && InpLotteryResetLossMoney<0 && buy.profit+sell.profit<=InpLotteryResetLossMoney)
     {
      Log.Event("LOTTERY_RESET","loss reset",buy.profit+sell.profit);
      CloseMagicPositions();
      g_lottery_factor=1.0;
      PersistState();
      return true;
     }
   return false;
  }

bool ExitMutationChain(const VCKSideStats &buy,const VCKSideStats &sell)
  {
   if(ManageGlobalExits(buy,sell)) return true;
   if(ManageBasketExit(buy,sell)) return true;
   if(ManageTrailing()) return true;
   return ManageTrendReversal(buy,sell);
  }

bool HedgeOriginExposureActive(){for(int i=0;i<PositionsTotal();i++){ulong t=PositionGetTicket(i);if(t==0||!PositionSelectByTicket(t))continue;if(PositionGetString(POSITION_SYMBOL)!=g_symbol||(long)PositionGetInteger(POSITION_MAGIC)!=InpMagic)continue;string c=PositionGetString(POSITION_COMMENT);if(StringFind(c,"VCK-HEDGE")>=0||StringFind(c,"VCK-HZ-")>=0)return true;}return false;}
bool SniperMutationChain(const VCKSideStats &buy,const VCKSideStats &sell)
  {
   if(InpStopSniperDuringHedge && (VCK_SNIPER_PAUSE_HEDGE_ORIGIN_ONLY?HedgeOriginExposureActive():(buy.count>0&&sell.count>0))) return false;
   if(ManageSniper(buy)) return true;
   if(ManageSniper(sell)) return true;
   return ManageCrossChainSniper(buy,sell);
  }

bool ExposureMutationChain(const VCKSideStats &buy,const VCKSideStats &sell)
  {
   if(GridRisk.FreezeDD())
     {
      Log.Event("DD_FREEZE","new exposure frozen",GridRisk.DD());
      return true;
     }
   if(ManageHedgeZone(buy,sell)) return true;
   if(g_hedge_zone&&VCK_HEDGE_ZONE_EXCLUSIVE) return false;
   if(ManageHedge(buy,sell)) return true;
   if(ManageReverseEntry(buy,sell)) return true;
   if(ManageLotBalance(buy,sell)) return true;
   if(ManageDCA(buy,sell)) return true;
   return ManageInitialEntry(buy,sell);
  }

void FinalizeCycleState(const VCKSideStats &buy,const VCKSideStats &sell)
  {
   if(buy.count+sell.count!=0 || g_state!=VCK_CLOSING) return;
   g_state=VCK_COOLDOWN;
   g_cooldown_until=TimeCurrent()+InpMinutesDelayAfterClear*60;
   PersistState();
  }

void ApplyTradeDeal(const ulong deal)
  {
   if(deal==0||!HistoryDealSelect(deal)||!EventReducer.MarkDealProcessed(deal)) return;
   Trade.ObserveDeal(deal);
   ENUM_DEAL_ENTRY entry=(ENUM_DEAL_ENTRY)HistoryDealGetInteger(deal,DEAL_ENTRY);
   if(entry!=DEAL_ENTRY_OUT&&entry!=DEAL_ENTRY_OUT_BY) return;
   ulong position_id=(ulong)HistoryDealGetInteger(deal,DEAL_POSITION_ID);
   double deal_realized=HistoryDealGetDouble(deal,DEAL_PROFIT)+HistoryDealGetDouble(deal,DEAL_SWAP)+HistoryDealGetDouble(deal,DEAL_COMMISSION);
   ENUM_DEAL_REASON reason=(ENUM_DEAL_REASON)HistoryDealGetInteger(deal,DEAL_REASON);
   bool position_fully_closed=!ManagedPositionIdentifierExists(position_id);
   if(position_fully_closed&&EventReducer.AcceptClosedPosition(position_id))
     {
      double position_realized=deal_realized;ENUM_DEAL_REASON final_reason=reason;PositionRealizedSummary(position_id,position_realized,final_reason);MfeMae.Finalize(position_id,position_realized);
      if(VCK_USE_LOTTERY&&final_reason==DEAL_REASON_SL){g_lottery_factor*=InpLotterySLMultiplier;g_cooldown_until=TimeCurrent()+InpLotteryDelayMinutes*60;}
      else if(final_reason==DEAL_REASON_TP)g_lottery_factor=1.0;
      Log.Event("POSITION_CLOSED",EnumToString(final_reason),position_realized);
     }
   else Log.Event("DEAL_OUT_PARTIAL",EnumToString(reason),deal_realized);
  }
void ProcessPendingTradeEvents()
  {
   if(EventReducer.Overflowed()){g_ea_enabled=false;Log.Event("EVENT_QUEUE_OVERFLOW","manual reconciliation required");return;}
   for(int i=0;i<EventReducer.Slots();i++){ulong deal=EventReducer.PendingDeal(i);if(deal>0)ApplyTradeDeal(deal);}
  }
void OnTick()
  {
   ProcessPendingTradeEvents();
   if(!TickAdmissionGate()) return;
   Trade.Reconcile();
   VCKSideStats buy,sell;
   Book.Collect(g_symbol,InpMagic,POSITION_TYPE_BUY,buy);
   Book.Collect(g_symbol,InpMagic,POSITION_TYPE_SELL,sell);
   ReconcileHedgeZoneState(buy,sell);
   if(RiskMutationGate(buy,sell)) return;
   if(ExitMutationChain(buy,sell)) return;
   if(SniperMutationChain(buy,sell)) return;
   if(ExposureMutationChain(buy,sell)) return;
   FinalizeCycleState(buy,sell);
  }
void OnTradeTransaction(const MqlTradeTransaction &trans,const MqlTradeRequest &request,const MqlTradeResult &result)
  {
   Trade.OnTransaction(trans,request,result);
   if(trans.deal>0&&!EventReducer.EnqueueDeal(trans.deal)){g_ea_enabled=false;Log.Event("EVENT_QUEUE_OVERFLOW","deal queue full",(double)trans.deal);}
   ProcessPendingTradeEvents();
   VCKSideStats buy,sell;Book.Collect(g_symbol,InpMagic,POSITION_TYPE_BUY,buy);Book.Collect(g_symbol,InpMagic,POSITION_TYPE_SELL,sell);ReconcileHedgeZoneState(buy,sell);
   PersistState();
   if(result.retcode!=0&&result.retcode!=TRADE_RETCODE_DONE&&result.retcode!=TRADE_RETCODE_PLACED&&result.retcode!=TRADE_RETCODE_DONE_PARTIAL)Log.Event("TRADE_RETCODE",IntegerToString((int)result.retcode),(double)request.action);
  }
