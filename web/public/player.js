//Decoder states.
const decoderStateIdle          = 0;
const decoderStateInitializing  = 1;
const decoderStateReady         = 2;
const decoderStateFinished      = 3;

//Player states.
const playerStateIdle           = 0;
const playerStatePlaying        = 1;
const playerStatePausing        = 2;

//Constant.
const maxBufferTimeLength       = 1.0;
const downloadSpeedByteRateCoef = 2.0;
const defaultChunkSize = 65536 * 8;
// The build stamps the entry script; use the same version for its workers.
const playerAssetVersion = typeof document !== 'undefined' && document.currentScript
    ? new URL(document.currentScript.src).search : '';

String.prototype.startWith = function(str) {
    var reg = new RegExp("^" + str);
    return reg.test(this);
};

function FileInfo(url) {
    this.url = url;
    this.size = 0;
    this.offset = 0;
    this.chunkSize = defaultChunkSize;
}

function Player() {
    this.destroyed = false;
    this.fileInfo           = null;
    this.chunkSize          = defaultChunkSize;
    this.maxAheadSeconds    = 0;
    this.audioBlocked       = false;
    this.audioBlockedCallback = null;
    this.pcmPlayer          = null;
    this.canvas             = null;
    this.webglPlayer        = null;
    this.callback           = null;
    this.waitHeaderLength   = 524288;
    this.duration           = 0;
    this.pixFmt             = 0;
    this.videoWidth         = 0;
    this.videoHeight        = 0;
    this.yLength            = 0;
    this.uvLength           = 0;
    this.beginTimeOffset    = 0;
    this.streamBaseOffset   = 0;
    this.decoderState       = decoderStateIdle;
    this.playerState        = playerStateIdle;
    this.decoding           = false;
    this.decodeInterval     = 5;
    this.videoRendererTimer = null;
    this.downloadTimer      = null;
    this.chunkInterval      = 200;
    this.downloadSeqNo      = 0;
    this.downloading        = false;
    this.downloadSwitch     = true;
    this.downloadProto      = kProtoHttp;
    this.timeLabel          = null;
    this.timeTrack          = null;
    this.trackTimer         = null;
    this.trackTimerInterval = 500;
    this.displayDuration    = "00:00:00";
    this.audioEncoding      = "";
    this.audioChannels      = 0;
    this.audioSampleRate    = 0;
    this.seeking            = false;  // Flag to preventing multi seek from track.
    this.justSeeked         = false;  // Flag to preventing multi seek from ffmpeg.
    this.urgent             = false;
    this.seekWaitLen        = 524288; // Default wait for 512K, will be updated in onVideoParam.
    this.seekReceivedLen    = 0;
    this.loadingDiv         = null;
    this.buffering          = false;
    this.bufferingWatchdog   = null;
    this.frameBuffer        = [];
    this.isStream           = false;
    this.streamReceivedLen  = 0;
    this.firstAudioFrame    = true;
    this.firstVideoFrame    = true;
    this.fetchController    = null;
    this.streamPauseParam   = null;
    this.logger             = new Logger("Player");
    this.finishNotified     = false;
    if (!this.destroyed) {
        this.initDownloadWorker();
        this.initDecodeWorker();
    }
    this.finishCallback     = null;
    this.timeCallback       = null;
    this.browserSource      = null;
    this.sourceEnded        = false;
    this.sourceWatchdog     = null;
    this.lastRenderedAt     = 0;
    this.displayAnimationFrame = null;
}

Player.prototype.resetWorkers = function () {
    if (this.downloadWorker) {
        this.downloadWorker.terminate();
        this.downloadWorker = null;
    }
    if (this.decodeWorker) {
        this.decodeWorker.terminate();
        this.decodeWorker = null;
    }
    if (!this.destroyed) {
        this.initDownloadWorker();
        this.initDecodeWorker();
    }
};

Player.prototype.initDownloadWorker = function () {
    var self = this;
    this.downloadWorker = new Worker("/downloader.js" + playerAssetVersion);
    var worker = this.downloadWorker;
    this.downloadWorker.onmessage = function (evt) {
        if (self.destroyed || self.downloadWorker !== worker) return;
        var objData = evt.data;
        switch (objData.t) {
            case kGetFileInfoRsp:
                self.onGetFileInfo(objData.i);
                break;
            case kFileData:
                if (objData.error) {
                    if (objData.q === self.downloadSeqNo) self.reportPlayError(-1, 0, objData.error);
                    break;
                }
                if (self.downloadProto == kProtoStream){
                    self.onFileDataStream(objData.d, objData.s, objData.e, objData.q, objData.size);
                } else {
                    self.onFileData(objData.d, objData.s, objData.e, objData.q);
                }
                
                break;
        }
    }
};

Player.prototype.initDecodeWorker = function () {
    var self = this;
    this.decodeWorker = new Worker("/decoder.js" + playerAssetVersion);
    var worker = this.decodeWorker;
    this.decodeWorker.onerror = function () {
        if (self.destroyed || self.decodeWorker !== worker) return;
        self.reportPlayError(-1, 0, 'WASM 解码器加载失败，请刷新后重试');
    };
    this.decodeWorker.onmessage = function (evt) {
        if (self.destroyed || self.decodeWorker !== worker) return;
        var objData = evt.data;
        // console.log('decode frame', objData);
        switch (objData.t) {
            case kInitDecoderRsp:
                self.onInitDecoder(objData);
                break;
            case kOpenDecoderRsp:
                self.onOpenDecoder(objData);
                break;
            case kVideoFrame:
                self.onVideoFrame(objData);
                break;
            case kAudioFrame:
                self.onAudioFrame(objData);
                break;
            case kDecodeFinishedEvt:
                self.onDecodeFinished(objData);
                break;
            case kRequestDataEvt:
                console.log('request data', evt);
                self.onRequestData(objData.o, objData.a);
                break;
            case kSeekToRsp:
                self.onSeekToRsp(objData.r);
                break;
            case kDataMax:
                console.log('stop download');
                self.downloadSwitch = false;
                break;
            case kDataNormal:
                self.downloadSwitch = true;
                break;
        }
    }
};

