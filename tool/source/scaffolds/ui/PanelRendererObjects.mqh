#ifndef VCK_PANEL_RENDERER_OBJECTS_MQH
#define VCK_PANEL_RENDERER_OBJECTS_MQH
#include "PanelSnapshot.mqh"
class CVCKPanelRendererObjects {
 private:
  string m_prefix;
  ulong m_last_render_us;
 public:
  CVCKPanelRendererObjects():m_prefix("VCKP_"),m_last_render_us(0) {}
  bool Create(const string prefix="VCKP_") { m_prefix=prefix; return true; }
  bool Render(const VCKPanelSnapshot &snapshot) {
    if(snapshot.dirty==VCK_DIRTY_NONE) return true;
    m_last_render_us=GetMicrosecondCount();
    // Add token-bound labels here. Never query trading/account APIs here.
    return true;
  }
  void Destroy() { ObjectsDeleteAll(0,m_prefix); }
};
#endif
