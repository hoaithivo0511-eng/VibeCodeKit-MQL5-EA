//+------------------------------------------------------------------+
//| CPipNormalizer.mqh                                                |
//|                                                                   |
//| Flagship: cross-broker pip math. Plan v5 reference 79 truth       |
//| table.                                                            |
//|                                                                   |
//|   digits ∈ {3, 5}  →  pip = 10 * point                             |
//|   otherwise        →  pip = 1  * point                             |
//|   metals (XAU/XAG) →  pip ×10 extra  (1 USD = 10 pips convention)   |
//|                                                                   |
//| Examples:                                                         |
//|   EURUSD 5d, 1.23456 → point 0.00001, pip 0.0001                  |
//|   EURUSD 4d, 1.2345  → point 0.0001 , pip 0.0001                  |
//|   USDJPY 3d, 151.234 → point 0.001  , pip 0.01                    |
//|   XAUUSD 2d, 4567.89 → point 0.01   , pip 0.1                     |
//|   XAUUSD 3d, 4567.890→ point 0.001  , pip 0.1                     |
//|                                                                   |
//| Public surface (per docs/phase-A-spec.md §"CPipNormalizer          |
//| interface"):                                                      |
//|   bool   Init(const string symbol = NULL)                          |
//|   double Pips(int pips) const                                      |
//|   double PriceToPips(double dist) const                            |
//|   double PipValue(int pips, double lots) const                     |
//|   double LotForRisk(double risk_money, int sl_pips) const          |
//|   bool   IsValidSLDistance(int sl_pips) const                      |
//|   int    ClampSLPips(int desired) const                            |
//+------------------------------------------------------------------+
#ifndef __CPIP_NORMALIZER_MQH__
#define __CPIP_NORMALIZER_MQH__

class CPipNormalizer
  {
private:
   string            m_symbol;
   int               m_digits;
   double            m_point;
   double            m_pip;
   double            m_pip_in_points;
   double            m_tick_size;
   double            m_tick_value;
   double            m_pip_value_per_lot;
   long              m_stops_level;
   long              m_freeze_level;
   bool              m_initialized;

public:
                     CPipNormalizer(void);
                    ~CPipNormalizer(void) {}

   bool              Init(const string symbol = NULL);
   double            Pips(int pips) const;
   double            PriceToPips(double dist) const;
   double            PipValue(int pips, double lots) const;
   double            LotForRisk(double risk_money, int sl_pips) const;
   bool              IsValidSLDistance(int sl_pips) const;
   int               ClampSLPips(int desired) const;

   string            Symbol(void)        const { return m_symbol; }
   bool              IsMetal(void)       const { return DetectMetal(m_symbol); }
   int               Digits(void)        const { return m_digits; }
   double            Point(void)         const { return m_point; }
   double            Pip(void)           const { return m_pip; }
   double            PipInPoints(void)   const { return m_pip_in_points; }
   long              StopsLevel(void)    const { return m_stops_level; }
   long              FreezeLevel(void)   const { return m_freeze_level; }
   bool              IsInitialized(void) const { return m_initialized; }

private:
   bool              DetectMetal(const string sym) const;
  };

//+------------------------------------------------------------------+
CPipNormalizer::CPipNormalizer(void) : m_symbol(""),
                                       m_digits(0),
                                       m_point(0.0),
                                       m_pip(0.0),
                                       m_pip_in_points(0.0),
                                       m_tick_size(0.0),
                                       m_tick_value(0.0),
                                       m_pip_value_per_lot(0.0),
                                       m_stops_level(0),
                                       m_freeze_level(0),
                                       m_initialized(false)
  {
  }

