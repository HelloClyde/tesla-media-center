# AMap live traffic-signal path

The examined `amap-release.apk` keeps live signal events inside the Android
navigation process. In `libamaptbt.so`, the endpoint registry has a
`traffic_signal` entry with base VA `0xf4e678`, name at `0xf4e698`, path
`ws/shield/trafficlights/realtime` at `0xf4e6a0`, request number **`0x6e`**,
and two zero selector fields. The next entry, beginning at `0xf4e6a8`, has
number `0x6f` and is `driving_behavior`. Earlier analysis incorrectly
attributed the following entry's number `0x6f` to `traffic_signal` because
the 0x30-byte registry records were offset by 0x10. The lookup loop at
`0x673354` checks the number and both selector fields, starting at
`0xf4de38`, for 87 entries; entry index 44 is `traffic_signal`.

The identifiable `0x6f` sender at `0x670a40` accepts a caller-provided byte
buffer. The nearby serializer at `0x66fc54` / `0x67075c` includes
`eventList`, `maxAcceleration`, `speedRestriction`, `speed`, and `naviID`;
that is driving-behavior telemetry, not evidence of a realtime-signal request
body. A scan of the direct callers of request allocator `0x6738ac` found the
`0x6f` sender at `0x670afc`, but no direct call with constant `0x6e`. Several
callers supply a variable request number, so this is not proof that the
`traffic_signal` registry entry is unused. Its actual sender, selector,
request body, and response handler remain unidentified. The inspected AJX
navigation scripts contain display and voice handling, but no request builder
for this endpoint.

The remaining variable-number allocator call at `0x79b85c` is now resolved.
It loads the request number from a map entry at `+0x34`. The map is initialized
by constructor `0x79b6a4`, which copies the constant pair at `0x112a28`:
map key `21` and request number `0x135` (`309`), with auxiliary value
`0x491`. The constructor inserts that entry through `0x79b760`; a direct-call
scan finds no other insertion into this map. Thus this variable call is for
request `0x135`, not a hidden `0x6e` sender. The other variable-number call
at `0x6bede8` is the ETA/TMC selector described below. This narrows the
unresolved `0x6e` path to an indirect send through another allocator entry
point, a registration-only endpoint, or code not reached by these callsites;
it does not establish that the endpoint is usable outside the Android process.
The direct-call scan also finds 22 calls to common sender `0x673354`.
They pair with the identified allocator callsites and expose no separate
direct sender for request `0x6e`. This is evidence about this binary's static
call graph, not proof that a dynamically dispatched sender cannot exist.
The registry row's relocated host strings are both `aos.m5`, so its URL is
`https://m5.amap.com/ws/shield/trafficlights/realtime`. A bounded reachability
probe on 2026-10-01 returned HTTP 405 / code 11 for GET, and HTTP 200 /
code 3 (`Params error`) for an empty JSON POST. The endpoint is active and
POST-only under those probes, but neither response establishes a valid
request body or a live signal feed. A fresh disassembly scan of the entire
executable section (skipping embedded non-instruction bytes) again found
direct allocator calls for neighboring IDs `0x6d`, `0x6f`, and `0x70`, but
none for `0x6e`. The possible indirect sender remains unidentified.

For one-time runtime evidence, the official APK was installed in a local
Android 11 API 30 x86_64 emulator that advertises `arm64-v8a` through
`libndk_translation`. Installation and initial startup succeeded, but the
App exited on `SIGILL`: tombstones identify unsupported ARM64 `fcvtzs`
instructions in `libtnet.so` and `libamapr.so`. This is a translator failure,
not evidence about the traffic-signal endpoint or an anti-bot response.
The x86 emulator was stopped. A native ARM64 image was then fetched for a
second local test; any emulator is research-only and is not a TMC runtime
dependency. While fetching the official image, `Accept-Encoding: gzip`
produced a transfer length different from the SDK manifest; explicitly
requesting `Accept-Encoding: identity` yielded the manifest's exact byte
length. The 1,244,324,730-byte archive passed its published SHA-1
`0e66987d6b4db2e278af83d453ce5d74a7e6ced3`.

The standard Android Emulator launcher rejects this ARM64 AVD on an x86_64
host before boot. A direct, research-only invocation of its AArch64 QEMU
backend reaches the Android `ranchu` machine when the launcher directory is
set explicitly; a copy of the backend was patched to omit the HDA sound-card
argument (the ARM `ranchu` machine has no PCI bus), and the unsupported
virtio-Wi-Fi feature was disabled. This boots the native ARM64 Android kernel,
mounts `super` and `/data`, and brings up ADB with `arm64-v8a` as the sole ABI.
It does **not** produce a usable App session: stock Android `zygote` repeatedly
segfaults in `/system/lib64/libcodec2_vndk.so` during static initialization,
and the graphics composer aborts, so the home screen never finishes booting.
The same `libcodec2_vndk.so` crash was seen using a separate generic AArch64
QEMU machine. These failures are in the test environment before the AMap APK
runs; they do not validate or refute any traffic-signal protocol hypothesis.
No live ACCS or HTTP traffic-signal payload was captured.
As a compatibility control, the official Android 9/API 28 ARM64 image was
downloaded with identity encoding and passed its published SHA-1
`28f59164bdb4cb18f1a1060f1880450e06cf4d10`. Under the same direct
AArch64 QEMU backend it mounts `/data` and exposes ADB, but multiple stock
audio/media processes segfault with the same impossible high-bit fault-address
pattern, and `zygote`/`system_server` do not stay up. The failure therefore
is not specific to Android 11's `libcodec2_vndk.so`; this local software
emulation path cannot currently provide a usable official-App capture.

A separate JSON response parser in `libamaptbt.so` has now been traced from
the byte-buffer handler `0x6cf88c` through top-level `data` (`0x6ddb68`),
`data.radar` (`0x6ddd5c`), and `data.radar.popLights[]` (`0x6ddf98` / vector
parser `0x6e8af8`) to each light record parser `0x6e9874`. A light record
reads `countDown`, `countDownDistance`, `state`, `stateDistance`, `location`,
`nodeId`, `linkId`, `greenEndOffset`, and `dirs`. This is a real APK parser
chain for signal data. The response dispatcher at `0x6cf268` also has a
special token `0x7fff` branch (`0x6cf2a0`), and navigation setup at
`0x6cde30` registers a listener with that token. The exact relationship
between this push-style response and registry request `0x6e` is still
unproven; neither the outbound payload nor a successful response has been
reproduced.

The native field types are now resolved. `countDown`, `state`, and `location`
each call `0x6e998c` / `0x6e9a48`, which read a nested `{lon,lat}` pair as
two doubles; **`countDown` is a coordinate here, not a countdown in seconds**.
`countDownDistance`, `stateDistance`, and `greenEndOffset` use the 32-bit
integer reader `0xd0c01c`; `nodeId` and `linkId` use the 64-bit reader
`0xd0c0ac`. Each `dirs[]` record (`0x6e9cd0`) has 32-bit `dir`, `showType`,
`phase`, `lightType`, and `controlLight`, plus `lightStates[]`. Each state
(`0x6e9fb8`) contains 32-bit `type`, `signalTag`, `signalChange` and 64-bit
`stime`, `etime`. `tools/amap-app/eta_pop_lights.py` preserves this typed
schema from an already-successful JSON body. Numeric phase meanings and
time-base units have not been verified against a successful capture; this
decoder must not be used to show a live countdown yet. The distinction also
explains why the existing `eventType=26403` / `statusInfos[]` parser cannot
simply consume `popLights[]`: they are different native message shapes.

The parsed `popLights[]` vector is consumed at `0x6d0be0`. That function
passes it through virtual method slot `+0x10` of the object held at navigation
engine offset `0x1038`; `popMultiLights[]` uses slot `+0x18`. The object is
installed by constructor `0x739860`; the slots resolve through its vtable
at `0xf528d0` to `0x7399e8` and `0x739c78`. `0x7399e8` copies incoming
light records into the engine's own 0x70-byte record vector and updates the
selected light index. This closes the APK's `data.radar.popLights[]` parser-to-
engine path. The corresponding navigation-update network operation is traced
below; its connection to the separate `traffic_signal` request `0x6e` is not
established.
The direct `0x6e` sender remains absent among calls to request allocator
`0x6738ac`; a computed request number or a dormant registry entry are both
possible.

Further callback tracing identifies a separate, concrete route for the
`popLights[]` parser. Navigation's send path at `0x6ce528` calls `0x6d2610`
with internal message kind `11` and a serialized navigation payload assembled
earlier in the same routine (`0x6ce220`–`0x6ce3b8`). `0x6d2610` obtains a
request token at `0x6d2664`, records kind `11` against it at `0x6d2778`
(`0x6ce6bc`), then sends through the transport object at engine offset
`0xf48` (`0x6d283c`). That object's listener is registered with reserved
token `0x7fff` at `0x6cde94`. The response dispatcher `0x6cf268` assigns
kind `11` to token `0x7fff` directly, or retrieves the kind for an ordinary
request token from its tracking table (`0x6cf314`–`0x6cf358`). Kind `11`
buffers are parsed by `0x6cf88c`, and the same dispatcher calls the
`popLights[]` consumer at `0x6cf624`. Thus the native navigation send,
response parser, and light-consumer path are linked by internal kind `11`.
This kind is **not** the registry request id `0x6e`; the required session
state and relation to the standalone `traffic_signal` endpoint still require
verification.

The object at engine offset `0xf48` is the transport subobject installed by
`0x6b9f2c` (`0x6ba0e0`). Its vtable starts at `0xf50d40`; method slot
`+0x10` resolves to `0x6bf7b4` / `0x6bf6cc`. That method treats `0x7fff`
as a reserved listener registration (`0x6bf700`–`0x6bf728`) and ordinary
tokens as send operations (`0x6bf72c` onward). This confirms that the
`0x7fff` path is a subscription/control operation, not request id `0x6e`.
There is also a distinct **zero-payload control-send** branch that earlier
probes missed. `0x6becbc` passes its send-mode bit to `0x6bf0f4`. If the
transport's JSON string at `+0x120` is empty and the bit is zero,
`0x6bf15c`–`0x6bf1c4` builds `cpcode=<value>&deviceId=<value>`, wraps it
in escaped CDATA markers for the later XML fragment, sets the inner ETA flag
to `2`, and supplies reserved token `0x7fff` for the reply. The `cpcode`
value is chosen at `0x6bf7bc` from process-global configuration offsets
`0xf93518` or `0xf93538` according to a navigation mode; `deviceId` is read
from `0xf93528`, the same global string used for XML `Uuid`. These are
application-supplied runtime values, not fields in a 5.1 planned route.
The same sender is invoked in mode zero through transport virtual slot
`+0x128` for several lifecycle events: callsites `0x6bb3a8`, `0x6bb4e4`,
`0x6bb704`, `0x6bbb9c`, `0x6bbc04`, and `0x6bbc74` load event codes
`8`, `7`, `9`, `2`, `4`, and `5` respectively as the builder's `ReqType`.
Their semantic names, especially which starts a navigation session, still
need to be tied to the navigation service. This establishes a concrete
request family preceding or accompanying kind-11 JSON updates; the previous
Python probes exercised only `ReqType=3` update bodies and did not reproduce
the App's control flow. It remains a hypothesis, not yet proven, that a
missing control request explains the 53-byte frame.
A bounded parser probe used the newly traced control-body shape with
`ReqType=2`, first with blank `cpcode`/`deviceId` and then with a candidate
APK account value. Both returned the same 53-byte frame. Subsequent Java
tracing resolves the value: `kh6.createModule()` copies
`ConfigerHelper.TBT_ACCOUNT` into `TBTInitConfig.mUserCode`; that key is
loaded from the APK's `assets/amap_configer.data`, whose account value was
compared in memory with the earlier candidate and matches exactly. The
asset's password is not needed for this request probe and was not sent or
recorded. `mDeviceID` comes from `NetworkParam.getDiu()`, whose supplier in
this pinned APK returns the empty string. Native config setter `0xcef57c`
copies its six string fields into globals `0xf93518` through `0xf93540`;
the first field feeds `cpcode`, and the third feeds `deviceId` and root
`Uuid`. This ties the observed empty device identity to the App init path,
subject to runtime overrides not yet observed.
The `nativeCreateTBTModule` JNI wrapper at `0x4a93a8` reads the eight
`TBTInitConfig` fields by name; its six account/batch/device/password/motor
strings are passed in that order. This fixes the native setter's first and
third field mappings without relying only on their offsets.

One controlled request then used the actual APK account, empty device ID,
explicit `Uuid=""`, `ReqType=2`, and the verified/default root attributes
(`DataVers`, `Zip`, `Flag`, `ContentOptions`, `EtaOptions`). It again returned
HTTP 200 with the 53-byte binary frame, including the expected version and
Zip echoes. A sequential request on the same freshly planned route sent
that control request followed immediately by `ReqType=3` with three
GPS-history samples near its first decoded traffic light; both replies were
the same 53-byte no-event frame. This excludes missing `cpcode`, empty
`Uuid`, and this simple control-then-update ordering *alone* as explanations.
The probe still lacks a real native navigation session and a faithful
active-update JSON payload; it does not establish that `ReqType=2` is the
session-start event or that the selected light has live coverage. The
`GuideService.startNavi(int)` JNI wrapper at `0x49b484` dispatches to
guide-engine virtual slot `+0x78`, whereas the `ReqType=2` callsite belongs
to the separate transport object's slot `+0x68`; their connection must be
traced before assigning lifecycle semantics.
The preceding `GuideService.setNaviPath(GNaviPath, int)` JNI wrapper is
`0x49b584`, dispatching the selected path through guide-engine slot `+0x50`.
The Java `GNaviPath` contains `long[] pathPtrs`: references to native route
objects, plus strategy and request POI data. A 5.1 route's `NaviID` string
is consequently only one field of the App's navigation context. The Python
probe has not reconstructed those native path objects or called the guide
engine's path-install and start sequence. The later JNI-registration check
below shows this particular `GuideService` binding may be dormant in the
current App, so it cannot by itself identify the live session setup behind
the empty 53-byte response. Server-side entitlement/coverage and the exact
kind-11 response transport remain separate unknowns.

The ordinary send reaches main transport vtable slot `+0x128`, which resolves
to `0x6becbc`. It assembles the outgoing payload with `0x6bf0f4` and
`0x6c5f6c`, then at `0x6bede8` allocates an AOS request using the number
returned by `0x6ba2c8`. That selector returns only `2`, `0x67`, or `0x0d`
under the observed branches. Their registry names and paths are respectively
`tmc_car` / `ws/transfer/navigation/etatrafficupdate/`, `tmc_truck` /
`ws/shield/truck/etatrafficupdate/`, and `tmc_car_elec` /
`ws/transfer/navigation/etatrafficupdate/charging` (with alternate
`ws/lbs/navigation/etatrafficupdate/` variants selected by a second registry
field). Therefore this particular kind-`11` feed is the navigation ETA/TMC
update channel, **not** a call to `ws/shield/trafficlights/realtime`. Its
response can still contain `data.radar.popLights[]`. Whether those entries
give usable live phases and countdowns throughout navigation must be checked
against a successful response; the dedicated request `0x6e` remains separate.
The registry's id-2 records are two distinct entries. Row `0xf4de38`
selects host alias `aos.nvg` and
`ws/transfer/navigation/etatrafficupdate/`; row `0xf4de68` selects
`aos.m5` and `ws/lbs/navigation/etatrafficupdate/`. Java host table
`ky1.java` maps `aos.nvg` to `https://nvg.amap.com/`. The common sender
`0x673354` matches both request id and the two selector fields, so a hard-
coded `m5` path is not equivalent to the primary registry row. A bounded
empty POST to the nvg transfer path returned HTTP 400 / JSON `code=2`, as
did an empty POST to the same transfer path on m5. An empty POST to the
*registered* m5 fallback path `/ws/lbs/navigation/etatrafficupdate/`
instead returned HTTP 200 with an empty octet-stream body. These only
establish reachability and divergent error behavior; none is a successful
navigation response or evidence of which row a real session selects.
The second registry selector is computed at `0x6733b8` by `0xcefb38`:
it reads a native mode word from the common request context at offset
`+0xc0` (locked accessor `0x4adc00`) and returns `1` only for values
`11`, `12`, or `13`; otherwise it returns `0`. The common sender matches
that selector against the row's second word (`0x6733f4`–`0x6733fc`).
Thus selecting the m5/lbs fallback depends on navigation runtime mode,
not on the endpoint path alone. The meaning of modes `11`–`13` and the
mode used by TMC's browser-only navigation are not yet established.
For the ETA/TMC request object, `0x6bee54` stores common-parameter mask
`0x491` at request offset `+0x18`. The common sender's mask dispatcher
`0x67314c` checks each bit and resolves the string keys in the pinned
binary: bit `0`=`channel`, bit `4`=`diu`, bit `7`=`div`, and bit
`10`=`_aosmd5`. This is the actual parameter set selected by `0x491`;
it is not equivalent to the minimal channel-only route-plan request.
The resulting values and sign/encryption placement still need tracing.
The outbound method and payload placement are now less ambiguous. Request
allocator `0x6738ac` calls constructor `0x67397c -> 0x673bb8`, which sets
request offset `+0x38` to `1` and adds an `sdk_version` request parameter.
The ETA/TMC caller does not overwrite that method field. Its send call
`0x6bef38 -> 0x6c1904 -> 0x673354` passes the generated XML buffer and its
length; the common sender checks `+0x38 == 1` at `0x673594`–`0x6735ac` and
places that buffer/length into its outbound body slot at `0x6735a4`–
`0x6735ac`. This is the native POST-body path, while request parameters and
headers are assembled separately. The subsequent HTTP bridge and server-side
acceptance still need verification.
The mask dispatcher is also more precise than "adding four common values":
`0x67314c` tests the request mask, then inserts the literal **key names**
into a linked-list field at outbound context `+0xc0` through `0x5874d4` and
`0x587488`. It only does so if a context flag at `+0x918` is set
(`0x673174`–`0x673198`). It does not read the Java `diu` or `div` values in
this function. Those values, the final digest, and any encryption must be
resolved downstream; the Java provider values below remain candidates until
that boundary is traced. Request-specific key/value pairs from the request
object's `+0x40` map are processed by `0x6736d8` before this sign-key list
is attached. Keys beginning with `header:` are separated into the header
collection; other keys, including the constructor's `sdk_version`, follow
the request-parameter path.
The APK's Java `AosPostRequest` independently confirms method code `1`
means POST (`setMethod(1)` in its constructor). With a non-null raw body in
its `f` field, `createHttpRequest()` sets that body, and `processParams()`
puts common and explicit parameters in the URL query before the parent
`AosRequest.buildHttpRequest()` encrypts that query under `ent=2&in=...`.
This matches the native method/body separation, but the native transport
vtable target at `0x6735c0` has not yet been proven to instantiate this
specific Java `AosPostRequest`; the final wire bytes remain unobserved.
For this pinned APK, the Java `NetworkParam.getDiu()` provider is
`NetworkParam.i.get()`, whose decompiled implementation returns the empty
string. `NetworkParam.getDiv()` returns `rl1.c`, resolved through the
package's initialization chain below. The presence of the `diu` key in
the mask therefore does not prove a nonempty device ID is sent or signed
in this build; the exact native common-parameter provider still needs a
runtime or dataflow comparison.
JADX single-class extraction of `rl1`, `gq0`, and `hq0` resolves the Java
`div` fallback. `rl1.c = gq0.d`; `gq0.d` defaults to `ANDH170000` unless
`hq0` loads a nonempty `div` property from `buildTypeConfig.data` or
`incrementalBuildConfig.data`. Neither asset exists in this pinned APK's
ZIP listing, so this package's Java provider returns `ANDH170000` under
the inspected initialization path. This narrows the candidate sign input
but does not alone prove the native ETA/TMC sender uses the same provider.
The existing isolated `native_signer.load_material()` plus
`aos_request_sign.sign_input()` successfully constructs a 57-character
candidate sign input and 32-character digest from the four mask keys with
this package's Java `diu`/`div` values. The material itself is not printed
or stored. This is an offline consistency check, not proof that the ETA/TMC
HTTP request will pass its server-side checks.
The ETA transport probe now uses that same tested sign-field assembler instead
of a separate hard-coded MD5 expression. The four native mask keys reduce to
`channel` plus `div` for the inspected Java provider because `diu` is empty
and `AosRequest` removes `_aosmd5`; the separately added `sdk_version` is not
in mask `0x491`. In the native request constructor, `0x673c04` passes zero
to `0x8097a0`, selecting literal `17.00.0.1007` for `sdk_version`; the probe
uses that value. These checks eliminate a drift between our two *candidate*
signing implementations. They do not establish that the native C++ sender
uses the Java provider or that its HTTP bridge produces the same wire query.
The XML root audit also finds a conditional `InteractionMode` attribute at
`0x6c6564`–`0x6c6574`, sourced from navigation-context offset `+0x508` and
only emitted when the string is nonempty. The current probe omits it, along
with some other runtime attributes; the 53-byte `etaCode=2` cannot therefore
be attributed to navigation-session rejection alone.
A fresh, bounded route-invoker-`navi` control/update probe added the four
always-emitted attributes `PathSwitch`, `SceneFlag`, `privacy`, and `BizScene`
at zero-state candidate values to the prior APK-account, near-light GPS,
native flag, route `DataVers`, and source/invoker request. The control and
following update both returned HTTP 200, 53-byte headers with native result
code `2` and zero payload. Their absence alone therefore did not explain the
rejection. The test still lacks an observed live navigation context, and the
zero-state candidate values are not a capture of the actual App at runtime.
A same-body differential probe changed exactly one hexadecimal digit of the
encrypted query's `sign` while retaining the fresh route, control XML and
other parameters. Both the candidate signature and deliberately invalid
signature returned HTTP 200 with the identical native result code `2`,
53-byte header and zero payload. Consequently that response **cannot be
used as evidence that the candidate AOS signature passed validation**.
The ETA server may reject earlier, ignore this query signature, or validate
it through a different transport rule; the experiment does not distinguish
those possibilities. This contrasts with the separately observed
`/routeInfo` plaintext signature failure (`code=4`) and reinforces that its
validation behavior cannot be projected onto ETA.

The kind-`11` navigation payload is assembled as a JSON object by serializer
`0x6dd538` (called at `0x6ce3ac`), then converted to sendable text at
`0x6ce458` and handed to `0x6d2610` at `0x6ce558`. Literal keys recovered
from that serializer are `flag`, `gpsdata`, `netLocationData`, `feedback`,
`prePoint`, `socolrunning`, `retryFlag`, `vehicleType`, `lightFeedback`,
`slowCar`, `extModules`, `commonBroadcastCount`, `radarLocation`, and
`radarFlag`. Nested `prePoint` has `lon`, `lat`, `dir`, `time`; `extModules[]`
has `name`, `version`, `data`; `radarLocation` includes `linkId`, `lon`, `lat`,
`type`, `invoker`, and `requestObj`. This identifies the native payload
structure, but the exact meaning and required values of its flags and nested
objects, and the complete transport envelope around it, remain unverified. The transport
preparation at `0x6bf0f4` also uses literal `cpcode=` and `&deviceId=` and
wraps nonempty content in `<![CDATA[` / `]]>`; its exact use depends on
navigation state and still needs an on-wire sample before reimplementation.
Rechecking the entire `0x6dd538` serializer shows these top-level fields
are emitted in a fixed order, with no per-field omission branch in this
routine. Native structure offsets are `flag` `+0x00` (64-bit integer),
`gpsdata` `+0x08`, `netLocationData` `+0x20`, `feedback` `+0x38`
(strings), `prePoint` `+0x50` (object), five integer fields at `+0x70`
through `+0x80`, then `extModules` `+0xb8`, `commonBroadcastCount`
`+0xd0`, `radarLocation` `+0x88`, and `radarFlag` `+0xb0` (64-bit integer).
The research probe's update JSON contains only `flag` and `gpsdata`; even
after matching account, device identity, XML attributes and request order,
it remains materially unlike an App update. A next probe must derive the
remaining runtime fields from the sender before a no-event response can be
attributed to missing server navigation state.
A controlled follow-up added every statically observed top-level key with
zero-state candidate values, the 64-bit flag candidate, and three recent
GPS samples near the route's first light. It sent the actual-account
`ReqType=2` control followed by this `ReqType=3` update for one fresh route.
Both replies remained the same 53-byte frame with no event payload.
Completing the key *shape* alone therefore did not change the result.
Native runtime values, route-context installation, and the actual server
event source remain unresolved; the zero-state candidates are not a
byte-faithful App request.
The `gpsdata` value is more specific than a current-position object. The
sender calls `0x6d23cc` at `0x6ce13c`, which serializes the navigation
engine's sample vector at `+0xc08` through `0x6d52dc`/`0x6d5488` into
JSON array **text**; the outer `0x6dd538` serializer handles that text as
the `gpsdata` string field. Each 16-byte sample is serialized by `0x7074a4` as integer
`lon`, integer `lat`, and 64-bit integer `time`. The append path is
`0x6cc6e0 -> 0x6d3510 -> 0x6d3584`; it accepts only a location report whose field
`+0x2e4` equals `0x80`, copies two raw 32-bit coordinate fields from
`+0x2b8`, and uses `0xcf8140 / 1,000,000` for the timestamp. The caller
at `0x6cc6f8`–`0x6cc72c` also converts those same two coordinates to
longitude/latitude by dividing each by **3,600,000** (the literal double at
`0x6cc700`–`0x6cc718`), establishing the sample's integer units. This is
the native navigation location callback, not a generic browser-position
object. The
minimal wire probe's `{"flag":7}` omitted this history, so it was not a
faithful kind-11 navigation update even if its XML was syntactically valid.
The inner JSON also remains incomplete after the one-sample probe. The
serializer `0x6dd538` writes `radarLocation` from request-structure offset
`+0x88` and `radarFlag` from `+0xb0`. The `radarLocation` serializer at
`0x6dd97c` emits `linkId`, `lon`, and `lat`, but this active sender initializes
the region from `+0x88` to `+0xe7` to zero at `0x6ce10c`–`0x6ce134`; no
write to its `radarLocation` subobject is visible before `0x6dd538`.
The seemingly relevant engine field `+0xe40` is actually an unordered map
initialized with load factor 1.0 at `0x633984`–`0x633a64`. The copy at
`0x6ce330`–`0x6ce360` feeds the request's `commonBroadcastCount` vector
at `+0xd0`, not `radarLocation`; the event-count update at `0x763364`–
`0x763434` is one producer of that map. Crucially, the
sender's `5`/`7` selection at `0x6ce2c4`–`0x6ce2dc` writes stack
`sp+0x100`, which is request-structure **`+0xb0`**, so it is `radarFlag`,
not JSON `flag`. The latter is a separate 64-bit bitmask returned by
`0x7233b8` and stored at the structure's `+0x00` at `0x6ce288`. Earlier
probes incorrectly used 5/7 as JSON `flag`; their no-event responses cannot
rule out a missing native bitmask or other session inputs. The test that
injected a first-route-link `radarLocation` was *less* faithful to this send
path than leaving it empty.
Disassembly of `0x7233b8` now shows that the update sender always passes
mode `1` with a 15-byte state record built at `0x6ce150`–`0x6ce224`.
Bytes 0–3, words at offsets 4 and 8, and bytes 12–14 select distinct mask
bits; later branches OR in more bits from navigation-engine state. If its
local state bytes and those external predicates are all zero, the base is
`0x00059def7001359e` (the earlier `0x00059dcf7001359e` is a different
branch selected when status bytes 1 and 2 are not both zero). The
actual mask therefore cannot be a fixed constant independent of the active
navigation state. A bounded fresh-route probe on 2026-10-01 used the
all-zero-state base, the APK account, `ReqType=8` control followed by
`ReqType=3` update, full top-level JSON key shape, and three recent GPS
samples near the first route light. Both replies were still HTTP 200 with
the same 53-byte echo-only frame. This rules out the previous 7/5 flag
mistake **alone** as the reason for the empty frame, but does not prove
that the zero-state flag matches the App in a real navigation session.
The subsequent envelope builder `0x6c5f6c` names the operation
`etatrafficupdate` and writes fields including `DataVers`, `SdkVer`, `Vers`,
`Flag`, `Zip`, `ContentOptions`, `EtaOptions`, `Uuid`, `NaviID`, `PathSwitch`,
`ReqType`, `SceneFlag`, `VPStatus`, `Plate`, `Source`, `Invoker`, `BizScene`,
`DisFlag`, `CongestionScene`, `extraInfo`, and `user_ext`. `NaviID` is filled
from a navigation-state string in this builder (`0x6c63f8`–`0x6c640c`);
the mere presence of a planned route in Python does not establish that
session value.
The envelope format is now confirmed as XML rather than a top-level JSON
object. `0x6c6324` calls `iks_new("etatrafficupdate")`; the named fields
above are written through `iks_insert_attrib` (PLT `0xf3e880`). The builder
conditionally creates `vehicle` (`0x6c671c`) and `user_ext` (`0x6c68f4`)
child elements with `iks_insert` (PLT `0xf3e890`). `NaviID` is an attribute
of the root at `0x6c640c`. The finished tree is converted with `iks_string`
at `0x6c73b8`; the resulting request buffer is prefixed with ASCII `0` at
`0x6c7404`–`0x6c7418`. This explains a major mismatch in the earlier
plaintext JSON probes: they did not reproduce the App's XML envelope. The
remaining per-attribute values, optional child structure, and outer AOS
encoding/signature still require tracing before a meaningful live probe.
One missing root field now has a more precise native source. Before writing
`DataVers`, the builder calls `0xcddc58` at `0x6c6330`, keeps only the low
16 bits of the result, and formats that integer. `0xcddc58` first invokes
virtual slot `+0x40` on the navigation object, then slot `+0x318` on the
returned object. On `DrivePathImpl`, slot `+0x40` is `libassembly_kit.so`
`0x96550`, which returns its adapter pointer at path offset `+0x930`;
the constructor at `0x94984` stores that pointer at `0x94b64`. The adapter
vtable at `0x109210` sends its `+0x318` call through `0x79cb0` to the
underlying `DrivePathImpl` slot `+0x320`, resolved to `0x96e10`. That getter
reads the path's 32-bit field at `+0x4dc` (subject to its validity check),
and the path setter at `0x9a7dc` writes it through virtual slot `+0x670`.
Thus `DataVers` is read indirectly through route-object state; its online
route-response source is identified below.
An independent assembly path does write this field: `0xb8920` copies a word
from `[x24+0x20]+4` into the selected path's `+0x4dc`. Its caller at
`0xb63a0` places the route-decoder input pointer `x19` at that stack slot,
so this path's source is decoded-input offset `+4`. The routine entered at
`0xb629c` receives that input as its second argument. Its tail-call wrapper
at `0xca5b0` is called at `0xb6158` and `0xb82ac`, immediately after
`0xb6214` parses a route record. The entry at `0x71588` supplies `0xb60c8`
with a record whose type field is `1`; `0xb60c8` checks that type and invokes
`0xb6214`. Thus this is the 5.1 response's online route-record decoding
path, rather than an unrelated offline path. `0xb6214` parses with schema
`0x10ead0`. Its field-1 descriptor relocates to the 5.1 *header* schema at
`0x191b0`; field 2 relocates separately to the route-message schema at
`0x10e7d0`. In `0xb8844`, `[x24+0x20]` is the parsed **header** object:
its `+4` word is header field 2, whereas the route message is passed as
`x21=x19+0x28`. Therefore the word copied into path `+0x4dc` is header
field 2, whose low 16 bits are emitted as ETA `DataVers`. The baseline
header field 2 is `30282`. More decisively, `0xb8900`–`0xb8908` copies
the header's length-prefixed string at `+0x18` into path `+0x34`. That is
header field 5 (32 ASCII hex bytes in the saved responses): the
`DrivePathImpl` virtual `+0xa0` getter at `0xa8040` returns path `+0x34`,
and JNI `Route.getNaviID()` uses that getter. This closes the 5.1
header-field-5 to native `NaviID` dataflow. It does **not** prove that the
server treats a Python route request's ID as an active navigation session.
The navigation content has a more specific XML position. `0x6c691c` calls
`0x6c7188` when a payload and positive length are present. That helper
creates `<ETAInfo>` under the root and `<ETAFlag>` under it, writes the
integer flag as CDATA, then, when the flag is nonzero, creates
`<TRRequestData>` under `ETAInfo` and inserts the serialized navigation
JSON as CDATA with its explicit byte length (`iks_insert_cdata`, PLT
`0xf3e8e0`). The already-identified `0x6ce3ac` JSON serializer is therefore
the *inner* request payload, not the outer HTTP body. This materially narrows
the Python port: it needs XML wrapping and the native flag value in addition
to the JSON and session metadata.
The active send adds one more layer before that call. `0x6bf0f4` copies the
nonempty navigation JSON from transport `+0x120`; its branch at
`0x6bf1f8`–`0x6bf230` prefixes literal `<![CDATA[` and suffixes literal
`]]>` to the copied text. `iks_insert_cdata` then receives that *already
wrapped text* and `iks_string` escapes the markers into XML entities. An
isolated run of the APK's ARM64 `libiksemel.so` confirms the resulting fragment
for `{"flag":7}` is `<TRRequestData>&lt;![CDATA[{&quot;flag&quot;:7}]]&gt;</TRRequestData>`.
This is text containing escaped markers, not an XML CDATA section. The
research-only `encode_active_eta_info()` and its native-output test capture
this active-send case; the earlier bare-JSON probe omitted the markers.
The ETA flag comes from navigation-engine state `+0x57c`: `0x6d2810` loads
it and passes it as argument 1 to the transport's virtual send method,
`0x6bf6f8` stores that argument at transport `+0x170`, `0x6bf138` copies it
into the envelope builder's output slot, and `0x6c6740` supplies it to
`<ETAFlag>`. After a send, `0x6d2910` stores value `2` back at engine
`+0x57c`. The engine constructor at `0x6cd448`–`0x6cd46c` copies 16 literal
bytes from `0x114d70` to offsets `+0x570`–`+0x57f`; their last word,
at `+0x57c`, is also `2`. A normal newly constructed engine therefore begins
with ETA flag `2`, and `0x6d2910` restores that value after sending. Earlier
uncertainty about a first-request flag of `0` was unfounded. The exact
semantic meaning of flag `2` remains unverified.
For an active kind-11 send, `0x6d283c` enters transport slot `+0x10`
(`0x6bf6cc`). When its active-send condition holds, `0x6bf768`–`0x6bf77c`
calls the main transport's slot `+0x128` with arguments `w1=1`, `w2=0`,
`w3=3`; that slot is `0x6becbc`. It forwards its `w3` to envelope-builder
argument `w6` at `0x6bedbc`–`0x6bedc4`, which the builder writes under
`ReqType` at `0x6c6430`–`0x6c6444`. Thus this concrete active kind-11 path
uses `ReqType="3"`. The minimal probes omitted `ReqType`; they cannot be
treated as byte-faithful navigation updates.
The APK's 40 KB ARM64 `libiksemel.so` can be run in an isolated local Unicorn
experiment (`tools/amap-app/probe_iks_xml.py`) without starting the App
or contacting the service. Its `iks_insert_cdata` + `iks_string` output for
flag `2` and JSON `{"flag":7}` is
`<ETAInfo><ETAFlag>2</ETAFlag><TRRequestData>{&quot;flag&quot;:7}</TRRequestData></ETAInfo>`.
With flag `0`, `TRRequestData` is absent. The text serializer escapes `&`,
`<`, `>`, double quotes, and apostrophes as XML entities; UTF-8 bytes are
preserved. The bounded Python port of this *fragment only* is
`eta_xml_fragment.py`, checked against the native output in
`test_eta_xml_fragment.py`. It deliberately does not claim to assemble the
unverified root attributes or AOS request.

