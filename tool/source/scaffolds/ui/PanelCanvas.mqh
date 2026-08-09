#ifndef VCK_PANEL_CANVAS_MQH
#define VCK_PANEL_CANVAS_MQH
#include <Canvas/Canvas.mqh>
#include "PanelSnapshot.mqh"
// Optional adapter for dense graphics. Chart objects remain the default.
class CVCKPanelCanvas {
 private: CCanvas m_canvas; string m_name;
 public:
  bool Create(const string name,const int width,const int height) { m_name=name; return m_canvas.CreateBitmapLabel(0,0,name,0,0,width,height,COLOR_FORMAT_ARGB_NORMALIZE); }
  bool Render(const VCKPanelSnapshot &snapshot) { if(snapshot.dirty==VCK_DIRTY_NONE) return true; m_canvas.Update(true); return true; }
  void Destroy() { m_canvas.Destroy(); if(m_name!="") ObjectDelete(0,m_name); }
};
#endif
