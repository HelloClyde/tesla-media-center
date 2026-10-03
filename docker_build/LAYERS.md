# Docker resource layers

The image separates application code from immutable/rarely changed assets:

- Python dependencies: invalidated only by requirements or the Python base image.
- `/opt/tmc/amap-app`: five verified runtime extracts (native libraries, styles and certificate), copied with `--link`; the full APK stays outside the Docker context.
- `web/dist/tts`, `models`, `textures`: independent native-platform compression stages and linked runtime layers.
- Remaining public files: separate compression stage (top-level files, catalogs, gam4980, icon, vendor).
- Python source and frontend JS/CSS/HTML: small linked layers after the resource layers.

`TMC_SEPARATE_PUBLIC=1` makes Vite skip copying public files into its output. Ordinary local builds still include public files. The runtime assembles resources and code under `web/dist`; `web/public` is a compatibility symlink for the backend catalog reader. Assets are no longer stored twice.

When adding a new top-level directory under `web/public`, add its COPY instruction to an asset stage. Do not reintroduce a whole-public copy in the runtime or web-builder. The precompression script accepts an optional directory argument; each asset family is compressed independently.

BuildKit is required (`COPY --link`); CI already uses Buildx and `gha` mode=max caching. The first build after this layout change creates new layers. Later code-only builds should reuse asset compression and blob digests. Registry transfer speed and cache eviction can still affect release time; this does not cache the workflow's external downloads.

Validation: build twice, changing only frontend or Python source for the second build. Check that asset-stage RUN steps and linked resource COPY steps are CACHED, and that the runtime still serves `/index.html`, `/models/...`, `/tts/...`, and the GBA catalog. A model update should invalidate only the model family, not the extracted map resources, TTS, or textures.