Player.prototype.play = function (url, canvas, callback, waitHeaderLength, isStream, browserSource, httpSources, prefetchedRange) {
    if (this.destroyed) return { e: -1, m: "Player destroyed" };
    this.logger.logInfo("Play " + url + ".");
    console.log('waitHeaderLength', waitHeaderLength);
    this.finishNotified = false;

    var ret = {
        e: 0,
        m: "Success"
    };

    var success = true;
    do {
        if (this.playerState == playerStatePausing) {
            ret = this.resume();
            break;
        }

        if (this.playerState == playerStatePlaying) {
            break;
        }

        if (!url) {
            ret = {
                e: -1,
                m: "Invalid url"
            };
            success = false;
            this.logger.logError("[ER] playVideo error, url empty.");
            break;
        }

        if (!canvas) {
            ret = {
                e: -2,
                m: "Canvas not set"
            };
            success = false;
            this.logger.logError("[ER] playVideo error, canvas empty.");
            break;
        }

        if (!this.downloadWorker) {
            ret = {
                e: -3,
                m: "Downloader not initialized"
            };
            success = false;
            this.logger.logError("[ER] Downloader not initialized.");
            break
        }

        if (!this.decodeWorker) {
            ret = {
                e: -4,
                m: "Decoder not initialized"
            };
            success = false;
            this.logger.logError("[ER] Decoder not initialized.");
            break
        }

        if (url.startWith("ws://") || url.startWith("wss://")) {
            this.downloadProto = kProtoWebsocket;
        } else if (url.startWith('stream://')) {
            url = url.replace('stream://', '')
            this.downloadProto = kProtoStream;
        } else {
            this.downloadProto = kProtoHttp;
        }

        this.fileInfo = new FileInfo(url);
        this.fileInfo.chunkSize = this.chunkSize;
        this.mp4HeaderProbe = { offset: 0, header: [], active: true, identified: false };
        this.canvas = canvas;
        this.callback = callback;
        this.waitHeaderLength = waitHeaderLength || this.waitHeaderLength;
        this.downloading = false;
        this.downloadSwitch = true;
        this.streamReceivedLen = 0;
        this.seekReceivedLen = 0;
        this.decoderState = decoderStateIdle;
        this.playerState = playerStatePlaying;
        this.isStream = isStream;
        this.browserSource = browserSource || null;
        this.sourceEnded = false;
        if (this.browserSource) {
            this.duration = browserSource.duration;
            this.streamBaseOffset = browserSource.startMs / 1000;
            this.displayDuration = this.formatTime(this.duration / 1000);
        }
        this.startTrackTimer();
        this.displayLoop();

        //var playCanvasContext = playCanvas.getContext("2d"); //If get 2d, webgl will be disabled.
        this.webglPlayer = new WebGLPlayer(this.canvas, {
            preserveDrawingBuffer: false
        });

        if (!this.isStream) {
            var req = {
                t: kGetFileInfoReq,
                sources: httpSources,
                prefetchedRange: prefetchedRange,
                u: url,
                p: this.downloadProto
            };
            this.downloadWorker.postMessage(req, prefetchedRange ? [prefetchedRange.data] : []);
        } else {
            this.onGetFileInfo({
                sz: -1,
                st: 200
            });
            if (this.browserSource) {
                this.consumeBrowserSource(this.browserSource);
            } else {
                this.requestStream(url);
            }
        }

        var self = this;
        // this.registerVisibilityEvent(function(visible) {
        //     if (visible) {
        //         self.resume();
        //     } else {
        //         self.pause();
        //     }
        // });

        this.buffering = true;
        this.showLoading();
    } while (false);

    return ret;
};

Player.prototype.pauseStream = function () {
    if (this.playerState != playerStatePlaying) {
        var ret = {
            e: -1,
            m: "Not playing"
        };
        return ret;
    }

    this.streamPauseParam = {
        url: this.fileInfo.url,
        canvas: this.canvas,
        callback: this.callback,
        waitHeaderLength: this.waitHeaderLength
    }

    this.logger.logInfo("Stop in stream pause.");
    this.stop();

    var ret = {
        e: 0,
        m: "Success"
    };

    return ret;
}

Player.prototype.pause = function () {
    if (this.isStream) {
        return this.pauseStream();
    }

    this.logger.logInfo("Pause.");

    if (this.playerState != playerStatePlaying) {
        var ret = {
            e: -1,
            m: "Not playing"
        };
        return ret;
    }

    //Pause video rendering and audio flushing.
    this.playerState = playerStatePausing;

    //Pause audio context.
    if (this.pcmPlayer) {
        this.pcmPlayer.pause();
    }

    //Pause decoding.
    this.pauseDecoding();

    //Stop track timer.
    this.stopTrackTimer();

    // Manual pause must not keep fetching and discarding the same range.
    this.stopDownloadTimer();
    var ret = {
        e: 0,
        m: "Success"
    };

    return ret;
};

Player.prototype.resumeStream = function () {
    if (this.playerState != playerStateIdle || !this.streamPauseParam) {
        var ret = {
            e: -1,
            m: "Not pausing"
        };
        return ret;
    }

    this.logger.logInfo("Play in stream resume.");
    this.play(this.streamPauseParam.url,
              this.streamPauseParam.canvas,
              this.streamPauseParam.callback,
              this.streamPauseParam.waitHeaderLength,
              true);
    this.streamPauseParam = null;

    var ret = {
        e: 0,
        m: "Success"
    };

    return ret;
}

Player.prototype.resume = function (fromSeek) {
    if (this.isStream) {
        return this.resumeStream();
    }

    this.logger.logInfo("Resume.");

    if (this.playerState != playerStatePausing) {
        var ret = {
            e: -1,
            m: "Not pausing"
        };
        return ret;
    }

    if (!fromSeek) {
        //Resume audio context.
        this.pcmPlayer.resume();
    }

    //If there's a flying video renderer op, interrupt it.
    if (this.videoRendererTimer != null) {
        clearTimeout(this.videoRendererTimer);
        this.videoRendererTimer = null;
    }

    //Restart video rendering and audio flushing.
    this.playerState = playerStatePlaying;

    //Restart decoding.
    this.startDecoding();
    if (!this.downloadTimer && this.fileInfo && this.decoderState === decoderStateReady) {
        this.startDownloadTimer();
    }

    //Restart track timer.
    if (!this.seeking) {
        this.startTrackTimer();
    }

    var ret = {
        e: 0,
        m: "Success"
    };
    return ret;
};

