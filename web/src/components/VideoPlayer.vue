<script setup lang="ts">
import { ref, onMounted, reactive, shallowRef, onUnmounted, computed, defineProps } from 'vue';
import JSMpeg from '@cycjimmy/jsmpeg-player';

const state = reactive({
    streamWsUrl: '',
    ctlWs: null as any,
    player: null as any,
    curTime: 0,
    totalTime: -1,
})

interface VideoProps {
    type: 'bv' | 'local';
    videoConfig: any;
    onClose?: () => void;
}

const props = defineProps<VideoProps>();


function send_ctl_msg(type: string, args: any) {
    state.ctlWs.send(JSON.stringify({
        type,
        args,
    }))
}

onMounted(() => {
    console.log('props', props);

    var hostname = document.location.hostname;
    var port = document.location.port;

    state.streamWsUrl = `ws://${hostname}:${port}/api/ws`
    state.ctlWs = new WebSocket(`ws://${hostname}:${port}/api/ws/ctl`);
    const videoConfig = props.videoConfig;
    videoConfig['type'] = props.type;

    state.ctlWs.onopen = function (event: any) {
        send_ctl_msg('init', videoConfig);
    };


    state.ctlWs.onmessage = function (event: any) {
        const msg = event.data;
        if (msg == 'init_ok'){
            state.player = new JSMpeg.VideoElement('#videoWrapper', state.streamWsUrl, {}, {
                onVideoDecode: (decoder:  any, time: any) => {
                    state.curTime = time;
                }
            });
        }
        // console.log("Received from server: " + event.data);  
    };
})

const formatTooltip = (val: number) => {
    return `${state.curTime} / ${state.totalTime}`
}


onUnmounted(() => {
    state.player.destroy();
})


</script>

<template>
    <div class="videoPlayView">
        <div id="videoWrapper"></div>
        <div class="videoCtl">
            <el-row justify="center">
                <el-col :span="24">
                    <el-slider v-model="state.curTime" :format-tooltip="formatTooltip" :disabled="true" />
                </el-col>
            </el-row>
            <el-row justify="start">
                <el-col :span="4">
                    <el-button icon="Back" size="large" @click="props.onClose" circle />
                </el-col>
            </el-row>
        </div>
    </div>
</template>

<style>
#videoWrapper {
    width: 1100px;
    height: 624px;
}

.videoPlayView {
    width: 1100px;
    height: 899px;
    position: absolute;
    top: 0px;
    z-index: 99999;
    background: #fff;
}

.videoCtl {
    padding: 20px;
}
</style>
