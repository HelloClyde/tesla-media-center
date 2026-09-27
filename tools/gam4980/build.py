"""Build with clang + lld (e.g. Ubuntu clang 18), no SDK or emscripten needed."""
from pathlib import Path
import subprocess, zipfile, argparse
ROOT=Path(__file__).resolve().parent
parser=argparse.ArgumentParser()
parser.add_argument('--output',type=Path,default=ROOT.parents[1]/'web/public/gam4980')
OUT=parser.parse_args().output.resolve()
OUT.mkdir(parents=True,exist_ok=True)
exports=['web_rom8','web_rome','web_init','web_load','gam4980_game_storage','gam4980_run_frame','gam4980_framebuffer','gam4980_key_down','gam4980_set_lcd_theme','gam4980_save_data','gam4980_save_dirty','gam4980_save_mark_clean','gam4980_shutdown_requested']
subprocess.run(['clang','--target=wasm32','-O2','-nostdlib','-ffreestanding','-fno-builtin','-I',str(ROOT),str(ROOT/'web.c'),str(ROOT/'gam4980_core.c'),'-Wl,--no-entry','-Wl,--export-memory','-Wl,--initial-memory=8388608','-Wl,--max-memory=8388608',*[f'-Wl,--export={f}' for f in exports],'-o',str(OUT/'core.wasm')],check=True)
with zipfile.ZipFile(OUT/'source.zip','w',zipfile.ZIP_DEFLATED) as z:
    for name in ['web.c','bda_sdk.h','gam4980_core.c','gam4980_core.h','s6502.c','COPYING','README.md','build.py']:
        z.write(ROOT/name,name)
