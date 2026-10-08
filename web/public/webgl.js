function Texture(gl) {
    this.gl = gl;
    this.texture = gl.createTexture();
    this.width = 0;
    this.height = 0;
    gl.bindTexture(gl.TEXTURE_2D, this.texture);

    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);

    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
}

Texture.prototype.bind = function (n, program, name) {
    var gl = this.gl;
    gl.activeTexture([gl.TEXTURE0, gl.TEXTURE1, gl.TEXTURE2][n]);
    gl.bindTexture(gl.TEXTURE_2D, this.texture);
    gl.uniform1i(gl.getUniformLocation(program, name), n);
};

Texture.prototype.fill = function (width, height, data) {
    var gl = this.gl;
    gl.bindTexture(gl.TEXTURE_2D, this.texture);
    if (this.width !== width || this.height !== height) {
        gl.texImage2D(gl.TEXTURE_2D, 0, gl.LUMINANCE, width, height, 0, gl.LUMINANCE, gl.UNSIGNED_BYTE, data);
        this.width = width;
        this.height = height;
    } else {
        // Keep the texture allocation across frames; reallocating three planes
        // on every frame is expensive on the car browser's WebGL implementation.
        gl.texSubImage2D(gl.TEXTURE_2D, 0, 0, 0, width, height, gl.LUMINANCE, gl.UNSIGNED_BYTE, data);
    }
};

function WebGLPlayer(canvas, options) {
    this.canvas = canvas;
    this.gl = canvas.getContext("webgl") || canvas.getContext("experimental-webgl");
    this.initGL(options);
}

WebGLPlayer.prototype.initGL = function (options) {
    if (!this.gl) {
        console.log("[ER] WebGL not supported.");
        return;
    }

    var gl = this.gl;
    gl.pixelStorei(gl.UNPACK_ALIGNMENT, 1);
    var program = gl.createProgram();
    var vertexShaderSource = [
        "attribute highp vec4 aVertexPosition;",
        "attribute vec2 aTextureCoord;",
        "varying highp vec2 vTextureCoord;",
        "void main(void) {",
        " gl_Position = aVertexPosition;",
        " vTextureCoord = aTextureCoord;",
        "}"
    ].join("\n");
    var vertexShader = gl.createShader(gl.VERTEX_SHADER);
    gl.shaderSource(vertexShader, vertexShaderSource);
    gl.compileShader(vertexShader);
    var fragmentShaderSource = [
        "precision highp float;",
        "varying lowp vec2 vTextureCoord;",
        "uniform sampler2D YTexture;",
        "uniform sampler2D UTexture;",
        "uniform sampler2D VTexture;",
        "const mat4 YUV2RGB = mat4",
        "(",
        " 1.1643828125, 0, 1.59602734375, -.87078515625,",
        " 1.1643828125, -.39176171875, -.81296875, .52959375,",
        " 1.1643828125, 2.017234375, 0, -1.081390625,",
        " 0, 0, 0, 1",
        ");",
        "void main(void) {",
        " gl_FragColor = vec4( texture2D(YTexture, vTextureCoord).x, texture2D(UTexture, vTextureCoord).x, texture2D(VTexture, vTextureCoord).x, 1) * YUV2RGB;",
        "}"
    ].join("\n");

    var fragmentShader = gl.createShader(gl.FRAGMENT_SHADER);
    gl.shaderSource(fragmentShader, fragmentShaderSource);
    gl.compileShader(fragmentShader);
    gl.attachShader(program, vertexShader);
    gl.attachShader(program, fragmentShader);
    gl.linkProgram(program);
    gl.useProgram(program);
    if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {
        console.log("[ER] Shader link failed.");
    }
    var vertexPositionAttribute = gl.getAttribLocation(program, "aVertexPosition");
    gl.enableVertexAttribArray(vertexPositionAttribute);
    var textureCoordAttribute = gl.getAttribLocation(program, "aTextureCoord");
    gl.enableVertexAttribArray(textureCoordAttribute);

    var verticesBuffer = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, verticesBuffer);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([1.0, 1.0, 0.0, -1.0, 1.0, 0.0, 1.0, -1.0, 0.0, -1.0, -1.0, 0.0]), gl.STATIC_DRAW);
    gl.vertexAttribPointer(vertexPositionAttribute, 3, gl.FLOAT, false, 0, 0);
    var texCoordBuffer = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, texCoordBuffer);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([1.0, 0.0, 0.0, 0.0, 1.0, 1.0, 0.0, 1.0]), gl.STATIC_DRAW);
    gl.vertexAttribPointer(textureCoordAttribute, 2, gl.FLOAT, false, 0, 0);

    gl.y = new Texture(gl);
    gl.u = new Texture(gl);
    gl.v = new Texture(gl);
    gl.y.bind(0, program, "YTexture");
    gl.u.bind(1, program, "UTexture");
    gl.v.bind(2, program, "VTexture");
}

