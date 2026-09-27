export type PlaceLabel = {
  name: string; point: [number, number]; minZoom: number; maxZoom: number;
  kind: 'province' | 'city'; priority: number;
};
export type PlacedLabel = PlaceLabel & { x: number; y: number; width: number };

// Compare actual label rectangles, not just grid cells: labels on opposite
// sides of a cell boundary can still overlap. Stable priority avoids flicker.
export function layoutPlaceLabels(labels: PlaceLabel[], zoom: number, width: number, height: number,
  project: (point: [number, number]) => { x: number; y: number }) {
  const result: PlacedLabel[] = [], seen = new Set<string>();
  const candidates = labels.filter(l => zoom >= l.minZoom && zoom <= l.maxZoom)
    .sort((a, b) => a.priority - b.priority || a.name.localeCompare(b.name));
  for (const label of candidates) {
    const key = `${label.kind}/${label.name}/${label.point.map(n => n.toFixed(2)).join('/')}`;
    if (seen.has(key)) continue;
    seen.add(key);
    const projected = project(label.point);
    // Leave room for the start/end pin at the actual city position.
    const p = { x: projected.x, y: projected.y - (label.kind === 'city' ? 20 : 0) };
    const labelWidth = Math.min(240, Array.from(label.name).reduce((n, c) => n + (/[^\x00-\x7f]/.test(c) ? 13 : 8), 0) + 12);
    if (p.x < labelWidth / 2 || p.x > width - labelWidth / 2 || p.y < 14 || p.y > height - 14) continue;
    if (result.some(other => Math.abs(other.x - p.x) < (other.width + labelWidth) / 2 + 5 && Math.abs(other.y - p.y) < 28)) continue;
    result.push({ ...label, ...p, width: labelWidth });
    if (result.length >= 80) break;
  }
  return result;
}
