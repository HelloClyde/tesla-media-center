# TMC GAM4980 WebAssembly port

Core: https://github.com/HelloClyde/BBK9588-gam4980
Pinned revision: 73b884a056ca0595de1552e6e365138687fb25a1
License: GPL-3.0 (COPYING). The three core files are unmodified upstream sources.
web.c and bda_sdk.h replace the device memory helpers with a freestanding browser bridge.
The bundled 8.BIN and E.BIN are copied from the upstream runtime directory; no games are bundled.

Build: install clang and lld, then `python3 tools/gam4980/build.py` from the TMC checkout.
The command produces core.wasm and its complete corresponding C source/build archive source.zip.
The worker and Vue frontend sources are part of the TMC source tree.

Runtime: dedicated Worker, bounded 60 Hz stepping, RGB565 canvas, browser-local per-game saves.
The upstream core has no audio output bridge; this port does not claim sound support.

To rebuild an extracted source.zip independently: `python3 build.py --output ./dist`.
Browser smoke check: `node tools/gam4980/test.mjs` exercises the bundled ROM boot and an original 6502 diagnostic program (no commercial game required).

The application icon web/public/icon/GAM4980_LOGO.png is the unmodified assets/gam4980-icon.png from the same pinned upstream revision.
