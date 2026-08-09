// digits-tested: 5,4,3,2
#pragma once
class CTradeIntentLedger
  {
private:
   string m_prefix,m_symbol; long m_magic; int m_counter,m_timeout,m_lookback;
   string Key(const int source,const int direction,const string suffix){return m_prefix+(string)source+"_"+(string)direction+"_"+suffix;}
   long MakeId(const int source,const int direction){m_counter=(m_counter+1)%1000;return (long)TimeCurrent()*10000+(long)(source+10)*100+(direction>0?50:0)+m_counter;}
   string Prefix(const long id){return "I"+(string)id+"|";}
   bool CommentHas(const string comment,const long id){return StringFind(comment,Prefix(id))==0;}
   bool FindLive(const long id)
     {
      for(int i=0;i<PositionsTotal();i++){ulong t=PositionGetTicket(i);if(t>0&&PositionSelectByTicket(t)&&PositionGetString(POSITION_SYMBOL)==m_symbol&&(long)PositionGetInteger(POSITION_MAGIC)==m_magic&&CommentHas(PositionGetString(POSITION_COMMENT),id))return true;}
      for(int i=0;i<OrdersTotal();i++){ulong t=OrderGetTicket(i);if(t>0&&OrderSelect(t)&&OrderGetString(ORDER_SYMBOL)==m_symbol&&(long)OrderGetInteger(ORDER_MAGIC)==m_magic&&CommentHas(OrderGetString(ORDER_COMMENT),id))return true;}
      return false;
     }
   bool FindHistory(const long id)
     {
      datetime from=TimeCurrent()-m_lookback;if(!HistorySelect(from,TimeCurrent()))return false;
      for(int i=0;i<HistoryOrdersTotal();i++){ulong t=HistoryOrderGetTicket(i);if(t>0&&(long)HistoryOrderGetInteger(t,ORDER_MAGIC)==m_magic&&CommentHas(HistoryOrderGetString(t,ORDER_COMMENT),id))return true;}
      for(int i=0;i<HistoryDealsTotal();i++){ulong t=HistoryDealGetTicket(i);if(t>0&&(long)HistoryDealGetInteger(t,DEAL_MAGIC)==m_magic&&CommentHas(HistoryDealGetString(t,DEAL_COMMENT),id))return true;}
      return false;
     }
   void Clear(const int source,const int direction){GlobalVariableDel(Key(source,direction,"id"));GlobalVariableDel(Key(source,direction,"sent"));GlobalVariableDel(Key(source,direction,"state"));}
public:
   void Configure(const long magic,const string symbol,const int timeout_seconds,const int lookback_seconds){m_magic=magic;m_symbol=symbol;m_timeout=MathMax(5,timeout_seconds);m_lookback=MathMax(3600,lookback_seconds);m_prefix="VCK_INTENT_"+(string)magic+"_"+symbol+"_";m_counter=0;}
   bool Prepare(const int source,const int direction,const string base_comment,string &wire_comment)
     {
      string id_key=Key(source,direction,"id"),sent_key=Key(source,direction,"sent");
      if(GlobalVariableCheck(id_key))
        {
         long existing=(long)GlobalVariableGet(id_key);datetime sent=GlobalVariableCheck(sent_key)?(datetime)GlobalVariableGet(sent_key):0;
         if(FindLive(existing)||FindHistory(existing)){Clear(source,direction);return false;}
         // Unknown broker outcome is a safety stop, not a retry timer. The
         // intent remains sealed until terminal truth is observed or an
         // operator explicitly clears it after reconciliation.
         if(VCK_BLOCK_UNKNOWN_OUTCOME)return false;
         if(sent==0||TimeCurrent()-sent<m_timeout)return false;
         if(!HistorySelect(TimeCurrent()-m_lookback,TimeCurrent()))return false;
         Clear(source,direction);
        }
      long id=MakeId(source,direction);GlobalVariableSet(id_key,(double)id);GlobalVariableSet(sent_key,(double)TimeCurrent());GlobalVariableSet(Key(source,direction,"state"),1.0);
      wire_comment=StringSubstr(Prefix(id)+base_comment,0,31);return true;
     }
   void MarkRejected(const int source,const int direction){Clear(source,direction);}
   void MarkAcknowledged(const int source,const int direction){GlobalVariableSet(Key(source,direction,"state"),2.0);}
   void ObserveComment(const string comment)
     {
      if(StringLen(comment)<3||StringGetCharacter(comment,0)!=73)return;
      int sep=StringFind(comment,"|");if(sep<2)return;long id=(long)StringToInteger(StringSubstr(comment,1,sep-1));
      for(int source=0;source<6;source++)for(int d=-1;d<=1;d+=2){string k=Key(source,d,"id");if(GlobalVariableCheck(k)&&(long)GlobalVariableGet(k)==id)Clear(source,d);}
     }
   void Reconcile(){for(int source=0;source<6;source++)for(int d=-1;d<=1;d+=2){string k=Key(source,d,"id");if(!GlobalVariableCheck(k))continue;long id=(long)GlobalVariableGet(k);if(FindLive(id)||FindHistory(id))Clear(source,d);}}
  };
