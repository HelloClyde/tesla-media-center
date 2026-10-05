import { expect, it } from 'vitest';
import { navigationVoicePhrase } from './amapVoicePhrases';
it('uses stable phrases for advance synthesis without promising stale distances', () => {
  expect(navigationVoicePhrase({ text: '左转', road: '长安街' }, false)).toBe('前方左转，进入长安街');
  expect(navigationVoicePhrase({ text: '左转', road: '长安街' }, true)).toBe('请左转');
  expect(navigationVoicePhrase({ text: '到达目的地附近', road: '' }, false)).toBe('前方即将到达目的地附近');
});
it('speaks the exit ordinal without repeating the ring road name', () => {
  const entry = { text: '进入环岛，从第2出口驶出', road: '西关环岛', maneuver: 'roundabout-enter' };
  expect(navigationVoicePhrase(entry, false)).toBe('前方进入环岛，从第2出口驶出');
  expect(navigationVoicePhrase(entry, true)).toBe('请进入环岛，从第2出口驶出');
  const exit = { text: '从第2出口驶出环岛', road: '出口路', maneuver: 'roundabout-exit' };
  expect(navigationVoicePhrase(exit, true)).toBe('请从第2出口驶出环岛');
});