Player.prototype.stop = function () {
    var ret = { e: 0, m: "Success" };
    this.logger.logInfo("Stop.");
    if (this.browserSource) {
        this.browserSource.cancel();
        this.browserSource = null;
    }
    clearInterval(this.sourceWatchdog);
    this.sourceWatchdog = null;
    clearTimeout(this.bufferingWatchdog);
    this.bufferingWatchdog = null;
    if (this.displayAnimationFrame !== null) {
        cancelAnimationFrame(this.displayAnimationFrame);
        this.displayAnimationFrame = null;
    }
    if (this.videoRendererTimer != null) {
        clearTimeout(this.videoRendererTimer);
        this.videoRendererTimer = null;
        this.logger.logInfo("Video renderer timer stopped.");
    }

    this.stopDownloadTimer();
    this.stopTrackTimer();
    this.hideLoading();

    this.fileInfo           = null;
    this.canvas             = null;
    this.webglPlayer        = null;
    this.callback           = null;
    this.duration           = 0;
    this.pixFmt             = 0;
    this.videoWidth         = 0;
    this.videoHeight        = 0;
    this.yLength            = 0;
    this.uvLength           = 0;
    this.beginTimeOffset    = 0;
    this.streamBaseOffset   = 0;
    this.decoderState       = decoderStateIdle;
    this.playerState        = playerStateIdle;
    this.decoding           = false;
    this.frameBuffer        = [];
    this.buffering          = false;
    this.streamReceivedLen  = 0;
    this.firstAudioFrame    = true;
    this.firstVideoFrame    = true;
    this.urgent             = false;
    this.seekReceivedLen    = 0;
    this.downloadSeqNo      = 0;
    this.downloading        = false;
    this.downloadSwitch     = true;
    this.finishNotified     = false;
    this.sourceEnded        = false;
    this.audioBlocked       = false;

    if (this.pcmPlayer) {
        this.pcmPlayer.destroy();
        this.pcmPlayer = null;
        this.logger.logInfo("Pcm player released.");
    }

    if (this.timeTrack) {
        this.timeTrack.value = 0;
    }
    if (this.timeLabel) {
        this.timeLabel.innerHTML = this.formatTime(0) + "/" + this.displayDuration;
    }

    if (this.fetchController) {
        this.fetchController.abort();
        this.fetchController = null;
    }
    if (this.infoRequest) {
        this.infoRequest.onreadystatechange = null;
        this.infoRequest.abort();
        this.infoRequest = null;
    }

    this.resetWorkers();

    return ret;
};

// Consume browser-remuxed FLV with bounded lookahead and decoder backpressure.
// No URL request, /info call, cache file or server FFmpeg process is involved.
Player.prototype.consumeBrowserSource = async function (source) {
    var self = this;
    var active = () => self.browserSource === source && !source.signal.aborted;
    var fail = (message) => {
        if (!active()) return;
        var callback = self.callback;
        self.stop();
        if (callback) callback({ error: -1, status: 0, message: message });
    };
    this.lastRenderedAt = Date.now();
    this.sourceWatchdog = setInterval(() => {
        if (active() && Date.now() - self.lastRenderedAt > 30000) {
            fail('源流直连播放超时，请重试或使用兼容播放');
        }
    }, 1000);
    try {
        var loadedUntil = source.startMs / 1000;
        for await (const chunk of source.chunks) {
            while (active() && (!self.downloadSwitch || (self.decoderState === decoderStateReady &&
                loadedUntil > source.startMs / 1000 + (self.pcmPlayer ? self.pcmPlayer.getTimestamp() + self.beginTimeOffset : 0) + 12) ||
                (self.decoderState !== decoderStateReady && self.streamReceivedLen >= 4 * 1024 * 1024))) {
                await new Promise(resolve => setTimeout(resolve, 25));
            }
            if (!active()) return;
            for (var offset = 0; offset < chunk.data.byteLength; offset += defaultChunkSize) {
                while (active() && !self.downloadSwitch) await new Promise(resolve => setTimeout(resolve, 25));
                if (!active()) return;
                var data = chunk.data.slice(offset, offset + defaultChunkSize).buffer;
                var length = data.byteLength;
                self.decodeWorker.postMessage({ t: kFeedDataReq, d: data }, [data]);
                self.fileInfo.offset += length;
                self.streamReceivedLen += length;
                // Yield so decoder queue and high-water events can catch up.
                await new Promise(resolve => setTimeout(resolve, 0));
            }
            if (!active()) return;
            if (self.decoderState === decoderStateIdle && self.streamReceivedLen >= self.waitHeaderLength) {
                self.decoderState = decoderStateInitializing;
                self.decodeWorker.postMessage({ t: kOpenDecoderReq });
            }
            loadedUntil = chunk.endTime;
        }
        if (active()) {
            self.sourceEnded = true;
            if (self.buffering && self.frameBuffer.length) self.stopBuffering();
            if (self.decoderState === decoderStateIdle) {
                self.decoderState = decoderStateInitializing;
                self.decodeWorker.postMessage({ t: kOpenDecoderReq });
            }
        }
    } catch (error) {
        fail(error.message || '源流直连失败');
    }
};

Player.prototype.destroy = function () {
    if (this.destroyed) return;
    this.destroyed = true;
    this.finishCallback = null;
    this.timeCallback = null;
    this.stop();
    if (this.downloadWorker) this.downloadWorker.terminate();
    if (this.decodeWorker) this.decodeWorker.terminate();
    this.downloadWorker = null;
    this.decodeWorker = null;
    if (this.timeTrack) {
        this.timeTrack.oninput = null;
        this.timeTrack.onchange = null;
    }
    this.timeTrack = null;
    this.timeLabel = null;
    this.loadingDiv = null;
    this.streamPauseParam = null;
};

Player.prototype.notifyFinish = function () {
    if (this.finishNotified) {
        return;
    }
    this.finishNotified = true;
    this.stop();
    if (this.finishCallback){
        this.finishCallback();
    }
};

Player.prototype.seekTo = function(ms) {
    if (this.isStream) {
        return;
    }

    // Pause playing.
    this.pause();

    // Stop download.
    this.stopDownloadTimer();

    // Clear frame buffer.
    this.frameBuffer.length = 0;

    // Request decoder to seek.
    if (this.decoderState === decoderStateFinished) this.decoderState = decoderStateReady;
    this.decodeWorker.postMessage({
        t: kSeekToReq,
        ms: ms
    });

    // Reset begin time offset.
    this.beginTimeOffset = ms / 1000;
    this.logger.logInfo("seekTo beginTimeOffset " + this.beginTimeOffset);

    this.seeking = true;
    this.justSeeked = true;
    this.urgent = true;
    this.seekReceivedLen = 0;
    this.startBuffering();
};

Player.prototype.fullscreen = function () {
    if (this.webglPlayer) {
        this.webglPlayer.fullscreen();
    }
};

Player.prototype.getState = function () {
    return this.playerState;
};

Player.prototype.setTrack = function (timeTrack, timeLabel) {
    this.timeTrack = timeTrack;
    this.timeLabel = timeLabel;

    if (this.timeTrack) {
        var self = this;
        this.timeTrack.oninput = function () {
            if (!self.seeking) {
                self.seekTo(self.timeTrack.value);
            }
        }
        this.timeTrack.onchange = function () {
            if (!self.seeking) {
                self.seekTo(self.timeTrack.value);
            }
        }
    }
};

Player.prototype.setFinishCallback = function (callback) {
    this.finishCallback = callback;
};

Player.prototype.setTimeCallback = function (callback) {
    this.timeCallback = callback;
};

Player.prototype.setAudioBlockedCallback = function (callback) {
    this.audioBlockedCallback = callback;
};

