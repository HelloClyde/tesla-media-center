/** Give the speech engine enough time to finish before the car reaches the turn. */
export function turnVoiceDistances(speedKmh: number | null | undefined) {
  const metersPerSecond = typeof speedKmh === 'number' && Number.isFinite(speedKmh)
    ? Math.max(0, speedKmh / 3.6) : 0;
  return {
    ahead: Math.max(250, Math.min(900, metersPerSecond * 17)),
    near: Math.max(60, Math.min(220, metersPerSecond * 6)),
  };
}
