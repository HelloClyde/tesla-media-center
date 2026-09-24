import { onBeforeUnmount, ref } from 'vue';
import { ElMessage } from 'element-plus';
import { generateSilentWav } from './audioUtils';

export function useAudioChannel() {
    const channelAudio = ref<HTMLAudioElement | null>(null);
    let source = '';
    let attempt = 0;
    let disposed = false;

    function retry() { play(false); }

    function play(manual: boolean) {
        const audio = channelAudio.value;
        if (!audio || disposed) return;
        const currentAttempt = ++attempt;
        document.removeEventListener('click', retry);
        if (!source) source = 'data:audio/wav;base64,' + generateSilentWav(60);
        audio.muted = false;
        audio.volume = 1;
        audio.loop = true;
        if (manual || audio.src !== source) {
            audio.pause();
            audio.src = source;
            audio.load();
        }
        // Keep play() within the button's user gesture, without an awaited step.
        void audio.play().then(() => {
            if (!disposed && currentAttempt === attempt && manual) {
                ElMessage.success('已重新播放通道音频');
            }
        }).catch(() => {
            if (disposed || currentAttempt !== attempt) return;
            if (manual) ElMessage.warning('音频未能启动，请再次点击“恢复声音”');
            else document.addEventListener('click', retry, { once: true });
        });
    }

    onBeforeUnmount(() => {
        disposed = true;
        attempt++;
        document.removeEventListener('click', retry);
        const audio = channelAudio.value;
        if (audio) {
            audio.pause();
            audio.removeAttribute('src');
            audio.load();
        }
    });

    return { channelAudio, startAudioChannel: () => play(false), restoreAudioChannel: () => play(true) };
}
