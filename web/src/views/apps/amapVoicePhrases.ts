export function navigationVoicePhrase(turn: { text: string; road: string; maneuver?: string }, near: boolean) {
  if (turn.text === '到达目的地附近') return near ? '目的地就在附近' : '前方即将到达目的地附近';
  if (turn.maneuver === 'roundabout-enter' || turn.maneuver === 'roundabout-exit') {
    return `${near ? '请' : '前方'}${turn.text}`;
  }
  // At the junction the direction matters more than the next road name, and a
  // shorter phrase can finish while the car is still approaching the turn.
  return near ? `请${turn.text}` : `前方${turn.text}${turn.road ? '，进入' + turn.road : ''}`;
}
