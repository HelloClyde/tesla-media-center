# Tesla app Model Y (2020–2024) local asset

TMC prefers `web/public/models/tesla-model-y-2020-2024.glb` in the vehicle status view and AMap 3D navigation. If the file is absent, it uses the repository's existing CC-BY 2022 display model. The Tesla asset is intentionally ignored by Git and must be provisioned on each machine that builds the site.

The local file was extracted from the Tesla Android 4.61.0-4607 XAPK. The base APK and `assets_pack.apk` both verified with Android `apksigner` against certificate SHA-256 `f27a58479622c8d7bfcd87cb30e9800915761191f6ef7b268e30476e9d7a0e71`. The [tesla-model-extractor](https://github.com/koenhendriks/tesla-model-extractor) `unreal --models y_high --paint PearlWhite` export produced `Y_High.glb`; Meshopt geometry compression and WebP textures at quality 90 reduced the local runtime copy from 11.0 MB to 2.82 MB without removing its 13 animations. A glTF validation run found no errors or warnings. The WebP conversion decodes Meshopt, so the final Meshopt pass must run after WebP conversion.

The Tesla model, textures, and animations are Tesla-owned material. Keep the XAPK, recovered project, and GLB in local ignored paths; do not add them to the public repository or container image published from it.
