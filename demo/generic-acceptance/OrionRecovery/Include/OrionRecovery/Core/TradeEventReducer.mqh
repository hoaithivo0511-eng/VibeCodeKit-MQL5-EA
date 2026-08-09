// digits-tested: 5,4,3,2
#pragma once
class CTradeEventReducer
  {
private:
   string m_prefix; int m_slots;
   string Key(const string kind,const int slot,const string part){return m_prefix+kind+"_"+(string)slot+"_"+part;}
   uint High(const ulong value){return (uint)(value>>32);}
   uint Low(const ulong value){return (uint)(value&0xFFFFFFFF);}
   ulong Read(const string kind,const int slot)
     {
      string hi=Key(kind,slot,"hi"),lo=Key(kind,slot,"lo");
      if(!GlobalVariableCheck(hi)||!GlobalVariableCheck(lo))return 0;
      return ((ulong)(uint)GlobalVariableGet(hi)<<32)|(ulong)(uint)GlobalVariableGet(lo);
     }
   void Write(const string kind,const int slot,const ulong value){GlobalVariableSet(Key(kind,slot,"hi"),(double)High(value));GlobalVariableSet(Key(kind,slot,"lo"),(double)Low(value));}
   bool Seen(const string kind,const ulong value){for(int i=0;i<m_slots;i++)if(Read(kind,i)==value)return true;return false;}
   bool Accept(const string kind,const ulong value){if(value==0||Seen(kind,value))return false;int cursor_key=(kind=="deal"?0:1);string ck=m_prefix+"cursor_"+(string)cursor_key;int cursor=GlobalVariableCheck(ck)?(int)GlobalVariableGet(ck):0;Write(kind,cursor%m_slots,value);GlobalVariableSet(ck,(double)((cursor+1)%m_slots));return true;}
public:
   void Configure(const long magic,const string symbol,const int slots=128){m_prefix="VCK_EVENT_"+(string)magic+"_"+symbol+"_";m_slots=MathMax(32,MathMin(256,slots));}
   int Slots(){return m_slots;}
   ulong PendingDeal(const int slot){if(slot<0||slot>=m_slots)return 0;return Read("pending",slot);}
   bool EnqueueDeal(const ulong deal)
     {
      if(deal==0||Seen("deal",deal)||Seen("pending",deal))return true;
      for(int i=0;i<m_slots;i++)if(Read("pending",i)==0){Write("pending",i,deal);return true;}
      GlobalVariableSet(m_prefix+"overflow",1.0);return false;
     }
   bool MarkDealProcessed(const ulong deal)
     {
      if(deal==0||Seen("deal",deal))return false;
      if(!Accept("deal",deal))return false;
      for(int i=0;i<m_slots;i++)if(Read("pending",i)==deal)Write("pending",i,0);
      return true;
     }
   bool Overflowed(){return GlobalVariableCheck(m_prefix+"overflow")&&GlobalVariableGet(m_prefix+"overflow")>0.5;}
   bool AcceptClosedPosition(const ulong position_id){return Accept("position",position_id);}
  };
