// digits-tested: 5,4,3,2
#pragma once
#include "../Config.mqh"
class CSpreadGuard
  {
private: string m_symbol; double m_max_pips;
public:
 void Configure(const string symbol,const double max_pips){m_symbol=symbol;m_max_pips=max_pips;}
 double Pip(){int d=(int)SymbolInfoInteger(m_symbol,SYMBOL_DIGITS);double p=SymbolInfoDouble(m_symbol,SYMBOL_POINT);return(d==3||d==5)?p*10.0:p;}
 bool Allowed(){MqlTick t;double pip=Pip();return SymbolInfoTick(m_symbol,t)&&pip>0&&(t.ask-t.bid)/pip<=m_max_pips;}
  };
class CGridRiskGuard
  {
private: double m_peak_equity;
public:
 void Init(const double persisted_peak=0){double now=AccountInfoDouble(ACCOUNT_EQUITY);m_peak_equity=MathMax(now,persisted_peak);}
 double Peak(){DD();return m_peak_equity;}
 double DD(){double e=AccountInfoDouble(ACCOUNT_EQUITY);m_peak_equity=MathMax(m_peak_equity,e);return m_peak_equity>0?(m_peak_equity-e)/m_peak_equity*100.0:0.0;}
 bool FreezeDD(){return InpFreezeDDPct>0&&DD()>=InpFreezeDDPct;}
 bool MustStop(){return InpMaxDDPct>0&&DD()>=InpMaxDDPct;}
 bool LevelAllowed(const int levels,const int MaxLevels){return levels<MaxLevels;}
  };
