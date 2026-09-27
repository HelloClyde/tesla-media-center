# Model Y 2022 · Blender editable display model

This is a Blender-authored **derivative of the existing pre-refresh Model Y asset**,
not an original from-scratch mesh or Tesla engineering CAD. The shared early Model Y
body is used as the basis for a 2022-style visualization; trim, wheel style and dimensions
are approximate, not a guarantee of a particular 2022 market/trim configuration.

## Attribution

- Original: **2021 Tesla Model Y** by **tonielpro520**.
- Source: https://sketchfab.com/3d-models/2021-tesla-model-y-59e2ead369984b1a85c800ff6cf6789d
- License: [Creative Commons Attribution 4.0](https://creativecommons.org/licenses/by/4.0/).
- Original source asset remains at `web/public/models/2021_tesla_model_y.glb`.
- Changes for TMC: reconstruct disconnected components in Blender, preserve custom
  surface normals, regroup doors with glass/mirrors/handles, add hinge pivots and
  open animations, regroup four wheels with axle pivots, retain fixed brakes,
  revise white paint / smoked glass / dark alloy materials, normalize overall length,
  export an articulated GLB with Meshopt compression. No endorsement by Tesla or
  the original author is implied.

## Files and parts

- `model_y_2022.blend`: editable model, packed textures, studio camera/lights, door animations.
- `closed.png` / `doors-open.png`: Blender renders for visual review.
- `parts.json`: build summary.
- Runtime: `web/public/models/2022_tesla_model_y.glb`.
- `Door_FL`, `Door_FR`, `Door_RL`, `Door_RR`: independent door hinge groups.
- `Wheel_FL`, `Wheel_FR`, `Wheel_RL`, `Wheel_RR`: independent axle groups.
- `Body_Static`: remaining chassis, interior and fixed trim.

L/R are the vehicle's left/right viewed in the direction of travel.
Blender: X across car, Z up, front points toward -Y.
glTF: X across car, Y up, front points toward +Z.
Doors rotate around local glTF Y using `extras.openAngle`; all wheels rotate around
local X with `extras.spinDirection=1`. Do not flatten these nodes during optimization.
The Tesla view's door preview is local visualization only, never a vehicle command.

## Rebuild

Run from repository root with installed web dependencies, Node 22+ and Blender 5.1:

```text
node tools/vehicle-model/prepare-source.cjs
blender -b --python tools/vehicle-model/build_model_y.py
node tools/vehicle-model/optimize-model.cjs
```

The source decoding intermediate is placed under ignored `.local-data/model-y`.
The build writes the editable asset, preview PNGs and runtime GLB. Blender backup
files (`*.blend1`) are not part of the deliverable.