WebGLPlayer.prototype.renderFrame = function (videoFrame, width, height, uOffset, vOffset) {
    if (!this.gl) {
        console.log("[ER] Render frame failed due to WebGL not supported.");
        return;
    }

    var gl = this.gl;
    var canvas = gl.canvas;
    
    // 计算视频宽高比
    var videoAspect = width / height;
    var canvasAspect = canvas.width / canvas.height;
    // console.log('canvas hw', canvas.width, canvas.height);
    
    // 计算保持宽高比的视口尺寸
    var viewport = { x: 0, y: 0, width: canvas.width, height: canvas.height };
    
    if (videoAspect > canvasAspect) {
        // 视频更宽，固定宽度，调整高度
        viewport.height = canvas.width / videoAspect;
        viewport.y = (canvas.height - viewport.height) / 2;
    } else {
        // 视频更高，固定高度，调整宽度
        viewport.width = canvas.height * videoAspect;
        viewport.x = (canvas.width - viewport.width) / 2;
    }

    // 设置视口并清除为黑色
    gl.viewport(0, 0, canvas.width, canvas.height);
    gl.clearColor(0.0, 0.0, 0.0, 1.0);  // 使用不透明黑色
    gl.clear(gl.COLOR_BUFFER_BIT);

    // 设置实际渲染区域（保持宽高比）
    gl.viewport(
        Math.round(viewport.x),
        Math.round(viewport.y),
        Math.round(viewport.width),
        Math.round(viewport.height)
    );

    // 填充纹理数据（保持原始视频分辨率）
    gl.y.fill(width, height, videoFrame.subarray(0, uOffset));
    gl.u.fill(width >> 1, height >> 1, videoFrame.subarray(uOffset, uOffset + vOffset));
    gl.v.fill(width >> 1, height >> 1, videoFrame.subarray(uOffset + vOffset, videoFrame.length));

    gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
};

WebGLPlayer.prototype.fullscreen = function () {
    // Fullscreen the picture container so touch controls remain above the canvas.
    var canvas = this.canvas;
    var target = canvas.parentElement;
    if (!target || document.fullscreenElement || document.webkitFullscreenElement) return;
    var request = target.requestFullscreen || target.webkitRequestFullscreen ||
        target.webkitRequestFullScreen || target.mozRequestFullScreen || target.msRequestFullscreen;
    if (!request) return;
    var player = this;
    var button = document.createElement('button');
    button.type = 'button';
    button.setAttribute('aria-label', '退出全屏');
    button.title = '退出全屏';
    button.innerHTML = '<svg viewBox="0 0 24 24" width="26" height="26" aria-hidden="true"><path d="M6 6L18 18M18 6L6 18" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"/></svg>';
    button.style.cssText = 'position:absolute;top:max(16px,env(safe-area-inset-top));right:max(16px,env(safe-area-inset-right));z-index:2147483647;width:52px;height:52px;min-width:52px;min-height:52px;padding:0;display:grid;place-items:center;border:1px solid #ffffff66;border-radius:50%;background:#000a;color:#fff;cursor:pointer;touch-action:manipulation;';
    button.onclick = function (event) { event.preventDefault(); event.stopPropagation(); player.exitfullscreen(); };
    var oldTargetStyle = target.getAttribute('style');
    var oldCanvasStyle = canvas.getAttribute('style');
    var active = false, cleaned = false;
    var events = ['fullscreenchange', 'webkitfullscreenchange', 'mozfullscreenchange', 'MSFullscreenChange'];
    function cleanup() {
        if (cleaned) return;
        cleaned = true;
        button.remove();
        if (active) {
            if (oldTargetStyle === null) target.removeAttribute('style'); else target.setAttribute('style', oldTargetStyle);
            if (oldCanvasStyle === null) canvas.removeAttribute('style'); else canvas.setAttribute('style', oldCanvasStyle);
        }
        events.forEach(function (name) { document.removeEventListener(name, changed); });
    }
    function changed() {
        var element = document.fullscreenElement || document.webkitFullscreenElement ||
            document.mozFullScreenElement || document.msFullscreenElement;
        if (element !== target) { cleanup(); return; }
        active = true;
        target.style.cssText += ';position:relative;width:100vw;height:100vh;max-width:none;max-height:none;background:#000;overflow:hidden;';
        canvas.style.cssText += ';display:block;width:100%;height:100%;object-fit:contain;';
    }
    target.appendChild(button);
    events.forEach(function (name) { document.addEventListener(name, changed); });
    try {
        var pending = request.call(target);
        if (pending && pending.catch) pending.catch(cleanup);
    } catch (_) { cleanup(); }
};

WebGLPlayer.prototype.exitfullscreen = function (){
    if (document.exitFullscreen) {
        document.exitFullscreen();
    } else if (document.webkitExitFullscreen) {
        document.webkitExitFullscreen();
    } else if (document.mozCancelFullScreen) {
        document.mozCancelFullScreen();
    } else if (document.msExitFullscreen) {
        document.msExitFullscreen();
    } else {
        alert("Exit fullscreen doesn't work");
    }
}
