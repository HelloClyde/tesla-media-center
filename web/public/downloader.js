self.importScripts("common.js" + (self.location ? self.location.search : ''));

function Downloader() {
    this.logger = new Logger("Downloader");
    this.ws = null;
}

Downloader.prototype.appendBuffer = function (buffer1, buffer2) {
    var tmp = new Uint8Array(buffer1.byteLength + buffer2.byteLength);
    tmp.set(new Uint8Array(buffer1), 0);
    tmp.set(new Uint8Array(buffer2), buffer1.byteLength);
    return tmp.buffer;
};

Downloader.prototype.reportFileSize = function (sz, st) {
    var objData = {
        t: kGetFileInfoRsp,
        i: {
            sz: sz,
            st: st
        }
    };

    //this.logger.logInfo("File size " + sz + " bytes.");
    self.postMessage(objData);
};

Downloader.prototype.reportData = function (start, end, seq, data, size=-1) {
    var objData = {
        t: kFileData,
        s: start,
        e: end,
        d: data,
        q: seq,
        size: size,
    };
    self.postMessage(objData, [objData.d]);
};

// Http implement.
// Opt-in range transport: try CDN URLs first, then the authenticated byte relay.
// Keep the selected source across reads (including seeks) without restarting decoding.
Downloader.prototype.readRange = async function (start, end) {
    var lastError;
    for (var index = this.sourceIndex; index < this.sources.length; index++) {
        var controller = new AbortController();
        var timer = setTimeout(() => controller.abort(), 8000);
        try {
            var response = await fetch(this.sources[index], {
                headers: { Range: 'bytes=' + start + '-' + end },
                mode: 'cors', credentials: 'same-origin', referrerPolicy: 'no-referrer',
                signal: controller.signal
            });
            var range = /^bytes (\d+)-(\d+)\/(\d+)$/.exec(response.headers.get('Content-Range') || '');
            var total = range && Number(range[3]);
            var actualEnd = Math.min(end, total - 1);
            if (response.status !== 206 || !range || !Number.isSafeInteger(total) || total <= start ||
                Number(range[1]) !== start || Number(range[2]) !== actualEnd ||
                (this.sourceSize && this.sourceSize !== total)) throw new Error('Invalid byte range');
            var expected = actualEnd - start + 1;
            var data = new Uint8Array(expected);
            var reader = response.body.getReader();
            var offset = 0;
            while (true) {
                var chunk = await reader.read();
                if (chunk.done) break;
                if (offset + chunk.value.length > expected) throw new Error('Oversized byte range');
                data.set(chunk.value, offset);
                offset += chunk.value.length;
            }
            if (offset !== expected) throw new Error('Incomplete byte range');
            this.sourceIndex = Math.max(this.sourceIndex, index);
            this.sourceSize = total;
            return { data: data.buffer, end: actualEnd, total: total };
        } catch (error) {
            lastError = error;
        } finally {
            clearTimeout(timer);
            controller.abort();
        }
    }
    throw lastError || new Error('No media source');
};

Downloader.prototype.getFileInfoByHttp = function (url) {
    if (this.sources) {
        this.readRange(0, 0).then(result => this.reportFileSize(result.total, 200),
            () => this.reportFileSize(0, 502));
        return;
    }
    this.logger.logInfo("Getting file size " + url + ".");
    var size = 0;
    var status = 0;
    var reported = false;

    var xhr = new XMLHttpRequest();
    xhr.open('get', url, true);
    var self = this;
    xhr.onreadystatechange = () => {
        var len = xhr.getResponseHeader("Content-Length");
        if (len) {
            size = len;
        }

        if (xhr.status) {
            status = xhr.status;
        }

        //Completed.
        if (!reported && ((size > 0 && status > 0) || xhr.readyState == 4)) {
            self.reportFileSize(size, status);
            reported = true;
            xhr.abort();
        }
    };
    xhr.send();
};

Downloader.prototype.reportDownloadError = function (seq) {
    self.postMessage({ t: kFileData, q: seq, error: '视频直连及转接均失败，请重试' });
};

Downloader.prototype.downloadFileByHttp = function (url, start, end, seq) {
    if (this.sources) {
        this.readRange(start, end).then(result => this.reportData(start, result.end, seq, result.data),
            () => this.reportDownloadError(seq));
        return;
    }
    //this.logger.logInfo("Downloading file " + url + ", bytes=" + start + "-" + end + ".");
    var xhr = new XMLHttpRequest;
    xhr.open('get', url, true);
    xhr.responseType = 'arraybuffer';
    xhr.setRequestHeader("Range", "bytes=" + start + "-" + end);
    var self = this;
    xhr.onload = function () {
        self.reportData(start, end, seq, xhr.response);
    };
    xhr.send();
};

Downloader.prototype.downloadFileByHttpStream = function (url, start, end, seq) {
    this.logger.logInfo("Downloading file " + url + ", bytes=" + start + "-" + end + ".");
    var xhr = new XMLHttpRequest;
    xhr.open('get', url, true);
    xhr.responseType = 'arraybuffer';
    xhr.setRequestHeader("Range", "bytes=" + start + "-" + end);
    var self = this;
    xhr.onload = function () {
        var size = xhr.getResponseHeader("BV-Content-Length");
        self.reportData(start, end, seq, xhr.response, size);
    };
    xhr.send();
};