Player.prototype.resumeBlockedAudio = function () {
    if (!this.audioBlocked || !this.pcmPlayer) return Promise.resolve(false);
    var self = this;
    return this.pcmPlayer.audioCtx.resume().then(function () {
        if (self.destroyed || !self.audioBlocked || self.pcmPlayer.audioCtx.state !== 'running') return false;
        self.audioBlocked = false;
        if (self.audioBlockedCallback) self.audioBlockedCallback(false);
        if (self.decoderState === decoderStateReady) {
            self.startDecoding();
            if (!self.downloadTimer) self.startDownloadTimer();
        }
        return true;
    });
};

Player.prototype.onGetFileInfo = function (info) {
    if (this.playerState == playerStateIdle) {
        return;
    }

    this.logger.logInfo("Got file size rsp:" + info.st + " size:" + info.sz + " byte.");
    if (info.st == 200) {
        this.fileInfo.size = Number(info.sz);
        this.logger.logInfo("Initializing decoder.");
        var req = {
            t: kInitDecoderReq,
            s: this.fileInfo.size,
            c: this.fileInfo.chunkSize,
            live: this.isStream && !this.browserSource,
            pt: this.browserSource ? this.browserSource.probeTime : null
        };
        this.decodeWorker.postMessage(req);
    } else {
        this.reportPlayError(-1, info.st, info.message || '读取视频信息失败（HTTP ' + info.st + '）');
    }
};

Player.prototype.onFileDataStream = function(data, start, end, seq, newSize){
    console.log("Got data bytes=" + start + "-" + end + "." + "newSize:" + newSize);
    this.downloading = false;
    var self = this;

    console.log('data', data, data.byteLength);
    if (newSize > 0) {
        this.fileInfo.size = Number(newSize);
    }

    if (data.byteLength <= 0){
        self.logger.logError("Reach file end.");
        this.decoderState = decoderStateFinished;
        self.stopDownloadTimer();
        return;
    }

    if (this.playerState == playerStateIdle) {
        return;
    }

    if (seq != this.downloadSeqNo) {
        return;  // Old data.
    }

    if (this.playerState == playerStatePausing) {
        if (this.seeking) {
            this.seekReceivedLen += data.byteLength;
            let left = this.fileInfo.size - this.fileInfo.offset;
            let seekWaitLen = Math.min(left, this.seekWaitLen);
            if (this.seekReceivedLen >= seekWaitLen) {
                this.logger.logInfo("Resume in seek now");
                setTimeout(() => {
                    this.resume(true);
                }, 0);
            }
        } else {
            return;
        }
    }

    var len = data.byteLength;
    this.fileInfo.offset += len;

    var objData = {
        t: kFeedDataReq,
        d: data
    };
    console.log('send to decode', objData);
    this.decodeWorker.postMessage(objData, [objData.d]);

    console.log('this.decoderState', this.decoderState);
    if (this.decoderState == decoderStateIdle) {
        this.onStreamDataUnderDecoderIdle(len);
    }
    
}

Player.prototype.onFileData = function (data, start, end, seq) {
    console.log("Got data bytes=" + start + "-" + end + ".");

    if (this.playerState == playerStateIdle) {
        return;
    }

    if (seq != this.downloadSeqNo) {
        return;  // Old data.
    }
    this.downloading = false;

    if (this.playerState == playerStatePausing) {
        if (this.seeking) {
            this.seekReceivedLen += data.byteLength;
            let left = this.fileInfo.size - this.fileInfo.offset;
            let seekWaitLen = Math.min(left, this.seekWaitLen);
            if (this.seekReceivedLen >= seekWaitLen) {
                this.logger.logInfo("Resume in seek now");
                setTimeout(() => {
                    this.resume(true);
                }, 0);
            }
        } else {
            return;
        }
    }

    // Inspect bytes before transferring their ArrayBuffer to the decoder worker.
    if (!this.isStream && this.decoderState === decoderStateIdle && !this.inspectMp4Header(data, start)) return;
    var len = end - start + 1;
    this.fileInfo.offset += len;

    var objData = {
        t: kFeedDataReq,
        d: data,
        eof: !this.isStream && end + 1 === this.fileInfo.size
    };
    console.log('send to decode', objData);
    this.decodeWorker.postMessage(objData, [objData.d]);

    console.log('this.decoderState', this.decoderState);
    switch (this.decoderState) {
        case decoderStateIdle:
            this.onFileDataUnderDecoderIdle();
            break;
        case decoderStateInitializing:
            this.onFileDataUnderDecoderInitializing();
            break;
        case decoderStateReady:
            this.onFileDataUnderDecoderReady();
            break;
    }

    if (this.urgent) {
        setTimeout(() => {
            this.downloadOneChunk();
        }, 0);
    }
};

// Track top-level MP4 boxes incrementally; retain at most 16 bytes, not the file.
// Large sample tables can make moov exceed the default 512 KiB startup buffer.
Player.prototype.inspectMp4Header = function (data, start) {
    var probe = this.mp4HeaderProbe;
    if (!probe || !probe.active) return true;
    var bytes = new Uint8Array(data), end = start + bytes.length;
    while (probe.offset < end) {
        var cursor = probe.offset + probe.header.length;
        if (cursor < start) { probe.active = false; return true; }
        var required = 8;
        if (probe.header.length >= 8 && probe.header[0] === 0 && probe.header[1] === 0 && probe.header[2] === 0 && probe.header[3] === 1) required = 16;
        while (cursor < end && probe.header.length < required) probe.header.push(bytes[cursor++ - start]);
        if (probe.header.length < required) {
            if (probe.identified) this.waitHeaderLength = Math.max(this.waitHeaderLength, end + 16);
            return true;
        }
        var header = new DataView(new Uint8Array(probe.header).buffer);
        var size = header.getUint32(0), type = String.fromCharCode.apply(null, probe.header.slice(4, 8));
        if (!probe.identified) {
            if (type !== 'ftyp') { probe.active = false; return true; }
            probe.identified = true;
        }
        if (size === 1) {
            if (probe.header.length < 16) continue;
            size = header.getUint32(8) * 4294967296 + header.getUint32(12);
        }
        if (!Number.isSafeInteger(size) || size < required || probe.offset + size > this.fileInfo.size) {
            probe.active = false;
            this.reportPlayError(8, 0, 'MP4 文件头不完整或长度无效，请重新获取视频');
            return false;
        }
        var boxEnd = probe.offset + size;
        if (type === 'moov') {
            probe.active = false;
            if (boxEnd > 16 * 1024 * 1024) {
                this.reportPlayError(8, 0, 'MP4 视频头超过 16 MiB，当前播放器暂不支持');
                return false;
            }
            this.waitHeaderLength = Math.max(this.waitHeaderLength, boxEnd);
            return true;
        }
        // Do not download an entire mdat in search of a tail index.
        if (type === 'mdat') { probe.active = false; return true; }
        probe.offset = boxEnd; probe.header = [];
    }
    if (probe.active && probe.identified) {
        if (probe.offset + 16 > 16 * 1024 * 1024) {
            this.reportPlayError(8, 0, 'MP4 视频头偏移超过 16 MiB，当前播放器暂不支持');
            return false;
        }
        this.waitHeaderLength = Math.max(this.waitHeaderLength, probe.offset + 16);
    }
    return true;
};

