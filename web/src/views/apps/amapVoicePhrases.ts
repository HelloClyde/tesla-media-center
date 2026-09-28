export function navigationVoicePhrase(turn: { text: string; road: string }, near: boolean) {
  if (turn.text === '到达目的地附近') return near ? '目的地就在附近' : '前方即将到达目的地附近';
  return `${near ? '请' : '前方'}${turn.text}${turn.road ? '，进入' + turn.road : ''}`;
}
