# Browser Chinese speech

Runtime: sherpa-onnx v1.13.8, Apache-2.0 (see LICENSE-sherpa-onnx).
Source: https://github.com/k2-fsa/sherpa-onnx/tree/v1.13.8/wasm/tts

Voice: matcha-icefall-zh-baker, with vocos-22khz-univ, shipped in the upstream
WASM release. Model provenance and terms are separate from the runtime license.
The model author states that the DataBaker training dataset is for **non-commercial
use only**. This voice must not be presented as commercially cleared.
Model card: https://huggingface.co/csukuangfj/matcha-icefall-zh-baker/blob/main/README.md
Training: https://github.com/k2-fsa/icefall/tree/master/egs/baker_zh/TTS

TMC uses its own Worker adapter and audio playback integration. No Amap TTS code,
voice model or trademarked speaker identity is included in this implementation.
