// Attach only to our diagnostic app. No TLS bypass or request modification.
// Full captures may contain credentials; the host must save them privately.
Java.perform(function () {
  function value(v) { return v == null ? null : String(v); }
  function bytes(v) { return v == null ? null : new Uint8Array(Array.from(v, x => x & 255)).buffer; }
  const network = Java.use('com.amap.api.navi.core.d');
  const sendRequest = network.onRequestSend.overload('com.autonavi.ae.guide.NaviNetworkRequest');
  sendRequest.implementation = function (req) {
    try {
      send({kind:'request', id:req.reqId.value, route:req.isRouteRequest.value,
        url:value(req.url.value), headers:value(req.requestHeader.value), params:value(req.requestParameters.value),
        serverType:req.serverType.value, transType:req.transType.value, post:req.isPostMethod.value}, bytes(req.data.value));
    } catch (error) { send({kind:'capture-error', stage:'request'}); }
    return sendRequest.call(this, req);
  };
  const core = Java.use('com.autonavi.amap.navicore.AMapNaviCoreManager');
  const callback = core.networkCallback.overload('int','int','[B','java.lang.String','[B');
  callback.implementation = function (a,b,c,d,e) {
    // Parameter semantics are not yet confirmed: retain positional names.
    try {
      send({kind:'response', arg1:a,arg2:b,arg4:value(d),part:3}, bytes(c));
      send({kind:'response', arg1:a,arg2:b,part:5}, bytes(e));
    } catch(error) { send({kind:'capture-error',stage:'response'}); }
    return callback.call(this,a,b,c,d,e);
  };
  send({kind:'ready'});
});
