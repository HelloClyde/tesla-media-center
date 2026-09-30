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
- `LicensePlate_Front_*` / `LicensePlate_Rear_*`: Blender-authored rounded mounts
  and separate UV-mapped plate faces. Runtime text is drawn onto one shared canvas
  texture; the faces carry `extras.partType=licensePlate`.

The Tesla status view's **车辆外观** control changes the named body paint material
and both license plates live. It supports custom colors, up to 10 plate characters,
four plate backgrounds and restoring defaults. Preferences stay in this browser's
local storage (`tmc.tesla.appearance.v1`); they are not sent to the vehicle or synced
between devices. Glass, tires and trim retain their original materials.

To update only the plates in an existing editable model, run Blender in background
with `--python tools/vehicle-model/add_plates.py`, then run the optimizer below.
The full rebuild also invokes this plate builder. Existing studio PNGs precede the
plate addition; the `.blend` and runtime GLB contain the updated geometry.

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

## Surface repair (revision 2)

The runtime GLB now includes offline local quadratic normal fitting for painted
panels and alloy wheels. The fit uses an orientation-filtered neighborhood and
bounded normal change; it preserves positions, UVs, material assignments, door
hinges, wheel axles and animation channels. Bumper crease regions are excluded.
This improves triangulation-related reflections, but does not make the original
approximate model an exact CAD surface. The editable Blender file remains the
unbaked source.

After exporting/optimizing the unbaked model, run:

```text
# Python needs numpy; PYTHON can select the interpreter.
node tools/vehicle-model/repair-surfaces.cjs path/to/unbaked-model.glb
```

The candidate is written to `.local-data/model-y/surface-repaired.glb`. Inspect it
before copying it to `web/public/models/2022_tesla_model_y.glb`, then run
`node tools/vehicle-model/validate-model.cjs`. Already baked inputs are rejected.
The runtime recognizes `surfaceRevision: 2` and avoids overwriting baked normals.