A bounded wire probe now distinguishes XML parsing from navigation-session
acceptance. A fresh 5.1 route's 32-hex header-field-5 candidate was sent in
`NaviID` with the verified `ETAInfo` fragment, a minimal root, and an
encrypted/signed URL query to the registered nvg ETA endpoint. HTTP 200
returned a 53-byte octet stream: fixed 21-byte prefix
`350000001400000002c80000000000000000000000` followed by the 32 ASCII
bytes of the submitted candidate ID. Repeating with a deliberately invalid
all-zero ID yielded the same prefix and echoed zeros. Therefore the reply
does **not** validate the route-derived candidate or demonstrate an active
navigation session, let alone a light phase/countdown. A malformed `0not-xml`
body under the same transport returned HTTP 400 JSON `code=2`/`Failure`,
which shows only that the minimal XML crossed an earlier parser boundary.
These are controlled observations, not a completed request contract. The
one-shot probe and raw responses remain ignored under `.local-data/amap-app/`;
no production request or display consumes them.
Adding one correctly scaled `gpsdata` history sample to the candidate-ID
probe yielded the same HTTP 200, 53-byte fixed-prefix-plus-ID response. This
rules out the missing GPS history **alone** as the cause of that response;
it does not validate the sample's eligibility or any of the omitted root
attributes/session state.
A byte-level audit of all four saved 53-byte ETA replies shows the same
structure: little-endian words `53` and `20` at offsets 0 and 4, bytes
`02 c8` at offsets 8–9, eleven zero bytes through offset 20, and then the
submitted 32-byte ASCII ID. This is a structured binary response rather than
an empty JSON `data.radar` result. Its field semantics are not established;
in particular `02 c8` must not be treated as proof of an accepted navigation
session. One saved successful 5.1 Beijing route for this probe corridor has
six signalized crossings in the static route decoder, so the absence of
`popLights` in the binary reply cannot be explained just by the route having
no marked traffic lights. Live signal coverage and route/session eligibility
remain separate questions.
A follow-up one-shot probe combined the corrected active-send marker wrapping
with that GPS sample and a fresh candidate ID. It still returned the same
53-byte prefix plus echoed ID. Thus neither GPS history nor the missing
marker layer, separately or together, explains the empty response. The
outer XML attributes and established route/session state remain the leading
unverified inputs.
The next controlled probe added the native active-send `ReqType="3"` attribute
to that wrapped-GPS request and repeated it once with a deliberately all-zero
ID. Both returned HTTP 200 and the same 53-byte binary frame, ending in the
ID supplied in each request. Therefore adding `ReqType` to this still-
incomplete root does not establish a session or yield a light event, and the
frame still cannot serve as ID validation. This does not rule out `ReqType`
being required when the other native attributes and state are present.
A first one-shot probe used `DataVers="0"` and inner JSON `flag=5`
(then mistakenly assumed to be the native flag; it is a `radarFlag` value),
together with the wrapped GPS sample and `ReqType="3"`. It again returned
the 53-byte response with zero bytes at offsets 6–7. Further inspection of
the 5.1 decoder then corrected that `DataVers` assumption: it comes from
header field 2, not route-message field 2. Repeating with a fresh route's
actual header field 2, `30282` (`0x764a`), changed response bytes 6–7 from
`00 00` to `4a 76` while retaining the same 53-byte frame, response-type/
status bytes, and echoed 32-byte ID. This confirms that the service parses
and echoes the supplied `DataVers`; it does not prove session acceptance or
yield `popLights`. The incomplete root attributes and established navigation
state remain unresolved.
After correcting the field distinction, a bounded probe supplied a
default-branch **candidate** 64-bit `flag=0x00059dcf7001359e` from
`0x7233b8`, plus `radarFlag=5`, the 5.1 header's real `DataVers`, the two
baseline options, and the prior GPS sample. It still returned the same
53-byte frame. This is not a native request reproduction: the bitmask has
additional runtime-dependent branches and other request fields remain absent.
Adding a **candidate** `radarLocation` with the decoded first route-link ID
and route origin longitude/latitude to that bounded probe still returned the
same 53-byte frame. The later dataflow check above shows this synthetic
location was not part of the active App sender's request; this probe does
not test a required radar-location field. It only shows that the guessed
object did not change the observed no-event frame.
A controlled repeat of the better candidate request (correct `DataVers`,
`ReqType`, baseline options, 64-bit flag candidate, `radarFlag`, GPS sample)
to the separately registered `m5`/`ws/lbs/navigation/etatrafficupdate/`
fallback row returned HTTP 200 with the same 53-byte frame and ID echo as
the primary `nvg` row. Host-row selection alone does not explain the absent
live event; both probes still lack full App session state.
The native builder writes decimal `ContentOptions` from its first option
accumulator at `0x6c63b8`–`0x6c63cc` and decimal `EtaOptions` from its
second accumulator at `0x6c63d0`–`0x6c63e4`. Under the inspected zero/default
branches of `0x6c61c0`–`0x6c622c`, both are `0x3eb` (`1003`), although live
context flags may add other bits. A one-shot request using those two baseline
values plus the correct `DataVers`, `ReqType=3`, synthetic JSON `flag=5`, and GPS sample
still produced the same 53-byte no-event frame. This does not establish the
actual App's option values or prove that the omitted XML/session state is
accepted.
The same root builder has an unconditional `Zip="1"` at `0x6c63a4`–`0x6c63b4`.
Its separate `Flag` attribute at `0x6c6390`–`0x6c63a0` is produced by
`0x6c5f04` from navigation-context flags. The zero-config branch computes
`0x4008210a8` (`17188393128`), but a real navigation session may choose
other bits. Two bounded, otherwise identical signed probes isolate these
attributes: adding only this candidate root `Flag` left the 53-byte reply
prefix unchanged; adding only `Zip="1"` changed exactly response byte 12
from `00` to `01` while retaining the 53-byte frame and echoed `NaviID`.
Adding both had the same byte-12 change. This shows the server reads and
reflects `Zip` in the binary header, just as it reflects `DataVers` at bytes
6–7; it does **not** make the response a usable navigation update or identify
the missing live-signal condition. The research-only probe exposes these
flags separately in `.local-data/amap-app/probe_eta_transport.py`.
Another omitted attribute, `Uuid`, is not copied from the route response:
`0x6c6060`–`0x6c6070` reads a process-global pointer at `0xf93528`, which
the setter `0xcef57c` fills from one field of a six-field application-supplied
configuration object (`0xcef5d8`–`0xcef5f0`). The `Uuid` attribute is written
at `0x6c63e8`–`0x6c63f4`. This establishes another difference between the
synthetic Python probe and an initialized App process. It does not establish
that an arbitrary UUID would activate a navigation session.
The prior GPS probe used the route origin, 858 m from the selected route's
first decoded traffic light. To check whether that distance alone explained
the empty reply, a fresh 5.1 route was decoded and the GPS sample moved to
its path point immediately before that light, 19 m away. A second bounded
probe sent three 1-second history samples, roughly 20 m/10 m/0 m before that
path point, using the native 3,600,000 coordinate scale. Both still returned
the same 53-byte binary frame (with `DataVers` and `Zip` echoed) and no JSON
`popLights`. Proximity to a decoded light and a short plausible GPS history
therefore do not, by themselves, unlock the live update. This does not prove
that the particular light has realtime coverage or that the incomplete
navigation session was accepted.
The native kind-11 dispatcher `0x6cf268` checks for gzip magic and otherwise
copies reply bytes to a buffer. Its JSON parser path starts at `0x6cf88c` via
`0x6d2da4` and invokes `0x6d0be0` for lights only after successful parsing.
There are two direct native callers of this dispatcher, not just the HTTP
success adapter. The second is an engine virtual callback at `0x6d7520`
(vtable relocation `0xf51248`): it receives a token and a native string,
extracts the string's pointer/length at `0x6d7550`–`0x6d757c`, and calls the
same dispatcher. Its own caller is virtual rather than a direct branch, so
the producer of that string has not yet been tied to an endpoint. This is a
concrete alternate event-input path to trace; it is not proof that the
53-byte HTTP frame is transformed into JSON.
The 53-byte reply is not JSON or gzip at this boundary. Whether an upstream
transport layer unwraps that envelope before invoking this dispatcher is
still unresolved; treating it as a `popLights` event would be unjustified.
The successful-HTTP callback in this native path is now identified as
`0x73204c`: it requires response type low word `2`, HTTP status `0xc8`, and
a clear navigation-context byte at `+0xac`, then passes its callback buffer
pointer and length directly to `0x6cf268` at `0x7320e0`–`0x7320f8`. It does
not remove the 21-byte prefix there. A bridge preceding this callback could
still transform the body, but no such transform has been observed. On the
known callback path, feeding the raw 53-byte probe reply would fail JSON
parsing and would not reach the light consumer.
The Java HTTP-to-native adapters narrow that remaining bridge question.
`com.amap.network.api.http.callback.cpp.NativeCallback.onSuccess` forwards
its `Response` object to `nativeOnSuccess`; the `libamapmain.so` registration
at `0xd4a8c` uses the `NativeCallback` class built at `0xd56fc` and method
table `0x101f70` (whose success entry points at `0xd4bdc`). The ordinary
`ResponseCallbackAdapter.e.run` wraps the lower-level `HttpResponse` in
`cj5` before calling the callback. `cj5.a.getByteData()` delegates directly
to `HttpResponse.getResponseBodyData()`, which reads the bytes from
`INetResponse.getBodyInputStream()` into an array without inspecting or
removing a frame header. The Java `NativeCallback`, `cj5`, and
`HttpResponse` layers therefore do not explain how the observed 53-byte
binary frame could become the JSON expected by `0x6cf88c`. A transform in
the underlying `INetResponse` implementation or a separate transport path
is still possible and needs direct evidence.
The older AOS response wrapper does not supply that transform either:
`AosInputStreamResponse` inherits `AosResponse`, whose
`getResponseBodyData()` delegates to its `InputStreamResponse` when present.
`InputStreamResponse` inherits the byte-copying implementation from
`HttpResponse`; its `getBodyInputStream()` wraps the underlying stream for
close/statistics observation. Neither class parses the 21-byte frame. The
remaining possible transform is below this Java response layer, at the
concrete network stream/provider, or the 53-byte frame is simply not the
same kind of payload that reaches the kind-11 JSON parser.
The deprecated `AosService` implementation confirms this for its own path:
`AosService.j` assigns the `InputStreamResponse` to an `AosResponse` and calls
`parse()`; `AosInputStreamResponse.b()` only returns `getBodyInputStream()`.
Its success callback then passes that response onward. There is no visible
binary-frame decoder in this service method either. The pinned native ETA
sender has not been conclusively tied to this particular deprecated Java
service, so this is a constraint on one possible bridge rather than proof
about every transport path.

The missing bridge has now been found **inside `libamaptbt.so`**, not in the
Java HTTP response classes. The ETA/TMC transport object's vtable at
`0xf50b40` has its HTTP callback slot `+0x10` pointing to `0x6bded4`.
After an HTTP 200, that callback calls `0x6cbc0c` to decode the binary
response. Its fixed header is 53 bytes on the observed reply: a 32-bit total
length, 16-bit format field (`20`), 16-bit `DataVers`, an 8-bit native result
code, 16-bit status field (`200`), one metadata byte, one flags byte,
32-bit checksum, 32-bit data length, and a 32-byte `NaviID`. This field
order follows the sequential reads in `0x686ed8`–`0x686f50`, not guessed
offsets into the raw HTTP bytes. The bounded Python envelope parser is
`eta_response.py`, with a regression check against the captured header.
The probe's 53-byte frame decodes to **native result code 2**, zero data
length, and no bytes after the header. `0x6cbc7c`–`0x6cbc80` sends any
nonzero result code directly back to the callback; only result code 0
enters the payload parser at `0x6cbd74`. Accordingly `0x6bdff4`–`0x6bdffc`
routes this reply to its error branch, never to the light-event parser.
All 23 saved responses with a valid ETA binary envelope, spanning the
bounded request variants in this research directory, decode to the same
native result code 2 and 53-byte header-only length; the one malformed
request is an HTTP/JSON error instead. The native parser's log literal at
`0xf85d4` labels byte 8 `etaCode`, while its other failure strings distinguish
size and decoder-version errors. Thus `2` is a server-result code, not a
local decompression or frame-length failure.
The previous label "no-event frame" was too weak: this is a **native
rejection/error response despite HTTP 200**. The meaning of code 2 and the
specific rejected request field remain unknown. Its echoed `NaviID`,
`DataVers`, and Zip flag show only partial envelope parsing.
On the successful branch, `0x6be3d0`–`0x6be3f0` calls `0x6baaec`, which
dispatches the extracted data through listener vector `engine+0xef0` via
`0x6bda08`. The listener registered by `0x6cdd18`–`0x6cddc8` is the
`0x6d7520` callback; it passes that extracted string to `0x6cf268`, whose
kind-11 JSON path can consume `data.radar.popLights[]`. This closes the
previously open binary-HTTP-to-JSON callback link for the ETA/TMC channel.
More precisely, a successful frame's flags byte bit 2 causes `0x6cbc0c`
to parse the `+0x870` section with `0x6899f8`; that section is a 16-bit
length followed by the copied string bytes. `0x6baaec` fetches exactly
this section through `0x6cbbe4` and sends its string to the registered
listener. The 53-byte error frame has bit 2 clear and zero payload length,
so it cannot contain this event string even before the nonzero result-code
check.
It does **not** prove a successful response contains live countdowns, but
it identifies the concrete condition that the current probes fail before
any event can reach TMC: native result code must be zero.

The `NaviID` source is now more precise. At `0x6c5fc4` the envelope builder
loads the native navigation context, then calls `0x633c50`. That helper
looks up key `1` in the context's object collection via `0x6600ec` and
returns the first field of the matched object (`0x6583b0`). The builder
wraps this pointer at `0x6c5fd4` and rejects the request if the resulting
route wrapper is empty (`0x6c5fe0`). At `0x6c63f8`, wrapper getter
`0xcd8540` invokes the underlying route object's virtual slot `+0xa0`;
that getter's string is emitted under `NaviID` at `0x6c640c`. The field is
therefore a **route-object pointer**, not itself a string, correcting the
earlier shorthand in this paragraph. The online 5.1 path's `+0xa0` getter
was independently traced to header field 5, so using that field as the
synthetic `NaviID` is supported by the full client-side dataflow. This does
not establish that the server accepts the route as an active navigation
session.

The owner chain is now concrete. ETA transport constructor `0x6b9f2c`
receives the guide engine and installs a holder at transport `+0x28` through
`0x6c5dfc`; it is created by guide-engine constructor `0x6b1ad4`, which
calls `0x6338f4`. That engine stores its caller-supplied route collection at
engine `+0x10` (`0x633924`). The route collection is allocated by the parent
at `0x5acfb0`–`0x5acfd8`, and an active route update reaches it through
`0x5c3268 → 0x5b5250 → 0x65ff10 → 0x6602f0 → 0x661aa4`. The latter walks
source route pointers at input `+0xe0`; `0x657a5c` stores each source route
pointer in the new collection entry's first field, and `0x662080` appends
that entry. `0x633c50` selects the entry with key `1` from this collection.
This explains why the native sender needs an installed route object even
though a Python probe can fill in the same XML `NaviID` from a 5.1 reply.
TMC's route decoder does not create this native collection. The server-side
meaning of `etaCode=2` and whether a further session registration is
required are still unverified.

The transport's immediate failure path confirms how early this dependency
applies. `0x6becbc` first builds the navigation content at `0x6bf0f4`, then
calls `0x6c5f6c` at `0x6bedc4`. If that builder returns false it branches
to local error `0x7d8` at `0x6bef40`, *before* selecting/allocating an AOS
request at `0x6bede0`–`0x6bede8`. The route planner response alone therefore
cannot be fed into this native send path without reconstructing the
navigation-context entry; this is a client-side precondition, not just an
upstream HTTP rejection. The send path branches again after request
allocation to a different local error `0x7d6` if its request buffer cannot
be prepared. The source string at context key `1` still has not been matched
to the 5.1 response's 32-hex header field.

The `0x6ce528` navigation sender builds a JSON payload at `0x6ce3ac`,
serializes it at `0x6ce3b8`, and only then calls transport kind `11` at
`0x6ce558`. Its flag word is set to `5` or `7` at `0x6ce2c4`–`0x6ce2dc`
depending on a navigation-state bit, and it conditionally includes fresh
location/radar data. This explains why a static route record cannot be
replayed as a full ETA/TMC update: the payload reflects current navigation
state as well as the route identity. The exact flag semantics remain open.

An empty POST to the realtime URL returned `code=3`, `Params error`; this does
not establish the required request body, authorization, route/session
identity, or response contract. A GET is unsupported. No successful
realtime-signal response has been obtained.

The decompiled App's `g02.format` handles an internal `dataType=1` event whose
`data` is a JSON array with `statusInfos`. `g02.d`, `lh0.j`, and `pr6.d`
accept visible entries with `showType=2`; statuses `2/3`, `4/5`, and `8` map to
red, green, and yellow respectively. The countdown comes from `remainTime`.
`traffic_signal_event.py` captures only this verified event shape. It has no
production feed: the App's private formatter is not an Android API available
to a Tesla browser or a Python server.

The AJX car-link interface confirms the event boundary. Its
`CruiseEyrieLogic.getTrafficData` subscribes to `OnNaviEvent` through
`TripMapManager` and listens for `NaviEventTypeNotifyCurrentTrafficLightsInfo`
(`26401`); it does not call the realtime HTTP URL. The related
`NaviEventTypeTrafficLightCountdown` is `26403`. In `libamaphorus.so`,
constructor VA `0xcf4d00` assigns `26401` and is called from `0x77d344`;
constructor VA `0xcf4f40` assigns `26403` and is called from `0x79f3a0` and
`0x7a13dc`. The `26403` native JSON serializer around `0xd11580` includes
`lightStatus`, `countDownStatus`, `status`, `remainTime`, `mainAction`,
`showType`, `linkId`, `remainDis`, and `commonInfos[].statusInfos[]`. The
Android live-activity code accepts only display type 2, positive remaining
time, and `remainDis < 100000`. The parser now accepts this second native
event shape as well, but still has no browser/Python source for it.

The `26403` path reads an internal component named
`component.dynamicTravelTrafficSignalInfo` (reference at `libamaphorus.so`
`0x7a1144`). More precisely, the component's update handler at `0xa88c40`
parses incoming data and writes the component through `0xa88dd0`; the
notification branch at `0xa64294` emits internal message `0x989ac5`; the
handler at `0x7a10b4` reacts to that message, reads the component and calls
the `26403` event constructor from `0x7a13dc`. This is a verified internal
component-to-event chain. Separately, a `libamaptbt.so` feature payload
contains a `traffic_light_event` field.
Its builder at `0x5344fc`–`0x534510` calls `0x538870` for the value; that
helper returns the numeric constant `1.0` before the JSON field insertion.
The same helper is used for several neighboring feature flags, while other
flags explicitly use a zero-valued helper. Thus this pinned APK's builder
actively sets `traffic_light_event=1` in that payload. The separate AJX
`TripCloudConfigUtil` method
`getTrafficLightCountDownConfig()` defaults its `navi_cloud` /
`TrafficlightCountdown` cold-boot switch to `0`; no caller of that method
was found in the extracted drive/carlink JS subset, so its relation to the
native request flag is still unproven.
The feature JSON builder is `0x5342dc`, called by `0x534164` before its
`0x5352ec` asynchronous dispatch. That dispatch uses an injected object
pointer at owner offset `+0x10` and passes a constant `0x7d0` (2000) to its
virtual send method at `0x5353d4`–`0x5353e4`; it does not itself embed an
HTTP URL. The owner sets readiness bytes at `+0x648/+0x649` before sending.
The constructor path `0x4b47fc -> 0x533fa8` supplies that pointer from
parent offset `+0x90`; `0x4afff8`–`0x4b0040` obtains it through a factory
request naming `NaviAgent` with type `6`. Java `AgentService` likewise
exposes a native ability/callback service. This makes the flag a likely
agent capability declaration rather than evidence of a cloud request for
signal data. The injected provider's virtual method still needs resolution
to prove its precise destination. Do not add `traffic_light_event` to the
separate AJX `/routeInfo` request merely because the field name matches.
These observations do not prove that an actual server response supplies live
phases. The component's constructor at `0xa88b4c` is created by the generic
factory at `0xa75b34` under component type `0x2972` (10610). That factory
registers the component but does not decode an HTTP reply. The update at
`0xa88c40` copies its input into an internal vector of 0x50-byte
records (`0x7a1930` / `0x7a18b0`) before notifying listeners; it does not
parse a recognizable HTTP envelope at that point. The `0x2972` component id
is an internal dispatch key, not an observed request parameter.
The component's vtable at `0xe12728` has generic update slot `+0x40`
(`0x6ac078`), which forwards its data argument to slot `+0xa8`
(`0xa88c40`). This confirms the component update is reached through a
generic dispatch interface. It does not identify the network response that
supplies that argument.

The pinned APK has **two distinct ACCS push routes** into navigation, in
addition to the periodic HTTP dynamic-info request. Extracting the
`amap_bundle_tripservice` AJX service from `bundles.oajx` closes the
previous gap between the page's broadcast receivers and Android transport:

* `TripDynamicInfoAccsServiceListener.onInit()` conditionally registers the
  native ACCS main type `AMAP_AOS_DYNAMIC_SERVER` when
  `drive_amapAosDynamicServerAccs` is available. On a native callback with
  `messageType=5`, it broadcasts the callback's `data` as
  `broadcast_dynamic_info_accs_topic`. The navigation page's
  `registerDynamicInfoAccsTopicEvent()` parses that data, accepts `code=1`
  or `7`, and passes `data.horus` to `TripDynamicInfoEyrieScheduler`, which
  uses the same map-engine interaction route as the HTTP response. This
  establishes a possible realtime feed into Horus, but there is no captured
  ACCS message proving that this feed contains traffic-light phases.
* After the first real navigation info event (and only outside simulation),
  `TripNaviStateEyrieEventUtil.registerAccsTrafficData()` registers the
  `trip_navi` scene with the AJX `tripAccsService`. Its
  `TripAccsService.onInit()` registers native ACCS main type
  `AMAP_TRIP_SERVICE`; `onDispatchMessage()` records the scene key locally.
  A `messageType=5` callback carries a JSON object keyed by scene; the
  service broadcasts the active scene's array to `trip_accs_trip_navi`.
  The page filters array elements by `moduleType=horus` or `tbt`, then sends
  them to `kPushInteraction` / `kPushInteractionTBT` in the map engine. This
  path bypasses `TripDynamicInfoEyrieScheduler`. The APK's command enum assigns these
  actions IDs `12` and `13`, distinct from HTTP Horus delivery through
  `kSetInteractionData` ID `9`. The later native check of action 12 points to
  `component.MeetWarningData`, not the traffic-signal component; it cannot
  currently be counted as a source of event `26403`.

