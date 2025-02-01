
export function generateSilentWav(durationSec: number = 60): string {
    const sampleRate: number = 44100;
    const numChannels: number = 1;
    const bitsPerSample: number = 16;
  
    // 类型明确的工具函数
    const writeString = (view: DataView, offset: number, str: string): void => {
      for (let i = 0; i < str.length; i++) {
        view.setUint8(offset + i, str.charCodeAt(i));
      }
    };
  
    // 计算数据块大小
    const byteRate: number = sampleRate * numChannels * bitsPerSample / 8;
    const dataSize: number = byteRate * durationSec;
  
    // 构建WAV文件头
    const header: ArrayBuffer = new ArrayBuffer(44);
    const view: DataView = new DataView(header);
  
    // RIFF标识
    writeString(view, 0, 'RIFF');
    view.setUint32(4, 36 + dataSize, true); // 文件总大小
    writeString(view, 8, 'WAVE');
    writeString(view, 12, 'fmt ');
    view.setUint32(16, 16, true); // fmt块长度
    view.setUint16(20, 1, true);   // PCM格式
    view.setUint16(22, numChannels, true);
    view.setUint32(24, sampleRate, true);
    view.setUint32(28, byteRate, true);
    view.setUint16(32, numChannels * bitsPerSample / 8, true);
    view.setUint16(34, bitsPerSample, true);
    writeString(view, 36, 'data');
    view.setUint32(40, dataSize, true);
  
    // 创建静音数据块（全零）
    const silentData: Uint8Array = new Uint8Array(dataSize);
  
    // 合并为完整WAV文件
    const wavFile: Uint8Array = new Uint8Array(header.byteLength + silentData.length);
    wavFile.set(new Uint8Array(header), 0);
    wavFile.set(silentData, header.byteLength);
  
    // 转换为base64
  //   return btoa(String.fromCharCode.apply(null, wavFile as unknown as number[]));
  
    // 安全转换为base64（分块处理）
    const CHUNK_SIZE = 0xffff; // 最大安全块大小
    let binaryString = '';
    
    for (let i = 0; i < wavFile.length; i += CHUNK_SIZE) {
      const chunk = wavFile.subarray(i, i + CHUNK_SIZE);
      binaryString += String.fromCharCode.apply(
        null, 
        Array.from(chunk) as number[] // 确保转换为普通数组
      );
    }
  
    return btoa(binaryString);
  }