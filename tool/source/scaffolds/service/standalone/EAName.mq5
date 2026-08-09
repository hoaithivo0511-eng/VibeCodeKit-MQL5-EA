//+------------------------------------------------------------------+
//| {{NAME}}.mq5                                                      |
//|                                                                   |
//| Scaffold:  service / standalone                                    |
//| Symbol:    {{SYMBOL}}  (data anchor only — service is account-wide)|
//| Timeframe: {{TF}}                                                  |
//|                                                                   |
//| MQL5 Service program (build 5320+) — long-running background task |
//| with its own thread, no chart, no symbol-driven OnTick.            |
//|                                                                   |
//| Lifecycle:                                                         |
//|   OnStart() runs once; the loop drives the work; ServiceShutdown  |
//|   triggers a clean exit through IsStopped().                       |
//|                                                                   |
//| When to use over an EA:                                            |
//|   - data collection across multiple symbols / chartless polling   |
//|   - LLM/REST polling that must NOT block any chart's OnTick       |
//|   - Telegram / Slack notification daemons                         |
//|   - VPS canary / health-check beacons                             |
//|                                                                   |
//| digits-tested: 5, 3                                                |
//+------------------------------------------------------------------+
#property service
#property copyright "vibecodekit-mql5-ea"
#property version   "1.00"
#property strict

input int    InpPollIntervalMs = 1000;   // main loop cadence
input string InpServiceTag     = "{{NAME}}";

//+------------------------------------------------------------------+
//| Service entry point. Stays alive until ServiceShutdown() or a    |
//| platform stop. IsStopped() returns true on shutdown — every loop |
//| body must check it before sleeping.                              |
//+------------------------------------------------------------------+
void OnStart(void)
  {
   PrintFormat("[%s] service starting, poll=%d ms", InpServiceTag, InpPollIntervalMs);

   while(!IsStopped())
     {
      //--- Replace this stub with your real work unit.
      //    Anything you'd put in OnTimer of an EA fits here; the
      //    service has its own thread so OnTick of any chart-bound
      //    EA is unaffected.
      DoOneCycle();
      Sleep(InpPollIntervalMs);
     }

   PrintFormat("[%s] service stopping cleanly", InpServiceTag);
  }

//+------------------------------------------------------------------+
//| Work unit.  Keep this idempotent so a restart never duplicates    |
//| side effects (writes, REST POSTs, queue pushes).                  |
//+------------------------------------------------------------------+
void DoOneCycle(void)
  {
   //--- Plan v5 §17: services that do I/O MUST emit a heartbeat to
   //    the Experts journal once per cycle so VPS-side canaries can
   //    detect a wedged thread.  Print is cheap — keep it.
   PrintFormat("[%s] heartbeat @ %s", InpServiceTag,
               TimeToString(TimeCurrent(), TIME_DATE | TIME_SECONDS));
  }