In both cases `natives.accs.registerAccsService()` is only a listener
registration, not an HTTP subscription body. The Java `AjxModuleAccs` calls
`IACCSService.addEventListener(mainType, "", 35, ...)`; its callback wrapper
labels incoming data with `messageType=5`. The actual transport is the
Android ACCS client: `AmapAccsClientManager` initializes the ACCS SDK and
calls `ACCSClient.getAccsClient("default").bindApp(...)`, with optional
`bindUser(uid)` after login. `AmapAccsDataDelegate.onData()` routes by ACCS
service/main/biz type using the native message's extended header. Merely
copying `AMAP_TRIP_SERVICE` or `AMAP_AOS_DYNAMIC_SERVER` into a Python HTTP
header cannot create this push session. Under TMC's browser-plus-Python
runtime, a live countdown still requires either a verified HTTP equivalent
or a separately implemented and validated ACCS session. Neither is present.
The SDK initialization at Java `o10.init()` reads the APK's ACCS app key and
mode, configures a Taobao ACCS client with the release in-app/channel hosts,
and binds the App. On a successful bind, `AmapAccsReceiver.onBindApp()` sends
an `AMAP_BASE_SERVICE` message with biz type `1`; `bindUser(uid)` and biz
type `2` occur only when an account UID is available. This is a persistent
message transport and handshake, not a variant of the AOS signed POST.
The AJX service's `sceneKey` is only kept in a local set for filtering
incoming scene-keyed messages; its `onDispatchMessage()` does not send that
key to the ACCS server. The server-side condition that starts a nav push
therefore remains unidentified. The separate `drive_amapAosDynamicServerAccs`
feature flag is checked dynamically, so static APK presence alone does not
prove that this channel is enabled for a given account or device.
The bundled ACCS SDK confirms that `bindApp` is a distinct control frame:
`ACCSClient` delegates to `ACCSManagerImpl.bindApp()`, which builds
`Message.buildBindApp(...)` using the configured app key, TTID, package name,
and App version, then sends it on the channel service before any pushed
message can arrive. This explains why the existing signed AOS `/routeInfo`
or ETA probes cannot, on their own, stand in for the App's push session.
The bind frame's `sign` is a separate prerequisite. In the APK,
`Message.buildBindApp()` calls `UtilityImpl.getAppsign()`. The pinned App's
`o10.init()` builds its ACCS config with an app key but **without** an app
secret; `AccsClientConfig.Builder.build()` therefore leaves security mode at
`0`. `UtilityImpl.isSecurityOff()` returns true only for mode `2`, so this
configuration takes the `SecurityGuardManager.getSecureSignatureComp()`
branch. Its input is `deviceId + appKey` with request type `3`. The
alternative local secret/HMAC branch is not selected by this APK config.
The existing AOS MD5/body codec cannot generate this ACCS bind signature.
The ACCS SDK's `Message.build()` then serializes the signed control payload
into a version-2 binary frame with source/target IDs, data ID, extended
headers, and optional compression; a plain WebSocket or HTTP POST would
not be protocol-equivalent. No Python ACCS bind has been implemented or
validated against a server reply.
The bundled Java `ISecureSignatureComponent.signRequest()` implementation
does not contain the request-type-3 signing formula: it forwards the map,
app key, request type, auth code, and a boolean to SecurityGuard's router
command `10401`, implemented below the Java layer. This is a separate
reverse-engineering task from AOS request signing. The ACCS frame also
includes `source=deviceId|packageName|serviceId|userInfo` and a JSON
control body with command, key, sign, SDK/App versions, TTID, and device
metadata. The exact channel/session protocol and a successful bind response
remain unverified in Python.

An additional candidate upstream path is present in the APK's extracted AJX
scripts. `TripDynamicInfoRequestUtils` sends periodic JSON POSTs through
`DynamicInfoNaviLoopRequestLogic` to
`$aos.m5$/ws/perception/drive/navigation`; its before-navigation variants
use `/ws/perception/drive/routePlan` and `/ws/perception/drive/routeInfo`.
The navigation request includes `navigation_id`, `main_path_id`,
`navi_route_links`, location, and route details obtained from
`TripNaviLinksHelper.fetchRouteLinks()`. That helper asks the native map
engine through `kSetInteractionData` and waits for
`NaviEventTypeDynamicInfoInteractionData`; it does not derive `navi_id` or
the route links from the JS route-plan object. The response dispatcher reads
`data.horus` and sends its JSON through `TripDynamicInfoEyrieScheduler` as
`distributeInfo_Horus` in `kSetInteractionData` (`interactionType: 4`).
`libamaphorus.so` registers `distributeInfo_Horus` as a reflected field at
`0xc8bee8` (object offset `+0x58`); that code builds a field schema, not a
response parser. The following dispatch path now closes the native
interaction-to-component link. Component virtual method `+0x18` resolves to
`0x6ac0a8`; its dynamic-info branch calls `0x6ac264`, whose
`interactionType == 4` branch calls `0x6ac6b0`. That function reads the
reflected `distributeInfo_Horus` string from input offset `+0x58`
(`0x6ac734`), then calls the current component's virtual `+0xa8` method if
the string does not contain `dynamic_push_channel`. On the traffic-signal
component, `+0xa8` is `0xa88c40`, the update handler described above. If
the marker is present, the dispatcher calls `+0xb0` instead, which resolves
to `0xa88e64` on that component. Thus a normal type-4 Horus interaction can
feed `component.dynamicTravelTrafficSignalInfo`; the response body still
needs a successful capture to verify that it actually contains live signal
records. The required navigation-session fields are also not yet reproduced.
This path may be separate from the ETA/TMC `popLights[]` path above.

The AJX response transformation matters when looking for a sample:
`TripDynamicInfoRequestUtils._dispatchResponse()` first calls
`mergeCommonData(data.common_data, data)`. For every common-data entry it
copies that entry's `data` under its key into each named `show_type` section,
including `horus` when selected. `_dispatchEyrieData()` then adds
`other.is_charging_user` and passes the merged `horus` object to the scheduler.
Consequently a signal field may originate in `data.common_data` and only
appear under `horus` after the App's merge; inspecting raw `data.horus` alone
could miss it. This follows the extracted AJX code; no successful live
response has been captured yet.

The AJX call order is now confirmed: `requestDynamicInfo()` first calls
`requestRouteInfo()` (`/ws/perception/drive/routeInfo` on the navigation page),
then calls `requestNavigationInfo()` when that request completes and starts a
periodic navigation loop. `DynamicInfoRequestLogic` sends serialized JSON as a
POST with `Content-Type: application/json`; its `getSign()` declares
`channel`, `e_poiid`, and `user_loc`. The navigation body extends common
route/location fields with `dynamic_scene`, `navi_count`, `naviCongestion`,
and `navigation_scene`. It is not a request consisting only of `navigation_id`;
the signature reconstruction and its live boundary checks are recorded below.
The result-page caller sets `isNaviPage: false`, selecting `/routePlan`;
the navigation-page caller sets it to true, selecting `/routeInfo` before
`/navigation`. The latter also passes `TripNaviDataManager.getNaviId()` into
`updateParams()` as `naviId`, but `_getCommonRequestParams()` does **not** read
that property for its `navigation_id` body field. It instead takes `navi_id`
from `TripNaviLinksHelper.fetchRouteLinks()`'s native
`NaviEventTypeDynamicInfoInteractionData`. Merely copying a JavaScript
navigation ID into the Python body would diverge from the APK's actual source.

The body transport was checked through the **native** bridge. AJX
`TripDynamicInfoRequestUtils._request()` calls `JSON.stringify()` before
`start()`. `DynamicInfoBaseRequestLogic` passes that string, declares
`Content-Type: application/json`, and sets `bodytransfer: false`; CLNetwork
therefore preserves the JSON text instead of form-encoding it. This is only
the *pre-bridge* body. CLNetwork's `AosRequest` also sets `aosSign.ent` true
for normal AOS requests (even in a debug package unless an IP-address proxy
is selected) and `aosSign.aos_params` true. In the APK's concrete
`ModuleRequest.optionsToRequestInfo()`, `bodytransfer: false` stores the
string verbatim in `cVar.g`, while `setAosSign()` copies `ent` into `cVar.e`
and `aos_params` into `cVar.i`. `c.a()` then runs
`serverkey.amapEncodeV2(cVar.g)` when `ent` is true and places those **encoded
bytes** in `AosPostRequest.f`; it also enables the common-parameter strategy
when `aos_params` is true. `NetworkParam.getNetworkParamMap()` names common
fields including `div`, `siv`, `dip`, `dic`, `diu`, `session`, `appstartid`,
`stepid`, and `channel` (some are conditional).
`AosRequest.buildHttpRequest()` actually retrieves those common params before
signing, and `AosPostRequest.processParams()` puts both common and explicit
params in the URL query when the POST already has a body. It then takes the
query string, applies `IAosEncryptor.xxTeaEncrypt()` (backed here by
`serverkey.amapEncodeV2`), and sends it under `in=` with `ent=2` instead of
leaving the query values visible. `securityGuardSignByV2()` may additionally
attach `x-sign`, `x-t`, `x-appkey`, `x-mini-wua`, and related headers, depending
on the App's SecurityGuard state. The Python probe's URL consequently differs
in both native device/session metadata **and encrypted query format**;
passing a plaintext three-field signature check is not equivalent to
reproducing the complete AOS request.
The APK's default SecurityGuard configuration is **enabled**:
`vu5.withSecurityGuardSign()` reads `security_guard_sign_switch` with default
`true`, and `vu5.isVirtualSignV2()` reads `virtual_v2_sign_type` with default
`true`. `rf2.virtualV2Sign()` calls `uu5.f()`, which obtains
`IUnifiedSecurityComponent` from `SecurityGuardManager` and signs the
encrypted request material and timestamp. The native bridge does not itself
generate these headers; `AosRequest.securityGuardSign()` attaches them later
when the provider is enabled. A Python request with only the AOS MD5 `sign`
therefore still lacks a second, normally enabled signing layer. The server's
generic `code=3` does not prove whether that layer or a body field was the
first rejection.
The exact default virtual-sign input is now visible in `uu5.f()`: `data` is
`appkey + "&" + MD5(encrypted query) + "&" + Unix-seconds timestamp`, and
the other fields are `api` (request URI), `extendParas` (empty map), `env`,
`appkey`, and `useWua`. The result comes from
`IUnifiedSecurityComponent.getSecurityFactors()` rather than
`libserverkey.so`; `AosRequest` maps its `x-sign`, `x-mini-wua`, and
`x-sgext` entries to HTTP headers, with `x-pv: 6.3`. The APK bundles
`libsgmainso-6.8.260404.so` and `libsgmain.so`, but this analysis has not
reproduced their Android-dependent initialization or output. This identifies
the second signing boundary without claiming it has been ported to Python.

The bundled `libsgmain.so` is an embedded plugin archive with `classes.dex`.
Its `SecurityGuardMiddleTierPlugin.onPluginLoaded()` loads the companion
native library. `C0046.m135()` registers a proxy for
`IUnifiedSecurityComponent`; the proxy in `C0058` handles
`getSecurityFactors()` and passes the app key, digest-and-timestamp `data`,
WUA flag, environment, API path, and other arguments through router command
`70102` (after command `70103` selects the business ID). This confirms that
copying the visible Java map assembly into Python does **not** produce the
security headers: their values are returned by the plugin's native command.
It also pinpoints the missing porting boundary more narrowly than a generic
"SecurityGuard dependency."

`AosRequest.securityGuardSign()` runs only when the request has signing
enabled, the SecurityGuard provider is enabled, the scene is not `startup`,
and there is encrypted query/body material to sign. For the normal AJX POST
path with `ent=2&in=...`, the last condition is met. However neither the
default-on client switch nor this call path proves that the server **requires**
`x-sign` for `/routeInfo` or `/navigation`: no successful paired request has
isolated that condition. A separate route-plan GET succeeds in the existing
Python adapter without SecurityGuard headers, but its request type and path
are different. Therefore the exact cause of `code=3` is still unresolved;
the probes differ simultaneously in native navigation context, route-link
payload, common parameters, and potentially SecurityGuard headers.

This corrects the earlier assumption that `requests.post(json=body)`
reproduced the APK's wire request. The research probes sent plaintext JSON
and only the manually signed query fields; the APK encrypts the body and
adds native common parameters. Thus their `code=3` / `Params error` **cannot
diagnose** whether the guessed `navigation_id`, `main_path_id`, or route-link
metadata are right. They do establish a successful signature boundary but
not a faithful endpoint request. A controlled endpoint test needs the native
body encoder, common parameters, and complete navigation data before a
parameter-error response can diagnose individual route fields.

The pinned APK's `serverkey.amapEncodeV2` JNI method was exercised in an
isolated ARM64 emulator with the APK's own signing certificate. It changed a
test `{"probe":1}` body from 11 bytes to 24 bytes of encoded text, confirming
that the native branch is substantive rather than an identity operation.
The APK's matching `amapDecodeV2` JNI method recovered the original JSON
from this encoded text in a round-trip check.
The reproducible research wrapper is `native_body_codec.py`; it reads local
APK assets and is intentionally separate from the production TMC server.
One fresh successful 5.1 route was followed by a single `/routeInfo` probe
with its candidate route ID and the same synthetic body, this time encoded
by that JNI method. The service still returned HTTP 200,
`code=3` / `Params error`. This probe still sent **plaintext query
parameters** and lacked the APK's native common parameters and possible
SecurityGuard headers. It therefore cannot isolate server-side validation of
the body, POIs, route links, or guessed native identifiers.
A subsequent bounded probe on another fresh 5.1 route encoded both the body
and the four available query values, supplying the latter as `ent=2&in=...`.
It again returned HTTP 200, `code=3`. This rules out those two transformations
as sufficient by themselves; the query still omitted the App's native common
parameters and any conditional SecurityGuard headers, and the body remained
synthetic. The response does not identify which of those missing pieces the
server requires.
The specific common-parameter gap is now enumerated from
`NetworkParam.getNetworkParamMap()`: the App normally attaches `div`, `siv`,
`dip`, `dic`, `diu`, `diu2`, `diu3`, `dai`, `cifa`, `session`, `appstartid`,
`stepid`, `channel`, `client_network_class`, `dibv`, `BID_F`, `ae_traffic`,
`oaid`, `buildABI`, and internationalization fields, plus conditional IDs
such as `adiu`, `uid`, `tid`, `ct_id`, `pcd`, and `pageSessionId`. The encoded
probe supplied only `channel`, `e_poiid`, `user_loc`, and `sign`. In
`AosRequest.buildHttpRequest()`, the ordinary AOS digest is computed after
retrieving the common map and before encrypting the assembled query. The
probe therefore did not merely omit optional metadata after signing: it
signed and encrypted a materially different query. Which fields the server
validates for these perception endpoints remains unverified.
The candidate probe body is also materially smaller than the AJX
`beforeNavi` body. It omits top-level `navigation_scene`, `car_type`,
`vehicleType`, `cloud_control`, `limitInfo`, `routeConfig`, `routeParam`,
`start_poi`, and `offline_map_param`, among others. Its sole
`navi_route_links[]` element contains only `path_id` and an endpoint, whereas
the native event supplies route-link IDs, lengths, road classes, points,
segment metadata, and path information. Consequently the remaining
`code=3` is consistent with multiple independently incomplete inputs; the
server's generic error does not identify one mandatory field.

`TripDynamicInfoTools.getCloudRequestIntervalAndDis()` defaults the periodic
request to 300,000 ms (five minutes) and its route-link distance window to
20,000 m when cloud configuration is absent. Its
`getLinkCommandParams()` sends `interactionType: 1` before navigation and
`interactionType: 3` during navigation, with the latter's
`calculteDistance` set to that configured distance. These values are from the
APK's AJX code. The five-minute default does not establish a seconds-level
live signal feed; `data.horus` remains a candidate source, not a verified
source of the countdown event. An unsigned empty JSON POST to each of
`/ws/perception/drive/routeInfo` and `/ws/perception/drive/navigation`
returns HTTP 200 with `result:false`, `code:3`, `Params error`, establishing
reachability only.
The AJX network wrapper passes `sign: ['channel', 'e_poiid', 'user_loc']` to
`CLNetwork.ajax.post`. The older bundled `CLfetch.js` forwards an `aosSign`
object to `natives.XMLHttpRequest.fetch`. The pinned APK's
`AosRequest.buildHttpRequest()` now establishes the signing input: move
`channel` to the first position, remove `_aosmd5`, concatenate non-null field
values without delimiters (request params, then extended sign params, then
common params, with empty values falling through), append `@` and the APK's
AOS key, then call `IAosEncryptor.sign`. The installed encryptor `rf2.sign`
delegates to `serverkey.sign`. The existing live route adapter's uppercase MD5
formula gives a matching implementation for that final digest step; the
reconstructed code is in `aos_request_sign.py`.

Live `routeInfo` probes on 2026-09-30 separated signature validation from
request validation. A signature computed over body-only `e_poiid` and
`user_loc` failed with `code=4` / `Signature verification failed`; the same
values present in the URL query with the matching signature passed that check
and reached `code=3` / `Params error.` A channel-only signature without those
query fields also reached `code=3`. This shows that the endpoint verifies
against the supplied query signing values in these **plaintext research
requests**, not merely the JSON body's fields. The APK instead sends its
query inside encrypted `in=`; these probes do **not** establish that the
common-param-free synthetic request passed the native transport or session
checks.
Two fresh, identical 5.1 route requests on the same day both succeeded. Their
header field 5 and per-alternative field 6 changed between responses, while
per-alternative field 9 remained equal across alternatives and both requests.
Changing only the destination also left field 9 unchanged; changing the origin
changed field 9. This argues against treating field 9 as a route-specific
`navi_id` and suggests an origin-related identifier, possibly an entry-link
ID, but that exact meaning has not been confirmed. Header field 5 is now
matched to the native `Route.getNaviID()` getter by the 5.1 decode copy at
`0xb8900`–`0xb8908`. No identifier is sent to TMC as a live navigation
session because server-side acceptance has not been established.

The `NaviEventTypeDynamicInfoInteractionData` native producer is at
`libamaphorus.so` `0x6ac428`. Its serializer at `0xd11274` exposes the event
keys `interactionType`, `requestID`, `navi_route_links`, `data_version`,
`navi_id`, `main_path_id`, and `offline_map_param`. At `0x6ac5c8` the producer
gets `navi_id` from a route/path object via `0x723f78` and copies it into the
event. The object is looked up by a numeric path key through `0x74dedc` /
`0x7493b4`; it comes from a native path registry, not the AJX destination
POI. The getter at `0x723f78` calls wrapper `0xc75cdc`, which dispatches the
route object's virtual slot `+0xa0` (`0xc75cf4`–`0xc75cfc`). This is the
same slot used by `Route.getNaviID()` and by the ETA builder; on the online
`DrivePathImpl`, it returns the 5.1 **header field 5** copied into the path
buffer. Route fields 6 and 9 are not alternative NaviID candidates: field 6
is a wire route value and field 9 is the base for packed link IDs. The
remaining uncertainty is whether a Python-created request with that correct
NaviID corresponds to an accepted server navigation session.
Separately, native serializers at `0x778a98` and `0x779dec` emit a `naviID` /
`naviid` string from offset `0x68` of their source route object. This supports
the conclusion that the value lives in native route state; it does not yet
identify the 5.1 response field or the route-state construction step.

The path-state source is now narrower. RTTI in `libassembly_kit.so` identifies
the vtable at `0x10aaa0` as `DrivePathImpl`. Its virtual `+0xa0` getter
(`0xa8040`) returns the path's character buffer at object offset `+0x34`;
virtual `+0xa8` (`0xa806c`) copies an input C string into that buffer, capped
at 36 bytes. The route assembly path at `0x6bd50`–`0x6bd5c` obtains the
source from its decoded-route object at offset `+0x50` and invokes this
setter. The caller at `0x6a888`–`0x6a898` supplies that decoded-route object
from a `PathManagerImpl` request context. Its preparation at `0x6d394`–
`0x6d3a0` copies 0x38 bytes starting at parsed route-data offset `+0x128`
into the source object. Thus the dynamic event reads an ID that came through
the native route-data structure, not one synthesized from coordinates. The
later `0xb8900`–`0xb8908` trace below directly maps 5.1 header field 5 into
that path buffer. Server-side navigation-session acceptance remains separate.
The captured header field 5 is exactly 32 ASCII hex bytes in the Beijing and
Hangzhou samples; per-alternative field 6 is four bytes, while field 9 is
eight bytes. The interaction event's
`main_path_id` is a 32-bit value at event offset `+0x70` (`0xd11318`). The
producer writes it at `0x6ac500` from `0x7217f4`, which returns a selected
path key's `+0x18` word or the first word of its path-key vector. That
identifies the native selected-path source; mapping it to route field 6
remains unverified.
An audit of all six unpacked saved responses found exactly one standalone
32-character ASCII hex string in each; in every case it is header field 5.
The APK's Java `RealNaviEventManager.onCalRoute` (`ae5.java`) creates a
`CalcRouteResult` from selected native route keys and reads
`route.getNaviID()`. Its AJX result model receives a single top-level
`naviId` alongside an array of routes. The separate `0xb8900`–`0xb8908`
trace confirms its header-field-5 source, but does not prove server acceptance
of that value as an active ETA/TMC navigation session.
JADX extraction of `com.autonavi.jni.ae.route.route.Route` confirms
`getNaviID()` is a native JNI method. Its registration table in
`libamaptbt.so` associates the name at relocation `0xf43d38` with
function `0x4a3640`. That function resolves the route object and invokes
its virtual `+0xa0` getter (`0x4a3670`–`0x4a3678`) before creating the
Java string. This ties the Java result consumed by AJX to the same native
getter traced on `DrivePathImpl`; the wire-field-to-path-buffer assignment
is now identified at `0xb8900`–`0xb8908`.

The codec boundary narrows the remaining mapping work. The virtual decode
method at `libassembly_kit.so` `0x6a7c4` takes a pre-parsed input structure in
register `x8`; `0x6a9e4` copies its `+0x128..+0x28f` region into a temporary
route structure. It rejects that structure unless its copied `+0x210` and
`+0x240` pointers are both present (`0x6a848`–`0x6a854`). Afterward,
`0x6d364` copies the first 0x38 bytes of the region into the path's ID source,
and `0x6ba08` installs that source on `DrivePathImpl`. This is an assembly
stage, not the wire-format parser: no instruction in this stage reads protobuf
field numbers 5 or 6. The missing evidence is the earlier writer of the
pre-parsed `+0x128` region. The six saved 5.1 replies show header field 5 as
32 ASCII hex bytes and route field 6 as four bytes; identical route requests
change both while retaining route field 9. The pre-parsed `+0x128` writer in
this older codec stage is still unknown, but the 5.1 decoder at `0xb8844`
independently establishes header-field-5 mapping. Neither path proves a
server navigation session exists for a synthetic Python request.
The codec's relocated virtual table at `0x108740` begins with callbacks
`0x6a7c4`, `0x6ac7c`, `0x6ad64`, and `0x6adac`. The next callback
(`0x6ac7c`) only advances codec state from 2/5 to 3; it calls a constant-true
helper (`0x6c95c`), not a protobuf reader. This rules out treating the next
virtual slot as the missing 5.1 field decoder. No direct write to the
pre-parsed route structure's `+0x128` source was found in this codec's
assembly path. This is still an open edge for that particular codec stage;
the separate `0xb8844` path supplies the 5.1 field-number mapping.
The AJX `CarResultData.js` route model takes `naviId` from the native route
result's `t.naviId` (`set` path around line 208); it does not derive the ID
from the destination or route coordinates in JavaScript. This is another
consumer of the already-decoded value, not the wire-field mapping.

The native event serializer at `0xd109a4` through `0xd10bec` exposes the
`navi_route_links[]` element's JSON keys: `startsegmentidx`,
`endsegmentidx`, `segment`, `links_prop_start_end`, `segment_distance`,
`links_adcode`, `links_eta`, `path_id`, `service_area_poi_ids`,
`sub_e_poiid`, `sub_e_poi_x`, `sub_e_poi_y`, `sub_e_navi_poi_x`,
`sub_e_navi_poi_y`, `sub_end_poi_type_code`, `recommend_level`,
`via_link_ids`, `length`, `rest_area_links`, `route_links`,
`route_links_length`, `route_links_road_class`, `route_links_start_point`,
`route_points`, and `car_info`. `route_links` is serialized as an array of
strings; `route_points[]` carries `lon`, `lat`, `navi_lon`, `navi_lat`,
`type`, `poiid`, `name`, `waypoint_name`, and `points`. This is far more than
a navigation ID and destination coordinate. The 5.1 decoder extracts
segment geometry and signalized-crossing flags; the cross-route check below
now also recovers stable candidate link IDs, but direct identity with the
native event and its path registry is not yet verified.
`TripNaviLinksHelper.fetchRouteLinks()` obtains these values
through `kSetInteractionData` rather than constructing them in AJX.
The string encoding itself is now verified at `libamaphorus.so` `0x6ae54c`:
each native link object is queried through `0xc75528` (virtual slot `+0x80`)
for a 64-bit ID. The first ID is formatted with `%llu` via `0xba0998`; every
subsequent ID is subtracted from the previous one and formatted with `%lld`
via `0xba0a6c`. The strings are appended to the output vector at
`0x6ae7dc`. The drive link implementation's `+0x80` method resolves in
`libassembly_kit.so` to `0x942b4`, which reads the packed 64-bit value at
link-object offset `+0x38` (initialized to all ones in `0x93b6c`). The
reversible Python encoder/decoder is `dynamic_route_links.py`. The candidate
underlying ID sequence is recovered from 5.1 field 9 and ZigZag link-field-1
deltas below; native-event equivalence and the rest of the route-link object
remain to be validated.

Tracing the ID one step farther reaches `libassembly_kit.so` `0x7bec4`:
`DriveOfflinePathAdapter` creates a `DriveLinkImpl` and stores a 64-bit packed
ID at link offset `+0x38`. The packed value combines a 64-bit base from its
source link record (`+0x00`) with a word at `+0x10` shifted left 21 bits and
a byte at `+0x30` shifted left 31 bits. `DriveLinkImpl`'s `+0x80` virtual
method (`0x942b4`) later returns precisely this offset. The relevant adapter
method is installed in its vtable at `0x109a80`; there is no direct `bl`
callsite. This establishes the native link-ID construction for that adapter,
but does **not** yet prove the online path uses the same source records.

The captured 5.1 responses now yield a consistent candidate link-ID decoder:
route field 9 is an eight-byte base, and each link's field 1 is an unsigned
varint holding a **ZigZag-encoded signed 64-bit delta**. Starting from the
base, add `(raw >> 1) ^ -(raw & 1)` modulo `2^64` for *every* link, including
the first (whose raw value is zero in all saved responses). The prior probes
and analyses tried unsigned accumulation, independent `base + field1`, and
separate signed 32-bit halves. Those interpretations were wrong: they failed
to preserve identity after routes diverged and rejoined.

The ZigZag interpretation has a strong cross-route invariant. Exact shared
link geometries decode to the same 64-bit value for **34/34** links across
Beijing alternatives, **63/63** across Hangzhou alternatives, and **8/8**
between captures with different Beijing origins. A fresh response for the
same Beijing route also matches **64/64** shared links. Across every pair of
the six saved 5.1 captures, all **135/135** exact shared geometries have
matching ZigZag-derived IDs. The corresponding
unsigned accumulator matches 28/34, 4/63, 0/8, and 33/64. This comparison
is reproducible with `compare_v51_link_ids.py` and the bounded decoder in
`dynamic_route_links.py`. Field 9 values such as `0x4712e5a9802009d3` also
have the packed bit layout returned by `DriveLinkImpl`, consistent with a
true link ID. These independent samples make the field mapping substantially
stronger than the previous guess, although a direct native event capture
would still be needed to prove byte-for-byte identity with `route_links`.

