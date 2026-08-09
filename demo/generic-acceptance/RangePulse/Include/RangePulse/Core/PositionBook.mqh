// digits-tested: 5,4,3,2
#pragma once
struct VCKSideStats { int count; double lots,weighted_price,average_price,profit,newest_price,oldest_profit,oldest_volume,best_profit,best_volume; datetime newest_time,oldest_time; ulong oldest_ticket,oldest_identifier,best_ticket; };
class CVCKPositionBook
  {
public:
   void Collect(const string symbol,const long magic,const ENUM_POSITION_TYPE side,VCKSideStats &s)
     { ZeroMemory(s); s.best_profit=-DBL_MAX; for(int i=0;i<PositionsTotal();i++){ ulong t=PositionGetTicket(i); if(t==0||!PositionSelectByTicket(t))continue; if(PositionGetString(POSITION_SYMBOL)!=symbol||(long)PositionGetInteger(POSITION_MAGIC)!=magic||(ENUM_POSITION_TYPE)PositionGetInteger(POSITION_TYPE)!=side)continue; double v=PositionGetDouble(POSITION_VOLUME),p=PositionGetDouble(POSITION_PRICE_OPEN),pr=PositionGetDouble(POSITION_PROFIT)+PositionGetDouble(POSITION_SWAP); datetime tm=(datetime)PositionGetInteger(POSITION_TIME); s.count++;s.lots+=v;s.weighted_price+=p*v;s.profit+=pr; if(tm>=s.newest_time){s.newest_time=tm;s.newest_price=p;} if(s.oldest_ticket==0||tm<s.oldest_time){s.oldest_ticket=t;s.oldest_identifier=(ulong)PositionGetInteger(POSITION_IDENTIFIER);s.oldest_time=tm;s.oldest_profit=pr;s.oldest_volume=v;} if(pr>s.best_profit){s.best_ticket=t;s.best_profit=pr;s.best_volume=v;} } if(s.lots>0)s.average_price=s.weighted_price/s.lots; }
   double Floating(const string symbol,const long magic)
     { double total=0; for(int i=0;i<PositionsTotal();i++){ulong t=PositionGetTicket(i);if(t==0||!PositionSelectByTicket(t))continue;if(PositionGetString(POSITION_SYMBOL)==symbol&&(long)PositionGetInteger(POSITION_MAGIC)==magic)total+=PositionGetDouble(POSITION_PROFIT)+PositionGetDouble(POSITION_SWAP);}return total;}
  };
