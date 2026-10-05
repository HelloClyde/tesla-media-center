import { expect, it } from 'vitest';
import { turnVoiceDistances } from './amapTurnVoice';

it('moves both turn prompts earlier as the vehicle gets faster', () => {
  expect(turnVoiceDistances(30)).toEqual({ ahead: 250, near: 60 });
  expect(turnVoiceDistances(90)).toEqual({ ahead: 425, near: 150 });
  expect(turnVoiceDistances(120).ahead).toBeCloseTo(567, 0);
  expect(turnVoiceDistances(120).near).toBe(200);
  expect(turnVoiceDistances(null)).toEqual({ ahead: 250, near: 60 });
});