The adjacent `route_links_length` native vector is also mapped. In
`libamaphorus.so` `0x6ae66c`, the producer reads each link's virtual slot
`+0x18` through `0xc7526c`. On `DriveLinkImpl`, that slot is `0x93f68` and
returns the object's length stored at `+0x18`; the offline adapter copies
it from source-link offset `+0x14` at `0x7bef0`–`0x7bef4`. The **online**
5.1 assembler is decisive for our route source: `libassembly_kit.so`
`0xbb794`–`0xbb7a8` reads parsed link offset `+0x14` (wire link field 2),
divides it by 100, and writes the integer result to `DriveLinkImpl+0x18`.
The previous research extractor accidentally emitted the raw wire value,
making every `route_links_length` about 100 times too large. It now emits
whole metres. In all six saved route responses, the per-link values sum
exactly to the route's native length (2,719–7,075 m), an independent
invariant of the corrected unit mapping.
`route_links_road_class` comes from another per-link virtual getter
(`+0xf0` via `0xc757ec`); a direct mapping to 5.1 fields is still open.
The research-only `v51_dynamic_route.py` now extracts candidate session ID,
selected path ID, native-format link-ID delta strings, per-link 5.1 lengths,
and link-start coordinates from one decoded route. It keeps these opaque
values outside TMC's public navigation DTO. The extractor passed all six
saved 5.1 responses (23–95 links in the selected alternatives); it is a
preparation for a faithful dynamic-info request, not a successful live
traffic-light response.
One bounded `routeInfo` probe used a freshly returned header field 5 as a
candidate `navigation_id`, the first route's field 6 as a candidate path ID,
and its decoded endpoint geometry. The signature passed verification but the
service still returned `code=3` / `Params error.` At the time, the
`route_links` IDs had not been decoded correctly and the request did not pass through
the APK's body encoder/common-parameter path, this does not disprove either
ID candidate or identify which validation failed.
A second bounded probe on a fresh successful 5.1 route supplied all 64
*incorrectly unsigned-decoded* candidate links as first absolute ID plus signed deltas, their
lengths, the route's start/end points, route field 6 as `main_path_id`, header
field 5 as `navigation_id`, and header field 2 (`30282`) as the candidate
`data_version`. It also included the ordinary AJX `routeInfo` envelope
fields. The service again returned HTTP 200 with `code=3` / `Params error.`
This establishes only that the plaintext synthetic request was rejected;
it cannot isolate body encoding, common parameters, wrong link IDs, or
session metadata. Do not turn this experimental request into a production
fallback.
The `data_version` value in that probe was also the wrong type. The native
event serializer at `libamaphorus.so` `0xd112e8`–`0xd112fc` emits it from a
string field at event offset `+0x40`; header field 2 (`30282`) was supplied
as an integer without evidence of that *event-field* mapping. The later
confirmed use of header field 2 for ETA XML `DataVers` does not make this
different `routeInfo` JSON `data_version` field an integer. The event constructor
`0xcf167c -> 0xd17fec` zero-initializes this field, and the inspected event
producer `0x6ac428` does not assign it. A fresh bounded probe repeated the
full candidate-link request with `data_version` as an empty string, matching
this native event's default. It still returned HTTP 200, `code=3` / `Params
error.` This result also cannot isolate the `data_version` type because the
outer request still differed from the APK's encoded/common-param request.

The Python research adapter has `dynamic_info_request.signed_query()` for
the AJX request's channel-only signing input. An earlier version incorrectly
copied `e_poiid` and `user_loc` from the JSON body into the URL. Although the
AJX logic declares these three signing *key names*, its `_postRequest()`
passes the values only as a body string; `ModuleRequest.optionsToRequestInfo()`
leaves `cVar.p` (the URL request-param map) empty for that call and stores the
body in `cVar.g`. `AosRequest.buildHttpRequest()` looks up signing values only
in URL request, extended-sign and AOS common-param maps, never in the JSON
body. The common map supplies `channel` but not `e_poiid` or `user_loc` in the
inspected provider. Thus their absent URL values append nothing and the
ordinary MD5 input is `channel + "@" + aos_key`. The research adapter does not
send a production dynamic request or invent the missing session fields. A
bounded trial with the same APK route endpoint
using `output=json` returned `code=2` / `Failure.` and an empty `path_list`;
it did not provide an alternate JSON source for the native path metadata.

`libamaptbt.so` contains a tempting `buildNaviID` log at `0xa12edc`, but
following its branch prevents a false shortcut. The branch at `0xa12f9c`
calls `0xa384dc`, which formats a locally generated value using the literal
`%s--%llu-%llu-%llu-%d-%d` (`0x97c83`) and appends `offnid` (`0xee850`).
This is the offline-route ID path. The other branch at `0xa13044` reads an
existing object from route state (`this+0x188`), invokes its virtual `+0xa0`
method to obtain a path, then its virtual `+0x40` method to obtain an ID and
installs it on the destination path through virtual `+0x90`. Thus copying the
offline `offnid` generator into Python would not reproduce the online
navigation session. Captured 5.1 responses also contain a 32-character hex
string in header field 5; it differs between two responses for the same
route. The online `navi_id` mapping is established independently by the
`0xb8900`–`0xb8908` copy described above.

The navigation drive-context builder gives a second, independent use of the
online path string. Its only direct caller, `0x4d1bb8`, passes the current
engine object at `+0xe8` to `0x51272c`. That builder reads the engine's
`+0x38` route-state pointer (`0x521b68`), wraps and checks it, then invokes
`0xcd8540` at `0x51277c`. The wrapper dispatches the route object's virtual
`+0xa0` getter (`0xcd8540`–`0xcd8550`), and the returned string is copied to
the first field of the drive context at `0x512784`–`0x512788`. The same
`+0xa0` getter is used by the JNI `Route.getNaviID()` path at `0x4a3670`–
`0x4a3678`. The builder also copies path identifiers to context offsets
`+0x18` and `+0x1c` from separate getters; the `NaviID` is not those numeric
IDs. This strengthens the conclusion that the online navigation ID comes
from the selected native route object, not the local `offnid` generator.
The 5.1 header-field-5 source is established by the direct copy above; a
Python request containing it still has not established a server navigation
session.

The direct `0x51272c` call also has an explicit empty-context fallback at
`0x4d1bbc`–`0x4d1c44`: it tests both the copied first string and the numeric
path ID at context `+0x18` and logs `fillDriveContext` when they are absent.
This is a local context-construction path, not evidence that the server has
accepted the route. In particular, the 53-byte ETA probe response echoes
both a candidate and an all-zero `NaviID` with the same fixed prefix, so
this context relationship does not change the probe's failure interpretation.

The App also contains `host_aos/ws/navigation/dynamic/data?` at
`libamaphorus.so` VA `0x141830`. The shared initializer at `0xd24a2c` copies
this literal into several request objects. It is **not** enough to identify a
traffic-signal request: one concrete class created at `0xd1c500` serializes
`keywords`, `query_type`, `pagesize`, `pagenum`, `longitude`, and `latitude`
(serializer `0xd22bb4`), while a second class created at `0xd1c7d0`
serializes `start_x`, `start_y`, `end_x`, and `end_y` (serializer `0xd23438`).
These are generic search/route fields, and neither class has been tied to
component `0x2972`. A bare GET or POST to
`https://m5.amap.com/ws/navigation/dynamic/data?` returned HTTP 200 with
`result=false`, `code=3`, `Params error`. This confirms reachability only,
not the request contract or a usable signal response.

For a browser + Python deployment, remaining work is to obtain either a
successful HTTP `data.horus` response with live signal records or a validated
ACCS message carrying them; establish that source's real navigation-session
contract; then bind updates to the current route and location and expire
them promptly. The APK proves both delivery paths exist, but no captured
payload has yet linked either one to the countdown component.
The standalone `ws/shield/trafficlights/realtime` registry entry may or may
not be this source. Until a successful response is validated, TMC must not
display a live phase or countdown. Route traffic-light counts and markers use
a separate, verified static route decoder.

The `traffic_signal` registry row's layout was rechecked against adjacent
records: it starts at `0xf4e678` with ID `0x6e`, then selectors, host
pointers, name at `0xf4e698`, and URL at `0xf4e6a0`. The **next** row starts
at `0xf4e6a8` with ID `0x6f` and name `driving_behavior`. This confirms the
earlier correction at the top of this note. Tracing the apparent `0x6f`
caller at `0x670afc -> 0x6738ac` reaches its request-object lookup, but
that is the driving-behavior request, not a traffic-signal sender. The
`0x6e` sender and request body remain unidentified.

A subsequent scan corrected an ELF-disassembly mistake: decoding executable
`PT_LOAD` from its first byte stopped before `.text`, so a previous absence
of literal `0x6e` was not evidence. Decoding the actual `.text` section finds
48 `mov ..., #0x6e` instructions in `libamaptbt.so`. Most are unrelated
numeric constants. In particular `0x5b5bdc` is a branch of an internal
event/error-code selector that forwards `0x6e` to `0x5ae5cc`; it is **not**
an AOS request. The confirmed AOS request factory is `0x6738ac`, used by the
ETA sender at `0x6bede8`. Its 25 direct `bl` callsites were checked: the
immediate request IDs include `0x6f` (`driving_behavior` at `0x670afc`) and
others, but none directly loads `0x6e`. The generic caller at `0x79b85c`
passes an ID from object offset `+0x34`, so this does not exclude an indirect
`0x6e` request. The dedicated URL is definitely registered, while its
runtime sender still has not been tied to navigation. Do not confuse any
`0x6e` literal with a verified traffic-signal request.

The ETA root builder writes `Source="amap"` at `0x6c64cc`–`0x6c64dc` and
`Invoker` from a runtime mode at `0x6c64e4`–`0x6c64f0`. The latter defaults
to `navi` (`0xda8c2`); the three indexed alternatives at table `0x118dd0`
are `explore`, `emergency`, and `commute`. The adjacent literal `privacy`
at `0x6c6514` is a **separate attribute name** whose value is formatted
from a context getter; it is not the `Invoker` value. A first bounded probe
mistakenly sent `Invoker="privacy"`; a corrected fresh-route probe sent
`Source="amap" Invoker="navi"` with the prior APK-account, `ReqType=8`
control then `ReqType=3` update request, GPS history near the first route
light, native static version and route `DataVers`. Both corrected replies
still decoded to native `etaCode=2`, zero payload, 53 bytes. Missing these
two default-branch root attributes alone is therefore not the cause. Other
dynamic attributes and, more critically, an established navigation session
remain unverified.

The App's AJX route constants accept `plan` and `navi` as distinct route
invokers, and `XbusRouteParamAdapter.generateXbusRouteParam()` defaults to
`navi`. To test whether the Python route planner's `invoker=plan` alone made
its header-field-5 `NaviID` ineligible for ETA, one bounded probe changed
only that route request parameter to `navi`, then used the fresh route in the
same `ReqType=8` control / `ReqType=3` update sequence. Both replies again
contained only the 53-byte frame, native `etaCode=2`, no payload. This
eliminates a lone route-invoker mismatch as the explanation, but the route
request is still not equivalent to `setNaviPath()` plus `startNavi()` or a
verified server-side navigation session.

The `GuideService` JNI registration deserves an important qualification.
Its `JNINativeMethod` table begins at `0xf437c8`: `init(GuideConfig)` maps
to `0x49b36c`, `startNavi(int)` to `0x49b484`, and `setNaviPath(GNaviPath,
int)` to `0x49b584`. The table is registered for
`com/autonavi/jni/ae/guide/GuideService` by the registration routine at
`0x49ac34` (class lookup `0x49ac54` and `RegisterNatives` near `0x49b1e8`).
But the registered `init` implementation is only a tail call through the
JNI table at offset `0x328`, i.e. `GetLongField(this, mPtr)`; it does not
construct an engine or set `mPtr`. Both `startNavi` and `setNaviPath`
first read that same `mPtr` and return or skip dispatch when it is zero.
In the inspected decompiled Java, `new GuideService(...)` has no external
caller; the only external reference found is its static SDK-version query
in `p02.java`. This makes the previously described `GuideService` path a
possibly dormant compatibility binding in this APK, **not** proof of the
active App's navigation startup sequence. More importantly, reproducing
its `startNavi()` call in Python cannot be treated as the missing server
session step. The live App's AJX trip-navigation/Horus path needs to be
traced independently. The cause of ETA `etaCode=2` remains unproven; the
missing active session is still a candidate, not a decoded error meaning.

One concrete start marker exists in that AJX path. In
`TripDynamicInfoRequestUtils._getCommonRequestParams()`, a request made from
the navigation page for `SCENE_TYPE.BEFORE_NAVI` compares the native
`fetchRouteLinks()` result's `navi_id` to `startNaviId`. On a change it sets
`behavior_type="start_navi"` exactly once for that ID. The corresponding
request is `DynamicInfoNaviRequestLogic` to
`/ws/perception/drive/routeInfo`; ongoing `SCENE_TYPE.NAVIGATION` uses
`DynamicInfoNaviLoopRequestLogic` to `/ws/perception/drive/navigation`.
This distinguishes the active page's before-navigation message from the
legacy `GuideService.startNavi()` JNI call. It does **not** show that
`behavior_type` alone creates a server session: the same body includes the
native `navi_route_links`, `main_path_id`, route points, vehicle and location
context. The existing encoded synthetic `/routeInfo` probe still returns
`code=3` / `Params error.` and lacks a verified complete native event.
Repeating that same encoded candidate with only `behavior_type="start_navi"`
added again produced HTTP 200, `code=3` / `Params error.` This rules out
that marker alone as the missing field in the incomplete synthetic body;
it does not test the full App request or the eligibility of a real route.

The earlier `main_path_id` candidate was **misidentified**. The 5.1 route
schema at `libassembly_kit.so` `0x10e870` maps route field 6 into its parsed
record's `+8` word. The online decoder at `0xb8924`–`0xb8928` copies that
word into `DrivePathImpl +0x4e4`; virtual getter `+0x330` (`0x96e7c`)
reads this wire-route value. In contrast, JNI `Route.getPathId()` is
registered at `libamaptbt.so` `0xf43f90` / `0x4a4780` and calls virtual
slot `+0x20`, which on `DrivePathImpl` resolves to `0xa7edc` and reads
object `+0x14`. That field is initialized to zero by constructor `0xa7b70`
and, on path-wrapper construction at `0x7acb0`–`0x7ad08`, receives a value
from allocator `0xab9b8` if still zero. The allocator's initial global is
`100001`; its first returned ID is `100002`, incrementing within a bounded
range. `CarRouteParser.java` independently assigns
`navigationPath.mPathId = route.getPathId()`. Therefore field 6 cannot be
substituted for the App's runtime path ID in a synthetic dynamic-info
request. `v51_dynamic_route.py` now names it `wire_route_field6` instead of
`main_path_id_candidate`.

This still does not prove that Horus event `main_path_id` always equals the
first locally allocated `Route.getPathId()`: the event reads the currently
selected path key from native registry state. A bounded synthetic encoded
`/routeInfo` probe used `100002` for both `main_path_id` and the sole
`navi_route_links[].path_id`, leaving the incomplete remainder unchanged.
It still returned HTTP 200, `code=3` / `Params error.` The numeric-ID
correction alone is insufficient, and the probe does not establish a valid
App navigation session.

Further path-registry tracing establishes the *type* of that selected key.
`libamaphorus.so` `0x721d78` walks the navigation state's path-key vector,
looks up each object through `0x74dedc`, then invokes its virtual `+0x20`
slot at `0x721e04`–`0x721e08`. JNI `Route.getPathId()` invokes that same
slot, and `DrivePathImpl` implements it by reading the locally allocated
path ID. `0x7216c0` retains the keys in the Horus state; `0x7217f4` selects
the explicit `+0x18` key or the first vector entry, which the event producer
writes as `main_path_id` at `0x6ac500`. Thus the event's numeric path key
comes from the route registry rather than 5.1 route field 6. It remains
unsafe to assume **100002** for a real session: that is merely the first
allocator result in a fresh process, and prior allocations, alternative
paths and route changes can select another ID. This explains why filling
field 6 or a fixed allocator seed cannot reconstruct the complete native
event by itself; it does not isolate the server's generic `code=3` cause.

The research probe initially provided only **6 of the 25** keys that the
APK serializer emits for each `navi_route_links[]` element: `path_id`,
`route_links`, `route_links_length`, `route_links_road_class`,
`route_links_start_point`, and `route_points`. It omits the segment-index
range, `segment`, `links_prop_start_end`, `segment_distance`, `links_adcode`,
`links_eta`, route length, via/rest-area metadata, recommendation level,
sub-destination metadata, and `car_info`. The saved 5.1 route used by the
probe has **12 segments and 64 links**; at that point all segment-level event
fields were absent. This is a concrete mismatch from the App event, although
the server's generic `Params error` does not identify which omitted or
inconsistent field is decisive. The next valid experiment must reconstruct
the segment objects and their native field values from the decoded route
before treating `/routeInfo` rejection as a signing or entitlement result.

The segment source is now partly traced. In `libamaphorus.so` `0x6ad530`,
the event builder iterates native route segments (`0xc7a71c`) and their
links (`0xc7b258`). For each link it reads the 64-bit ID via `0xc75528`
and appends it to a per-segment vector at `0x6ad758` / `0x6add34`.
`0x6ad858`–`0x6ad888` passes that vector to `0x6ab5d8`, whose formatters
emit the first ID as `%llu` and subsequent differences as `%lld`, joined by
commas. The resulting per-segment strings are copied into event offset
`+0x38` at `0x6ad940`–`0x6ad948`, which the serializer labels `segment`.
This proves `segment` is constructed from native link IDs grouped by
segment, not merely the segment count. The later-segment base choice is
also recoverable: `0x6ad788` captures the first selected link ID, and
`0x6ad868` supplies it to `0x6ab5d8` as the base for later segments.
The research-only extractor now outputs `segment_candidate`, grouping the
decoded 5.1 link IDs by wire segment and applying that native
first-absolute/then-anchor-delta scheme. All six saved route responses
produce nonempty groups (11–25 segments, 23–95 links). The source-ID
mapping to actual `DriveLinkImpl` objects remains a strong cross-route
inference, not a captured native-event comparison.

Adding this seventh field to one fresh, native-body-encoded `/routeInfo`
probe did **not** change the server response: both ordinary and intentionally
invalid-`x-sign` controls returned HTTP 200 with `code=3` / `Params error.`
Other native event fields and the actual navigation session are still
missing, so this negative result isolates only the `segment` field alone.

The adjacent `links_prop_start_end` builder is `0x6ad0e0`, called at
`0x6ad7a8` for boundary links. It invokes link-object virtual slots
`+0xf0` and `+0xe8` and formats their integer results as `%d-%d`, with a
leading comma when another boundary record already exists. The `+0xf0`
slot is the same road-class getter already mapped to the 5.1 attribute;
`+0xe8` resolves to `DriveLinkImpl` `0x94520`, which reads road-record
offset `+4` or returns `-1` when unavailable. The online route builder
copies parsed-link offset `+0x48` into that road-record word at
`libassembly_kit.so` `0xbb8c4`–`0xbb8c8`. The nested 5.1 schema chain can
now be followed through ELF relocation targets: root field 2
(`0x10eaf0`) → route message `0x10e7d0`, message field 7 (`0x10e890`) →
route `0x10e370`, route field 10 (`0x10e490`) → segment `0x10db70`, segment
field 3 (`0x10dbb0`) → link `0x10d990`, and link field 7 (`0x10da50`)
→ attribute schema `0x10d790`. Attribute fields 1 and 2 are consecutive
4-byte scalars, matching the parsed-link `+0x40` and `+0x48` source words
copied to the road record. All 191 attribute records in the six saved
responses contain field 2. This establishes the second formatter input as
link attribute field 2, with the same per-segment inheritance as road class.
The native loop at `0x6ad790`–`0x6ad7a8` invokes the formatter for the
first and last link of each included segment; a single-link segment is
emitted once. The research extractor now emits a
`links_prop_start_end_candidate` array using this rule. That still assumes
the full planned path is selected, since the App can truncate a navigation
segment range, and has not been compared to a captured native event.
Adding `links_prop_start_end` as an eighth populated event field to one
fresh encoded `/routeInfo` probe again returned HTTP 200 with `code=3` /
`Params error` for both the ordinary request and invalid-`x-sign` control.
This does not isolate a server validator: `segment_distance`, `links_eta`,
road-area metadata and the rest of the native event remain absent.

The encoded probe also accidentally kept the older integer
`data_version=header.field2` despite the native event's string field being
default-initialized to empty. Correcting it to `""` while retaining the two
new segment arrays still produced HTTP 200, `code=3` / `Params error` for
both ordinary and deliberately invalid-`x-sign` variants. The integer type
was a real fidelity error in the probe, but not by itself the observed
server rejection.

The AJX transport adds another concrete request difference. In the
extracted `CLNetwork.js`, `Ajax.prototype.request()` instantiates an
`AosRequest` whenever the call specifies `sign`; that constructor sets
`aosSign.aos_params=true` and `ent=true` for a release build. The native
`XMLHttpRequest` bridge therefore adds App AOS common parameters. The
synthetic Python request currently includes only `channel`, `e_poiid`,
`user_loc`, and `sign` before body encoding. APK Java
`NetworkParam.getNetworkParamMap()` populates `div`, `siv`, `dip`, `dic`,
`diu`, `diu2`, `diu3`, `dai`, `cifa`, session/app-start/step IDs, channel,
network class, `dibv`, `BID_F`, `aetraffic`, `oaid`, ABI and locale fields,
plus conditional account/device fields. `getAosCommonParam()` also adds
`x-gen` and `Ap-Tid` headers. This is a demonstrable transport mismatch,
not evidence that any one common parameter causes `code=3`. Reconstructing
the bridge's exact canonicalization and a stable synthetic device identity
is necessary before treating route-event-field probes as decisive.

The AOS common-param provider is now traced end to end, rather than inferred
from matching class names: `ModuleRequest.c.a()` selects common-param strategy
0; `AosRequest.buildHttpRequest()` calls `l60.a().getAosCommonParam()`;
`AosService.e(new m60())` registers the App context; `m60` constructs `mp5`;
and `mp5.getAosCommonParam()` delegates to
`NetworkParam.getAosCommonParam()`, which calls `getNetworkParamMap()` for
strategy 0. The App therefore really does put that map in this AJX request.
For `/routeInfo`, a JSON POST body exists, so `AosPostRequest.processParams()`
places the common params in the URL query, then `AosRequest` encrypts that
query as `ent=2&in=...`. The earlier Python probe's explicit URL copies of
`e_poiid` and `user_loc` were not App-equivalent, even though they passed a
separate plaintext signature check.

After correcting the research helper and encoded probe to the channel-only
signing input, one fresh-route `/routeInfo` request still returned HTTP 200,
`code=3` / `Params error` for both the ordinary and deliberately invalid
`x-sign` variants. This narrows a real local mismatch but does not identify
the first rejecting server condition: the probe still lacks the actual
device/session common-param values, complete native navigation event and
SecurityGuard output. The older plaintext channel-only probe also reached
`code=3`, so the encoded result is consistent with that earlier boundary
check, not a new successful session.
The same corrected request sent to the AJX result-page `/routePlan` variant
also returned `code=3`; changing the page endpoint does not make this
incomplete native-event candidate valid.
The base `AosRequest.getAosCommonParam(true)` also appends `output=json` for
an AOS request. Adding this confirmed query field to the bounded encoded
`/routeInfo` probe again left both security-header controls at `code=3`.
This rules out that single omitted field as the cause for that candidate;
it does not cover the remaining common-param map or response validation.

For a before-navigation event, `libamaphorus.so` `0x6ad56c`–`0x6ad588`
initializes the segment window to start index 0 and end index
`segment_count - 1`; only the mode-3 branch at `0x6ad590` narrows that
window. The research extractor now emits those two index candidates from the
decoded 5.1 segment count, and the probe includes `startsegmentidx` and
`endsegmentidx`. One fresh-route encoded `/routeInfo` request with them still
returned `code=3` for both security-header controls. Other native event
fields and App runtime context are still absent; this result isolates neither
the index values nor a server-side validator.

The route-link start-point wire shape is now identified. The Horus native
producer at `libamaphorus.so` `0x6ae6b8`–`0x6ae708` reads each link's first
integer coordinate, divides both axes by the double constant `3600000.0`
at `0x102748`, and formats it with literal `"%.6f,%.6f"` at `0x13c292`.
The JSON serializer uses a vector-of-strings writer for
`route_links_start_point`. A research probe therefore added all 64
candidate link-ID strings, corresponding 5.1 lengths, these formatted
start-point strings, and start/end route points to the same synthetic
`navi_route_links` element. `/routeInfo` still returned HTTP 200,
`code=3` / `Params error.` The unchanged result does not invalidate the
recovered field format: other element fields (including road classes and
segment metadata), native route state, and request context remain missing.

The encoded routeInfo experiment was then repeated with a **freshly fetched**
successful 5.1 route (`invoker=navi`) and its new header-field-5 navigation
ID, rather than the previously saved response. It immediately sent the
same candidate native link arrays and local path-ID hypothesis through the
research body/query encoder. The endpoint again returned HTTP 200,
`code=3` / `Params error.` Route-ID age alone does not explain this
particular failure; missing complete route-event fields, common parameters,
or SecurityGuard headers remain unresolved. The fresh route was used only
for this bounded research probe, not installed as a real App navigation
session.

A further bounded fresh-route probe filled the most visible
`TripDynamicInfoRequestUtils._getCommonRequestParams()` and
`_getResultRequestParams()` top-level fields: POI/adcode, current city,
navigation type, app version, cloud-control defaults, vehicle and
result-page context, plus the decoded 5.1 data version. It still returned
HTTP 200, `code=3`, `Params error.` These synthetic values are **not** a
captured App session; several nested values and all native AOS common
parameters/SecurityGuard headers remain unverified. This rules out only
the narrow hypothesis that those omitted top-level *keys by themselves*
were enough to make this probe succeed. It does not locate the validator's
first failing condition or establish a usable live signal feed.

The missing `route_links_road_class` value was traced one step farther.
`libamaphorus.so` `0x6ae688` calls virtual slot `+0xf0` for each link. The
relocated `DriveLinkImpl` vtable at `libassembly_kit.so` `0x10a438` maps
that slot to `0x9454c`. It reads a linked road/attribute object through
link offset `+0xa0` and returns that object's word at `+8`, or the
fallback `11`; it does **not** read a simple byte from the link itself.
`DriveOfflinePathAdapter` stores the road-context pointer into link
`+0xa0` at `0x7be64`–`0x7be6c`, while copying source-link byte `+0x3c`
into link `+8` separately at `0x7bec8`–`0x7bed0`. Therefore assigning a
5.1 link field directly to `route_links_road_class` without tracing the
linked object would be speculative. This is another concrete part of the
unreproduced native route-event state.

The linked value can now be traced through that adapter: `x26` is the path
context loaded from adapter `+0x10` at `0x7be10`. A new 0x10-byte road
record is appended to its pointer vector at `+0x88`, and the resulting
index is stored on the link at `+0x40` (`0x7be70`–`0x7bea4`). Helper
`0x7c164` copies the source link's byte `+0x31` into that record's word
`+8` (`0x7c184`–`0x7c190`). The `+0xf0` getter's bounds check at
`0x94940` uses exactly this vector and index before returning record
`+8`. Thus the native event's road-class value is the decoded source-link
byte `+0x31` when the context is intact, or `11` on failure. The remaining
mapping is **5.1 wire link field → decoded source-link `+0x31`**; none of
the candidate wire fields should be used until that mapping is established.

The indirect AOS factory call at `libamaptbt.so` `0x79b85c` was followed
through its enclosing request class. It reads the factory ID from a
registered RB-tree node at `+0x34`; the neighboring startup/send method at
`0x79b8f0` itself allocates request type `0x134` (`0x79b918`–`0x79b934`),
then builds a payload from native navigation context. Its tree registration
copies a caller-provided node (`0x79be10`–`0x79be40`), so this path does
not prove the registered `0x6e` traffic-signal request is sent. The earlier
direct factory-call scan likewise found no `0x6e` sender. Treat the
realtime URL as a registered but unverified source, not the source of the
observed `26403` event.

One same-body, same-fresh-route differential request tested whether a
deliberately invalid `x-sign` plus `x-t` and `x-pv` changes the
`/routeInfo` failure. Both the no-header and invalid-header variants
returned HTTP 200 `code=3` / `Params error.` This is inconclusive: the
synthetic body, absent native common parameters, and omitted companion
SecurityGuard headers can fail independently. It neither proves that
`x-sign` is unnecessary nor that the server validates it at this stage.

The result-page `/ws/perception/drive/routePlan` variant was also tested
once with a newly fetched 5.1 route, `page_scene=1` and no `start_navi`
behavior. It returned the same HTTP 200 `code=3` / `Params error.` Thus
switching from the navigation-page endpoint to the result-page endpoint
does not by itself remove the synthetic request's rejection. It still
omits the native common parameters and verified route-event data; no
traffic-signal payload was obtained.

The pinned ARM64 `libsgmainso-6.8.260404.so` has malformed section
headers, so ordinary ELF section iteration fails; its valid program and
dynamic headers still expose 171 dynamic symbols and a large native import
surface, including threading, filesystem, socket, Android properties,
`dlopen`/`dlsym`, and zlib. This is the library behind the SecurityGuard
router called by Java for virtual V2 signing. It is not a self-contained
hash function that can be substituted with the AOS MD5 signer. Porting or
emulating its 70102/10401 paths would require handling Android-dependent
initialization and runtime inputs; no valid `x-sign` or ACCS bind signature
has been produced yet. The two `code=3` differential probes above do not
establish that this signer is the first failed check.

An isolated Unicorn probe of this pinned ARM64 library now reaches its
`JNI_OnLoad` registration. With stubbed Android/libc imports it returns
JNI version `0x10004` and calls `RegisterNatives` for
`com/taobao/wireless/security/adapter/JNICLibrary.doCommandNative`
with signature `(I[Ljava/lang/Object;)Ljava/lang/Object;` at VA
`0x57598`. This is the concrete native router entry for Java's 70102
request, not an exported `getSecurityFactors()` symbol. At `0x575c4`–
`0x57680` it decomposes the integer command and forwards it to `0x54e10`;
that routine selects a registered handler through `0x54648`. Directly
invoking 70102 after only `JNI_OnLoad`, with fake Java objects, falls
through the native exception path and yields no signature. The Java
`SecurityGuardMainPlugin.onPluginLoaded()` calls router command 10101
first with an 11-element array including real Android Context, package,
version, process and plugin objects; middle-tier setup follows. A crude
10101 emulation with synthetic objects entered native initialization but
did not finish within its 200,000-instruction bound. Thus JNI registration
has been located and experimentally reached, while valid plugin
initialization and 70102 input/result semantics remain open. The probe
is research-only at `.local-data/amap-app/probe_sg_jni.py`; its stubbed
return values do not authenticate an AOS request.

The probe was extended to retain one Unicorn instance across the Java
startup command sequence `10101 → 10104 → 70103 → 70102`, with bounded
synthetic Object arrays. This reached the **actual 70102 handler lookup**:
the router decomposes 70102 as group `7`, component `1`, operation `2`,
and `0x54648` returns handler VA `0xcb410` with lookup status zero. The
handler begins by reading the passed array via helpers such as `0x149890`
and enters further native commands; it later reaches the exception path
under the fake JNI/Android environment. No output map or `x-sign` was
obtained. This rules out the previous suspicion that the handler could
not be registered at all in isolated emulation; the remaining failure is
inside handler execution and/or its nested runtime dependencies, not the
router's inability to identify command 70102. `0xcb410` is now the exact
static-analysis target for the V2 signature path.

