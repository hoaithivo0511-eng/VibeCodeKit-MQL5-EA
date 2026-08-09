# UI panel scaffold

Use `PanelRendererObjects.mqh` by default. `PanelCanvas.mqh` is optional for dense graphics. The EA owns event routing: `OnTick` publishes only a cheap snapshot/dirty flags, `OnChartEvent` queues intent, and bounded `OnTimer` calls the renderer. Destructive actions must pass confirmation and the existing risk/execution layer.
