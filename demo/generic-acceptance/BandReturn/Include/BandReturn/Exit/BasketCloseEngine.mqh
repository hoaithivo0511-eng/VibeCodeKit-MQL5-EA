// digits-tested: 5,4,3,2
#pragma once
class CBasketCloseEngine
  {
public:
 bool MoneyHit(const double profit,const double target,const double stop){return(target>0&&profit>=target)||(stop<0&&profit<=stop);}
 bool SidePipsHit(const int direction,const double current,const double average,const double target_pips,const double pip){if(target_pips<=0)return false;return direction>0?current>=average+target_pips*pip:current<=average-target_pips*pip;}
  };