The next bounded trace separated the router's two handler registries. With
the synthetic startup sequence, `70102` first resolves in **mode 1**
registry `0x580160` to wrapper `0xcb410`. That wrapper successfully copies
the first supplied Java string (`example`, length 7) and parses all twelve
array slots; its first-argument empty check at `0xcba00`–`0xcba84` passes.
At `0xcbac8`–`0xcbae8` it dispatches the same `(7,1,2)` command through
the **mode 0** registry `0x580020`. This lookup has no handler and returns
`0x29c8de12` (`70102 * 10000 + 9906`), which becomes the Java-side
`701029906` exception code. The observed failure is therefore not caused
by the synthetic first string being empty, nor by failure to enter the
outer wrapper. The inner provider has not registered in this isolated
environment. This does **not** prove the actual Android App lacks it:
the fake JNI/Context, Android imports and startup state can suppress its
registration.

The sequence also matters. Omitting `10104` after `10101` makes `70103`
fail with `701039904` and prevents even the outer `70102` lookup
(`701029904`); running `10104` makes the outer `70102` and `70103`
available, but still leaves the inner `(7,1,2)` provider absent. Thus
`10104` performs at least part of middle-tier registration, while a
further native/Android initialization dependency remains. The probe
records both registry addresses and per-command error codes; no valid
signature or authenticated traffic-signal response has been obtained.

The APK's actual Java async plugin loader calls
`SecurityGuardSecurityBodyPlugin.onPluginLoaded()` before
`SecurityGuardMiddleTierPlugin.onPluginLoaded()`. In its cached-library
branch these invoke `10103` and `10104`, respectively. Repeating the
isolated probe with `10101 → 10103 → 10104 → 70103 → 70102` still leaves
the mode-0 `(7,1,2)` handler absent and returns `701029906`. The Java
plugins also perform Context-dependent setup before and after these
commands (including `SecurityBodyAdapter.initialize`, `LifeCycle.init`,
and middle-tier initialization); the probe models none of that. The
missing provider can therefore be attributed to this **incomplete
isolated runtime**, not yet to a specific absent library or single failed
call. The APK contains `libsgmainso-6.8.260404.so` and a `libsgmain.so`
archive holding Java bytecode; the latter is not another directly
loadable native signer.

During `10104`, the native middle-tier initializer itself tries mode-0
group-7 operations `(7,1,53)`, `(7,1,70)`, and `(7,1,34)` from call sites
`0xd27d0`, `0xd287c`, and `0xce328`; each lookup also has no handler in
the isolated run. This showed several related unavailable operations,
rather than a malformed `70102` argument alone. The trace saw no direct
`dlopen`/`dlsym` call during these synthetic
commands; that observation does not exclude Java-side library loading or
other setup outside the probe. No production TMC code was changed because
there is still no authenticated live signal feed to render.

JNI tracing explains why replaying only the three router startup commands
is an incomplete test: `10103` invokes `RegisterNatives` for
`com.alibaba.one.android.sdk.OneMain.initNative(Context)` at `0x1ab1e4`,
`playNative(...)` at `0x1ab520`, and `OneStubCenter.oneStubCenterCallFunc`
at `0x1ab92c`. The APK's `OneMain.initialize(Context)` would call
`initNative(Context)` from Java if invoked, but no direct Java call to
`OneMain.initialize` was found in the inspected decompilation, and the standalone router probe never
executes that Java callback or supplies a real Context. This is a concrete
unmodeled startup path to examine before treating the mode-0 registry as
intrinsically unavailable. It has not yet been shown that `initNative`
specifically registers `(7,1,2)`.

An additional synthetic call to the registered `OneMain.initNative` after
`10103` returned normally and reached a few JNI calls, but the later
`70102` trace was unchanged: the outer handler remained present and the
mode-0 `(7,1,2)` lookup still returned `701029906`. Because JNI method
calls (including the Context interaction) are generic stubs, this is
only a negative result for the **synthetic** initialization, not for
the App on Android. The next useful static target is the native code
that populates the mode-0 group-7 registry, together with the Java
callbacks it requires.

The registry layout has now been decoded more precisely. After
`10101 → 10103 → 10104`, **mode 0 does contain group 7 and component 1**.
That component has 25 operations (`60, 61, 7, 16, 18, 25, 26, 42, 43,
46, 44, 45, 49, 52, 54, 55, 13, 19, 32, 33, 56, 27, 30, 31, 35`),
but **not operation 2**. Mode 1 contains `(7,1,2)` mapped to wrapper
`0xcb410`. Thus it was imprecise to call the entire inner group-7
provider absent; the gap is specific to several operations, including
the signing operation. The native registrar at `0x54bc8` receives
`(group, component, operation, mode, handler)` and is called via an
indirect vtable; the exact `(7,1,2)` registration observed at `0xcaf60`
passes mode `1` only. Nearby `0xcafc0`/`0xcafe0` register `(7,1,60)`
and `(7,1,61)` in mode `0`. A scan for nearby immediate `7,1,2,0`
argument sequences found only two **dispatch** calls (`0xcada8`,
`0xcbad8`), not a registrar call. This does not exclude indirect or
runtime-computed registration elsewhere, but it narrows the static
search: the wrapper expects a mode-0 signer that this startup path
does not install. Widening that literal-argument scan to 80 bytes around
each `mov w2, #2` still found only the two mode-0 **dispatch** sites,
not an additional static registration site.

The `70102` wrapper's post-lookup path was exercised as well. At
`0xcbb04` the inner call returns zero; its subsequent recovery branch
(`0xd1c98` followed by `0x10617c`) also returns zero in the isolated
runtime, so it does not produce a signature. This observation does not
establish whether recovery could succeed with real Android state.

One substantial emulator defect was removed: `10101` invokes zlib
`inflateInit_`/`inflate`/`inflateEnd`, but the first probe treated these
as no-ops. The probe now performs bounded real zlib streaming; observed
chunks decompress to nonzero output (including completed streams), yet
the mode-0 group-7/component-1 operation set and `701029906` result are
unchanged. File probes during `10101` also show its synthetic Context is
being interpreted as a path prefix (`context/storage/...`), with other
startup probes such as `/SG_FAST_CONFIG`. Correcting nonexistent-file
`access`/`open`/`stat` stubs from false success to failure likewise leaves
the missing operation unchanged. These negative controls rule out the
zlib no-op and the simple file-existence return value as *sole* causes;
they do not make the fake Context equivalent to the App's Android runtime.

ELF load order was checked as another control. The library has one
`DT_INIT_ARRAY` entry, relocated to VA `0x1afcac`, and no `DT_INIT` or
preinit array. That constructor checks a CPU feature and sets a global
byte; it does not register handlers. Running it before `JNI_OnLoad` in
the isolated probe returns normally, but `(7,1,2)` mode 0 is still absent
after the same plugin startup sequence. The missing registration is not
explained solely by skipping the ELF constructor.

The online 5.1 route's road-class mapping is now traced independently of
the offline adapter. The 5.1 schema chain is route-message field 7
(`0x10e7d0`, alternative-route size `0x2d0`) → alternative-route field 10
(`0x10e370`, segment size `0x80`) → segment field 3
(`0x10db70`, link size `0x158`) → link field 7 (`0x10d990`, attribute
size `0x64`) → attribute field 1 (`0x10d790`). The online constructor
`0xbaa3c` iterates those subsegments at `0xbb030`; `0xbb100` calls
`0xbb6cc` for their links. At `0xbb88c`–`0xbb8c0`, a present link-field-7
attribute creates a road record on the segment context, and its field-1
word at parsed-link `+0x40` is copied to that record's `+8`. At
`0xbbbf4`–`0xbbc18`, every link references the latest road record in its
segment; absent attributes therefore inherit the preceding class. The
first link without a record falls back to class 11 through `DriveLinkImpl`
getter `0x9454c`. The online `DriveLink` wrapper vtable `0x109ef0`
forwards slot `+0xf0` to that `DriveLinkImpl` getter. This closes the
wire-field-to-`route_links_road_class` mapping for the online route path.
The other conversion path observed at `0xbd7e4` copies a parsed `+0x14`
word to source-link `+0x31`, but it is **not** evidence that a 5.1 wire
field maps that way; using it for the online path would be incorrect.

The research-only `v51_dynamic_route.py` now extracts one road class per
link with the segment-local inheritance rule. All 10 alternatives across
six saved successful 5.1 captures decode with equal lengths for ID,
length, start-point and road-class arrays (23–95 links per alternative).
Their emitted classes are 6–10, and every saved segment's first link has
the attribute present, so the class-11 fallback is a native-code finding,
not directly exercised by these captures. This does not make the
synthetic `/routeInfo` request valid: full event segment metadata, native
common parameters, SecurityGuard signing and server acceptance are still
unverified, and ETA responses still contain no live `popLights[]`.
One fresh-route, native-body-encoded `/routeInfo` probe added the decoded
road-class array to the previous candidate request. Both the no-SecurityGuard
and deliberately invalid-`x-sign` variants still returned HTTP 200,
`code=3` / `Params error.` The unchanged generic error cannot isolate
road classes from the remaining missing event fields, common parameters or
session state; the invalid-header control still does not prove the server
ignores SecurityGuard headers.

The missing mode-0 SecurityGuard signer cannot yet be attributed to the
App's delayed Java startup tasks. The main plugin's three-second task calls
`C0113.m347`, which subscribes to broadcast actions; the security-body
two-second task initializes user-track callbacks; the middle-tier background
task initializes network interception, sensors and `MidBridge` switches.
None of those inspected Java tasks directly registers `(7,1,2)`.

More importantly, the isolated `10101` JNI environment is demonstrably
not an Android-equivalent initialization. Unique method lookups in the
pinned native library include `Context.getPackageCodePath()` at `0x5818c`,
`Context.getFilesDir()` at `0x58250`, `File.getAbsolutePath()` at `0x582e8`,
`Context.getApplicationInfo()` at `0x58390`, and
`ApplicationInfo.nativeLibraryDir` at `0x584f4`. The original generic JNI
stubs return the same synthetic string/object for these calls, and return
null for the `nativeLibraryDir` field. File probes consequently used the
spurious prefix `context/storage/...` and even empty paths. A research-only
variant returning distinct synthetic APK/files paths changed those file
probes to `/data/user/0/com.autonavi.minimap/files/...`, confirming that
the path input is consumed. The apparent invalid registry in its first run
was a **probe bug**: the dump used hard-coded group-7 heap addresses, and
the path variation changed allocation order. Discovering group 7 from the
registry roots at runtime removes that false corruption signal. Supplying
only `nativeLibraryDir`, only APK/files paths, or both leaves exactly the
same 25 mode-0 group-7/component-1 operations; operation 2 is still absent
and `70102` still returns `701029906`. These are negative controls for
those path strings **alone**, not a faithful Android initialization: the
probe still returns synthetic method results, reports missing files, and
does not load App package resources. The `--trace-jni-methods`,
`--context-paths` and `--native-lib-dir` switches preserve the comparisons.
This does not show whether the signer would register on a real Android
runtime, nor whether `x-sign` is the server's first failed validator.

Thread creation was another previously invisible difference. During the
synthetic startup, `10101` calls `pthread_create` seven times: one entry
at `0x7ad2c`, three at worker-loop `0x729f0`, and three one-shot task
entries at `0x727c8`; `10103` adds one one-shot task and `10104` adds one
worker loop plus one one-shot task. The original stub returned success from
`pthread_create` without executing any entry. Running the `0x7ad2c`
entry once after `10101` returned normally (only three JNI slot-129 calls
were observed); running all five recorded `0x727c8` one-shot entries
after their owner commands also returned normally. In each controlled run
the mode-0 group-7/component-1 list was unchanged and `70102` still
failed with `701029906`. Those entries alone do not supply the signer.
The `0x729f0` worker loops and their queued callbacks remain unmodeled,
and the generic pthread/condition stubs cannot stand in for their normal
concurrent execution. `--run-initial-thread` and `--run-task-threads` in
the ignored probe make the negative controls reproducible; they do not
establish that real Android background work is irrelevant.

The first `0x729f0` worker was also entered with its recorded argument
after `10101`, and the worker spawned by `10104` was entered after that
command. Both stayed in condition-wait loops under the synthetic
`pthread_cond_wait`/`pthread_cond_timedwait` stubs (thousands of immediate
returns before the instruction bound); neither reached a completed worker
iteration or added operation 2. Returning `ETIMEDOUT` for the timed wait
did not change this behavior. This is evidence of an **idle or
inadequately modeled work queue in the probe**, not proof that actual App
workers never initialize the signer. The bounded `--run-worker-once` and
`--run-worker-after-third` options preserve these observations without
letting the worker run indefinitely.

The native dynamic-route element's `length` is now traced through the actual
online route object. Horus builder `0x6ad958`–`0x6ad96c` calls route getter
`0xc75b20` and stores its result at element offset `+0x140`, which the JSON
serializer `0xd10b38`–`0xd10b4c` names `length`. That getter dispatches
virtual slot `+0x58`; the online `DrivePathImpl` implementation `0xa7ef0`
reads its `+0x18` word. The 5.1 assembly path `0xbaa8c`–`0xbaa98` writes
`wire_route.field1 / 100` there using integer division. The research
extractor therefore now emits `length_candidate` from this exact wire field,
rather than summing decoded polyline lengths. Across six saved routes the
values are 2,719–7,075 m and differ by 14–47 m from geometry sums, so the
distinction matters. A fresh encoded `/routeInfo` probe with this field
still returned `code=3` for both security-header controls. The endpoint's
remaining missing context is not isolated by this negative result.

The adjacent `links_adcode` source is also resolved.
Horus `0x6ad7ac`–`0x6ad7e4` groups changes in link virtual slot `+0xd0`.
The online `DriveLink` wrapper forwards that slot to `DriveLinkImpl`
`0x94474`, which reads the link's `+0x60` word. The 5.1 online assembler
`0xbb930`–`0xbb940` copies parsed-link `+0x78` to that word. This is the
attribute field-8 adcode: for example the first saved Beijing link has
field 8 = `110101`, and its route contains both `110101` and `110102`.
The assembler also inherits a previous link's `+0x60` when their `+0x40`
record indices match (`0xbbc1c`–`0xbbc4c`).

The grouping is now resolved for the before-navigation full-route event.
`libassembly_kit.so` `0xbb750`–`0xbb768` appends each new link to its
segment's `+0x70` collection. A parsed link with attribute field 7 creates
a new **segment-level** road record at `0xbb894`–`0xbb8ac`; the record
index is copied into link `+0x40` at `0xbbbf4`–`0xbbc18`. When the current
and previous links have the same index, `0xbbc1c`–`0xbbc4c` copies the
previous adcode. Thus attribute field 8 starts a code, and subsequent
links without a new road record inherit it until the next attribute;
the inheritance resets at a segment boundary. The saved Beijing 5.1 route
has 58 links: extracted effective codes change at links 8 and 26.

Horus initializes the running link index to zero at `0x6ad5d8` and then
increments it before writing the new range bounds at `0x6ad7d8`, so the
event uses one-based inclusive link indices. Its `0x6acf90` helper formats
each range as `start,end`, appending it to an adcode-keyed map. The
`0x6ad170` formatter joins multiple ranges with `-`, converts the numeric
adcode key to text, and `0x842504` serializes that map as JSON string
keys and values. Zero-code runs are skipped on a transition from zero,
but the final run is always flushed. The research extractor now emits
`links_adcode_candidate`; the saved Beijing route produces
`{"110101":"1,7-26,58","110102":"8,25"}`. Six saved routes and
57 focused tests pass. A fresh native-body-encoded `/routeInfo` probe with
this field still returned HTTP 200, `code=3` / `Params error` for both the
ordinary and deliberately invalid-signature controls; this result does
not isolate the remaining validator failure.

The serializer labels event offsets `+0x68` and `+0x98` as
`segment_distance` and `links_eta`, each an integer/string-vector field.
For the **beforeNavi** builder, the event constructor `0xcf1444`
zero-initializes those offsets. The builder `0x6ad530`–`0x6ada40`
does not populate them, and its late helper calls `0x6ae00c` and
`0x6ae8c4` write elsewhere in the event. The research probe now includes
both as empty arrays. This does not establish their values for active
navigation or a mode-3 partial-route event.

The request-level AJX comparison found three further type/value mismatches
in the synthetic navigation probe. `TripDynamicInfoRequestUtils.js`
`_getCommonRequestParams()` emits `navigation_scene` from the route type,
and `RouteRequestConstUtil.js` defines `CAR = 0`; our probe omitted the
field. The result-page caller sets `routeScene: ['normal']` and
`isLongTripScene: 2`, `isUgcCloudOpen: 2`, whereas the previous synthetic
body omitted `scenes` and used booleans for the latter two. Its
`updateParams()` uses `Object.assign`, so those result-page values can
carry into a navigation-page beforeNavi request. The probe now uses these
APK-derived values plus numeric `route_mode: 0` for the normal car case.
This bounded correction still yields `code=3` with and without the
deliberately invalid security header. It therefore does not prove whether
the next failure is an unpopulated native event field, a missing AOS
common parameter, an unregistered navigation session, or SecurityGuard
signing. No live traffic-light phase/countdown payload has been obtained.

The AJX `TripNaviLinksHelper.fetchRouteLinks()` returns the complete
`navi_route_links` array, and `_getCommonRequestParams()` maps every member
into `reachableEndPoi`. The earlier synthetic request sent only the first
candidate although the fresh 5.1 route had two. The local encoded probe
now extracts both and builds two elements with candidate local path IDs
100002 and 100003 and matching end-POI entries. This is a more faithful
shape, but the allocator IDs remain unconfirmed for that real session.
The two-route request still returned HTTP 200, `code=3` for both security
header controls. Missing alternative routes alone therefore did not
explain the rejection in this bounded probe.

One transport field was still missing from that probe. For AOS requests,
`AosRequest.shouldAppendCSIDAndOutput()` always returns true; after
encrypting and signing the query, `buildHttpRequest()` appends a plaintext
`csid` query parameter. `AosService` seeds the statistic-data `csid` from
`AosRequest.getId()`, whose field initializer uses `UUID.randomUUID()`.
The local probe now appends a fresh UUID after `ent=2&in=...`, matching its
position outside the encrypted signing input. A fresh two-route `/routeInfo`
request with this correction still returned HTTP 200, `code=3` for both
header controls. Omission of `csid` was real but not the sole cause.

The route-element serializer at `libamaphorus.so` `0xd109a4`–`0xd10bfc`
always writes all 25 `navi_route_links[]` keys, including vectors and strings
which may be empty. Constructor `0xcf1444` zero-initializes the storage for
`service_area_poi_ids`, `sub_e_poiid`, the four sub-endpoint coordinates,
`sub_end_poi_type_code`, `recommend_level`, `via_link_ids`,
`rest_area_links`, and `car_info`; the serializer reads the coordinates as
doubles and `recommend_level` as a 32-bit integer. The encoded probe now
includes those default-shaped keys, so its route elements have the complete
*key set*. This does **not** prove native-equivalent values: later builders
may populate some members for the selected route, and at this stage
`route_points[]` still lacked several native subfields (added later below).
One fresh two-route request with these
additional keys still returned HTTP 200 / `code=3` / `Params error` both
without SecurityGuard headers and with a deliberately invalid signature.
The previously missing key set alone is therefore not the sole rejection;
complete App AOS parameters, actual native route-event values, signing, and
session establishment remain unresolved.

A four-way control on one fresh two-route request distinguishes at least two
`code=3` error producers. The default encoded query, deliberately invalid
SecurityGuard headers, and deliberately malformed JSON body all returned
HTTP 200 with string `"code":"3"`, string `"result":"false"`, and
`"message":"Params error."`. Replacing only encrypted URL parameter `in`
with an invalid literal returned HTTP 200 with numeric `"code":3`, boolean
`"result":false`, and `"message":"Params error"` (no period). The
different JSON types/text suggest a gateway rejection for the corrupt `in`,
while the correctly encoded candidate reaches a later error producer. This
does not prove its query is fully valid or locate the later validator:
malformed body and invalid signing headers still receive that same generic
later error. It does, however, make blindly changing the `in` encoding a
lower-priority hypothesis than reproducing native body/session fields and
the remaining App request metadata.

The AJX body comparison exposed more routinely emitted fields omitted from
the local candidate: `mp_id` defaults to `""`, `templateType` to `0`, and
`disableRectifyPoiIdList` to `""`; the fresh-driver helper emits string
`novice_switch` and `novice_broadcast_switch`; `cloud_control` includes
`gas_path_bubble`, `isRadarAllowBigButton`, and
`routePlanRestrictedPolicy`. The research probe now supplies their
default-shaped values (driver settings are still synthetic). The four-way
control on a new two-route response remained unchanged: the correctly
encoded, invalid-signature, and malformed-body variants reached the same
string-code `Params error.` branch; only the corrupt encrypted query reached
the numeric-code branch. In particular, adding those fields alone does not
establish a navigation session. `routeConfig` is still `{}` in the probe,
whereas the App navigation page calls `RouteConfigUtil.getRouteConfigMap()`
and copies its `horusKey` values; those depend on native route preferences
and remain unreplicated.

`NetworkParam.getAosCommonParam()` also always adds an `x-gen` header.
Its `getGenID()` fallback is the literal
`gen000000000000000000000000000000000` until the App has a generated ID.
Adding that fallback to the local probe did not change `/routeInfo`'s
`code=3` response. This is only a fallback-shaped header; it is not proof
that the real App would send that exact value for an established device.

The two-route native-event probe had a substantive length-unit bug.
`libassembly_kit.so` `0xbb794`–`0xbb7a8` divides 5.1 link field 2 by 100
before storing it in `DriveLinkImpl+0x18`; Horus `0x6ae66c` reads that
native value into `route_links_length`. The extractor was sending raw
centimetres while `length` was already metres. After correcting each link
to integer metres, all six saved routes satisfy the native invariant
`sum(route_links_length) == length` exactly (23–95 links per route).
A new synthetic 5.1 fixture guards this conversion. A fresh corrected
two-route request with `csid` and the `x-gen` fallback still returned
HTTP 200, `code=3` with and without the deliberately invalid security
signature. This genuine 100× payload error was not the sole rejection.

The AJX lifecycle shows why a reconstructed route object cannot yet be
assumed to represent a started navigation session. `PlanResultAction._startNavi()`
first calls `TripDynamicInfoRequestUtils.destroy()`, then jumps through
`natives.route_drive_result.jump(CAR_NAVI, ...)` with the selected route and
native result state. On the navigation page,
`TripNaviStateEyrieEventUtil.sendTripDynamicInfoRequest()` calls
`requestDynamicInfo()`; that issues `beforeNavi` `/routeInfo` and then
`navigation` `/navigation`. For the former,
`TripDynamicInfoRequestUtils._getCommonRequestParams()` requests
`navi_route_links`, `main_path_id`, and `navi_id` from the native
`TripNaviLinksHelper.fetchRouteLinks()` interaction, rather than rebuilding
them in AJX. Separately, `TripMapService.startNavi()` sends
`MapBaseActionType.START_NAVI = 17` through `ajx.business.set`.
This establishes that the official `/routeInfo` call happens in an active
native navigation-page lifecycle that the Python route-only probe bypasses.
It does **not** prove which native action establishes server-side eligibility
or that the missing lifecycle alone causes `code=3` or ETA `etaCode=2`.
The next useful trace is the native handler for the page jump / action 17
and its outbound requests, rather than another isolated static field guess.
The Java side of that jump is now identified: `ModuleRouteDriveResultImpl.jump`
delegates ordinary `carNavi` paths to the current result page's
`DriveSwitchSceneCallback`; `AjxRouteCarResultPage.G` calls `o02.g`, which
builds a `PageBundle` for the car navigation page with start/end/via POIs,
latest GPS position, navigation flags, and the original JS parameter blob.
That route is a real Android page transition, not an HTTP request that the
browser can replay. The `TripMapService.startNavi()` AJX action sends
`guideMode` under `MapBaseActionType.START_NAVI=17` through
`ajx.business.set`; its native handler and any server-side effect remain to
be linked. This further narrows the current gap to lifecycle and state
created behind the native page/action boundary, without proving that those
are the only reason for the generic server errors.

Follow-up audit corrects the emphasis on action 17. In the extracted **drive**
AJX bundle, `TripMapService.startNavi()` only defines that method; no drive
call site invokes it. The other call site is in the separate car-link bundle.
The `guideMode` references at `libamaphorus.so` `0xcb5650`, `0xcb728c`, and
`0xcb7488` are generic JSON field parsers, not evidence of an action-17
dispatcher. Pursuing action 17 as the ordinary car-navigation startup was a
false lead. The drive AJX bundle defines `ENaviGuideAction.kStart=1` but has
no call site for it either (its `kStop`/pause/resume actions are used). This
points to native page/guide setup before AJX starts receiving map events.

The actual dynamic-request ordering is now sharper. `TripNaviStateEyrieEventManager`
listens to native `NaviEventTypeUpdateNaviInfo`; the first such event calls
`TripNaviStateEyrieEventUtil.registerFirstNaviInfoResponse()`. Only after
that first navigation-info event does the utility invoke
`sendTripDynamicInfoRequest()`, and only when navigation is real rather than
simulated. Its `TripDynamicInfoRequestUtils` path fetches native route-link
data and sets `behavior_type="start_navi"` for the first `beforeNavi`
request whose native `navi_id` differs from its remembered ID. The local
Python probe already sends that behavior type, but it reconstructs the route
data instead of receiving the native first event. `AjxRouteCarNaviPage.pageCreated()`
also assigns a navigation ID to `NavigationDataResult` and notifies Android's
location service of the navigation scene. None of these steps proves that
the server requires a persistent session, but they rule out the idea that
action 17 by itself is the missing request.

The normal initial-route path is now identified at the AJX/Java boundary.
`TripNaviInitialState._handleCompleteRoute()` sends
`natives.drive_navi.onCalRoute({routeSet,focusIndex,naviId})` before entering
the normal navigation state. Java `ModuleDriveNavi.onCalRoute()` forwards the
JSON to `ae5.onCalRoute()`. That callback treats `routeSet[]` as **native
integer route handles**, constructs a native `PathResult` with
`NaviManager.createPathResult()`, reads the selected `Route.getNaviID()`,
adds it to the page's route-ID set, and releases the temporary result. It
does not issue the dynamic-info HTTP request or itself start guidance. The
separate native map-state transition (`TripNaviMapUtil.setMapNavigationStatus`)
and first `NaviEventTypeUpdateNaviInfo` precede that HTTP request. A Python
route byte buffer or reconstructed link JSON is therefore not equivalent to
AJX's `routeSet[]` handles. This identifies a precise native-state gap, but
still does not identify the server's reason for `Params error.`

There are also distinct IDs that must not be conflated. The Java page's
`NavigationDataResult.setNaviId(this.o0)` falls back to the current
millisecond timestamp when `o0` is empty. Separately, `ae5.onCalRoute()`
reads `Route.getNaviID()` from the selected native route and stores it in
the page's route-ID set; AJX's route parameters keep a `naviID` from the
calculation result. The dynamic request ultimately uses the `navi_id`
returned by the native `TripNaviLinksHelper` interaction. Earlier native
traces at `libassembly_kit.so` `0xb8900`–`0xb8908` and
`libamaphorus.so` `0x6ac5c8` already establish that, for this online 5.1
route path, the latter route ID comes from the response header's 32-hex
field 5. The page-level millisecond ID is a different value. This known
mapping does not make the Python route an accepted server session.

One more request-body mismatch was removed. The initial navigation-page
`beforeNavi` call reuses `_getResultRequestParams()`, but the caller
`sendTripDynamicInfoRequest()` supplies neither `routeScene` nor
`isLongTripScene` nor `isUgcCloudOpen`; `JSON.stringify` omits their
undefined `scenes`/trip fields. The later `_getNaviRequestParams()` adds
`isLongTripScene=2` and `isUgcCloudOpen=2` for the **navigation** loop, not
the first `/routeInfo` call. The earlier Python probe incorrectly sent those
three result-page fields in its navigation-page `/routeInfo` body. It now
omits them and includes the caller-supplied empty `workMapId`/`businessId`.
A fresh two-route, four-control probe still returned the same string-code
`Params error.` for valid-encoded, invalid-signature, and malformed-body
variants, and numeric-code `Params error` for the corrupt encrypted query.
This body correction is real but not sufficient; the remaining causes are
not isolated by that generic response.

The nested route-point serializer has been mapped more fully. In
`libamaphorus.so`, `0xd10c00` walks fixed-size `0xb8` route-point entries;
`0xd10d0c` emits doubles `lon/lat/navi_lon/navi_lat`, integer `type`, strings
`poiid/name/waypoint_name`, and `points[]`. The latter's `0xd10e00`
serializer walks `0x50`-byte entries and writes `lon`, `lat`, `name`.
Producer `0x6ae00c` grows the `route_points` vector through `0x6b26c8`
at its start/end and optional intermediate-point branches, and grows a
nested `points` vector for endpoint coordinates. The ignored Python probe
now supplies this complete *shape* for two coordinate-only endpoints with
empty metadata, rather than four-coordinate stubs. Those metadata values
and exact snapped endpoint coordinates remain synthetic; no native event
sample has been captured. A fresh two-route control probe was unchanged:
string-code `Params error.` for the encoded/invalid-signature/malformed-body
variants and numeric-code `Params error` for a corrupt `in` query. The
missing nested keys were not the sole cause of rejection.

