#property strict
#property version   "1.00"
#property description "VibeCodeKit RC7 native compile demo"

#include <Trade/Trade.mqh>

CTrade g_trade;

input ulong InpMagic = 270812;

int OnInit()
{
   g_trade.SetExpertMagicNumber(InpMagic);
   Print("VibeCodeKit RC7 compile demo initialized");
   return(INIT_SUCCEEDED);
}

void OnDeinit(const int reason)
{
   PrintFormat("VibeCodeKit RC7 compile demo deinitialized, reason=%d", reason);
}

void OnTick()
{
   // Compile-only demo. Intentionally does not place trades.
}
