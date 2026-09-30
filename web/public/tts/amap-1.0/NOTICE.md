# Browser voice components

- `amap-mnn.js` and `amap-mnn.wasm` are built from Alibaba MNN 3.1.1,
  commit `e552986eceb10905a6e015b8cfe847fb0d82a46b`. MNN states Apache-2.0
  in its README; the license text is in `MNN-LICENSE.txt`.
- `amap-core.js` bundles `pinyin-pro` 3.29.4 (MIT); its license is in
  `pinyin-pro-LICENSE.txt`. Other application code is in this repository.
- `am_encoder.mnn`, `am_decoder.mnn`, `ddspganV2_f0.mnn`,
  `ddspganV2_ctrl.mnn`, and `am_dict.json` are extracted at build time from the
  checksum-pinned AMap 17.00.0.2005 APK. The project owner confirmed on
  2026-09-30 that these voice models may be publicly distributed with this app.
