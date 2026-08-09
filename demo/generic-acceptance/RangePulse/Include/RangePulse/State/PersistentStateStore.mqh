// digits-tested: 5,4,3,2
#pragma once
class CPersistentStateStore
  {
private:
 string m_prefix;
 string Key(const string suffix){return m_prefix+suffix;}
 void SaveUlong(const string suffix,const ulong value){GlobalVariableSet(Key(suffix+"_hi"),(double)(value>>32));GlobalVariableSet(Key(suffix+"_lo"),(double)(value&0xFFFFFFFF));}
 ulong LoadUlong(const string suffix){ulong hi=GlobalVariableCheck(Key(suffix+"_hi"))?(ulong)GlobalVariableGet(Key(suffix+"_hi")):0;ulong lo=GlobalVariableCheck(Key(suffix+"_lo"))?(ulong)GlobalVariableGet(Key(suffix+"_lo")):0;return (hi<<32)|lo;}
public:
 void Configure(const long magic,const string symbol){m_prefix="VCK_"+(string)magic+"_"+symbol+"_";}
 void Save(const bool enabled,const bool new_cycle,const bool stop_buy,const bool stop_sell,const double lottery)
   {GlobalVariableSet(Key("enabled"),enabled?1:0);GlobalVariableSet(Key("new_cycle"),new_cycle?1:0);GlobalVariableSet(Key("stop_buy"),stop_buy?1:0);GlobalVariableSet(Key("stop_sell"),stop_sell?1:0);GlobalVariableSet(Key("lottery"),lottery);}
 void Load(bool &enabled,bool &new_cycle,bool &stop_buy,bool &stop_sell,double &lottery)
   {if(GlobalVariableCheck(Key("enabled")))enabled=GlobalVariableGet(Key("enabled"))>0.5;if(GlobalVariableCheck(Key("new_cycle")))new_cycle=GlobalVariableGet(Key("new_cycle"))>0.5;if(GlobalVariableCheck(Key("stop_buy")))stop_buy=GlobalVariableGet(Key("stop_buy"))>0.5;if(GlobalVariableCheck(Key("stop_sell")))stop_sell=GlobalVariableGet(Key("stop_sell"))>0.5;if(GlobalVariableCheck(Key("lottery")))lottery=GlobalVariableGet(Key("lottery"));}
 void SaveExtended(const int halt_day,const int balance_day,const double day_balance,const double peak,const bool hedge_zone,const int zone_phase,const int zone_cycle_id,const ulong zone_anchor_position_id,const double zone_low,const double zone_high,const datetime cooldown)
   {GlobalVariableSet(Key("state_schema"),3.0);GlobalVariableSet(Key("halt_day"),(double)halt_day);GlobalVariableSet(Key("balance_day"),(double)balance_day);GlobalVariableSet(Key("day_balance"),day_balance);GlobalVariableSet(Key("peak_equity"),peak);GlobalVariableSet(Key("hedge_zone"),hedge_zone?1:0);GlobalVariableSet(Key("zone_phase"),(double)zone_phase);GlobalVariableSet(Key("zone_cycle_id"),(double)zone_cycle_id);SaveUlong("zone_anchor_position",zone_anchor_position_id);GlobalVariableSet(Key("zone_low"),zone_low);GlobalVariableSet(Key("zone_high"),zone_high);GlobalVariableSet(Key("cooldown"),(double)cooldown);}
 void LoadExtended(int &halt_day,int &balance_day,double &day_balance,double &peak,bool &hedge_zone,int &zone_phase,int &zone_cycle_id,ulong &zone_anchor_position_id,double &zone_low,double &zone_high,datetime &cooldown)
   {double schema=GlobalVariableCheck(Key("state_schema"))?GlobalVariableGet(Key("state_schema")):0;if(GlobalVariableCheck(Key("halt_day")))halt_day=(int)GlobalVariableGet(Key("halt_day"));if(GlobalVariableCheck(Key("balance_day")))balance_day=(int)GlobalVariableGet(Key("balance_day"));if(GlobalVariableCheck(Key("day_balance")))day_balance=GlobalVariableGet(Key("day_balance"));if(GlobalVariableCheck(Key("peak_equity")))peak=GlobalVariableGet(Key("peak_equity"));if(GlobalVariableCheck(Key("cooldown")))cooldown=(datetime)GlobalVariableGet(Key("cooldown"));if(schema>=3.0){if(GlobalVariableCheck(Key("hedge_zone")))hedge_zone=GlobalVariableGet(Key("hedge_zone"))>0.5;if(GlobalVariableCheck(Key("zone_phase")))zone_phase=(int)GlobalVariableGet(Key("zone_phase"));if(GlobalVariableCheck(Key("zone_cycle_id")))zone_cycle_id=(int)GlobalVariableGet(Key("zone_cycle_id"));zone_anchor_position_id=LoadUlong("zone_anchor_position");if(GlobalVariableCheck(Key("zone_low")))zone_low=GlobalVariableGet(Key("zone_low"));if(GlobalVariableCheck(Key("zone_high")))zone_high=GlobalVariableGet(Key("zone_high"));}else{hedge_zone=false;zone_phase=0;zone_cycle_id=0;zone_anchor_position_id=0;zone_low=0;zone_high=0;}}
  };