`routeConfig` is no longer treated as an unspecified empty map in the
navigation-page control. The pinned drive AJX bundle's
`TripNaviSceneConfigUtil.afterShowScene()` runs
`RouteConfigUtil.getRouteConfigMap()` before the first dynamic request;
`TripDynamicInfoRequestUtils._getCommonRequestParams()` then copies every
`horusKey` into `routeConfig`. For an Android CAR profile with no saved
vehicle, the emitted shape includes `carInfo`, `vehicleType`,
`vehicleETCFlag`, `etaRestrictionSet`, `specialVehicleInfo`, `strategy`,
`constraintCode`, `trafficPermit`, `privacy`, `noviceLevel`, `playStyle`,
`mute`, `soundType`, `userTypeInfo`, `favoriteSource`, and
`airPressureGauge`. The scene also prepends `truckMPID` and `sbiz` entries.
`ANAdapter` supplies default CAR path method `1` and broadcast state `7`;
the route-preference mapping turns that path method into strategy `"32"`
with constraint `"0"`. Other settings and native state may differ on an
actual installation, so the probe's fresh-profile values remain candidates.
With that candidate map, a fresh two-route, four-control `/routeInfo` probe
still gave string `code="3", result="false", message="Params error."` for
the encoded request, invalid SecurityGuard signature, and malformed JSON
body. Corrupt encrypted `in` again reached the distinct numeric-code branch.
This rules out the **empty routeConfig alone** as the cause of the observed
rejection. It does not validate the candidate configuration or identify the
remaining failure condition.

The ETA/TMC XML root has also been tested with the App's
`ucar_fullscreen` `InteractionMode` string, together with the prior
native-root defaults, near-light GPS sample, route `DataVers`, and
`source/invoker` fields. A fresh HTTP 200 reply still decoded to the
53-byte, zero-payload frame with `etaCode=2`. The pinned native parser
returns any nonzero `etaCode` through a common error branch; no APK-side
mapping of value `2` to a specific rejection reason has been found. The
missing `InteractionMode` was therefore not, by itself, the cause either.

The native sender's transport indirection is now explicit. In
`libamaptbt.so`, request allocation at `0x673930` reads global transport
pointer `0xf93600` through getter `0xcf801c` into request offset `+0x78`.
The common sender at `0x6735b0` calls virtual slot `+0x10` on that pointer.
The only **direct** call to setter `0xcf8010` in a full-width ARM64 `BL`
scan is at `0x4ac84c`, where teardown sets the pointer to null. Its active
initializer may use an indirect registration path; this scan does not prove
the pointer stays null. The later native request-type and matching network
service vtable analysis below narrows the Java bridge substantially, though
the exact assignment to this TBT global has not been located. Without a
successful native request, server rejection still cannot be assigned to one
XML/body field rather than the transport/signing layer.

One concrete *conditional* transport mismatch deserves a separate check.
The APK's Java `k33.sendAos()` converts the SDK-level request through
`p60.c()`. When that request carries a `RequestBinaryBody`, `p60` stores its
bytes in `AosPostRequest.g`, sets query placement to URL, and removes an
`is_bin=1` marker from the input queries before `AosPostRequest` adds that
marker back to the built URL. `AosPostRequest.createHttpRequest()` applies
`xxTeaEncrypt(byte[])` to `g` when `mEncryptStrategy == 2`; the App's
`rf2.xxTeaEncrypt(byte[])` calls `serverkey.amapEncodeBinaryV2()`.
The SDK-level `AosRequest.Option.mNeedEncrypt` defaults to `true`.
The current Python ETA probe instead posts its XML bytes directly and only
encodes the URL query with the **string** `amapEncodeV2` routine. Thus, if
the native ETA transport delegate at `0xf93600` uses this Java binary-body
path with its default encryption option, our test wire body is definitely
different from the App's. We still need to tie that delegate to
`k33.sendAos()` (or identify its actual bridge) and reproduce the binary
codec before treating this as the cause of `etaCode=2`. The `routeInfo`
AJX JSON path is separate and already uses string-body encryption.
Adding only that unsigned `is_bin=1` URL marker to an otherwise unchanged
fresh near-light ETA request still returned HTTP 200 with the same 53-byte
`etaCode=2` error frame. The marker alone is not sufficient; subsequent
binary-body encoding and bridge analysis are recorded below.

The binary V2 encoding candidate is now executable in isolation. The
registered JNI wrapper at `libserverkey.so` `0x9980` takes a byte array,
calls core routine `0x2fd4` (also used by the confirmed string-V2 encoder),
then allocates a Java byte array and copies the result through
`SetByteArrayRegion`. The neighboring byte-array wrapper at `0x8748`
instead calls `0xbd24`, separating the two algorithm generations. The
research helper `native_body_codec.encode_binary()` invokes `0x9980` under
Unicorn with the pinned APK certificate; its bytes differ from the string
codec and decode back to the original ASCII sample via the V2 decoder.
This identifies a binary-V2-shaped path without a native network capture.
Two fresh near-light ETA probes sent the binary-encoded XML with and without
the `is_bin=1` marker. Both still returned HTTP 200, the same 53-byte frame,
`etaCode=2`, and zero payload. Thus even this body-codec correction is not
enough to obtain a live light event. The unverified native transport binding,
common device/session parameters, signing layer, and any server-side route
eligibility remain independent possibilities.

The native-to-Java AOS route is now supported by a tighter instruction chain.
`libamaptbt.so` builds the outgoing request at `0x6734d4`–`0x67355c`:
`stp wzr,w8,[sp,#0x80]` at `0x673534` makes its first request field **zero**.
The sender at `0x6735b0` passes that request to virtual network-service slot
`+0x10`. In `libamapmain.so`, the service created by
`InterfaceAppImpl.nativeAMapNetworkServiceImpl()` has vtable `0x101d10`;
relocation at vtable `+0x10` points to `0xd33e0`, which forwards to
`0xd53a8`. This bridge reads the same first field at `0xd53fc` and takes its
zero branch to the Java method table entry for `IHttpService.sendAos()`
(`0xd5424`–`0xd5430`); nonzero chooses `sendHttp()`. The App bootstrap
(`lo5.java`) passes `getNativeNetworkServiceHandle()` to both native module
initialization and its network service registration. This does not expose an
in-process pointer assignment to TBT global `0xf93600`, but it confirms the
request type and the matching network-service vtable, strongly connecting
the ETA sender to the AOS Java path.

The native AOS bridge's `RequestBinaryBody` builder at `libamapmain.so`
`0xd82a8` creates an `AosRequest.Option` and calls its custom-common-param
and common-param-placement methods (`0xd83f0`, `0xd8438`). No direct call in
this builder overrides `Option.mNeedEncrypt` or `mNeedCommonParams`, both of
which default to `true` in the pinned Java class. The downstream `p60.c()`
therefore normally keeps AOS strategy `2`, and `AosPostRequest` encodes
the binary body with `serverkey.amapEncodeBinaryV2()` before sending it.
The Python probe can reproduce those body bytes, but the full wire shape is
still missing.

The body subtype also matches this path: `libamapmain.so` tests native POST
body kind at request offset `+0x54` (`0xd85d0`–`0xd85f4`). Values 1–3
take the explicit form/multipart/stream branches; the default branch at
`0xd8880` uses metadata getter `0xd7bc4`, whose class initializer
`0xd80ac` names `RequestBinaryBody`. The TBT sender zero-initializes its
request structure and only explicitly writes zero to body-kind at
`0x6735a4`. This supports the binary-body interpretation directly, while
still leaving request-specific content-type and compression fields to check.

Specifically, `NetworkParam.getAosCommonParam()` adds `x-gen` and `Ap-Tid`
headers and, for the default common-param strategy, calls
`getNetworkParamMap()`. That map adds more than thirty values, including
`siv`, `dip`, `dic`, `diu2`, `diu3`, `dai`, `cifa`, `session`, `appstartid`,
`stepid`, `client_network_class`, `dibv`, `BID_F`, `aetraffic`, `buildABI`,
and locale fields; some depend on an initialized device, network, location,
or App session. `AosRequest.buildHttpRequest()` merges them before encrypting
the query and calls `securityGuardSignByV2()`. The default App cloud config
enables both SecurityGuard signing and virtual V2 signing. That path produces
time-bound `x-sign`, `x-mini-wua`, `x-sgext`, `x-pv`, `x-t`, `x-appkey`, and
`x-umidtoken` headers (where available). The present Python ETA control
only builds `{channel,div,diu,sdk_version,sign}` and sends no matching
SecurityGuard factor headers. This is a definite **request-canonicalization
mismatch**, not proof that the server's `etaCode=2` specifically denotes a
signature failure: earlier invalid-signature controls reached the same generic
response. The precise native common values, a working mode-0 SecurityGuard
factor provider, and a successful active navigation-session response remain
necessary before TMC can display genuine live lamp phase/countdown.

The App's *actual* common-parameter provider has now been found in the
other decompiled DEX: startup `ag4.b()` installs `og4` as the network context,
and `og4.getCommonParamsProvider()` returns `h71`. `h71` reads `dip` from
`ConfigerHelper` key `ProductID`, `dic` from `CustomID`, `siv` from
`SearchApiVersion`, `dib` from `dib`, and `aetraffic` from `aetraffic`;
it also obtains ADIU and account-related values through live App services.
The pinned APK's `assets/amap_configer.data` gives fresh-install static
candidates `dip=10880`, `dic=C3060`, `siv=ANDH170000`, `dib=a`, and
`aetraffic=9`. The `CustomID` file override and device/session values can
still change these at runtime. This corrects the earlier possibility that
the empty `NetworkParam.H` fallback provider represented normal App use.

The ignored one-shot ETA probe can now add only those five APK-backed fields
with `--apk-static-common`. A fresh-route control used the previous
near-light GPS point, default root attributes, actual APK cpcode candidate,
`ucar_fullscreen`, and binary V2 body, plus these fields. It still received
HTTP 200 with the same 53-byte `etaCode=2` frame and zero payload. Thus the
five omitted **static** fields alone do not account for acceptance. It did
not include the App's dynamic common values or SecurityGuard factor headers.

The Java `uu5.f()` virtual-V2 wrapper supplies a more exact signing input:
it computes UTF-8 lowercase `MD5` of the encrypted `in` string, then passes
`<ACCS app key>&<that MD5>&<Unix seconds>` as `data`, the URL path as `api`,
the environment mode and `useWua` flag to
`IUnifiedSecurityComponent.getSecurityFactors()`. The returned factor map
becomes the `x-sign` family of headers. Reproducing the wrapper's input is
straightforward; the mode-0 native factor provider remains missing in the
isolated runtime. No valid factor map has been produced, so the server's
`etaCode=2` still cannot be assigned to this missing signature alone.

Local Android verification was attempted without changing the production
browser/Python architecture. API 30 x86_64 boots from a D-drive AVD with the
pinned 17.00.0.2005 APK installed; the package runs using Android's ARM64
`ndk_translation` bridge. A Frida 17.4.0 x86_64 server and Java bridge can
attach: a trivial script, `Java.perform()`, and reflection of `uu5` all work.
Reflection confirms `uu5.f(String,String,String,boolean,byte[])` in the loaded
APK. Direct Frida wrapping of `uu5`, and a reflected call to its `f` signer,
both terminate the App with SIGSEGV. Logcat reports
`ndk_translation ... mmap_posix.cc:24: CHECK failed: -1 == 0` during the signer
call. This is an emulator/native-translation failure at the proposed dynamic
probe boundary; it does **not** establish that production ETA requests fail
for the same reason. The locally installed API 30 ARM64 system image could not
be launched by the Windows x86_64 QEMU2 emulator (`CPU Architecture
'arm64-v8a' is not supported`). Thus this local emulator has not yielded a
valid SecurityGuard factor map. Native static reconstruction and a real
successful navigation-session response are still required before authentic
traffic-light phase/countdown can be wired to TMC.

Further isolation showed reflective `uu5.b()` returns the initialized ACCS
app-key provider value (its length only was logged), whereas reflective
`uu5.e()` can return a UMID component and then the process crashes in a native
thread. This narrows the emulator failure to native SecurityGuard activity,
rather than class loading, basic Java reflection, or the App network-context
provider. No key or signing output was copied into the research record.

A second local control avoided Frida entirely. A small standalone Java DEX
launched through `app_process` can create an AMap package context and reach
`SecurityGuardManager.getInstance()`, but its ordinary x86_64 process cannot
load the APK's ARM64 native library: Android reports `EM_AARCH64 (183) instead
of EM_X86_64 (62)`. This establishes an ABI mismatch for that *standalone*
process, not a defect in the original App process (which Android launches with
the ARM translation bridge). Passing `-Xnative-bridge` to `app_process` was
rejected as an unknown VM argument. Together with the Frida crash, this rules
out these two simple local invocation routes for obtaining a factor map.

The fresh emulator's six files under `app_SGLib/.ab394a9964` begin with a
four-byte prefix followed by zlib data. They decompress to structured binary
records of roughly 29–306 KB, without a valid ELF or DEX header or readable
signing-related strings. Incidental `ELF`/ZIP byte patterns do not have valid
headers. These files are therefore not an obvious loadable signer module; their
semantic format remains unknown. The missing mode-0 `(7,1,2)` operation in
the isolated Unicorn runtime is still best treated as an initialization or
runtime-state gap, not proof that the APK lacks signing code.

On the local API 30 x86_64 emulator, the pinned App can reach its first-run
privacy screen, but accepting it exits with `SIGILL` in Android's ARM
`libndk_translation` layer. This prevents an in-App navigation-session capture
on that emulator. A Frida Java-bridge read **before** accepting the screen did
obtain the actual `NetworkParam.getNetworkParamMap()` result for
`/ws/perception/drive/navigation`: 24 keys, including `session`, `appstartid`,
`stepid`, `spm`, `cifa`, `diu2`, and `diu3`. The raw snapshot is private to the
local temporary drive and is neither printed here nor committed. Ten values
were empty in that pre-consent state; five of them (`siv`, `dip`, `dic`, `dib`,
`aetraffic`) have nonempty APK-config defaults. This snapshot is **not** a
sample from an initialized navigation session.

The bounded Python ETA probe now accepts that private snapshot with
`--runtime-common-file`, fills only the five known APK-config defaults when
blank, and compares the base and enriched URL parameters against one freshly
planned route. Both requests returned HTTP 200 with the same 53-byte binary
frame, `etaCode=2`, and no payload. Thus those observed pre-consent common
values did not independently unlock the navigation response. This does not
distinguish absent SecurityGuard factors from absent active-session state,
native body differences, or service eligibility.

The Java AOS builder also adds an `output` query value through
`getAosCommonParam(true)` and appends an unsigned `csid` UUID after the
encrypted query. The SDK-level `AosRequest` defaults its accepted response
type to `json` unless a caller changes it. A same-route ETA control added
`output=json` and a fresh `csid`, together with the captured common values;
the base and enriched calls still returned identical 53-byte `etaCode=2`
frames. These metadata omissions are real but not sufficient to explain the
failed ETA probe. The exact native bridge's response-type choice remains to
be confirmed before treating `json` as the production ETA value.

Repeating the enriched call with `output=bin` instead of `json` also left
the same 53-byte `etaCode=2` result. The SDK's default `json` and the
plausible binary-response override are therefore both insufficient in this
synthetic, pre-consent request. This is not an App-network capture and does
not identify which validator emitted code 2.

The isolated SecurityGuard probe was extended to trace thread creation during
the first `70102` factor request, not only during plugin startup. Its fallback
starts one thread at `0x729f0` (the same worker-loop entry already seen in
startup) with a new queue argument. Running that worker for a bounded
iteration under the synthetic JNI/libc environment reached repeated
`pthread_cond_wait` calls but registered no mode-0 `(7,1,2)` handler. A
second `70102` on the same Unicorn instance still returned `701029906`.
The retry took fewer internal dispatches (8 rather than 28), consistent with
a one-time fallback attempt, but did not produce a factor map. Therefore
omitting this one spawned worker iteration is not the sole reason the
isolated signer fails. This result cannot exclude work the real Android
thread receives later or Java/Context-dependent setup not modeled here.

A further trace of the same first `70102` call located its recovery failure.
After the absent mode-0 `(7,1,2)` lookup, the one-shot fallback invokes
several registered internal commands and then mode-0 group 1, component 1,
operation 15 (`10115`) from `libsgmainso` `0x10649c`–`0x1064b0`. That lookup
returns `101159906`, leaving the recovery routine's return value zero.
Registry dumps after `10101`, `10103`, `10104`, and the failed `70102` show
group 1/component 1 has operations `1,2,7,4,3,5,6,8,9,10,11,13,14,17`,
but no 15. A scan for the matching immediate `mov w2,#15` registration
sequence found only the `0x1064a0` dispatch site, not a direct registrar
call. Thus the synthetic runtime is missing an **additional recovery
operation**, not merely the signature operation `(7,1,2)`. The exact
registration source may be indirect or data-driven; neither absence in the
synthetic registry nor this static scan proves the original App lacks it.

The APK packaging was checked to avoid mistaking a version marker or Java
archive for a second signer: `libsgmainso-6.8.260404.so` is the 3,020,876-byte
ARM64 ELF, `libsgmainso.version.so` is only a 16-byte version string, and
`libsgmain.so` is a 115,083-byte ZIP containing manifest/resources and one
DEX, with no nested native library. No separately named SecurityGuard body
or middle-tier ELF was found in the pinned APK. This makes another ordinary
packaged `.so` an unlikely missing step; dynamic/data-driven registration or
incomplete Android initialization remain possible.

The isolated `10101` JNI shim's generic method returns were tested as a
separate initialization hypothesis. Returning integer zero for the two
`CallIntMethod` invocations instead of a synthetic object pointer, and then
also returning false for the 17 `CallStaticBooleanMethod` invocations, left
the core registry contents unchanged after `10104`: mode-0 group 1/component
1 still omitted operation 15, and mode-0 group 7/component 1 still omitted
operation 2. `70102` still failed with `701029906`. These two overly generic
JNI return values are genuine emulator inaccuracies, but neither alone
accounts for the missing handlers. Other Context/JNI methods and process
state remain synthetic; this is not a faithful App startup.

The Java plugin loader has one more conditional native step that earlier
synthetic sequences omitted. The main plugin archive's binary manifest has
`hasso=true`; in the framework's has-SO branch, after `onPluginLoaded()`
performs `10101`, it calls router command `10102` with three plugin/load-path
strings. The research probe now models the sequence
`10101 → 10102 → 10103 → 10104 → 70103 → 70102` in one Unicorn instance.
With bounded synthetic string arguments, `10102` returns normally but does
not add group-1/component-1 operation 15 or group-7/component-1 operation 2.
The final `70102` still returns `701029906`. Combining this step with
distinct Context APK/files/native-library paths and corrected integer/boolean
JNI return values gives the same registry and result. `10102` made JNI calls
but no observed `dlopen`/`dlsym` or filesystem imports in this isolated run.
This rules out the *omission of the conditional 10102 call alone*; its real
arguments and Android callbacks are not reproduced, so the successful App
behavior remains unverified.

A separate local Android 33 x86_64 image was booted as a possible newer
ARM-translation control. It reports API 33 but only `x86_64` in
`ro.product.cpu.abilist`, with no `ro.dalvik.vm.isa.arm64` mapping. The pinned
APK ships ARM64 native libraries, so this image cannot run the App's native
navigation or signer; it does not replace the API 30 `ndk_translation`
environment. The API 33 emulator was stopped after that compatibility check.

The Java-side initialization after native `10101` was audited for an omitted
provider-registration command. `SecurityGuardMainPlugin` calls `C0118.m360`,
which stores the router and constructs a report executor, then schedules
`C0113.m347` after three seconds. That delayed task queries config commands
`13204` and `13805` and registers an Android broadcast receiver. The
`SecurityGuardSecurityBodyPlugin` delay calls `C0090.m265` and `C0094.m272`
to register optional monitoring callbacks. The middle-tier delay calls
`C0047.m148`, `SensorUtil.init`, and `MidBridge.init`; the latter queries
four config switches through `13204`. None of these Java methods directly
calls a native registrar or another `101xx` bootstrap command. They can
still trigger native work indirectly through callbacks, so this does not
prove they are irrelevant in a real Android process.

The native `10101` initialization flags were then varied in the bounded
probe. A targeted JNI `CallIntMethod` return supplied flag values `0`, `1`,
`32`, and `33` to the second `10101` object (the value was observed at the
JNI call). All four trials used the same synthetic
`10101 → 10102 → 10103 → 10104 → 70103 → 70102` sequence. The mode-0
group-1/component-1 operations still lacked 15; mode-0 group-7/component-1
still lacked 2; `70102` still followed the failed recovery path. These
flag variants do not fix this isolated runtime. Real Context, persisted
SecurityGuard state, and native threads remain unmodeled.

A full executable-segment scan found only one *direct* ARM64 `BL` to the
generic native registry inserter `0x54bc8`, a bootstrap call at `0x55500`.
All the observed group-7 registrations reached it indirectly; for example,
the mode-1 `(7,1,2)` wrapper was registered from `0xcaf64`, whereas the
neighboring mode-0 `(7,1,60)` and `(7,1,61)` registrations came from
`0xcafc4` and `0xcafe4`. This explains why scanning only direct `BL`
instructions could not locate the absent mode-0 provider. The remaining
static target is the indirect registration or dynamically initialized
provider behind the mode-0 operations, not another obvious direct Java
startup call. No authenticated live-light response or TMC countdown has
been obtained.

The six SecurityGuard runtime files captured from the local App emulator
(`app_SGLib/.ab394a9964/*`) were rechecked against the pinned native ELF.
After their four-byte length prefix and zlib decompression, every file starts
with the same `1a0825b2 00040400` container header. The exact four-byte
magic occurs three times in `libsgmainso-6.8.260404.so` at file offsets
`0x2b8098`, `0x2d7438`, and `0x2da64c` (mapped VAs `0x2c0098`,
`0x2df438`, and `0x2e264c`). The runtime files are *not* byte-identical to
the embedded containers. A dynamic-relocation check found native pointers
to the first two embedded headers at `0x1b6a70` and `0x1b6a88`.
This supports a shared SecurityGuard container format, not a claim that
those runtime files contain the missing signature handler.

The isolated probe now traces emulated reads and `memcpy` sources in that
embedded-data region, plus reads of the two relocated pointers. Across
`10101 → 10102 → 10103 → 10104 → 70103 → 70102`, none of those accesses
occurred. The handler registry still lacked mode-0 `(7,1,2)`. Thus these
particular embedded containers are not consumed by this synthetic startup
path; an Android callback, native worker, or another initialization command
could still use them in a real process. The runtime files' format and
relevance to V2 signing remain unverified.

Static cross-references now identify consumers for the first two embedded
containers. The ELF relocation at `0x1b6a70` points to the first header
`0x2c0098`; `0x1b6a78` points to its 23,800-byte length word at
`0x2c5d90`. Native function `0x1a5364` reads both at `0x1a53b0`–
`0x1a53c0` and passes the blob pointer and length to an indirect call.
Similarly, `0x1b6a88` and `0x1b6a90` point to the second header
`0x2df438` and its 39,120-byte length word; `0x14ed0c` passes those to
`0x14ed88` (`0x14ed34`–`0x14ed4c`). That second consumer is invoked from
`0x14eedc`, which has direct callers at `0x14f128` and `0x14f304`.
The bounded `10101`–`70102` replay did not execute either consumer.
This locates real native loaders for the containers, but no call-chain
evidence yet connects them to the missing mode-0 `(7,1,2)` registration.
Running the already modeled one-shot native tasks after `10101` and `10103`,
plus one bounded worker iteration, also produced no observed embedded-blob
read/copy. Those thread trials do not cover the real Android scheduler or
later network callbacks; they narrow only the current isolated replay.

Further replay exposed a flaw in the research-only Unicorn environment: its
`realloc` import always returned null. Implementing bounded allocation/copy
and expanding the synthetic heap changes `10101` startup materially: it now
spawns native thread `0x1a5368` with an initialized argument, without an
explicit call to `0x1a5284`. `10101` also reaches the synchronous second
container loader `0x14ed0c`. Thus the earlier lack of embedded-container
reads in the replay was an emulator artifact, not evidence that startup
ignores these containers. The previously omitted `dlopen("libc.so")`,
`dlsym`, and `strdup` behaviors were likewise needed for the first loader
to advance. These are bounded compatibility stubs for investigation, not
production code or a faithful Android runtime.

Executing the `10101`-spawned thread after startup now copies and parses
the first embedded container. The parser's 16-byte identifier lookup
through `0x1613ac → 0x163438 → 0x162c2c` matches multiple entries in
the initialized table. In the earlier incomplete replay, the same lookup
had failed with code `44` because the table lacked an expected entry;
that failure cannot be carried over to the corrected startup order.
The corrected thread next calls the Android/Linux syscall wrapper at
`0x19cb78` (observed numbers `130` and `113`). The probe models the invalid
zero-argument `tkill` and `clock_gettime(CLOCK_REALTIME)` paths only to
continue static/dynamic analysis. A bounded 10-million-instruction run
advanced into further container processing but had not returned; it did
not register the missing mode-0 `(7,1,2)` signature operation.
The replay still uses synthetic Context/JNI state, so even a longer bounded
thread run would not by itself establish a valid AMap signing session or
live traffic-light response. No live phase/countdown is connected to TMC.

The synchronous second-container failure has now been traced further. In
`0x14ed0c → 0x15222c → 0x15172c → 0x15b170`, status `44` originated at
`0x15b254` when a `0x162e40` symbol lookup returned null. The loader
resolves some libc functions with `dlsym` rather than ELF imports, so the
probe's static-import-only symbol table was incomplete. The missing dynamic
exports encountered in sequence were `pthread_mutexattr_destroy`,
`strerror`, and `wctomb`. After providing bounded synthetic handles for
these genuine libc names, retrying `0x14ed0c` with the `10101` context
returns `0`, rather than mapped error `0xfa3` (internal status `44`).
With the same symbols present from the start of a fresh replay, the
`10101`-initiated call to `0x14ed0c` itself also returns `0`; the explicit
retry is no longer necessary to pass that stage.
This establishes a specific probe-environment cause for that failure.
It is not a valid signing result: with the first asynchronous thread still
bounded/incomplete, mode-0 `(7,1,2)` remains absent and `70102` still
returns `701029906`. The next question is whether finishing the first
container and any follow-on native task registers the missing provider.

The asynchronous first-container worker is substantially longer than the
early bounded trials. With the second container now loading successfully,
10-million-, 30-million-, and 100-million-instruction trials all reached
different PCs within its native bytecode interpreter but did not return
to `0x1a53c4`, where the worker would invoke its next callback. The
100-million-instruction run recorded different PCs and VM cursor values
at 10-million-instruction milestones; this rules out a single short
fixed-PC spin, but does not show that the worker will terminate or that
its later callback registers the signer. The mode-0 `(7,1,2)` lookup
remained absent and `70102` returned `701029906` after each bounded trial.
Replacing the probe's zero-valued `time()` and `gettimeofday()` imports
with current timestamps did not change the 10-million-instruction outcome.
These bounds are not a valid live App request or an authenticated response.

Follow-up bounded trials reached 300 million and then one billion native
instructions without the first-container thread returning. The faster
probe removes general code/memory tracing while preserving import, JNI,
and syscall hooks. At 10 million instructions it counted 568 calls to
`pthread_cond_timedwait`, alternating between the static condition at
`0x2bdbd0` and a heap condition. Returning either `ETIMEDOUT` or success
for the wait did not make the thread finish in a 10-million-instruction
trial. The generic interpreter call site is `0x156968` (`blr x22`), so
the wait is being reached through dynamically resolved libc functions.

Moving that thread after `10102`, `10103`, and `10104` did not change the
10-million-instruction result: it again made 568 timed waits, the
mode-0 `(7,1,2)` handler was still absent, and `70102` returned
`701029906`. The later startup commands signaled queue conditions
`0x585d98` and `0x861d68`; neither matches the embedded worker's
observed wait conditions. Bounded iterations of the queue workers after
`10104` also did not register `(7,1,2)`. The first worker did execute
some JNI/file operations before entering its wait loop, while the
`10104` worker remained in `pthread_cond_wait`. This narrows the issue to
the missing asynchronous synchronization or follow-on callback in the
isolated replay; it does not prove that the real App lacks the signer.
There is still no authenticated native navigation event or live traffic
light phase/countdown feed available for TMC.

The wait stub's timing was checked against its actual `timespec` argument.
The first observed static-condition deadline was roughly five seconds in
the future; returning `ETIMEDOUT` instantly while `clock_gettime` kept
wall time fixed was not faithful. A controlled probe now advances one
synthetic realtime clock to each requested deadline and uses it for
`clock_gettime`, `time`, and `gettimeofday`. The next static deadline then
advances as expected, but the 10-million-instruction trial still makes
568 timed waits and does not return from the first-container parser or
register `(7,1,2)`. A real concurrent signal or other Android process
state may still be required; simply allowing timeout time to pass in the
isolated thread is insufficient.

The first-container thread's Unicorn register context can now be saved
after a bounded run and restored after the first `70102` factor request.
With one million instructions on each side of that request, the worker
continued from its prior PC but still timed out on its conditions;
retrying `70102` left mode-0 `(7,1,2)` absent and returned `701029906`.
Running the request's newly spawned `0x729f0` queue worker between those
two slices likewise left the same result. A 10-million-instruction slice
followed by a second slice confirmed that no new group-7/component-1
registration reached native registrar `0x54bc8` in the observed worker
execution. This tests one cooperative interleaving, not every possible
Android scheduling order.

The continuation callback at `0x150080` was tested only as a diagnostic,
using the argument layout shown at `0x1a53ec`–`0x1a541c`; the production
path does **not** skip the parser. Called before the parser, it returned
status `7`; after a bounded partial parser run, it returned `0x37` and
did not register `(7,1,2)`. Thus prematurely invoking that callback is
not a valid shortcut to a working signer. The evidence now points to
the parser's still-unmet state or a different initialization path, rather
than a simple command-order or elapsed-time mismatch.

