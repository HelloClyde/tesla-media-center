# Debug WebGL 算力测试

入口：Debug → WebGL 算力。测试手动启动，切换 Tab、离开页面或进入后台自动停止并释放独立上下文；不共享地图和车模的 WebGL 上下文。

- 能力：渲染器、WebGL 版本、浮点渲染扩展、着色器精度、纹理限制；WebGPU 仅检测接口存在，不代表适配器可用。
- 计算：真实 GPU FP32 矩阵乘法，从 64 阶到所选上限（最多 512）。预热后运行 5 次，取中位数；4 个输出与 CPU 对照，误差超过 0.001 判失败。
- 有效 GFLOP/s 按 `2*N^3 / 耗时` 计算，包含提交、同步、浏览器调度。异步 fence 避免通过 `gl.finish()` 长时间阻塞页面。
- 如独立 GPU timer 可用，且 5 次读数均有效、未出现 disjoint，额外报告 GPU GFLOP/s。该朴素着色器不是优化后的推理内核，更不是设备理论峰值。
- 纹理：每步 4 MiB，写入并抽样读回校验，最多 128 MiB；完成立即释放。这不是显存容量探测，不保证模型分配同样大小也能成功。
- 单次端到端计算超过 250 ms 提前结束；GPU 等待超过 10 秒报错。已提交的 GPU 工作不能即时撤回。
- 测试结果直接显示在页面上；通过测试仅说明基础计算可用，真实模型还需要算子兼容、模型加载和推理延迟测试。

接口依据：[WebGL 2 规范](https://registry.khronos.org/webgl/specs/latest/2.0/)、[浮点渲染扩展](https://registry.khronos.org/webgl/extensions/EXT_color_buffer_float/)。

本机 Edge / RTX 4090 已验证计算正确性、32 MiB 分配、手动停止和切换 Tab 清理；不能替代车机实测。
