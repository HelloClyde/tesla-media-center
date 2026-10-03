# Original Amap junction-image integration

User explicitly requests the original junction illustration, not a zoomed map.
The substitute preview was detached from AmapAppView on 2026-09-30.

Verified static evidence from the local App:
- libamaptbt.so contains `ws/transfer/auth/new_vector_cross/` and
  `ws/lbs/auth/new_vector_cross/`; selection, full host and actual invocation
  have not yet been established.
- XML templates contain device ID, SDK version, dimensions, data version,
  optional NaviID and a pict element with CrossType/Dist/Navi. These are
  templates, not proof of a complete request contract.
- ServerCrossImageLoader receives HTTP data; VectorCrossImageProvider has a
  request-message handler. libamaphorus has distinct WidgetCross vector and
  raster setters.
- Decompiled NaviCrossManager receives eventType=3 plus width/height,
  isShowCrossImg/errorType/imgType and raw pixel bytes, then creates a Bitmap.
  This is a rendered output callback, not an HTTP PNG URL.

Reproduce binary string inventory with `inspect_junction_images.py APK`;
its output records library hashes and file offsets. No production endpoint,
image decoding or original-image display has been verified yet. Next: trace
request template call sites and route maneuver identifiers, obtain a valid
response, then reproduce the original decoder/rendering and show/hide timing.

## Request-road contract traced

`libamaptbt.so+b7408c..b743b8` formats the cross/pict XML and iterates
0x70-byte road records. Verified format strings establish original road
fields: id, rc, fw, coords, coords3d; optional in/out/confusion/signlight/
solidWhiteLine/swLanes and mainAction/assiAction. At +b74130 it reads rc/fw
from record+0/+4 and the uint64 road ID from +40. Flags +49/+4a select
entry/exit roads; +68/+69 supply main/assistant actions. These are request
builder observations, not yet a decoder mapping from v5.1 route protobuf.

`inspect_junction_images.py APK --request-evidence` now reproduces templates
and disassembly, alongside library hashes. Generic string-reference finder
now accepts --library for cross-resource research. No HTTP call was made
with invented roads/IDs. Next missing edge: route-native crossActionParam
construction -> these road records, then the response decoder/rendering.

## Road-object source trace (2026-09-30)

The record converter at `b77584` establishes the following getter mapping:

| XML field | Native source | Record offset |
| --- | --- | --- |
| id | cd8160, link virtual slot 0x80 | 0x40 (64 bit) |
| rc | cd82f4, slot 0xf0 | 0x00 |
| fw | cd82d8, slot 0xe8 | 0x04 |
| coords | cd8080, slot 0x38; count via slot 0x40 | 0x10 |
| coords3d | cd80b0, slot 0x48; count via slot 0x50 | 0x20 |

`b74fb4` collects 0x70-byte records, traversing nearby links with accumulated
length checks against 99 and 49/50. Units and complete selection semantics
remain unverified. `b77584` selects the first two points in one branch and a
representative middle point in another; arbitrary full route polylines are
not interchangeable with this input.

The link lookup at `ce0624` checks segment virtual slot 0x88 for the link
count, then calls slot 0xc8 with the index and wraps the returned object.
The concrete implementation of these virtual methods still needs resolving
before assigning protobuf field numbers. No protobuf mapping is inferred
from native object offsets.

The evidence command now exports these instruction ranges and getter slots.
It ran successfully against the local APK. This verifies the static trace,
not a successful HTTP response or a working original junction image.

## Endpoint profile and response check (2026-09-30)

The APK's relocated request-profile table at `f4e130..f4e280` contains eight
`aos.m5` entries for original cross pictures: both
`ws/lbs/auth/new_vector_cross/` and
`ws/transfer/auth/new_vector_cross/`, with `vector`, `cross`,
`motor_cross`, and `three_d_cross` categories and numeric request kinds
6, 7, 10. The evidence command exports the full rows. These profiles
identify actual native routes and variants, but do not by themselves
establish the selected variant or its HTTP parameter/signature layout.