Player.prototype.onFileDataUnderDecoderIdle = function () {
    console.log('this.waitHeaderLength', this.waitHeaderLength);
    console.log('this.fileInfo.offset', this.fileInfo.offset);
    console.log('this.fileInfo.size', this.fileInfo.size);
    if (this.fileInfo.offset >= this.waitHeaderLength || (!this.isStream && this.fileInfo.offset == this.fileInfo.size)) {
        this.logger.logInfo("Opening decoder.");
        console.log("Opening decoder.");
        this.decoderState = decoderStateInitializing;
        var req = {
            t: kOpenDecoderReq
        };
        this.decodeWorker.postMessage(req);
    }

    this.downloadOneChunk();
};

Player.prototype.onFileDataUnderDecoderInitializing = function () {
    this.downloadOneChunk();
};

Player.prototype.onFileDataUnderDecoderReady = function () {
    // Refill encoded data immediately while below the bounded lookahead;
    // waiting for the periodic timer can leave a variable-bitrate clip dry.
    if (this.buffering || this.maxAheadSeconds > 0) this.downloadOneChunk();
};

Player.prototype.onInitDecoder = function (objData) {
    if (this.playerState == playerStateIdle) {
        return;
    }

    this.logger.logInfo("Init decoder response " + objData.e + ".");
    if (objData.e == 0) {
        if (!this.isStream) {
            this.downloadOneChunk();
        }
    } else {
        this.reportPlayError(objData.e, 0, 'WASM 解码器初始化失败（错误码 ' + objData.e + '）');
    }
};

Player.prototype.onOpenDecoder = function (objData) {
    if (this.playerState == playerStateIdle) {
        return;
    }

    this.logger.logInfo("Open decoder response " + objData.e + ".");
    if (objData.e == 0) {
        this.onVideoParam(objData.v);
        this.onAudioParam(objData.a);
        this.decoderState = decoderStateReady;
        this.logger.logInfo("Decoder ready now.");
        if (this.pcmPlayer && this.pcmPlayer.audioCtx.state === 'suspended') {
            this.audioBlocked = true;
            this.stopDownloadTimer();
            if (this.audioBlockedCallback) this.audioBlockedCallback(true);
            return;
        }
        this.startDecoding();
    } else {
        if (this.browserSource && this.sourceEnded) {
            this.reportPlayError(objData.e, 0, '源流格式无法解码，请使用兼容播放');
            return;
        }
        if (this.isStream) {
            this.decoderState = decoderStateIdle;
            this.streamReceivedLen = this.fileInfo ? this.fileInfo.offset : this.streamReceivedLen;
            this.waitHeaderLength = Math.min(
                this.streamReceivedLen + this.fileInfo.chunkSize,
                4 * 1024 * 1024
            );
            this.logger.logInfo("Open decoder failed in stream mode, retry with waitHeaderLength " + this.waitHeaderLength + ".");
            return;
        }
        this.reportPlayError(objData.e, 0, 'WASM 打开视频失败（错误码 ' + objData.e + '）');
    }
};

Player.prototype.onVideoParam = function (v) {
    if (this.playerState == playerStateIdle) {
        return;
    }

    this.logger.logInfo("Video param duation:" + v.d + " pixFmt:" + v.p + " width:" + v.w + " height:" + v.h + ".");
    if (this.downloadProto == kProtoStream){
        // ignore
    } else {
        this.duration = v.d;
    }
    this.pixFmt = v.p;
    //this.canvas.width = v.w;
    //this.canvas.height = v.h;
    this.videoWidth = v.w;
    this.videoHeight = v.h;
    this.yLength = this.videoWidth * this.videoHeight;
    this.uvLength = (this.videoWidth / 2) * (this.videoHeight / 2);

    /*
    //var playCanvasContext = playCanvas.getContext("2d"); //If get 2d, webgl will be disabled.
    this.webglPlayer = new WebGLPlayer(this.canvas, {
        preserveDrawingBuffer: false
    });
    */

    if (this.timeTrack) {
        this.timeTrack.min = 0;
        this.timeTrack.max = this.duration;
        this.timeTrack.value = this.browserSource ? this.streamBaseOffset * 1000 : 0;
        this.displayDuration = this.formatTime(this.duration / 1000);
    }

    if (this.downloadProto == kProtoStream){
        // ignore
    } else {
        var byteRate = 1000 * this.fileInfo.size / this.duration;
        var targetSpeed = downloadSpeedByteRateCoef * byteRate;
        var chunkPerSecond = targetSpeed / this.fileInfo.chunkSize;
        this.chunkInterval = 1000 / chunkPerSecond;
        this.logger.logInfo("Byte rate:" + byteRate + " target speed:" + targetSpeed + " chunk interval:" + this.chunkInterval + ".");
        this.seekWaitLen = byteRate * maxBufferTimeLength * 2;
        this.logger.logInfo("Seek wait len " + this.seekWaitLen);
    }

    if (!this.isStream) {
        this.startDownloadTimer();
    }

};

Player.prototype.onAudioParam = function (a) {
    if (this.playerState == playerStateIdle) {
        return;
    }

    this.logger.logInfo("Audio param sampleFmt:" + a.f + " channels:" + a.c + " sampleRate:" + a.r + ".");

    var sampleFmt = a.f;
    var channels = a.c;
    var sampleRate = a.r;

    var encoding = "16bitInt";
    switch (sampleFmt) {
        case 0:
            encoding = "8bitInt";
            break;
        case 1:
            encoding = "16bitInt";
            break;
        case 2:
            encoding = "32bitInt";
            break;
        case 3:
            encoding = "32bitFloat";
            break;
        default:
            this.logger.logError("Unsupported audio sampleFmt " + sampleFmt + "!");
    }
    this.logger.logInfo("Audio encoding " + encoding + ".");

    this.pcmPlayer = new PCMPlayer({
        encoding: encoding,
        channels: channels,
        sampleRate: sampleRate,
        flushingTime: 5000
    });

    this.audioEncoding      = encoding;
    this.audioChannels      = channels;
    this.audioSampleRate    = sampleRate;
    if (this.browserSource && this.buffering) this.pcmPlayer.pause();
};

Player.prototype.restartAudio = function () {
    if (this.pcmPlayer) {
        this.pcmPlayer.destroy();
        this.pcmPlayer = null;
    }

    this.pcmPlayer = new PCMPlayer({
        encoding: this.audioEncoding,
        channels: this.audioChannels,
        sampleRate: this.audioSampleRate,
        flushingTime: 5000
    });
};

