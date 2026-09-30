import { pinyin } from 'pinyin-pro';
import phonemeMap from './amapPhonemeMap.json';
import type { AmapPhonemes } from './amapTtsCore';

const syllables = phonemeMap as Record<string, number[]>;
const chineseDigits = '零一二三四五六七八九';
const smallUnits = ['', '十', '百', '千'];
const letterNames: Record<string, string> = {
  A: '诶', B: '比', C: '西', D: '迪', E: '伊', F: '艾弗', G: '吉', H: '艾尺',
  I: '艾', J: '杰', K: '凯', L: '艾勒', M: '艾姆', N: '恩', O: '欧', P: '皮',
  Q: '丘', R: '阿尔', S: '艾丝', T: '提', U: '优', V: '维', W: '达布柳',
  X: '艾克斯', Y: '歪', Z: '兹',
};

function chineseInteger(value: number): string {
  if (value === 0) return chineseDigits[0];
  if (value >= 10000) {
    const high = Math.floor(value / 10000);
    const low = value % 10000;
    return `${chineseInteger(high)}万${low === 0 ? '' :
      `${low < 1000 ? '零' : ''}${chineseInteger(low)}`}`;
  }
  let output = '';
  let zero = false;
  for (let place = 3; place >= 0; place--) {
    const divisor = 10 ** place;
    const digit = Math.floor(value / divisor) % 10;
    if (digit === 0) {
      if (output) zero = true;
    } else {
      if (zero) output += '零';
      zero = false;
      if (!(place === 1 && digit === 1 && output === '')) output += chineseDigits[digit];
      output += smallUnits[place];
    }
  }
  return output;
}

/** Covers distances and ordinary numeric road names before the pinyin frontend. */
export function amapNormalizeNumbers(text: string): string {
  return text.replace(/\d+(?:\.\d+)?/g, raw => {
    const [integer, fraction] = raw.split('.');
    const value = Number(integer);
    if (!Number.isSafeInteger(value) || value > 99999999)
      throw new Error(`高德文本前端不支持数字 ${raw}`);
    let output = chineseInteger(value);
    if (fraction) output += `点${[...fraction].map(digit => chineseDigits[Number(digit)]).join('')}`;
    return output;
  });
}

/** Converts Chinese navigation clauses to the four tensors accepted by AMap's encoder. */
export function amapTextFrontend(text: string): AmapPhonemes[] {
  const normalized = amapNormalizeNumbers(text).replace(/[A-Za-z]/g,
    letter => letterNames[letter.toUpperCase()]);
  const clauses = normalized.split(/[，。！？；、,!?;·/\n]+/u).map(item => item.trim()).filter(Boolean);
  if (clauses.length === 0) throw new Error('高德文本前端收到空文本');
  return clauses.map(clause => {
    const characters = Array.from(clause.replace(/\s+/g, ''));
    if (!characters.every(character => /\p{Script=Han}/u.test(character)))
      throw new Error(`高德文本前端暂不支持片段 ${clause}`);
    const readings = pinyin(characters.join(''), { type: 'array', toneType: 'num' });
    if (!Array.isArray(readings) || readings.length !== characters.length)
      throw new Error(`高德文本前端无法解析片段 ${clause}`);
    const parsed = readings.map((reading, index) => {
      const match = /^([a-zü]+)([0-5])?$/iu.exec(reading);
      if (!match) throw new Error(`高德文本前端无法解析字 ${characters[index]}`);
      const syllable = match[1].toLowerCase().replace(/ü/g, 'v');
      if (!syllables[syllable]) throw new Error(`高德音素表缺少 ${syllable}`);
      return { syllable, tone: match[2] && match[2] !== '0' ? Number(match[2]) : 5 };
    });
    for (let i = 0; i < parsed.length - 1; i++) {
      if (parsed[i].tone === 3 && parsed[i + 1].tone === 3) parsed[i].tone = 2;
      if (parsed[i].syllable === 'bu' && parsed[i + 1].tone === 4) parsed[i].tone = 2;
      if (parsed[i].syllable === 'yi' && parsed[i].tone === 1)
        parsed[i].tone = parsed[i + 1].tone === 4 ? 2 : 4;
    }
    const txtTokens = [174], tone = [3], prosody = [3], ph2char = [100001];
    parsed.forEach((reading, index) => {
      const ids = syllables[reading.syllable];
      for (const id of ids) {
        txtTokens.push(id);
        tone.push(reading.tone + 3);
        prosody.push(index === parsed.length - 1 ? 7 : 3);
        ph2char.push(index + 1);
      }
    });
    txtTokens.push(174); tone.push(3); prosody.push(7); ph2char.push(100001);
    return {
      txtTokens: Int32Array.from(txtTokens), tone: Int32Array.from(tone),
      prosody: Int32Array.from(prosody), ph2char: Int32Array.from(ph2char),
    };
  });
}
