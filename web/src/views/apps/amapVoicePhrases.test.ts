import { expect, it } from 'vitest';
import { navigationVoicePhrase } from './amapVoicePhrases';
it('uses stable phrases for advance synthesis without promising stale distances', () => {
  expect(navigationVoicePhrase({ text: '左转', road: '长安街' }, false)).toBe('前方左转，进入长安街');
  expect(navigationVoicePhrase({ text: '左转', road: '' }, true)).toBe('请左转');
  expect(navigationVoicePhrase({ text: '到达目的地附近', road: '' }, false)).toBe('前方即将到达目的地附近');
});