A diagnostic substitution tested all six zlib-decoded `app_SGLib`
containers as the first embedded blob, one at a time and then in a
single sequential synthetic instance. A wrapper-thread return with `X0=0`
was initially misleading: the thread returns zero even on parser failure.
Its state object at `+0x70/+0x74` showed `(error=42, status=10)` for
**every** substituted container. None installed mode-0 `(7,1,2)`;
`70102` still returned `701029906`. By comparison, the original embedded
blob's state remained `(0,0)` during a bounded partial parse. The
larger runtime files also needed a research-allocator cap above 1 MiB;
after allowing their observed roughly 1.3-MiB request, they followed the
same error-42 path. This experiment does not reproduce the runtime files'
normal App loader or device binding and must not be read as proof that
those files are invalid in Android.

The first error-42 return was traced backward through
`0x1596fc → 0x15c348 → 0x15d53c → 0x1517b4`. At `0x159a28`, the
container parser calls the native candidate lookup at `0x1612fc` and
gets a null result; `0x159a30` branches to the status-42 handler.
`0x1612fc` scans candidate records and checks their match/ready fields,
so the substituted runtime blobs lack a matching registered object in
this synthetic loader. The direct post-load-callback trial's status
`0x37` likewise came from virtual-machine branch `0x1671d0` while the
original parser had not completed. These failures characterize the
diagnostic substitutions, not a successful production-signing path.

The original embedded blob's timed-wait state was sampled at waits 1,
2, 3, 32, 100, 300, and 568 in a bounded 10-million-instruction replay.
Both condition-variable addresses recur, while the same context pointer
is used at every sample. In the first 0x200 bytes of that context, the
later samples changed only a handful of timing-related fields; the early
state setup fields stopped changing. Its wrapper state at `+0x70/+0x74`
remained `(0,0)`, unlike the substituted runtime blobs' `(42,10)`.
This is consistent with an initialized long-lived wait loop, rather than
evidence that merely raising the instruction bound will finish the
container parser. The probe is single-threaded and still cannot prove
what the Android scheduler or an external request would signal.

The first `70102` and its retry were also traced for condition signals.
They signal the generic task queues (`0x585d98`, `0x861d68`, and a new
request queue at `0x8d6078`), but no observed signal targets the
first-container thread's conditions (`0x2bdbd0` or its heap condition).
This weakens the hypothesis that the factor request itself directly wakes
that thread. It is still possible that a later queued task or Android
callback would do so; the probe has not executed a faithful multithreaded
queue lifecycle.

The generic `0x729f0` task workers were next run with a synthetic clock
advanced to their scheduled `pthread_cond_timedwait` deadlines. This let
startup callbacks run without spending the instruction budget on idle waits.
The `10101` queue executed callbacks including `0xfeef4`, `0xfe600`,
`0xe94ec`, `0xeae44`, `0xf1f38`, `0x12cec4`, `0x7d924`, `0xebe5c`,
`0x1073b4`, and `0xe9450`. The `10104` queue executed `0x10839c` twice.
After `70102` it additionally executed `0x108e00` twice. The latter is a
generic event dispatcher, **not yet identified as a signing callback**:
its observed events have types 1 and 4, whereas the synthetic handler table
currently holds two type-2 handlers. Running the workers before and after
the factor request still leaves mode-0 `(7,1,2)` unregistered and returns
`701029906`. JNI lookup tracing shows startup callback `0xfe600` requests
`play(IIILjava/lang/Object;)Ljava/lang/Object;` and
`initialize(Landroid/content/Context;)V`; their real Java behavior is not
modeled by the generic JNI shim. These observations narrow the remaining
work to the registration/Java-adapter path rather than queue delay alone.

The startup worker's JNI lookup at `0xfd060` obtains
`OneMain.initialize(Context)`; the JNI call at `0xfd094` is a static void
invocation. The APK's Java implementation stores `mContext` and invokes
registered native `OneMain.initNative(Context)` at `0x1ab1e4`. A new bounded
replay now runs that native entry **after** both startup queue workers,
which better matches this callback order than the earlier trial immediately
after `10102`. The entry returned normally. It looked up another
`initialize(Context)` method, called a static void JNI method, and queried
mode-0 group-2/component-7/operation-3, but the later `70102` still found
mode-0 `(7,1,2)` absent and returned `701029906`. The JNI shim does not run
either downstream Java `initialize` method, so this excludes only the
direct native callback under synthetic returns. It identifies a specific
next target: resolve the two downstream class references and their Java
initializers, then determine whether either can install the missing signer.

Class-reference tracing further narrows that result. Startup calls
`FindClass(com/alibaba/one/android/inner/DeviceInfoCapturerFull)` and
stores its global reference at `0x2fd7b0` (`0x1ac1bc`). Immediately before
the synthetic `OneMain.initNative` call, that reference is nonnull but
the first class reference read at `0x2fd968` is zero. The first
`initialize(Context)` branch at `0x1ab340`–`0x1ab3b4` is therefore skipped;
the observed JNI method lookup and static-void call belong to the second,
`DeviceInfoCapturerFull` branch. The test does not exercise the first
class's Java initializer at all. Its zero reference may be intended for
this startup order or may expose another missing initialization step;
neither interpretation proves the signer path. The source of `0x2fd968`
and the role of `DeviceInfoCapturerFull.initialize` were checked next.

Inspecting those Java bodies changes the priority: `DeviceInfoCapturerFull`
stores the Context and conditionally binds vendor device-security services;
`DeviceInfoCapturer` gathers Context, class-loader, telephony, and Wi-Fi
access. Neither directly calls the SecurityGuard registry or supplies a
mode-0 `(7,1,2)` implementation. Replaying those Context side effects may
matter for device identity, but is not currently the most direct route to
the missing signer. The first embedded container's native registration or
its asynchronous activation remains the stronger target.

A fresh audit of the **separate ETA/TMC control path** found a request-body
omission in the previous Python probes. Navigation setup at
`libamaptbt.so` `0x6cde54`–`0x6cde94` calls `0x6d4348` twice (mode 0 and 1)
and registers the two serialized strings with reserved token `0x7fff`.
`0x6d4348` builds a native request structure and serializes it with the
same `0x6dd538` JSON writer used for navigation updates. When the ordinary
transport has no pending JSON and send mode is zero, `0x6bf15c`–`0x6bf1c4`
builds `cpcode=<value>&deviceId=<value>`; then `0x6bf1c8`–`0x6bf1e4`
appends one of those prebuilt strings, choosing transport `+0x150` when
navigation-context byte `+0xea0` is zero and `+0x138` otherwise. Earlier
zero-payload control probes sent only the `cpcode/deviceId` prefix and
therefore were not faithful to this branch. The `0x6d4348` serializer calls
flag builder `0x7233b8` with mode 0, which returns fixed 64-bit candidate
`0x00059def75102080`; this is different from the earlier synthetic JSON
`flag=7` and from the transport's outer `ETAFlag=2`.

The guide engine's vtable at `0xf50878` maps the JNI `startNavi` virtual
slot `+0x78` to `0x6b4628`. That function can schedule `0x6b4cf0`, which
sets navigation-context byte `+0xea0` to one when its timing/route condition
holds. A later transport send at `0x6bf788` resets the same byte to zero.
This ties the choice between the two prebuilt control strings to navigation
state; a Python route ID alone cannot establish the correct branch.

For a bounded diagnostic, `probe_eta_transport.py` gained
`--control-prepared-json`, appending a zero-state JSON candidate with the
verified 64-bit flag after `cpcode/deviceId`. A fresh planned-route test
with the APK account, native root defaults, `ReqType=2`, then a full-shape
`ReqType=3` update near the first route light received HTTP 200 for both,
but each response remained the 53-byte header-only frame with native
`etaCode=2`. This excludes that **candidate** prepared JSON as a sufficient
fix. It does not validate the actual prebuilt bytes, the `+0xea0` state,
runtime location fields, server navigation session, or entitlement.

The prebuilt-control serializer was then examined more closely. In
`0x6d4348`, the 0/1 mode argument is written only into byte 3 of a local
15-byte option record, while the call to `0x7233b8` passes selector **0**.
That selector's branch at `0x7233f4`–`0x723400` constructs the fixed mask
`0x00059def75102080` and skips all reads of the option record. Thus, on
this observed path, the mode argument does not alter the serialized flag.
The two cached strings could still differ if their surrounding navigation
state changes between calls, but choosing `+0x138` versus `+0x150` is not
by itself evidence of two different JSON schemas. The structure is zeroed
at `0x6d43f0`–`0x6d4408`, then receives the fixed flag, vehicle type from
the context, two 32-bit state words from context `+0xe70`, and the
`commonBroadcastCount` entries copied from the context map. The serialized
`gpsdata` string is empty in this startup preparation, whereas the previous
candidate used `"[]"`; `radarLocation` still emits explicit zero-valued
`linkId`, `lon`, and `lat`. A corrected zero-state candidate for these
fields was sent on another fresh route, followed by a `ReqType=3` update.
Both replies again had native `etaCode=2` and no payload. This strengthens
the negative control for a zero-state request, but live context and server
session acceptance remain unverified.

The vtable audit also found a previously untested lifecycle code:
`0x6bbd9c` dispatches `ReqType=0` through transport slot `+0x128`, in
addition to the already probed codes 2, 4, 5, 7, 8, and 9. The research
probe now accepts this code. A fresh route with the corrected zero-state
prepared JSON, `ReqType=0`, then `ReqType=3` again returned the same
53-byte, `etaCode=2` frame for both requests. The meaning of code 0 is not
yet established; the result only rules out changing the lifecycle code to
0 as a sufficient fix under the tested synthetic navigation state.

The ACCS bind-signature alternative was checked against the same isolated
SecurityGuard startup. The Java `ISecureSignatureComponent.signRequest`
calls router command `10401` with a nonempty map, app key, request type 3,
auth code, and boolean. After `10101 → 10102 → 10103 → 10104`, mode 1
contains group-1/component-4/operation-1, but mode 0's corresponding
component is empty. The mode-1 handler at `0x7f5a0` performs argument
checks and then dispatches mode-0 `(1,4,1)` at `0x7f760`–`0x7f770`;
there is no standalone signing algorithm in that visible wrapper. The
synthetic `10401` call currently fails even earlier with error `601`
because its JNI map/Integer/Boolean objects are only generic probe stubs,
so that result does not test a valid ACCS signature. The registry evidence
does show that ACCS cannot bypass the missing mode-0 provider merely by
calling the already registered wrapper. Both mode-0 `(1,4,1)` for ACCS and
mode-0 `(7,1,2)` for AOS V2 are absent in this synthetic startup; whether
the same embedded container installs both is not yet proven.

A bounded first-container-thread run after `10104` left `(1,4,1)` absent,
matching the earlier `(7,1,2)` result. Another diagnostic made the
`sgFile.lock` `open` calls succeed while running the startup task workers;
neither missing operation appeared. That excludes a failed lock-open alone
as the explanation under this replay. The data-file reads and full Android
filesystem behavior remain unmodeled.

The Java plugin-manager call site narrows the synthetic startup arguments.
For a fresh install without `init.config`, its config object is an empty
`JSONObject`, serialized as `"{}"` for `SecurityGuardMainPlugin.onPluginLoaded`;
the next argument is the absolute `app_SGLib` directory, not an empty string.
The research probe now has `--realistic-startup-values` for those two fields.
With distinct Android-style Context paths, the native initialization reaches
`app_SGLib/.ab394a9964`, attempts to create it, and scans two child hashes:
`204f22e1f34732a873d0c9e5d8210920` and
`977966b0ece28f4eee6216434b6175ea`.

This exposed a concrete emulator error: `vsnprintf` and `__vsnprintf_chk`
were previously stubbed without writing their output, so both `opendir`
calls received empty paths. The probe now decodes the ARM64 `va_list` for
the observed `%s/%s`, `/.sg%s`, and `%d_%d` formats and writes the formatted
buffer. A bounded diagnostic also models the newly created SGLib directory
and its two child directories as readable but empty. This causes real
`opendir → readdir` control flow rather than the old immediate failure.
After `10101 → 10102 → 10103 → 10104`, startup workers, then `70102`,
mode-0 `(1,4,1)` and `(7,1,2)` are still absent and `70102` still returns
`701029906`. The empty-directory result only excludes the missing path
formatting and directory-existence checks as sufficient causes; actual
runtime file contents and Android callbacks are still unmodeled. No live
traffic-light event has been obtained.

A fresh local API-30 emulator install of the pinned APK reproduced the known
ARM-translation `SIGILL` after the privacy-consent splash, but SecurityGuard
initialized far enough before the crash to create `app_SGLib`. Its files were
copied into the ignored `.local-data/amap-app/sg-runtime-cache` research area;
the emulator was then stopped. This fresh cache has seven zlib-compressed
containers under `.ab394a9964`, including `204f22.../79@31`, plus a 59-byte
`SG_INNER_DATA_AVMP` file. All seven containers decompress to the same
`1a0825b2 00040400` family of headers. No cache content is checked into the
repository.

The research probe now has `--sg-runtime-cache` to model that captured
directory tree using native `stat`/`opendir`/`readdir` and bounded
`fopen`/`fread`/`fseek`/`ftell` calls. Supplying real `stat.st_size` was
necessary: with a zeroed synthetic `struct stat`, the native file reader
requested zero bytes even though `fopen` succeeded. With that corrected,
startup reads all 59 bytes of `SG_INNER_DATA_AVMP` twice and enumerates
`79@31` in its directory. The observed startup path only counts/scans that
container name; it has not opened the container for the native provider.
After the usual startup commands and bounded workers, mode-0 `(1,4,1)` and
`(7,1,2)` remain absent and `70102` returns `701029906`. Running a bounded
first embedded worker after the cache reads gives the same registry result.
This is a more faithful negative control, not proof that the real App's
SecurityGuard lacks those operations. The runtime cache's loader/activation
step remains to be identified.

The cache loader was blocked by two more missing libc behaviors in the
research-only Unicorn shim. The directory reader splits names such as
`79@31` with `strtok_r` and converts both parts with `atoi`; treating those
imports as no-ops prevented it from selecting the cached entry. Implementing
them makes the `10101` startup open that 43,789-byte file, read its four-byte
header and 3,299-byte footer, and parse a nonnull metadata object. The same
startup also invokes `__vsprintf_chk` with `%lld` while constructing
`app_<APK mtime>` and with `%d` while selecting the cache payload. Modeling
those formats makes it reopen `79@31` and read its complete 40,486-byte data
region. The native body parser returns a nonnull object and follows its
success branch; the cache is therefore no longer merely enumerated.

The emulator's installed `base.apk` reports 195,437,758 bytes and mtime
`1790905683`, matching the captured `app_1790905683` directory. The probe
now optionally uses that captured mtime for its synthetic APK `stat`, rather
than the different timestamp on the downloaded host copy. The emulator also
confirms that `files/storage/com.taobao.maindex` is absent, while the
`files/0a231bd8575dcf72.txt` marker is present but empty; modeling the
empty marker and successful `.lock` opens did not add either missing mode-0
handler. These are local test-environment controls, not production code.

After full cached-body loading, the normal `10101 → 10102 → 10103 → 10104`
sequence and bounded startup workers still leave mode-0 `(1,4,1)` and
`(7,1,2)` absent. A ten-million-instruction slice of the asynchronous first
embedded worker still remains in its timed-wait/interpreter path, and the
first `70102` factor request returns `701029906`. The cache-read omission
was real, but it was not the final cause of the missing signer in this
single-threaded replay. No live traffic-light phase or countdown has been
obtained or connected to TMC.

The earlier startup-worker replay had a research-harness logging fault:
printing a numeric `vsnprintf` argument as a UTF-8 pointer raised a Windows
`UnicodeEncodeError` inside callback `0xfe600`. Removing that invalid debug
dereference allows the worker to finish its queued callbacks (`0xfe600`,
`0xe94ec`, `0xeae44`, `0xf1f38`, `0x12cec4`, `0x7d924`, `0xebe5c`,
`0x1073b4`, and `0xe9450`) instead of stopping after the first two. The
completed worker still does not register mode-0 `(7,1,2)` or `(1,4,1)`.
The callback requests Java `OneMain.initialize(Context)` and later calls
`OneMain.play(IIILjava/lang/Object;)`; the latter's captured arguments were
`(0, 0, 0x30afb, object)` in this synthetic startup. A diagnostic replay of
registered `OneMain.initNative` followed by `playNative` with those captured
arguments returned normally but did not add the missing signer. That replay
is not a faithful nested Java call and does not rule out other Java state or
event ordering. It does rule out the previously hidden logging exception as
the sole reason for the absent handler in this bounded experiment.

With that completed startup worker and the full cached `79@31` body loaded,
all distinct observed `pthread_cond_signal` targets from the startup and
first factor-request paths were compared with the embedded worker's two
wait conditions. Startup signaled `0x586ae8` and `0x7dd148`; the factor
request additionally signaled `0x8644e8`. The embedded worker waited on
`0x2bdbd0` and heap condition `0x858430` in that run. None matched.
This rules out the completed, bounded startup callbacks and first factor
request directly waking the embedded worker through those observed
condition signals; it does not cover another Android callback, an indirect
event path, or a different scheduler ordering.

The local API-30 x86_64 emulator's ARM translator (NDK translation 0.2.2)
also blocks official-App startup on scalar `FCVTZS` instructions. The first
observed `SIGILL` was at `libtnet.so+0x2b000`; after a research-only NOP
substitution, further unsupported instructions appeared at
`libamapr.so+0xba9fcc`, `+0xba9848`, and `+0xba9628`. Scanning executable ELF
segments of the original installed libraries found 1 such opcode in
`libtnet.so` and 95 in `libamapr.so`. Replacing that entire opcode class
with NOPs in the disposable emulator advanced startup far enough to draw
the App home UI, but the main App process then crashed with `SIGSEGV` about
ten seconds after launch. The App's own crash record reports a native
signal 11 without a stack trace. Because NOP changes conversion results,
this experiment does not establish that an unmodified App can run on that
translator, and it produced no navigation request or live traffic-light
event. The patched binaries are ignored local research artifacts only;
neither the APK nor TMC production libraries were changed. The two installed
emulator libraries were restored from pre-patch backups, their SHA-256 hashes
matched the originals, and the emulator was shut down after the experiment.

A second disposable-emulator run replaced those unsupported scalar
FP-register `FCVTZS` forms with five-instruction branch trampolines rather
than NOPs. Each trampoline saves `x16`, converts through `w16`/`x16`, moves
the integer bits back into the destination FP register, restores `x16`, and
branches back. One executable `FCVTZS` in `libtnet.so` and 95 in
`libamapr.so` were rewritten; the trampolines live in appended RX ELF
segments occupying the original `PT_NOTE` program-header slots. This is
still a research patch, not a pristine APK execution. The App advanced to
loading its navigation/location kit and stayed up roughly thirty seconds,
but then its main process reported native `SIGSEGV` and left the foreground.
The subsequent kernel log contained several null-pointer segfaults as the
process shut down; the App's crash record again lacked a useful native stack.
The crash could reflect another translator gap, the rewrite, or replacing
`PT_NOTE`; it has not been attributed to a specific instruction. Thus the
opcode-class rewrite removed the earlier `SIGILL` barrier but did
not yield a stable navigation session, request capture, or live signal data.
The installed libraries were restored byte-for-byte from the original
backups (matching SHA-256 hashes) and the emulator was shut down.

To isolate the ELF-header alteration, a third local run preserved the
original `PT_NOTE` bytes and moved the enlarged program-header table into
the appended RX segment. `readelf -l` verified that the resulting library
still had its note and a separate loadable trampoline segment. The App again
advanced through startup and native navigation-kit loading, then reported
native `SIGSEGV` after roughly forty seconds. This makes loss of `PT_NOTE`
insufficient as the sole explanation for the crash. It still does not
identify the failing native instruction or establish authentic request
behavior. No live traffic-light response was captured. The original
installed emulator libraries were restored with matching SHA-256 hashes,
and the emulator was stopped.

In a debugger follow-up, WSL Linux GDB connected to the emulator's
`gdbserver64 --multi stdio` through `adb shell -T`. Android's GDB server
returned overlong `qXfer:threads:read` and `qXfer:features:read` responses;
disabling those two remote packets let GDB attach. The first intercepted
`SIGSEGV` in that debugged run was an x86_64 ART OAT null dereference
(`boot-core-libart.oat`, `mov 0x8(%rsi),%ebp`, `rsi=0`), which may be ART's
ordinary implicit Java null-check rather than the fatal native crash.
Passing it through led to a later `tgkill(..., SIGSEGV)` inside
`libndk_translation.so`, followed by the App's `ADCrash_so` report. Because
debugger-mediated signal delivery can perturb Android's signal chain, this
does **not** identify the original nondispatched crash or prove a particular
App fault. It does show why treating every intercepted signal 11 as the
root cause would be wrong. No navigation request was captured. The patched
emulator libraries were restored and hash-checked again before shutdown.

A lower-interference `strace -f -i` pass on the same disposable x86_64
emulator changed the observable failure from the earlier undifferentiated
`SIGSEGV`: the first fatal log was `ndk_translation: Undefined instruction
0x5ee1b900`, followed by `SIGILL` on the JavaScript-service thread. Scanning
the pinned APK found an aligned executable match at `libqking2.so+0x49b88`
(`fcvtzs d0, d8`) and another unsupported instruction of that class at
`+0x750cc`; the apparent exact-byte matches in `libamapr.so` were unaligned
data, whereas its 95 executable matches had already been rewritten. The
installed original `libqking2.so` SHA-256 matched the APK-extracted backup.

Adding only those two `libqking2.so` instructions to the research-only
trampoline rewrite eliminated that observed `SIGILL` in the next runs, but
the App still exited on `SIGSEGV`. A second `strace` run recorded the first
signal on the crashing thread as `SEGV_ACCERR` with address
`0x79ac243fbdb0`; the corresponding fixed-address system mapping in the
same emulator image placed it inside `libsqlite.so`'s executable segment.
The trace's instruction pointer was already at Bionic's signal-delivery
path, so this does **not** prove that SQLite caused the original fault or
that the trampoline is correct in all contexts. No stable navigation
session or live traffic-light response was obtained. Both signal traces
remain in ignored local research files. All three modified emulator
libraries (`libtnet`, `libamapr`, and `libqking2`) were restored from
pre-patch backups and hash-checked before the emulator was shut down.

Follow-up static check of the ETA sender's apparently variable factory ID
(`libamaptbt.so` `0x6bedd4 → 0x6c1978 → 0x6ba2c8`) rules it out as a hidden
`trafficlights/realtime` selector. Its return branch at `0x6ba37c` selects
request ID `0x67`; the ordinary branch at `0x6ba384` selects either `2` or
`0x0d` according to the request state and `0x4000` flag. It never returns
`0x6e`. This narrows the dedicated realtime endpoint to some other indirect
factory caller or an unused registry entry; it does not alter the stronger
`routeInfo`/`navigation` event path. No live countdown has been obtained.

The isolated SecurityGuard replay was advanced with the cached files, realistic
startup values, bounded queue workers, and the registered `OneMain.initNative`
and captured `OneMain.playNative` JNI callbacks. Both JNI callbacks returned,
but the subsequent `70102` factor request still failed with `701029906`;
mode-0 signing operations `(7,1,2)` and `(1,4,1)` were not registered. This
rules out omission of those two callbacks alone in that synthetic sequence.

