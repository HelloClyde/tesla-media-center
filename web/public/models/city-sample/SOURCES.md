# Vehicle street sample assets

## Buildings
- Author: Quaternius, Downtown City MegaKit (free Standard edition).
- Source: https://quaternius.com/packs/downtowncitymegakit.html
- Download: https://quaternius.itch.io/downtown-city-megakit
- License: CC0 1.0; original notice in LICENSE.txt.
- Selected: Building_Large_2, Building_Medium_2_001, Building_Small_1 and their textures.
- Processing: combined GLB, shared materials/textures, maximum 1024-pixel textures, Meshopt geometry compression. Runtime clones share geometry and textures.
- Rebuild with Node 22.12+ from repository root: `node tools/vehicle-model/prepare-city-sample.cjs <extracted-gltf-directory>` after installing web development dependencies. Place the three glTF files, binary buffers and referenced PNG textures together in that directory.
- No paid engine project or paid interior shader is included. Window interior images are those supplied with the free models.

## Asphalt
- Author/source: ambientCG, https://ambientcg.com/view?id=Asphalt012
- License: CC0 1.0, https://creativecommons.org/publicdomain/zero/1.0/
- Files in ../../textures/city-sample: 1K JPG color, OpenGL normal and roughness from Asphalt012_1K-JPG.zip. Runtime overlays the app's lane markings on the color texture.

This is a lightweight browser street sample, not a complete AAA scene. Desktop rendering is verified; vehicle-browser frame rate and initial load time still require on-device testing.

## Realistic tree sample
- Source: https://polyhaven.com/a/island_tree_01 (Poly Haven, CC0).
- 1K glTF source obtained using https://api.polyhaven.com/files/island_tree_01 (Powered by Poly Haven).
- Prepared by tools/vehicle-model/prepare-tree.cjs: weld, simplify, shared textures, Meshopt compression. Original sources are kept outside the runtime bundle in .local-data/tree-source.

## Generated brick albedo
- Runtime asset: ../../textures/city-sample/brick-realistic.jpg.
- Generated with the built-in image_gen tool, editing Quaternius T_RedBrick_BaseColor.png. The tool does not expose a selectable model version.
- Prompt: Edit target: supplied brick diffuse texture. Produce a photorealistic PBR base-color texture for a real weathered New York red-brown clay brick facade. Keep every brick boundary, mortar joint, row count, stagger, and UV layout exactly in the same position as input, square full-bleed. Replace flat cartoon fill with subtle authentic fired-clay grain, pores, small chips, varied brown muted red mineral coloration, aged grey mortar and restrained soot/efflorescence. Flat orthographic uniformly diffuse illumination, no directional light, no baked shadows or highlights, no perspective, no windows, no text. Seamlessly tileable all edges. Preserve overall brick scale and moderate contrast. This is a technical albedo map, not a scene photograph.
- Limitation: generated albedo alignment is approximate, not a calibrated scan; existing normal intensity is reduced to avoid overstating correspondence. Other facade textures remain original assets.

## Hidden Alley apartment sample
- Source: https://polyhaven.com/a/modular_urban_apartments_facade, from https://polyhaven.com/collections/hidden_alley.
- License: CC0. Asset metadata/downloads via Poly Haven API (Powered by Poly Haven).
- Only the apartment modules are bundled, not the 1.5 GB complete Blender scene.
- tools/vehicle-model/prepare-alley.cjs assembles four facades with six floors, merges compatible meshes, compresses textures and geometry into alley-apartments.glb.
- Street reflections are captured at 128px per cube face when assets load or day/night changes; they are not continuously updated during driving.

## Runtime size optimization
Run `node tools/vehicle-model/optimize-scene-textures.cjs` after asset preparation. Full-resolution JPEG recompression (4:4:4 chroma); opaque GLB textures are converted from PNG where smaller. No geometry simplification or resolution reduction in this pass. Original inputs backed up to ignored .local-data/scene-size-originals. Street assets: 34,492,627 -> 18,139,066 bytes; vehicle excluded.