A controlled signed route request for identical coordinates was compared
with and without App route options `contentoptions=65536&threeD=1`.
Both responses contained exactly one kind-1 route record. The uncompressed
response lengths matched; differences were request/route IDs only. Thus
these route options did not supply the separate junction-image response.

The candidate junction endpoint returned `code=3, Params error` for an empty
request and for XML sent as a guessed `reqstr` query/form/raw POST. This
does not validate any request shape. No further speculative production
request or image display is wired into TMC.

## Local App navigation observation (2026-09-30)

The installed 17.00.0.2005 App was started in the local BlueStacks Rvc64
instance via its documented `amapuri://route/plan/` deep link. A short driving
route planned successfully and the App entered live navigation after the
driving notice. The navigation screen showed its built-in lane-arrow guide.
That is **not** evidence that the separate vector junction illustration or
its HTTP response has been captured. The emulator subsequently reported a
mock network location in Hong Kong and replanned the Hangzhou route as a
long-distance trip, so those pixels cannot validate junction show timing for
the requested route.

The emulator shell can read logcat but cannot capture packets with tcpdump
(`Operation not permitted`). Enabling its host `enable_root_access` flag did
not give the shell `su` or a root ADB daemon and was reverted. No packet,
request parameters or image bytes were obtained from the App.

The reproducible evidence command now also emits direct AArch64 `BL` call
sites. It locates the route-to-cross parameter builder at `b73ff0`, called
from `b6ff3c`, `b70034`, and `b715e0`. The road collector at `b74fb4` is
called by the XML builders at `b73fbc`, `b744e8`, and `b74704`. This narrows
the actual native route-to-request chain, but the code at `b72634` and
`b72be8` appears to format diagnostics; it is not proof of HTTP dispatch.
The remaining boundary is the concrete request object's parameter/body
construction and the matching response decoder. Until a valid original
response is captured and decoded, TMC must not label a substitute image as
the original App junction illustration.

The caller chain continues through `b6e7dc -> b6f830 -> b6f91c ->
b6fd70 -> b6ff3c/b70034 -> b73ff0`; `b6e624` invokes `b6f830`
and is registered as a virtual method in the relocated table at `f66348`.
This identifies native navigation-state selection upstream of the XML
builder. It does not yet identify the network request object or response
bitmap construction downstream.

## HTTP boundary narrowed (2026-09-30)

The `ServerCrossImageLoader` vtable points to response callback `78f65c`.
Its request method at `78f280..78f3cc` obtains AOS request kind 7, adds a
`cross_ver=4.0` parameter, and invokes the shared submission routine
`673354` with the cross payload. That routine scans the 0x30-byte AOS profile
table and matches request kind, variant, and transfer variant before handing
the request to a virtual transport method. The callback `78f65c` passes
returned bytes to `78f730`, which invokes decoder `78ff38`. The decoder
passes the raw buffer through `790200`, checks response identifiers, then
iterates 0x98-byte decoded records. This establishes submission and receive
edges; earlier XML construction alone did not.

It still does not establish all shared AOS request parameters, auth/signing,
which profile variant the App selects in this environment, or the cross
payload from real neighboring road objects. A controlled request adding
`cross_ver=4.0` and `is_bin=1` to an otherwise minimal XML body, then form
variants with `reqstr` or `xml`, all returned `code=3, Params error`.
No valid original vector or raster response has been obtained, so no
original-image rendering path is connected to TMC yet.

## Route-link ID check (2026-10-03)

The three link wrapper vtables at `f68f70`, `f695a8`, and `f6a0d0` all
forward road ID, class, form and coordinate getters to an underlying link
object. The public v5.1 route response does include per-link data, but field 1 has
not been verified as the road ID: the sampled Hangzhou route mixes 0,
small values such as 2 and 1401, and packed-looking 64-bit values such as
`0x2b00000017`. It would be unsafe to insert that field into `<road id=…>`
without tracing the underlying getter. This is the missing data boundary
between the decoded route and the original junction request. Green-wave
arrival advice uses the separately verified live signal phases and does not
depend on this image endpoint.

