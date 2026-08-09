// digits-tested: 5,4,3,2
#pragma once
#include <Trade/Trade.mqh>
#include "TradeIntentLedger.mqh"
#include "../Risk/GridRiskGuard.mqh"
#include "../Telemetry/MfeMaeLogger.mqh"
class CAsyncTradeExecutor
  {
private:
   CTrade m_trade; CSpreadGuard m_spread; CTradeIntentLedger m_intents; long m_magic; long m_last_bars;
   bool GoodRetcode(){uint c=m_trade.ResultRetcode();return c==TRADE_RETCODE_DONE||c==TRADE_RETCODE_PLACED||c==TRADE_RETCODE_DONE_PARTIAL||c==TRADE_RETCODE_NO_CHANGES;}
   bool DefinitelyRejected(){uint c=m_trade.ResultRetcode();return c==TRADE_RETCODE_REJECT||c==TRADE_RETCODE_INVALID||c==TRADE_RETCODE_INVALID_VOLUME||c==TRADE_RETCODE_INVALID_PRICE||c==TRADE_RETCODE_INVALID_STOPS||c==TRADE_RETCODE_TRADE_DISABLED||c==TRADE_RETCODE_MARKET_CLOSED||c==TRADE_RETCODE_NO_MONEY||c==TRADE_RETCODE_INVALID_FILL||c==TRADE_RETCODE_INVALID_ORDER;}
public:
   void Configure(const long magic,const string symbol,const ENUM_TIMEFRAMES tf,const double max_spread,const bool async_mode){m_magic=magic;m_last_bars=Bars(symbol,tf);m_spread.Configure(symbol,max_spread);m_trade.SetExpertMagicNumber((ulong)magic);m_trade.SetAsyncMode(async_mode);m_intents.Configure(magic,symbol,InpIntentUnknownTimeoutSeconds,InpIntentHistoryLookbackSeconds);}
   void Reconcile(){if(VCK_RECONCILE_BEFORE_RETRY)m_intents.Reconcile();}
   void ObserveDeal(const ulong deal){if(deal>0&&HistoryDealSelect(deal)){string c=HistoryDealGetString(deal,DEAL_COMMENT);if(StringLen(c)>0)m_intents.ObserveComment(c);}}
   void OnTransaction(const MqlTradeTransaction &trans,const MqlTradeRequest &request,const MqlTradeResult &result){if(trans.order>0&&OrderSelect(trans.order)){string c=OrderGetString(ORDER_COMMENT);if(StringLen(c)>0)m_intents.ObserveComment(c);}if(trans.deal>0)ObserveDeal(trans.deal);}
   double NormalizeVolume(const string symbol,const double requested,const double maximum){double step=SymbolInfoDouble(symbol,SYMBOL_VOLUME_STEP),lo=SymbolInfoDouble(symbol,SYMBOL_VOLUME_MIN),hi=SymbolInfoDouble(symbol,SYMBOL_VOLUME_MAX);if(step<=0)step=0.01;if(lo<=0)lo=step;if(hi<=0)hi=maximum;hi=MathMin(hi,maximum);if(hi<lo||requested<lo)return 0;double v=MathMin(requested,hi);return NormalizeDouble(MathFloor(v/step+1e-8)*step,8);}
   bool MarginAvailable(const ENUM_ORDER_TYPE type,const string symbol,const double volume){MqlTick t;if(!SymbolInfoTick(symbol,t))return false;double m=0,p=type==ORDER_TYPE_BUY?t.ask:t.bid;return OrderCalcMargin(type,symbol,volume,p,m)&&m<=AccountInfoDouble(ACCOUNT_MARGIN_FREE);}
   bool Open(const int direction,const string symbol,const double requested,const double maximum,const double sl_requested,const double tp_requested,const string comment,const int source){long bars=Bars(symbol,PERIOD_CURRENT);if(bars<=0||!m_spread.Allowed())return false;m_last_bars=bars;ENUM_ORDER_TYPE type=direction>0?ORDER_TYPE_BUY:ORDER_TYPE_SELL;double v=NormalizeVolume(symbol,requested,maximum);if(v<=0||!MarginAvailable(type,symbol,v))return false;MqlTick tick;if(!SymbolInfoTick(symbol,tick))return false;double price=direction>0?tick.ask:tick.bid,point=SymbolInfoDouble(symbol,SYMBOL_POINT),sl=sl_requested,tp=tp_requested;int digits=(int)SymbolInfoInteger(symbol,SYMBOL_DIGITS),stops=(int)SymbolInfoInteger(symbol,SYMBOL_TRADE_STOPS_LEVEL);double min_dist=MathMax(0,stops)*point;if(sl>0&&MathAbs(price-sl)<min_dist)sl=NormalizeDouble(price-direction*min_dist,digits);if(tp>0&&MathAbs(tp-price)<min_dist)tp=NormalizeDouble(price+direction*min_dist,digits);string wire_comment=comment;if(VCK_RECONCILE_BEFORE_RETRY&&!m_intents.Prepare(source,direction,comment,wire_comment))return false;m_trade.SetExpertMagicNumber((ulong)m_magic);m_trade.SetTypeFillingBySymbol(symbol);bool ok=direction>0?m_trade.Buy(v,symbol,0,sl,tp,wire_comment):m_trade.Sell(v,symbol,0,sl,tp,wire_comment);if(!ok){if(DefinitelyRejected())m_intents.MarkRejected(source,direction);return false;}if(GoodRetcode()){m_intents.MarkAcknowledged(source,direction);return true;}return false;}
   bool Modify(const ulong ticket,const double sl,const double tp){return m_trade.PositionModify(ticket,sl,tp)&&GoodRetcode();}
   bool Close(const ulong ticket){return m_trade.PositionClose(ticket)&&GoodRetcode();}
   bool ClosePartial(const ulong ticket,const double volume){return m_trade.PositionClosePartial(ticket,volume)&&GoodRetcode();}
   bool DeleteOrder(const ulong ticket){return m_trade.OrderDelete(ticket)&&GoodRetcode();}
  };