Advancing the queue worker's synthetic clock exposed repeated `stat()` calls
for `app_SGLib/.mwua`, which was absent from the App-generated cache captured
before the Android translation crash. A deliberately hypothetical research
control made that marker appear to exist. It changed the worker's control
flow, but after one million bounded instructions the same `70102` error and
missing mode-0 operations remained. Neither the missing marker nor timed-wait
clock modeling alone explains the signer gap. These are only isolated runtime
controls; they are not evidence of an accepted AMap session or response.
Correction: the clock-advanced worker's repeated `handler_lookup 10101 1 1 8
0x0 0x535a4` is **not** a failed mode-1 `(1,8,2)` registration. Inspection of
`0x54ee4`–`0x54f14` shows that `0x0` is the successful lookup status, while
`0x535a4` is the registered handler pointer. The mode-0 `(1,1)` registry
already lists operation `8`, and the native callback at `0xe9450` supplies
arguments `(1,8,2)` to a higher-level dispatcher which transforms them before
lookup. The `.mwua` poll is therefore part of a running handler path, not
proof of another absent handler. The still-missing operations are the
specific signing providers `(7,1,2)` and `(1,4,1)` in mode 0. The
hypothetical marker control did not install either provider.

The registrar itself is called through an indirect router slot. In the
`libsgmainso-6.8.260404.so` initializer at `0x554c4`–`0x55500`, the address
`0x54bc8` is stored into the router method table before that router is
initialized. A full-width ARM64 direct-branch scan finds only the initializer's
own call to `0x54bc8`; absence of other direct calls therefore cannot show
that no embedded module tries to register the missing signing operations.
The worker's successful `(1,1,8)` lookup also means its repeated `.mwua`
checks cannot be explained as a failed lookup of that handler. The remaining
trace target is the indirect registrar invocation during embedded-module
activation, including any JNI callback or condition signal it waits for.

A renewed bounded test on the local BlueStacks Rvc64 instance supplied a
second, independent App-startup observation. The pinned APK opened its map
home screen, but did not respond to map taps. At the ANR, its process consumed
roughly four vCPUs: `GPosService`, `Map-1-2`, `basic_satAlgo_t`,
`JavaScriptThrea`, and `ubw_thread` were the hot threads. Logcat separately
reported long `SecurityGuardManager.getInstance()` monitor contention.
Android's generated ANR trace, retained only in ignored local files
`bluestacks-anr.zip`/`.txt`, shows the main thread executing inside the x86_64
ARM translator `libhoudini.so`; the trace did not expose a usable Java stack
for that main thread. A map tap reproducibly caused an input-dispatch ANR.
This is an emulator/translation-level failure, not a server rejection or a
successful navigation session. No live signal request or response was captured.

The instance's temporary root-access configuration was reverted to its
original setting, and the VM was stopped. BlueStacks is not a TMC runtime
dependency. The present local emulator routes cannot furnish the official
navigation-session capture without resolving native translation behavior.

An inventory of the local research assets found no second official AMap App
version or saved navigation-session capture. The only official installation
package is the pinned `17.00.0.2005` APK with ARM64 libraries. The separate
`tools/amap-probe` APK is our own minimal AMap Navi SDK test application, not
an alternate App version; its route test requires an Android SDK key bound to
its package and signing certificate. The available webpage JavaScript key
cannot activate that probe. Consequently neither this APK nor an existing
capture supplies the missing authentic traffic-light response.

The `libamaphorus.so` component-to-event branch was checked again at
`0xa88c40` and `0x7a10b4`. After writing
`component.dynamicTravelTrafficSignalInfo`, `0xa88cc8` dispatches internal
message `0x989ac5`. The matching branch at `0x7a1140` reads the component,
then reaches `0x7a13b0` and its `26403` event constructor regardless of
whether the optional object at owner offset `+0x78` exists. Therefore each
component update can produce a countdown event (including an empty update
that should clear old guidance). The event is generated by the component
update, while the standalone `trafficlights/realtime` URL's possible upstream
role remains unproven. This closes one internal emission condition but still
does not identify or reproduce the upstream live feed.

The component's generic update slot at `0x6ac078` accepts its data argument
only when the dispatch key equals `0x98a117` (`w1 - 0x98a000 == 0x117`), then
forwards it to `0xa88c40`. A scan for direct `mov`/`movk` construction found
no complete `0x98a117` key in this library. The nearby `0xa117` arguments at
`0x6fc230`/`0x6fc274` lack the high `0x98` half at those call sites; whether
their callees transform them is unverified. This makes `0x98a117` an internal
dispatcher contract, not yet a network field or endpoint selector. Other
`0x989ac5` senders at `0xa642fc`
and `0xacc808` broadcast component-change notifications, so observing that
notification alone cannot distinguish HTTP response from ACCS push.

The separate navigation-loop HTTP path was probed once using a fresh pinned
APK 5.1 planned route and the AJX `_getNaviRequestParams()` field split.
Unlike the earlier `/routeInfo` probes, this diagnostic removed result-page
fields, set `dynamic_scene=navigation`, and added `navi_count=0`,
`naviCongestion=0`, `isLongTripScene=2`, `isUgcCloudOpen=2`, and the cold-boot
Lunar flag. `POST /ws/perception/drive/navigation` returned HTTP 200 with
string `code="3"`, `result="false"`, `message="Params error."`, and no data.
Thus jumping straight to the periodic endpoint with reconstructed route
links does not bypass the missing accepted navigation state. Because this
request still used synthetic native-route fields and did not establish a
real App session, the generic error cannot isolate a single bad field or
prove whether SecurityGuard signing was checked first.

Another bounded `/routeInfo` control added the five fresh-install static
common query values from the APK's `amap_configer.data` and `h71` provider:
`dip=10880`, `dic=C3060`, `siv=ANDH170000`, `dib=a`, and `aetraffic=9`.
A newly fetched 5.1 route with the otherwise unchanged encoded candidate
body still returned HTTP 200, string `code="3"` / `Params error.`, and no
data. Those five static parameters alone do not establish a valid dynamic
request; device/session common values, an exact native event, and SG factor
headers remain unverified. This does not assign the generic rejection to any
one of them.

The remaining common-param initializer has a reproducible time base, not an
opaque random session identifier. `NetworkParam.getSession()` and
`getAppstartid()` each memoize `gj0.k()`; that method returns whole seconds
since **2011-01-01 00:00:00 in the device's local timezone**. `genStepId()`
increments a process counter for each request. `rl1.c` comes from `gq0.d`
and defaults to `ANDH170000`; `rl1.b` is the last component of
`t1.o()`'s default version `17.00.0.2005`, hence `dibv=2005` on a fresh
unoverridden install. `getMac()` is an unconditional empty string, so `diu2`
is present but empty. These fields can be reproduced in a Python request;
they still leave device-derived `diu`/`diu3`/`dai`/`cifa`, other runtime
parameters, and the SecurityGuard factor map unresolved.

`dynamic_info_request.py` now computes that local 2011 epoch and builds the
reproducible fresh-install common subset without inventing a device ID. Six
focused tests cover the signing-field and time-base behavior. One fresh 5.1
route `/routeInfo` probe with this subset (`div`, `siv`, `dip`, `dic`, `dib`,
`aetraffic`, `dibv`, empty `diu2`, `buildABI`, `session`, `appstartid`, and
`stepid`) still returned HTTP 200, string `code="3"` / `Params error.`, and
no data. This excludes that subset alone as a sufficient fix. It does not
identify the first rejected value because all device-derived common fields,
the exact native navigation state, and SG factors remain absent.

On 2026-10-02, the pinned App reached a **real route-planning and navigation
session** on the local BlueStacks Rvc64 instance. Earlier map-home tap ANRs
were not reproduced in this run. From the official App's driving entry, the
destination search for `MongKok` returned POIs; a manually selected Kowloon
Park origin and MOKO destination produced a 4.5 km route with 21 traffic
lights. Tapping Start Navigation opened the official 3D guidance screen and
rendered traffic-light markers along the route. `logcat` emitted a
`WuKongNative` Navigation `travel_start` record with a nonempty `navId`, then
`travel_process`. This proves that an actual App session can be created in the
local emulator despite absent device location, by selecting both endpoints
manually. It does **not** establish the live-light feed: the stationary
emulator has not displayed a live state or countdown, and no authenticated
network request body or response was captured. The next experiment should
observe App requests during this session, then distinguish route light count
from a genuine real-time signal update.

A follow-up unrooted BlueStacks network observation used the Android global
HTTP proxy with a byte-transparent local research relay. The App did route
connections through it. Startup traffic included TLS `CONNECT` to
`amap-aos-info-nogw.amap.com:443` as well as `m5.amap.com` / `m5-x.amap.com`
and other map/telemetry hosts; some location/telemetry POSTs used cleartext
port 80. The proxy recorded destinations and URL paths only, not credentials
or bodies. It did not reveal the signed navigation payload because the
relevant AOS connection was TLS. A later driving tap during this proxied
startup hit an App ANR before a route request was observed; this cannot be
attributed conclusively to the proxy. The proxy setting was deleted afterward.
The APK targets SDK 35, declares `allowBackup=false`, and its
`network_security_config` only enables cleartext traffic; it does not opt in
to user-installed CA trust. A temporary BlueStacks root-setting toggle made
`/system/xbin/su` appear but `su -c id` exited 1, so this did not furnish
system CA installation or an instrumentation foothold. The VM root setting
was restored. External App monitor files did not contain the target endpoint
names, and the one recent HTTP cache entry could not be pulled without its
App UID. Thus a successful official navigation session is now established,
but its encrypted request/response content is still unobserved.

The stopped BlueStacks instance's data VHDX was converted to a temporary
read-only raw image and mounted at its ext4 data partition. Its private
`shared_prefs/sp_realtime.xml` contains a post-startup
`req_common_params` JSON map with 30 names (not copied into the repository).
Compared with the pre-consent snapshot, fields such as `adiu`, `cifa`, and
`diu3` are populated. This supplied a controlled way to isolate the generic
`Params error`: replaying the earlier routeInfo body with the full map
returned HTTP 200, `code=1`, `Successful`, and `front_end`/`lane_engine`/`tbt`
data. The analogous navigation request also returned `code=1`.

Common-field ablations narrowed that acceptance gate. Dropping seven
device-like fields failed, while dropping session/start/step/SPM, locale,
or empty fields individually by group did not. Splitting the seven showed
that omitting `adiu` alone caused `code=3`; omitting `cifa` alone did not.
Replacing the captured `adiu` with a 30-character zero string or even a
one-character research value still returned `code=1`. Removing all other
captured values but retaining `channel`, `output`, `sign`, and a nonempty
`adiu` yielded `code=1` with empty data. Adding the APK-reproducible
fresh-install common subset restored the normal data keys. These are bounded
endpoint observations, not evidence that an arbitrary client ID is the App's
intended identity or a safe production default.

More importantly, the full APK-derived native route body with the same
reproducible common subset and temporary nonempty `adiu` returned `code=1`
from both `/ws/perception/drive/routeInfo` and `/navigation`, without any
captured private common values or SecurityGuard headers. For a fresh
Hangzhou 5.1 route containing seven static traffic lights, routeInfo also
returned `data.horus` (keys `bizType`, `weak_network`). Setting `user_loc`
to the first route light still did not produce
`component.dynamicTravelTrafficSignalInfo`; a navigation-scene response
contained `data.horus.characteristicEye` but no live-light fields. The
server's successful response therefore does not yet establish a live
countdown. The standalone `/ws/shield/trafficlights/realtime` endpoint
returned `code=4` / signature-verification failure with the dynamic-info
sign and with a `channel,adiu` sign; omitting sign returned `code=3`.
The dedicated endpoint's actual signer/request body or an eligible App
navigation update remains to be recovered. No countdown should be inferred
from the route's seven-light count.

A same-route, same-navigation-ID `/routeInfo` → `/navigation` sequence
confirmed both successful responses without a captured device session. The
routeInfo Horus section contained `bizType`/`weak_network`; the navigation
Horus section on one Hangzhou sample contained `characteristicEye`. Moving
`user_loc` to the first, fourth, or seventh static light and increasing
`navi_count` did not yield a countdown field. A Beijing route showed the
same absence. These checks bound the HTTP observations but do not rule out
eligibility by intersection, active navigation state, or ACCS push delivery.
The extracted App service `TripDynamicInfoAccsServiceListener` registers
`AMAP_AOS_DYNAMIC_SERVER` and forwards `messageType == 5` `data` into the
dynamic-info AJX receiver; this remains a plausible path for updates that
the sampled HTTP replies lack. The standalone realtime endpoint's
`code=4` with both channel-only and channel-plus-adiu MD5s means its true
request signing input is still unknown.

One further bounded navigation-loop control reused **one** Hangzhou 5.1
route and navigation ID across `/routeInfo` and three successive
`/navigation` calls. Each update advanced `navi_count` and set `user_loc`
to the next route light, with a one-second gap. All four HTTP calls returned
`code=1`; each navigation Horus section contained only
`characteristicEye`, never `dynamicTravelTrafficSignalInfo`. Thus the
absence is not explained solely by issuing each update with a new route ID
or by holding `navi_count` and location fixed. The App's native ACCS service
passes `messageType=5` payloads to `TripNaviCustomEventManager`, which accepts
inner response codes 1 or 7 and routes `data.horus` through the same
`TripDynamicInfoEyrieScheduler` used by HTTP replies. That gives ACCS push
an independently verified path into the relevant component, but no actual
live-light push frame has been captured or reproduced.

A temporary local MITM attempt added a test CA only to a clone of the
BlueStacks `Root.vhd`. The cloned system image did not expose its ADB port
after startup, so it yielded no official request bodies. The VM was stopped,
the original `Root.vhd` restored byte-for-byte (SHA-256
`8BCEB4ED88321751E69F2107407B20E591206B51087A43144F42286381AB37F8`),
and the research proxy stopped. This path cannot be counted as evidence about
the realtime response. The next useful evidence is either an actual eligible
navigation session's dynamic HTTP/ACCS payload or the dedicated realtime
endpoint's signer and request schema from the APK.

A bounded identity-control probe used a fresh six-light route in central
Hangzhou (`120.153612,30.274084` to `120.165820,30.277360`). With the
private common-parameter map captured from the official App, `/routeInfo`
and three same-navigation-ID `/navigation` updates returned HTTP 200/code 1,
but no `data.horus`. Repeating `/routeInfo` with only reproducible APK common
parameters and a research `adiu` also returned code 1 and no `data.horus`.
Both responses contained `front_end`, `lane_engine`, and `tbt`. For this route,
the missing live component therefore cannot be attributed to the synthetic
identifier alone. It remains compatible with route/intersection eligibility,
App session registration, or delivery on the native ACCS channel; none is
proven by this negative sample.

A tighter same-route control on a fresh Beijing 5.1 route changed only the
body's 32-hex `navigation_id` from the native header-field-5 value to all
zeros. Both `/routeInfo` variants returned HTTP 200/code 1 with the same
top-level data keys and `horus` keys (`bizType`, `weak_network`). Both
`/navigation` variants also returned code 1 with the same data keys and no
`horus`. Thus these endpoints' generic success code does **not** validate the
navigation ID as an active server session in this probe. Prior code-1 results
must be interpreted as accepted requests, not proof that the Python client
has subscribed to, or can receive, the App's realtime signal updates.

The clone's boot failure was narrowed to two BlueStacks host checks. A normal
`qemu-img` VPC conversion changed the VHD's virtual size from 8,589,934,592
to 8,590,417,920 bytes; using `force_size=on` fixed that. The converted disk
also acquired a new VHD UUID, which BlueStacks compared against
`Engine/Manager/BstkGlobal.xml` and rejected. Copying only the original UUID
into both VHD footers and recomputing their checksums allowed the Android
guest to boot to the launcher. BlueStacks then independently verified
`root.vhd` blocks against `root.vhd.bvs`, reported block 0 modified, and shut
the VM down as a disk-integrity violation. Temporarily moving the `.bvs`
aside did not disable this check; a missing `.bvs` is likewise rejected.
The original VHD and `.bvs` were restored, with the VHD's SHA-256 verified.
No official AMap HTTPS request was intercepted, and changing the clone did
not provide evidence of a traffic-signal response. A host-only VHD clone is
not a viable capture path unless BlueStacks's separate disk attestation is
accounted for; do not weaken the production TMC design around this probe.

A bounded SecurityGuard `10401` control removed one ambiguity in the ACCS
bind-signature replay. The previous synthetic JNI array supplied a Java
string where the wrapper expected a nonempty map and supplied zero where it
expected request type 3; it stopped with generic error 601. A research-only
adapter now returns a native map shell with its count set to one and integer
3 at those two conversion boundaries, without installing or fabricating a signing
provider. Under the same `10101 → 10102 → 10103 → 10104` startup sequence,
`10401` reaches its group-1/component-4/operation-1 mode-0 dispatch at
`libsgmainso-6.8.260404.so` `0x7f760`–`0x7f770`. The registry lookup for
`(1,4,1)` then returns no handler (`0x63337c1`, decimal `104020505`), and
the router returns that error. This directly isolates the still-missing
mode-0 provider after passing the map-count/type gate in the bounded
synthetic startup. The map's entry content was not modeled. This does not
produce an ACCS bind signature or show how the full Android App activates
that provider.

The `AMAP_TRIP_SERVICE` scene-push-to-native Horus handoff is now pinned more precisely. The extracted
TripNavi AJX event utility wraps a `moduleType: "horus"` scene push as
`MapActionType.kDynamicInfoAction` (1000012), action
`kPushInteraction` (12), with `interactionHorus` in its value. The parallel
TBT module uses action 13 and `interactionTBT`. In `libamaphorus.so`, the
action switch at `0xbb8c4c` sends case 12 to `0xbb8d38` and case 13 to
`0xbb8e7c`. The former posts internal event `0x1fbd3`; the latter posts
`0x1fbd2`. An `0x1fbd3` observer at `0x6ac0a8` branches to
`0x6ac3d4`; closer disassembly shows this function only constructs and
destroys a temporary object, with no demonstrated traffic-signal update.
The other direct comparison of `0x1fbd3`, at `0x7c85f4`, passes the payload
to `0x7c8a04`, which caches it under the literal key
`component.MeetWarningData` (`0x126d74`). The exact ARM64 instruction
`mov w8,#0xfbd3` occurs at only those two sites in this ELF. Thus the
scene-push action is demonstrably consumed by native Horus, but its observed
receivers are **not evidence** that it updates
`component.dynamicTravelTrafficSignalInfo`. The separate
`AMAP_AOS_DYNAMIC_SERVER → TripDynamicInfoEyrieScheduler` path remains the
stronger candidate for live signals, and still requires an authenticated
ACCS session and an actual payload capture.

The stronger `AMAP_AOS_DYNAMIC_SERVER` path has a precise AJX envelope and
gate. `TripServiceConfig` initializes `tripDynamicAccsInfoService` at
`LOAD_PRIORITY.INIT`, but its `onInit()` registers the ACCS listener only
when `canIUseFeature("drive_amapAosDynamicServerAccs")` is true. That helper
delegates to native `ajx.getFeatureState`; this APK's extracted JS does not
contain a default value for the flag. The listener accepts only
`messageType===5`, broadcasts the message's `data` string, and the
navigation page parses it as JSON. It accepts numeric response code 1 or
7, then independently forwards `data.tbt`, `data.front_end`, and
`data.horus` to their schedulers. `TripDynamicInfoEyrieScheduler` wraps the
Horus value as `distributeInfo_Horus: JSON.stringify(value)` with
`interactionType:4` and sends native action 9. The periodic HTTP
`/routeInfo`/`/navigation` response uses the same scheduler. This proves a
common downstream processing path for HTTP and this ACCS push, but does
not prove the feature flag is enabled on the target device, that its push
contains countdown data, or that code-1 HTTP replies establish a push
subscription.

The stopped BlueStacks `Data.vhdx` was mounted read-only through QEMU NBD
and ext4 `ro,noload` to check whether the previously successful official
navigation session left a reusable dynamic-response trace. The App has
`files/logs/alc/ajx3.biz*`, `paas.network`, `paas.accs`, and binary
`amapstream/horus` logs from that period, plus a route-cache blob. The ALC
files contain newline-separated URL-escaped Base64 records; decoding a
record produces opaque binary, not JSON/plaintext. Searches across the App
logs, HTTP caches, and external monitor files found no plaintext
`dynamicInfo`, `/ws/perception/drive/navigation`,
`AMAP_AOS_DYNAMIC_SERVER`, or traffic-signal event. The small persisted
`app_accs` queue file names `GD_AMAP_ACCS_SERVICE` only; it does not contain
the target dynamic service. No real countdown payload was recovered from
this saved session. The ext4 mount and NBD device were disconnected after
the read-only check. A future capture would need to instrument the App's
request/response boundary or decode the proprietary log records; scanning
the saved files as plaintext is insufficient.

The ALC encoding was checked one layer deeper using private, ignored copies
of two App log files. The navigation AJX sample contains 636 separate
URL-escaped Base64 rows. Per-row decoding yields 106,608 bytes total,
aggregate Shannon entropy about 7.998 bits/byte, and no Zstandard or gzip
frame magic at any row start. Decoded row lengths are multiples of four but
not consistently multiples of sixteen. The APK's `libamaplog.so` imports
Zstandard compression functions and `ALCManager` delegates records to that
native library; these facts do not identify a decoder for the on-disk rows.
The high entropy and varying row prefixes are consistent with ciphertext,
but cryptography/keys are not proven solely by these statistics. Also,
`DriveLogUtil.objectToFile()` and `logToV()` only invoke `ajx.log.debug`
when `ajx.app.appType < 30`; the saved log's exact coverage must be checked
before investing in a decoder. A prior statement that the records were
definitively encrypted should be read as "encoded opaque records" until
the native writer or a successful decode confirms the transform.
The Java `ALCManager` facade exposes native record/upload controls and
`fetchBizFlowLogs`, but no general decoder for those ALC storage rows.
`AjxModuleLog.debug()` delegates through `k8.e` to the installed AMap log
service. Consequently the saved ALC files are not an immediately usable
offline response archive. The next capture experiment should observe the
App's AJX network callback or AOS request/response boundary before log
encoding, rather than assume all dynamic replies can be recovered from
these files.

A rootless Java-heap capture was attempted against the unchanged App on the
local BlueStacks Rvc64 instance. Android's `am dumpheap` accepted the
request and created the output path, but it remained zero bytes while the
main App process occupied roughly 220–300% CPU. Logcat recorded an ANR in
`SplashActivity` during the attempt. One App force-stop/relaunch again stayed
on `SplashActivity` with elevated native CPU; the guest was powered off
after this bounded control. Thus this particular run yielded no heap
snapshot or navigation response, and `am dumpheap` acceptance does not
prove a responsive, inspectable App session. The next local capture route
should first establish a stable official navigation run; waiting longer on
this ANR or treating the zero-byte HPROF as a capture is unsupported.

A bounded follow-up compared dynamic HTTP updates at three successive
decoded traffic-light coordinates on a fresh Hangzhou route
(`120.153612,30.274084` to `120.165820,30.277360`). Each run sent one
`/routeInfo` and three `/navigation` requests with increasing `navi_count`.
The first used APK-reproducible common query fields and a nonempty research
`adiu`; the second used the previously captured, private official-App
common-query map. All eight requests returned HTTP 200 / code 1, and none
returned a `data.horus` object. The script prints only status and field
names, not the captured identity or signing values. This excludes a simple
"set `user_loc` directly on a known light, then increment `navi_count`"
fix for this route under both identity controls. It does not establish that
the route has live signal coverage, nor that these Python requests created
an official active navigation session or ACCS subscription. Additional
same-shape polls are unlikely to close the missing event-source gap.
An additional field-name-only check of a fresh `/routeInfo` plus one
near-light `/navigation` response found only `front_end`, `lane_engine`,
and `tbt` under `data`. The former's keys were ordinary route/property,
energy, and button-tip fields; the `tbt.event` entries in a saved accepted
response contained playback/business identifiers, with no light phase or
remaining-time fields. This closes the simple possibility that the missing
countdown was already present in another obvious top-level component of
these accepted HTTP responses. It does not rule out a different eligible
server response or a separate push feed.

The locally downloaded Android 28 ARM64 Google APIs image was also checked as
an alternative to the Android 30 raw-QEMU boot. Its `vendor.img` is a GPT disk
image with an ext4 partition at sector 2048; a read-only mount confirms it
still provides `hwcomposer.ranchu.so` and `gralloc.ranchu.so` (alongside
goldfish variants). The prior Android 30 raw-QEMU boot failed in the Ranchu
graphics composer, so changing only the API-level image does not remove that
host-service dependency. No Android SDK `emulator.exe` is installed in the
usual local SDK locations. This is a compatibility check, not an Android 28
boot result; a proper emulator host or a stable BlueStacks session remains
necessary for a genuine App capture.

On 2026-10-02 a later local BlueStacks run did reach a stable official-App
navigation session, and `am dumpheap` produced usable Java heap snapshots.
The previous zero-byte/ANR result was therefore specific to that earlier
session, not a permanent limitation of rootless heap capture. A Hong Kong
navigation heap contained plaintext JSON from three accepted official
dynamic HTTP responses. Their `data` sections included `front_end`, `tbt`,
`lane_engine`, and sometimes `horus` (`arrival_bubble` / `biz_switch`) or
`weak_network`, but no live traffic-signal event or countdown. This proves
that the heap method can expose at least some official dynamic replies; it
does not prove that all network or ACCS messages are Java-heap resident.

To test the hypothesis that Hong Kong lacked signal coverage, the same
official App was positioned in Hangzhou using BlueStacks' location-provider
broadcast with Java `Double` extras. After restarting the App, its map and
vehicle marker appeared in Hangzhou. The App initially could not resolve
`我的位置` in the route form, so both endpoints were selected manually on the
Hangzhou map: Wulin Road to Shaoxing Road, about 4 km. The official route
preview explicitly counted **10 traffic lights**, and active navigation
showed the same count. A fresh navigation heap contained an accepted dynamic
response whose `data.horus` had only `characteristicEye`; another contained
`front_end`, `tbt`, and `lane_engine`. Searches in that heap for
`dynamicTravelTrafficSignalInfo`, `trafficLightInfo`, `popLights`,
`statusInfos`, `trafficSignal`, and event `26403` found nothing. A second
heap after refreshing the simulated Hangzhou location gave the same result.
Thus Hangzhou route-light **count** is present, but this stationary run did
not obtain live light color or seconds. Hong Kong coverage alone does not
explain the missing live feed. A moving near-intersection official session
or an eligibility/push condition remains to be tested before TMC can display
genuine countdowns.

One further official-App control changed the simulated position while this
Hangzhou navigation was active. The App rerouted, increased its static light
count to **14**, and drew an upcoming traffic-light icon at about **295 m**.
The subsequent Java heap still had only `data.horus.characteristicEye` in
the relevant accepted response and no live signal/countdown field. This
shows route-light markers do respond to the Hangzhou position change, while
the live-light source remains separate or ineligible in this local session.
Another roughly 200 m simulated location change triggered the App's weak
satellite-signal warning; its next heap still had no live-light fields.
Because the simulated feed was discrete and the App did not maintain a
reliable moving fix at that point, this does **not** rule out a proximity or
continuous-GPS eligibility condition for live countdowns.

The usable Hangzhou navigation heap also retained several **actual official
App request URLs** for `/ws/perception/drive/routeInfo` and
`/ws/perception/drive/navigation`. Their `ent=2&in=...` query was decoded
locally using the APK-backed `serverkey.amapDecodeV2` wrapper, while keeping
all device identifiers and signatures private. The navigation query had
31–33 fields depending on the request. Compared with the earlier captured
App common-parameter cache, the only absent field names were `output` and
`sign`, which the existing Python probe already adds. Session-specific
values (`adiu`, `appstartid`, `dai`, `pageSessionId`, `session`, `spm`,
`stepid`) changed as expected. This rules out a *missing common query field*
as the sole reason that the prior Python near-light requests lacked a live
signal; it does not validate their body, active session identity, or
SecurityGuard headers.

A bounded scan of encoded Base64-like Java-heap strings found two official
navigation-associated **cross-image** request bodies that the same native
decoder turned into JSON. They share a 32-character `naviID` and numeric
`pathInfo.pathID`, and their `pathInfo` holds link IDs plus static
`trafficLight` integer flags. No dynamic-navigation request JSON body was
recovered from the heap; its encrypted wire query is distinct from that
body. The cross-image `trafficLight` flags are not evidence of live phases
or seconds. Exact identifiers remain only in ignored local research files.

To exercise proximity with steadier input, a research-only BlueStacks
location sender replayed 29 coordinates along a decoded Hangzhou road path
at roughly 1.4-second intervals, ending about 30 m before its first marked
light. Android's GPS provider accepted the points, and the App had an
active 1-second GPS subscription, but navigation continued to warn of weak
satellite signal and kept its vehicle display at the previous location.
Supplying speed and bearing through an Android test provider likewise did
not clear that warning. Therefore this emulator run did **not** establish a
valid moving near-intersection official navigation state, and a negative
live-light result from it cannot prove service coverage is absent.

The App's own **模拟导航** tool was also started on the same Hangzhou route
after removing Android test providers. Its vehicle moved along the planned
road and passed visible static red-light markers, so it exercises route/TBT
animation without the weak-GPS freeze. A heap captured during that run had
no `dynamicTravelTrafficSignalInfo`, `trafficLightInfo`, `popLights`,
`statusInfos`, or `trafficSignal` payload. This simulation is not proof of a
live server subscription: it may intentionally disable realtime features.
It does demonstrate that the visual traffic-light markers and TBT movement
alone do not produce the countdown event.

An immediate `am dumpheap` issued directly after tapping **Start Navigation**
still lacked plaintext `navigation_id`, `navi_route_links`, `navi_count`,
`routeConfig`, and `dynamic_scene` strings. Since the AJX request builder
does construct those fields, this negative Java-heap sample is consistent
with the body living in AJX/native memory or being freed before the snapshot;
it is not proof that the App omitted those fields on the wire. The official
encrypted query URLs and some response JSON remained recoverable in Java
heap. Further body capture needs a closer request-boundary hook, not more
post-response heap searches.

### Hangzhou live countdown reproduced with a real navigation session

The weak-GPS result above was caused by the research feed, not by absent
Hangzhou signal coverage. Two problems were isolated:

* `BstLocationProviderReceiver` accepts only latitude/longitude. Its
  decompiled `Utils.mockGpsLocationProvider()` is empty; the host command
  eventually updates the emulator GPS fix with `vel=0` and no bearing.
* Decoded AMap route vertices are GCJ-02, while Android `Location` GPS fixes
  are WGS-84. Sending the route coordinates unchanged displaced the vehicle
  by roughly 500 m in Hangzhou. The first route vertex
  `(120.15222667, 30.27452944)` maps approximately to WGS-84
  `(120.14752393, 30.27685314)`.

A research-only `app_process` sender held a GPS test provider open and sent
fresh WGS-84 fixes every second with `accuracy=3 m`, speed, bearing,
wall-clock time, and elapsed-realtime timestamp. After starting the official
App with a stationary feed, its main map located the vehicle in Hangzhou.
The official **Start Navigation** action opened a real Wulin Road to
Shaoxing Road route; while replaying route fixes at `8 m/s`, the navigation
HUD showed `28 km/h`, advanced maneuvers, and moved the car along the road.
This is the App's real navigation mode, not its `模拟导航` mode.

Near a marked intersection, the official UI displayed a **green signal with
8 seconds remaining**. Holding the vehicle about 137 m before the next
intersection later showed a **red signal with 21 seconds** and then a
**green signal with 13 seconds**. The changing phase and seconds are positive
evidence that the official real-navigation session receives live signal
information for this Hangzhou route. They invalidate any inference from the
earlier no-event simulated run that the location lacks live coverage.

Local evidence is saved in ignored research artifacts:
`tmc-realdrive.png`, `tmc-nearlight.png`, `tmc-livehold.png`, and
`tmc-laterlight.png`. The repeatable route converter is
`.local-data/amap-app/build_mock_drive.js`, the test-provider sender is
`.local-data/amap-app/mock-location-src/TmcMock.java`, and its generated
route points are `hz-real-nav-drive.txt`. The emulator is used only to study
the APK; no Android device has been added to TMC's production runtime.

An 87 MB Java HPROF captured while the live countdown was visible contained
official `/ws/perception/drive/navigation` and
`/ws/shield/traffic/smartGuide/queryLightEnv` request URLs, plus ordinary
`front_end`/`horus` route responses. A printable-string scan still found no
`dynamicTravelTrafficSignalInfo`, `popLights`, or `statusInfos` body. This
does not contradict the UI: the relevant live signal is plausibly processed
in native memory or delivered through a separate push channel. The validated
next step is to capture the live response at its native request or event
boundary and map its phase/time fields before connecting a Python-only TMC
backend. A screen OCR or emulator dependency would not satisfy that goal.

### Live ETA request recovered and reproduced without Android at runtime

The captured Java HPROF also held gzip-compressed byte arrays that ordinary
printable-string scans missed. Four arrays were original App
`etatrafficupdate` XML requests. Its `/ws/transfer/navigation/etatrafficupdate/`
wire call prefixes the XML with ASCII `0` and sends an APK-encoded `in`
query. The signed fields are `channel`, `diu`, and `div`; the pinned APK's
AOS material reproduces the captured signature. Preserving the
`ETAInfo/TRRequestData` CDATA is essential: XML round-tripping it as escaped
text yields inner status `100004` although the outer binary frame says
success.

Replaying the real request produced an accepted 53-byte ETA frame and zlib
payload. The inner JSON has `status=0` and
`data.onlineNavi.commonPoints[].lightInfo.lightStates[]` entries with phase
`type`, Unix-second `stime` and `etime`. A freshly fetched Python 5.1 route
provided the navigation ID, path IDs, version, geometry, and road-link delta
string. A newly constructed XML body for that route, current position, and
timestamp returned four matching live signal points. The query likewise
works with a generated 30-hex-character `adiu`; no recorded Android device
identifier or running Android process is used. The minimum successful
`ETAInfo` has `requestType=3` and a current `frontParam.prePoint`; omitting
that front parameter was rejected. These experiments are reproducible with
the ignored local `probe_clean_eta.py` and `probe_module_eta.py` scripts.

`eta_live.py` now builds this request and decodes only fresh, matching
navigation/path responses. `tmc_route_helper.py` requests navigation-grade
routes and performs the live ETA query in an isolated subprocess. The Flask
API stores the raw route behind an opaque expiring token, then exposes only
coordinates and phase intervals at `/api/amap-app/traffic-signals`.
`AmapAppView.vue` polls this endpoint during **real** navigation, selects a
signal ahead on the selected route, and displays its phase and countdown.
The research emulator supplied mock GPS to the official App to establish
the wire behavior; it is absent from TMC production runtime.

The local Hangzhou HTTP route→signal API test returned three route choices
and four live points for the first choice. This verifies the full Python and
Flask path, not a Tesla browser drive. Live coverage remains location- and
route-dependent; stale, unmatched, or rejected results are hidden rather
than synthesized. The phase mapping `1=red`, `11=green`, `30=yellow` follows
the captured cycle and official UI observations, and should be checked on
an actual vehicle before treating countdowns as driving guidance.

The captured moving request also explained why simply changing `curloc`
was insufficient: `path/startpoint` moves with the car, `roadlinks` starts
at the current link rather than the route origin, and `linklens.startlen`
records progress within that link. Python now projects the current position
onto decoded 5.1 links and slices the remaining chain. A bounded live check
at route vertices 0, 40, and 80 returned different first signal locations
as the vehicle advanced. Each of the three alternative paths also returned
an accepted, matching-path live response at its start.