## Emulator capture attempt (2026-10-03)

The local BlueStacks instance entered real navigation on a short Hangzhou
route, confirming the App can run its native guidance path on this machine.
An `adb reverse` tunnel carried an Android `wget` control request through a
local HTTP proxy, so host-to-emulator proxy connectivity was verified.
After setting Android's global proxy and restarting the App, route planning
and navigation produced no intercepted AMap HTTP flow. This observation does
not prove that the junction endpoint was requested: the vehicle remained near
the first turn, and the App may bypass the system proxy or use cached data.
No original junction request or response was captured.

A separate host-process memory probe could enumerate the BlueStacks process
regions but `ReadProcessMemory` returned access denied for committed regions;
it did not expose the in-memory XML. The proxy setting and `adb reverse`
tunnel were removed after the experiment. The next useful step is still to
derive a valid original cross payload from native road objects and obtain a
successful `new_vector_cross` response, then port its decoder and display
timing. Neither the screenshot of native navigation nor a route polyline is
an original junction-image asset.

The APK evidence command now checks the instruction sites for request kind 7,
the `cross_ver=4.0` parameter addition, and shared AOS submission. It emits
these as `cross_http_contract` alongside the endpoint profiles, making that
part of the native call chain reproducible. This still does not supply the
route-specific body or a valid response.

## Elevated-fork runtime observation (2026-10-03)

A fresh App 5.1 route from `(120.1974, 30.2924)` to
`(120.165, 30.335)` includes 秋石高架路, 石石立交桥 and 留石高架路. The route's
elevated fork is around `(120.19355, 30.33128)` (GCJ-02). The official
17.00 App entered **real navigation** in BlueStacks and received continuous
WGS-84 GPS fixes transformed from that route's GCJ-02 vertices. It displayed
its original large three-dimensional road-fork illustration, yellow branch
arrow and lane arrows. One frame showed a fork illustration about 134 m
ahead; another showed the 留石高架路上塘高架路 exit illustration about 265 m ahead.
These were visually observed, not inferred from route labels. Local ignored
screenshots are `fork-live-now.png` and `fork-live-later.png`.

An App Java heap captured during the route contained live
`https://m5.amap.com/ws/transfer/auth/new_vector_cross/` request URLs. Their
outer query has `ent`, `in`, `csid`, `is_bin`. Decoding `in` with the APK's
known query codec yielded 36 named fields, including `cross_ver=4.0` and
`sdk_version=17.00.0.1007`. This resolves the active endpoint choice to the
**transfer** variant for this session. The heap contained no plaintext
`<cross` XML; the route-specific body and successful binary response remain
to be captured or reconstructed. Replaying one captured URL with an empty
body returned HTTP 400, so it is not a standalone image URL.

Run `inspect_junction_runtime.py --route ROUTE.bin --heap APP.hprof` to
reproduce the sanitized route/request summary. It never prints signed query
values or device identifiers. The on-screen App picture remains a research
reference; TMC does not yet display this original data.

The same heap contains gzip JSON from the App's lane-suggestion request with
ordered `linkInfos[].linkId`. The existing 5.1 base-plus-ZigZag-delta decoder
recovered **all 57** route-0 link IDs in the same order; later live windows
matched the final 54 and 47 IDs exactly. This validates the route's actual
road-link IDs against independent App runtime data. It does not establish
the cross-image body's road selection, coordinates3d, or response format.
The runtime inspection command now reports these exact contiguous matches
without printing link IDs.

A bounded replay of a captured signed cross URL, both with an empty body and
with a locally assembled candidate XML road list, returned the same HTTP 400
`code=2`. Changing only the outer `csid` did not change that result. This
does not distinguish a stale/session-bound signature from an invalid body;
the candidate must not be treated as the App's original request. The actual
road-window selection and successful response are still missing.
