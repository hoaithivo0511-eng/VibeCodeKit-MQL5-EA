// digits-tested: 5,4,3,2
#pragma once
class CMfeMaeLogger
  {
private:
 string m_file;
 string Key(const ulong id,const string suffix){return "VCK_MFE_"+(string)id+"_"+suffix;}
public:
 void Configure(const string name){m_file=name+"-mfe-mae.csv";}
 void Sample(const string symbol,const long magic)
   {for(int i=0;i<PositionsTotal();i++){ulong t=PositionGetTicket(i);if(t==0||!PositionSelectByTicket(t))continue;if(PositionGetString(POSITION_SYMBOL)!=symbol||(long)PositionGetInteger(POSITION_MAGIC)!=magic)continue;ulong id=(ulong)PositionGetInteger(POSITION_IDENTIFIER);double p=PositionGetDouble(POSITION_PROFIT)+PositionGetDouble(POSITION_SWAP),mfe=GlobalVariableCheck(Key(id,"mfe"))?GlobalVariableGet(Key(id,"mfe")):p,mae=GlobalVariableCheck(Key(id,"mae"))?GlobalVariableGet(Key(id,"mae")):p;GlobalVariableSet(Key(id,"mfe"),MathMax(mfe,p));GlobalVariableSet(Key(id,"mae"),MathMin(mae,p));}}
 void Finalize(const ulong id,const double realized)
   {double mfe=GlobalVariableCheck(Key(id,"mfe"))?GlobalVariableGet(Key(id,"mfe")):0,mae=GlobalVariableCheck(Key(id,"mae"))?GlobalVariableGet(Key(id,"mae")):0;int h=FileOpen(m_file,FILE_COMMON|FILE_CSV|FILE_READ|FILE_WRITE|FILE_SHARE_READ,';');if(h!=INVALID_HANDLE){FileSeek(h,0,SEEK_END);FileWrite(h,TimeToString(TimeCurrent(),TIME_DATE|TIME_SECONDS),(string)id,DoubleToString(mfe,2),DoubleToString(mae,2),DoubleToString(realized,2));FileClose(h);}GlobalVariableDel(Key(id,"mfe"));GlobalVariableDel(Key(id,"mae"));}
  };