//+------------------------------------------------------------------+
//| Detect digits / point / pip for the symbol and cache broker-side  |
//| stops & freeze levels. Returns false if the symbol is invalid.    |
//+------------------------------------------------------------------+
bool CPipNormalizer::Init(const string symbol = NULL)
  {
   m_symbol = (symbol == NULL || symbol == "") ? _Symbol : symbol;

   m_digits = (int)SymbolInfoInteger(m_symbol, SYMBOL_DIGITS);
   m_point  = SymbolInfoDouble(m_symbol, SYMBOL_POINT);
   if(m_point <= 0.0 || m_digits <= 0)
     {
      m_initialized = false;
      return(false);
     }

   // Canonical rule: digits ∈ {3, 5} → pip = 10 * point; else pip = 1 * point.
   m_pip_in_points    = (m_digits == 3 || m_digits == 5) ? 10.0 : 1.0;
   // Metals (XAU/XAG): 1 USD = 10 pips convention → pip ×10 extra.
   if(DetectMetal(m_symbol))
      m_pip_in_points *= 10.0;
   m_pip              = m_point * m_pip_in_points;

   m_tick_size        = SymbolInfoDouble(m_symbol, SYMBOL_TRADE_TICK_SIZE);
   m_tick_value       = SymbolInfoDouble(m_symbol, SYMBOL_TRADE_TICK_VALUE);
   if(m_tick_size > 0.0)
      m_pip_value_per_lot = (m_pip / m_tick_size) * m_tick_value;
   else
      m_pip_value_per_lot = 0.0;

   m_stops_level  = SymbolInfoInteger(m_symbol, SYMBOL_TRADE_STOPS_LEVEL);
   m_freeze_level = SymbolInfoInteger(m_symbol, SYMBOL_TRADE_FREEZE_LEVEL);

   m_initialized = true;
   return(true);
  }

//+------------------------------------------------------------------+
//| Convert an int pip count into a price-space distance.             |
//+------------------------------------------------------------------+
double CPipNormalizer::Pips(int pips) const
  {
   return(pips * m_pip);
  }

//+------------------------------------------------------------------+
//| Convert a price-space distance into a pip count (double).         |
//+------------------------------------------------------------------+
double CPipNormalizer::PriceToPips(double dist) const
  {
   if(m_pip <= 0.0)
      return(0.0);
   return(dist / m_pip);
  }

//+------------------------------------------------------------------+
//| Money value of `pips` pips at `lots` lots, per broker tick.       |
//+------------------------------------------------------------------+
double CPipNormalizer::PipValue(int pips, double lots) const
  {
   return(pips * m_pip_value_per_lot * lots);
  }

//+------------------------------------------------------------------+
//| Lot size that places `risk_money` at risk over `sl_pips` SL.      |
//+------------------------------------------------------------------+
double CPipNormalizer::LotForRisk(double risk_money, int sl_pips) const
  {
   if(sl_pips <= 0 || m_pip_value_per_lot <= 0.0 || risk_money <= 0.0)
      return(0.0);
   double raw = risk_money / (sl_pips * m_pip_value_per_lot);

   double step = SymbolInfoDouble(m_symbol, SYMBOL_VOLUME_STEP);
   double lmin = SymbolInfoDouble(m_symbol, SYMBOL_VOLUME_MIN);
   double lmax = SymbolInfoDouble(m_symbol, SYMBOL_VOLUME_MAX);
   if(step <= 0.0) step = 0.01;
   if(lmin <= 0.0) lmin = 0.01;
   if(lmax <= 0.0) lmax = 100.0;

   double snapped = MathFloor(raw / step) * step;
   if(snapped < lmin) snapped = lmin;
   if(snapped > lmax) snapped = lmax;
   return(snapped);
  }

//+------------------------------------------------------------------+
//| Returns true iff `sl_pips` ≥ broker stops_level (in pip units).   |
//+------------------------------------------------------------------+
bool CPipNormalizer::IsValidSLDistance(int sl_pips) const
  {
   if(sl_pips <= 0) return(false);
   if(m_pip_in_points <= 0.0) return(false);
   double min_pips = (double)m_stops_level / m_pip_in_points;
   return(sl_pips >= (int)MathCeil(min_pips));
  }

//+------------------------------------------------------------------+
//| Bumps `desired` to broker stops_level if it would be rejected.    |
//+------------------------------------------------------------------+
int CPipNormalizer::ClampSLPips(int desired) const
  {
   if(m_pip_in_points <= 0.0) return(desired);
   int min_pips = (int)MathCeil((double)m_stops_level / m_pip_in_points);
   return(desired < min_pips ? min_pips : desired);
  }

//+------------------------------------------------------------------+
//| Detect metal symbols (gold/silver) by name substring.             |
//+------------------------------------------------------------------+
bool CPipNormalizer::DetectMetal(const string sym) const
  {
   string upper = sym;
   StringToUpper(upper);
   return(StringFind(upper, "XAU") >= 0 || StringFind(upper, "GOLD") >= 0 ||
          StringFind(upper, "XAG") >= 0 || StringFind(upper, "SILVER") >= 0);
  }

#endif // __CPIP_NORMALIZER_MQH__