Player.prototype.bufferFrame = function (frame) {
    // If not decoding, it may be frame before seeking, should be discarded.
    if (!this.decoding) {
        return;
    }
    this.frameBuffer.push(frame);
    if (this.browserSource && this.sourceEnded && this.buffering) this.stopBuffering();
    //this.logger.logInfo("bufferFrame " + frame.s + ", seq " + frame.q);
    // Live sources may never build a full second of queued frames on slower
    // decoders. Resume after a short cushion instead of repeatedly stalling.
    var resumeBufferTime = this.isStream && !this.browserSource ? 0.25 : maxBufferTimeLength;
    if (this.getBufferTimerLength() >= resumeBufferTime || this.decoderState == decoderStateFinished) {
        if (this.decoding) {
            //this.logger.logInfo("Frame buffer time length >= " + maxBufferTimeLength + ", pause decoding.");
            this.pauseDecoding();
        }
        if (this.buffering) {
            this.stopBuffering();
        }
    }
}

Player.prototype.displayAudioFrame = function (frame) {
    if (this.playerState != playerStatePlaying) {
        return false;
    }

    if (this.seeking) {
        this.restartAudio();
        this.startTrackTimer();
        this.hideLoading();
        this.seeking = false;
        this.urgent = false;
    }

    if (this.isStream && this.firstAudioFrame) {
        this.firstAudioFrame = false;
        this.beginTimeOffset = frame.s - (this.browserSource
            ? Math.max(this.pcmPlayer.startTime, this.pcmPlayer.getTimestamp()) : 0);
        this.logger.logInfo(
            "stream sync first audio frame.s=" + frame.s +
            " streamBaseOffset=" + this.streamBaseOffset +
            " beginTimeOffset=" + this.beginTimeOffset
        );
    }

    this.pcmPlayer.play(new Uint8Array(frame.d));
    return true;
};

Player.prototype.onAudioFrame = function (frame) {
    this.bufferFrame(frame);
};

Player.prototype.onDecodeFinished = function (objData) {
    this.pauseDecoding();
    this.decoderState   = decoderStateFinished;
    if (this.buffering) this.stopBuffering();
};

Player.prototype.getBufferTimerLength = function() {
    if (!this.frameBuffer || this.frameBuffer.length == 0) {
        return 0;
    }

    let oldest = this.frameBuffer[0];
    let newest = this.frameBuffer[this.frameBuffer.length - 1];
    return newest.s - oldest.s;
};

Player.prototype.onVideoFrame = function (frame) {
    this.bufferFrame(frame);
};

Player.prototype.displayVideoFrame = function (frame, deferRender) {
    if (this.playerState != playerStatePlaying) {
        return false;
    }

    if (this.seeking) {
        this.restartAudio();
        this.startTrackTimer();
        this.hideLoading();
        this.seeking = false;
        this.urgent = false;
    }

    var audioCurTs = this.pcmPlayer.getTimestamp();
    var audioTimestamp = audioCurTs + this.beginTimeOffset;
    var delay = frame.s - audioTimestamp;

    if (this.isStream && this.firstVideoFrame) {
        this.firstVideoFrame = false;
        this.logger.logInfo(
            "stream sync first video frame.s=" + frame.s +
            " audioCurTs=" + audioCurTs +
            " beginTimeOffset=" + this.beginTimeOffset +
            " audioTimestamp=" + audioTimestamp +
            " delay=" + delay
        );
    }

    if (this.isStream && (delay < -1 || delay > 1)) {
        this.logger.logInfo(
            "stream sync drift frame.s=" + frame.s +
            " audioCurTs=" + audioCurTs +
            " beginTimeOffset=" + this.beginTimeOffset +
            " audioTimestamp=" + audioTimestamp +
            " delay=" + delay
        );
    }

    if (delay <= 0 || (audioTimestamp <= 0 && frame.s <= 0.05)) {
        if (!deferRender) this.renderVideoFrame(new Uint8Array(frame.d));
        return true;
    }
    return false;
};

Player.prototype.onSeekToRsp = function (ret) {
    if (ret != 0) {
        this.justSeeked = false;
        this.seeking = false;
    }
};

Player.prototype.onRequestData = function (offset, available) {
    if (this.justSeeked) {
        this.logger.logInfo("Request data " + offset + ", available " + available);
        if (offset == -1) {
            // Hit in buffer.
            let left = this.fileInfo.size - this.fileInfo.offset;
            if (available >= left) {
                this.logger.logInfo("No need to wait");
                this.resume();
            } else {
                this.startDownloadTimer();
            }
        } else {
            if (offset >= 0 && offset < this.fileInfo.size) {
                this.fileInfo.offset = offset;
            }
            this.startDownloadTimer();
        }

        //this.restartAudio();
        this.justSeeked = false;
    } else if (!this.isStream && this.playerState === playerStatePlaying && offset === -1 &&
               this.fileInfo && this.fileInfo.offset < this.fileInfo.size) {
        // The decoder exhausted its input before the periodic timer fired.
        this.downloadOneChunk();
    }
};

Player.prototype.displayLoop = function() {
    if (this.playerState !== playerStateIdle) {
        this.displayAnimationFrame = requestAnimationFrame(this.displayLoop.bind(this));
    }
    if (this.playerState != playerStatePlaying) {
        return;
    }

    if (this.frameBuffer.length == 0) {
        return;
    }

    if (this.buffering) {
        return;
    }

    // Audio packets also occupied the old two-frame quota. At 30 Hz, 48 kHz
    // AAC + 30 fps video needs ~77 packets/s, exceeding that quota of 60.
    // Drain due packets and render only the newest due video frame per refresh.
    var pendingVideo = null;
    var frameBudget = 128;
    for (var i = 0; i < frameBudget; ++i) {
        var frame = this.frameBuffer[0];
        var consumed = false;
        // console.log('frame', frame);
        switch (frame.t) {
            case kAudioFrame:
                if (this.displayAudioFrame(frame)) {
                    this.frameBuffer.shift();
                    consumed = true;
                }
                break;
            case kVideoFrame:
                if (this.displayVideoFrame(frame, true)) {
                    this.frameBuffer.shift();
                    consumed = true;
                    pendingVideo = frame;
                }
                break;
            default:
                return;
        }

        if (!consumed || this.frameBuffer.length == 0) {
            break;
        }
    }
    if (pendingVideo) this.renderVideoFrame(new Uint8Array(pendingVideo.d));

    if (this.getBufferTimerLength() < maxBufferTimeLength / 2) {
        if (!this.decoding) {
            //this.logger.logInfo("Buffer time length < " + maxBufferTimeLength / 2 + ", restart decoding.");
            this.startDecoding();
        }
    }

    if (this.frameBuffer.length == 0) {
        if (this.decoderState == decoderStateFinished) {
            this.reportPlayError(1, 0, "Finished");
            this.notifyFinish();
        } else {
            this.startBuffering();
        }
    }
};

