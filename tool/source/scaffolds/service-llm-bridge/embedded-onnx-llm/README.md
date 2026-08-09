# service-llm-bridge / embedded-onnx-llm

Embeds an ONNX-quantised small LLM (Phi-3 mini, TinyLlama 1B, etc.) as
an MQL5 resource. No network, no API key, no rate limit. The model
runs inside the MetaTrader process so inference latency is single-digit
milliseconds — safe to call directly from `OnTick()`.

**Required file:** `phi3_mini.onnx` placed alongside the .mq5. The
build system declares it via:

```cpp
#resource "phi3_mini.onnx"
```

A 128-byte **stub** model ships with the scaffold so the EA compiles
out of the box (the embedded `OnnxCreate()` call will fail gracefully
at runtime because the stub isn't a valid ONNX protobuf, and the EA
falls back to the MA(20)/MA(50) trend signal). **Before running the
EA on a real broker, replace `phi3_mini.onnx` with your quantised
LLM model.** You can use any ONNX-exported Phi-3 mini / TinyLlama
quantisation that fits the MQL5 OnnxRuntime constraints (≤200 MB,
INT8 / FP16 / FP32 weights).

The fallback is an MA(20)/MA(50) trend signal (Trader-17 #14 + #16).

Render via:

```bash
python -m vibecodekit_mql5.build service-llm-bridge \
    --name MyOnnxLlmEA --symbol EURUSD --tf M15 --stack embedded-onnx-llm
```

The kit does not ship a fake/stub model. Supply and hash a real compatible
`phi3_mini.onnx` before enabling this scaffold; without it the project remains
non-runnable and non-release-eligible.
Replace it with your real model, then run
`python -m vibecodekit_mql5.compile <ea>.mq5`.
