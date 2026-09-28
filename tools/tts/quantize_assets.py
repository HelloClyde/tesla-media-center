"""Weight-only int8 storage; DQ constants restore FP32 weights for CPU inference.

Reduces transfer size, not a claim of INT8 execution or reduced runtime memory.
Source assets must first pass prepare_assets.py's pinned archive verification.
"""
import json
from pathlib import Path
import re
import shutil
import numpy as np
import onnx
from onnx import helper, numpy_helper as nh

ROOT = Path(__file__).resolve().parents[2]
MODEL_NAMES = {'/model-steps-3.onnx', '/vocos-22khz-univ.onnx'}

def quantize(raw):
    model = onnx.load_model_from_string(raw)
    tensors, nodes = [], []
    for tensor in model.graph.initializer:
        values = nh.to_array(tensor)
        if values.dtype != np.float32 or values.ndim < 2 or values.size < 256:
            tensors.append(tensor)
            continue
        # Per-row symmetric quantization; preserve biases and small constants.
        scale = np.maximum(np.max(np.abs(values), axis=tuple(range(1, values.ndim))) / 127,
                           np.finfo(np.float32).tiny)
        broadcast = (values.shape[0],) + (1,) * (values.ndim - 1)
        weights = np.clip(np.rint(values / scale.reshape(broadcast)), -127, 127).astype(np.int8)
        names = [tensor.name + suffix for suffix in ('__q8', '__scale', '__zero')]
        tensors.extend([nh.from_array(weights, names[0]), nh.from_array(scale, names[1]),
                        nh.from_array(np.zeros_like(scale, dtype=np.int8), names[2])])
        nodes.append(helper.make_node('DequantizeLinear', names, [tensor.name], axis=0,
                                      name=tensor.name + '__dequant'))
    original = list(model.graph.node)
    del model.graph.initializer[:]
    model.graph.initializer.extend(tensors)
    del model.graph.node[:]
    model.graph.node.extend(nodes + original)
    onnx.checker.check_model(model)
    return model.SerializeToString()

def main():
    source = ROOT / '.local-data/tts/source'
    output = ROOT / 'web/public/tts/matcha-1.13.8-q8-v1'
    output.mkdir(parents=True, exist_ok=True)
    name = 'sherpa-onnx-wasm-main-tts'
    script = (source / (name + '.js')).read_text(encoding='utf8')
    package = (source / (name + '.data')).read_bytes()
    blocks, report = [], []
    offset = 0
    pattern = r'\{filename:"([^"]+)",start:(\d+),end:(\d+)\}'
    def replace(match):
        nonlocal offset
        filename, start, end = match[1], int(match[2]), int(match[3])
        if not 0 <= start <= end <= len(package):
            raise ValueError('Invalid package entry')
        data = package[start:end]
        if filename in MODEL_NAMES:
            data = quantize(data)
        report.append({'file': filename, 'originalBytes': end-start, 'bytes': len(data)})
        begin = offset
        offset += len(data)
        blocks.append(data)
        return '{filename:"' + filename + '",start:' + str(begin) + ',end:' + str(offset) + '}'
    script = re.sub(pattern, replace, script)
    if not MODEL_NAMES.issubset({entry['file'] for entry in report}):
        raise ValueError('Expected models missing')
    script, count = re.subn(r'remote_package_size:\d+', f'remote_package_size:{offset}', script)
    if count != 1:
        raise ValueError('Unexpected Emscripten package format')
    (output / (name + '.data')).write_bytes(b''.join(blocks))
    (output / (name + '.js')).write_text(script, encoding='utf8')
    (output / 'manifest.json').write_text(json.dumps(report, indent=2), encoding='utf8')
    for asset in ('sherpa-onnx-tts.js', 'sherpa-onnx-wasm-main-tts.wasm'):
        shutil.copyfile(source / asset, output / asset)
    print('Compact TTS data bytes:', offset)

if __name__ == '__main__':
    main()