Player.prototype.startBuffering = function () {
    if (this.browserSource && this.sourceEnded) {
        // Let the already scheduled audio finish and the media clock reach EOF.
        // Suspending here would prevent the completion/next-episode callback.
        this.buffering = false;
        this.hideLoading();
        return;
    }
    this.buffering = true;
    this.showLoading();
    if (this.isStream) {
        if (this.browserSource && this.pcmPlayer) this.pcmPlayer.pause();
        return;
    }
    // Buffering still needs the decoder and downloader to accept new data.
    if (this.pcmPlayer) this.pcmPlayer.pause();
    this.stopTrackTimer();
    clearTimeout(this.bufferingWatchdog);
    var self = this;
    this.bufferingWatchdog = setTimeout(function () {
        if (self.buffering && self.playerState === playerStatePlaying) {
            self.reportPlayError(-1, 0, '视频缓冲超时，请重试');
        }
    }, 30000);
}

Player.prototype.stopBuffering = function () {
    clearTimeout(this.bufferingWatchdog);
    this.bufferingWatchdog = null;
    this.buffering = false;
    this.hideLoading();
    if (this.isStream) {
        if (this.browserSource && this.pcmPlayer) this.pcmPlayer.resume();
        return;
    }
    if (this.pcmPlayer) this.pcmPlayer.resume();
    if (this.playerState === playerStatePlaying && !this.trackTimer) this.startTrackTimer();
}

Player.prototype.renderVideoFrame = function (data) {
    this.lastRenderedAt = Date.now();
    this.webglPlayer.renderFrame(data, this.videoWidth, this.videoHeight, this.yLength, this.uvLength);
};

Player.prototype.downloadOneChunk = function () {
    if (!this.downloadSwitch){
        // console.log('disable download, return');
        return;
    }

    if (this.downloading) {
        // console.log('downloading, return');
        return;
    }

    if (this.downloadProto != kProtoStream && this.isStream){
        // console.log('not support proto, return');
        return;
    }
    

    var start = this.fileInfo.offset;
    if (this.maxAheadSeconds > 0 && this.decoderState === decoderStateReady && !this.urgent &&
        this.duration > 0 && this.pcmPlayer) {
        var elapsed = Math.max(0, this.pcmPlayer.getTimestamp() + this.beginTimeOffset);
        var bytesPerSecond = this.fileInfo.size * 1000 / this.duration;
        var aheadLimit = this.waitHeaderLength + bytesPerSecond * (elapsed + this.maxAheadSeconds);
        // Buffering pauses the audio clock. A variable-bitrate section may
        // need more than the time-based estimate before one second of frames
        // can be decoded; keep a bounded extra window to avoid deadlock.
        if (start >= aheadLimit + (this.buffering ? 16 * 1024 * 1024 : 0)) return;
    }
    if (start >= this.fileInfo.size) {
        this.logger.logError("Reach file end.");
        this.stopDownloadTimer();
        return;
    }

    var end = this.fileInfo.offset + this.fileInfo.chunkSize - 1;
    if (end >= this.fileInfo.size) {
        end = this.fileInfo.size - 1;
    }

    var len = end - start + 1;
    if (len > this.fileInfo.chunkSize) {
        console.log("Error: request len:" + len + " > chunkSize:" + this.fileInfo.chunkSize);
        return;
    }

    var req = {
        t: kDownloadFileReq,
        u: this.fileInfo.url,
        s: start,
        e: end,
        q: this.downloadSeqNo,
        p: this.downloadProto
    };
    console.log('req', req);
    this.downloadWorker.postMessage(req);
    this.downloading = true;
};

Player.prototype.startDownloadTimer = function () {
    if (this.downloadTimer !== null) return;
    var self = this;
    // start download timer
    // Decoder initialization can start this timer while a Range request is
    // already in flight. Changing its sequence here drops that valid reply.
    this.downloadTimer = setInterval(function () {
        self.downloadOneChunk();
    }, this.maxAheadSeconds > 0 ? Math.min(this.chunkInterval, 500) : this.chunkInterval);
    this.logger.logInfo("startDownloadTimer." + self.downloadTimer + "," + self.downloadSeqNo);
};

Player.prototype.stopDownloadTimer = function () {
    console.log('stopDownloadTimer');
    if (this.downloadTimer != null) {
        clearInterval(this.downloadTimer);
        this.downloadTimer = null;
    }
    this.downloadSeqNo++;
    this.downloading = false;
};

Player.prototype.startTrackTimer = function () {
    var self = this;
    this.trackTimer = setInterval(function () {
        self.updateTrackTime();
    }, this.trackTimerInterval);
};

Player.prototype.stopTrackTimer = function () {
    if (this.trackTimer != null) {
        clearInterval(this.trackTimer);
        this.trackTimer = null;
    }
};

Player.prototype.updateTrackTime = function () {
    if (this.playerState == playerStatePlaying && this.pcmPlayer) {
        var currentPlayTime = this.pcmPlayer.getTimestamp() + this.beginTimeOffset;
        if (this.isStream) {
            currentPlayTime = this.pcmPlayer.getTimestamp() + this.streamBaseOffset;
            if (this.browserSource) currentPlayTime += this.beginTimeOffset;
        }
        // Live HTTP-FLV metadata may contain a tiny placeholder duration.
        // Only browser-backed finite streams should stop at that timestamp.
        var maxPlayTime = this.isStream && !this.browserSource ? 0 : this.duration > 0 ? this.duration / 1000 : 0;
        if (maxPlayTime > 0 && currentPlayTime > maxPlayTime) {
            currentPlayTime = maxPlayTime;
        }
        if (this.timeCallback){
            this.timeCallback(currentPlayTime);
        }
        if (this.isStream && maxPlayTime > 0 && currentPlayTime >= maxPlayTime) {
            this.notifyFinish();
            return;
        }
        if (!this.isStream && maxPlayTime > 0 && currentPlayTime * 1000 >= this.duration && this.decoderState == decoderStateFinished){
            this.notifyFinish();
            return;
        }
        if (this.timeTrack) {
            this.timeTrack.value = 1000 * currentPlayTime;
        }

        if (this.timeLabel) {
            this.timeLabel.innerHTML = this.formatTime(currentPlayTime) + "/" + this.displayDuration;
        }
    }
};

Player.prototype.startDecoding = function () {
    if (this.decoderState === decoderStateFinished) return;
    // this.logger.logInfo("startDecoding.");
    var req = {
        t: kStartDecodingReq,
        i: this.urgent ? 0 : this.decodeInterval,
    };
    this.decodeWorker.postMessage(req);
    this.decoding = true;
    // this.downloadSwitch = true;
};

