# Nearby-vehicle warnings from the pinned APK

Status: the push entry and basic warning metadata/scene schema are recovered.
`vehicle_warning_push.py` is an offline schema decoder only. **TMC cannot yet
receive or announce live nearby-vehicle warnings.** No frontend warning, polling
endpoint, GPS-only inference, fake nearby vehicle, or Android runtime dependency
has been added.

## Source identity

- APK: AMap 17.00.0.2005, APK SHA-256
  `022c844511dce2958fd37c8d0941feb72587a434701debc9b2fda3e69ec07152`.
- `lib/arm64-v8a/libamaphorus.so`, SHA-256
  `cc8bc29dfb2116e7d6289e0f5fcd613c5e76d8fc396dc9ceafd3436ade004684`.
- Addresses below are ELF virtual addresses for that library, not another version.
- AJX references are paths inside the APK's `bundles.oajx`; extracted copies
  and binary analysis artifacts stay under ignored `.local-data/amap-app`.

## Confirmed delivery and native consumer

1. `TripAccsService.js` registers `AMAP_TRIP_SERVICE`, accepts callback
   `messageType === 5`, parses the JSON `data`, and broadcasts the active
   `trip_navi` scene's records. Registering the scene updates a local set; it
   does not serialize an HTTP subscription.
2. `TripNaviStateEyrieEventUtil.js:registerAccsTrafficData()` filters records
   with `moduleType === "horus"` and sends
   `kDynamicInfoAction / kPushInteraction` (action 12), value
   `{interactionHorus: records}`. TBT records go separately through action 13.
3. The native action dispatch posts event `0x1fbd3`. The observer at `0x7c85f4`
   accepts that event, forwards its payload through `0x7c8640`, and calls
   `0x7c9e24` at `0x7c868c`.
4. `0x7c9e24` parses `interactionHorus` through `0xc80278 -> 0xc8bfb4`.
   Reflected records use **numeric** `bizType` and string `bizData`
   (`0xc8bf60`). The whole interaction is checked for the literal
   `trafficserviceJson`; that literal must not be substituted for the numeric
   record field. `0x7c9ea0` calls the `bizData` consumer at `0x7c9efc`.
5. The consumer reaches `0xc81068 -> 0xc810a0 -> 0xc968a0`, which parses
   `metaInfo` and `data`. `data.v2xSafe.show` reaches `0xc91954`.
6. Accepted data is cached under `component.MeetWarningData`
   (`0x7c8a04`, literal reference at `0x7c8a9c`). Duplicate scene handling is
   present at `0x7c88d0`; this is not yet ported into a production warning loop.

The native scene-name constants include `curveMeet`, `nodeMeet`, `rearFastCar`
and `rearFastTruckRemind`. Additional constants include `slowVehicle`,
`emergencyBreaking`, `truckOvertake`, `truckRemind`, `bycCurveMeet` and
`bycOvertake`. Their presence does not prove that every scene is available on
every road or that a particular HTTP request can return one.

## Recovered fields and a correction

| Object | Fields | Parser |
| --- | --- | --- |
| `metaInfo` | string `pushId`, integer `pushType`, string `pushTime` | `0xc93304` |
| `data` | `v2xSafe`, `smartDrive`, `speedRoute` | `0xc96524` |
| `v2xSafe` | `show` | `0xc96438` |
| `show` | string `sceneType`, integer `warningLevel`, `curveMeet`, `nodeMeet`, string `sceneData`, `guardData` | `0xc91954` |
| `curveMeet` | `actionsOnCurves` | `0xc8e2b8` |
| an action on a curve | `curveInfo`, `meetActions` | `0xc8db8c` |
| `curveInfo` | `curveId`, `accLinks`, `oppLinks`, `curveStartPoint`, `curveEndPoint`, `curveMidPoint`, `turnAction` | `0xc8d67c` |
| a meet action | `actionId`, `otherVehicleType`, `meetRange`, string `meetTs`, `otherTPsOverTime` | `0xc8d170` |
| `nodeMeet` | `actionsOnNodes` | `0xc8f70c` |
| `guardData` | integer `guardType`, string `data` | `0xc91900` |

An adjacent **different** object, `commonParameter`, has string `pathId` and
`traceId`, parsed at `0xc93374`. Initially following the neighboring call
mistakenly suggested these were `metaInfo` fields. The exact call
`0xc9610c -> 0xc93304` confirms that warning `metaInfo` uses push metadata.
Do not bind warnings to a route using an invented `metaInfo.pathId` field.

The offline decoder preserves the push clock and scene data as opaque strings.
It does not assign a clock unit, expiry, geometry, vehicle position, voice text,
or warning severity from unverified values. Nested meeting geometry and the
native selection/animation/voice consumers still require further recovery.

## What prevents a usable browser + Python integration

The verified source above is an App push channel. TMC's working routeguide and
ETA HTTP paths do not establish an ACCS session. The examined accepted ETA
responses contained `onlineNavi`, but no `v2xSafe`/`rearFastCar`/`curveMeet`
records. Examined dynamic-navigation response samples did not establish an
HTTP equivalent. Absence from those samples is **not** proof that no HTTP
equivalent exists.

The ACCS client binds the App separately and requires a device/App signature.
The pinned Java initialization uses SecurityGuard, whose request type 3 calls
router command 10401; it does not use the existing AOS signing formula.
The previous mode-0 provider investigation and binary frame/handshake findings
are recorded in `TRAFFIC_SIGNAL_RESEARCH.md`. No authenticated Python bind or
validated nearby-vehicle push capture exists in this workspace.

The APK additionally performs scene checks and native road/vehicle matching.
Once transport is available, a live payload must establish the push clock,
lifetime, route/link matching, vehicle samples and prioritization before
displaying or speaking warnings. Copying an icon and assigning a timer cannot
substitute for that input.

## Reproducible checks

```powershell
.venv/Scripts/python.exe -X utf8 tools/amap-app/verify_vehicle_warning_schema.py --apk .local-data/amap-app/amap-release.apk
.venv/Scripts/python.exe -X utf8 -m pytest tools/amap-app/test_vehicle_warning_push.py -q
```

The verifier pins the native library digest and checks 14 field declarations
and 10 direct calls. It validates disassembly evidence, **not** a successful
push connection or running warning behavior. The decoder tests use explicitly
synthetic schema cases and cover malformed records, unrelated scenes, missing
metadata, invalid integer types, byte limits and record limits. They are not
live server fixtures.
