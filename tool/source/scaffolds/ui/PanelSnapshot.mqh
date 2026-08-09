#ifndef VCK_PANEL_SNAPSHOT_MQH
#define VCK_PANEL_SNAPSHOT_MQH
enum VCKPanelDirty { VCK_DIRTY_NONE=0, VCK_DIRTY_ACCOUNT=1, VCK_DIRTY_POSITION=2, VCK_DIRTY_STATE=4, VCK_DIRTY_LAYOUT=8 };
struct VCKPanelSnapshot {
  double equity;
  double drawdown_pct;
  double exposure;
  string status;
  datetime captured_at;
  uint dirty;
};
#endif