Player.prototype.pauseDecoding = function () {
    // this.logger.logInfo("pauseDecoding.");
    var req = {
        t: kPauseDecodingReq
    };
    this.decodeWorker.postMessage(req);
    this.decoding = false;
    // this.downloadSwitch = false;
};

Player.prototype.formatTime = function (s) {
    var h = Math.floor(s / 3600) < 10 ? '0' + Math.floor(s / 3600) : Math.floor(s / 3600);
    var m = Math.floor((s / 60 % 60)) < 10 ? '0' + Math.floor((s / 60 % 60)) : Math.floor((s / 60 % 60));
    var s = Math.floor((s % 60)) < 10 ? '0' + Math.floor((s % 60)) : Math.floor((s % 60));
    return result = h + ":" + m + ":" + s;
};

Player.prototype.reportPlayError = function (error, status, message) {
    var e = {
        error: error || 0,
        status: status || 0,
        message: message
    };

    if (this.callback) {
        this.callback(e);
    }
};

Player.prototype.setLoadingDiv = function (loadingDiv) {
    this.loadingDiv = loadingDiv;
}

Player.prototype.hideLoading = function () {
    if (this.loadingDiv != null) {
        this.loadingDiv.style.display = "none";
    }
};

Player.prototype.showLoading = function () {
    if (this.loadingDiv != null) {
        this.loadingDiv.style.display = "block";
    }
};

Player.prototype.registerVisibilityEvent = function (cb) {
    var hidden = "hidden";

    // Standards:
    if (hidden in document) {
        document.addEventListener("visibilitychange", onchange);
    } else if ((hidden = "mozHidden") in document) {
        document.addEventListener("mozvisibilitychange", onchange);
    } else if ((hidden = "webkitHidden") in document) {
        document.addEventListener("webkitvisibilitychange", onchange);
    } else if ((hidden = "msHidden") in document) {
        document.addEventListener("msvisibilitychange", onchange);
    } else if ("onfocusin" in document) {
        // IE 9 and lower.
        document.onfocusin = document.onfocusout = onchange;
    } else {
        // All others.
        window.onpageshow = window.onpagehide = window.onfocus = window.onblur = onchange;
    }

    function onchange (evt) {
        var v = true;
        var h = false;
        var evtMap = {
            focus:v,
            focusin:v,
            pageshow:v,
            blur:h,
            focusout:h,
            pagehide:h
        };

        evt = evt || window.event;
        var visible = v;
        if (evt.type in evtMap) {
            visible = evtMap[evt.type];
        } else {
            visible = this[hidden] ? h : v;
        }
        cb(visible);
    }

    // set the initial state (but only if browser supports the Page Visibility API)
    if( document[hidden] !== undefined ) {
        onchange({type: document[hidden] ? "blur" : "focus"});
    }
}

Player.prototype.onStreamDataUnderDecoderIdle = function (length) {
    this.streamReceivedLen += length;
    if (this.streamReceivedLen >= this.waitHeaderLength) {
        this.logger.logInfo("Opening decoder.");
        this.decoderState = decoderStateInitializing;
        var req = {
            t: kOpenDecoderReq
        };
        this.decodeWorker.postMessage(req);
    }
};

Player.prototype.requestStream = function (url) {
    var self = this;
    if (self.downloadProto == kProtoStream){
        this.logger.logInfo("Getting file size " + url + ".");
        var size = 0;
        var duration = 0;
        var status = 0;
        var reported = false;

        var infoUrl = url;
        var queryIndex = url.indexOf('?');
        if (queryIndex >= 0) {
            infoUrl = url.slice(0, queryIndex) + '/info' + url.slice(queryIndex);
        } else {
            infoUrl = url + '/info';
        }

        var xhr = new XMLHttpRequest();
        this.infoRequest = xhr;
        xhr.open('get', infoUrl, true);
        xhr.onreadystatechange = () => {
            if (self.destroyed || self.infoRequest !== xhr || !self.fileInfo) return;
            var len = xhr.getResponseHeader("BV-Content-Length");
            var dur = xhr.getResponseHeader('BV-Duration');
            if (len) {
                size = Number(len);
            }

            if (xhr.status) {
                status = xhr.status;
            }

            if (dur){
                duration = Number(dur)
            }


            //Completed.
            if (!reported && ((size > 0 && duration > 0 && status > 0) || xhr.readyState == 4)) {
                console.log('size', size, 'status', status, 'duration', duration);
                self.duration = duration;

                // var byteRate = 1000 * 1000;
                // var byteRate = 1000 * size / self.duration;
                // var targetSpeed = downloadSpeedByteRateCoef * byteRate;
                // var chunkPerSecond = targetSpeed / defaultChunkSize;
                self.chunkInterval = 1000;
                // self.chunkInterval = 1;
                console.log('chunkInterval', self.chunkInterval);
                self.fileInfo.size = 1024 * 1024 * 1024;


                // start download timer
                self.startDownloadTimer();
                
                reported = true;
                xhr.abort();
            }
        };
        xhr.send();
    } else {
        this.fetchController = new AbortController();
        const signal = this.fetchController.signal;
    
        fetch(url, {signal}).then(async function respond(response) {
            if (!response.ok || !response.body) throw new Error('直播流请求失败（HTTP ' + response.status + '）');
            const reader = response.body.getReader();
            if (signal.aborted || self.destroyed) return reader.cancel();
            return reader.read().then(function processData({done, value}) {
                if (signal.aborted || self.destroyed) return reader.cancel();
                if (done) {
                    self.logger.logInfo("Stream done.");
                    return;
                }
    
                if (self.playerState != playerStatePlaying) {
                    return reader.cancel();
                }
    
                var dataLength = value.byteLength;
                var receivedLength = dataLength;
                var offset = 0;
                if (dataLength > self.fileInfo.chunkSize) {
                    do {
                        let len = Math.min(self.fileInfo.chunkSize, dataLength);
                        var data = value.buffer.slice(value.byteOffset + offset, value.byteOffset + offset + len);
                        dataLength -= len;
                        offset += len;
                        var objData = {
                            t: kFeedDataReq,
                            d: data
                        };
                        // console.log('objData', objData);
                        self.decodeWorker.postMessage(objData, [objData.d]);
                    } while (dataLength > 0)
                } else {
                    var objData = {
                        t: kFeedDataReq,
                        d: value.buffer.slice(value.byteOffset, value.byteOffset + value.byteLength)
                    };
                    // console.log('objData', objData);
                    self.decodeWorker.postMessage(objData, [objData.d]);
                }
    
                if (self.decoderState == decoderStateIdle) {
                    self.onStreamDataUnderDecoderIdle(receivedLength);
                }
    
                return reader.read().then(processData);
            });
        }).catch(err => {
            if (!signal.aborted && !self.destroyed) self.reportPlayError(-1, 0, err.message || '直播流读取失败');
        });
    }
    
};