// http stream implement
Downloader.prototype.getFileInfoByHttpStream = function (url) {
    this.logger.logInfo("Getting file size " + url + ".");
    var size = 0;
    var status = 0;
    var reported = false;

    var xhr = new XMLHttpRequest();
    xhr.open('get', url + '/info', true);
    var self = this;
    xhr.onreadystatechange = () => {
        var len = xhr.getResponseHeader("BV-Content-Length");
        if (len) {
            size = len;
        }

        if (xhr.status) {
            status = xhr.status;
        }

        //Completed.
        if (!reported && ((size > 0 && status > 0) || xhr.readyState == 4)) {
            self.reportFileSize(size, status);
            reported = true;
            xhr.abort();
        }
    };
    xhr.send();
};
// Websocket implement, NOTICE MUST call requestWebsocket serially, MUST wait
// for result of last websocket request(cb called) for there's only one stream
// exists.
Downloader.prototype.requestWebsocket = function (url, msg, cb) {
    if (this.ws == null) {
        this.ws = new WebSocket(url);
        this.ws.binaryType = 'arraybuffer';

        var self = this;
        this.ws.onopen = function(evt) {
            self.logger.logInfo("Ws connected.");
            self.ws.send(msg);
        };

        this.ws.onerror = function(evt) {
            self.logger.logError("Ws connect error " + evt.data);
        }

        this.ws.onmessage = cb.onmessage;
    } else {
        this.ws.onmessage = cb.onmessage;
        this.ws.send(msg);
    }
};

Downloader.prototype.getFileInfoByWebsocket = function (url) {
    //this.logger.logInfo("Getting file size " + url + ".");

    // TBD, consider tcp sticky package.
    var data = null;
    var expectLength = 4;
    var self = this;
    var cmd = {
        url : url,
        cmd : "size",
    };
    this.requestWebsocket(url, JSON.stringify(cmd), {
        onmessage : function(evt) {
            if (data != null) {
                data = self.appendBuffer(data, evt.data);
            } else if (evt.data.byteLength < expectLength) {
                data = evt.data.slice(0);
            } else {
                data = evt.data;
            }

            // Assume 4 bytes header as file size.
            if (data.byteLength == expectLength) {
                let int32array = new Int32Array(data, 0, 1);
                let size = int32array[0];
                self.reportFileSize(size, 200);
                //self.logger.logInfo("Got file size " + self.fileSize + ".");
            }
        }
    });
};

Downloader.prototype.downloadFileByWebsocket = function (url, start, end, seq) {
    //this.logger.logInfo("Downloading file " + url + ", bytes=" + start + "-" + end + ".");
    var data = null;
    var expectLength = end - start + 1;
    var self = this;
    var cmd = {
        url : url,
        cmd : "data",
        start : start,
        end : end
    };
    this.requestWebsocket(url, JSON.stringify(cmd), {
        onmessage : function(evt) {
            if (data != null) {
                data = self.appendBuffer(data, evt.data);
            } else if (evt.data.byteLength < expectLength) {
                data = evt.data.slice(0);
            } else {
                data = evt.data;
            }

            // Wait for expect data length.
            if (data.byteLength == expectLength) {
                self.reportData(start, end, seq, data);
            }
        }
    });
};

// Interface.
Downloader.prototype.getFileInfo = function (proto, url) {
    switch (proto) {
        case kProtoHttp:
            this.getFileInfoByHttp(url);
            break;
        case kProtoWebsocket:
            this.getFileInfoByWebsocket(url);
            break;
        case kProtoStream:
            this.getFileInfoByHttpStream(url);
            break;
        default:
            this.logger.logError("Invalid protocol " + proto);
            break;
    }
};

Downloader.prototype.downloadFile = function (proto, url, start, end, seq) {
    switch (proto) {
        case kProtoHttp:
            this.downloadFileByHttp(url, start, end, seq);
            break;
        case kProtoWebsocket:
            this.downloadFileByWebsocket(url, start, end, seq);
            break;
        case kProtoStream:
            this.downloadFileByHttpStream(url, start, end, seq);
            break;
        default:
            this.logger.logError("Invalid protocol " + proto);
            break;
    }
}

self.downloader = new Downloader();

self.onmessage = function (evt) {
    if (!self.downloader) {
        console.log("[ER] Downloader not initialized!");
        return;
    }

    var objData = evt.data;
    switch (objData.t) {
        case kGetFileInfoReq:
            self.downloader.sources = Array.isArray(objData.sources) && objData.sources.length ? objData.sources : null;
            self.downloader.sourceIndex = 0;
            self.downloader.sourceSize = 0;
            self.downloader.getFileInfo(objData.p, objData.u);
            break;
        case kDownloadFileReq:
            self.downloader.downloadFile(objData.p, objData.u, objData.s, objData.e, objData.q);
            break;
        case kCloseDownloaderReq:
            //Nothing to do.
            break;
        default:
            self.downloader.logger.logError("Unsupport messsage " + objData.t);
    }
};
