/** The upstream radio returns batches, not numbered pages. Bound duplicate retries. */
export async function freshRadioBatch<T extends { mid: string }>(
  fetchBatch: () => Promise<T[]>, known: string[],
): Promise<T[]> {
  const seen = new Set(known);
  for (let attempt = 0; attempt < 3; attempt++) {
    const batch = await fetchBatch();
    const fresh = batch.filter(song => {
      if (!song.mid || seen.has(song.mid)) return false;
      seen.add(song.mid);
      return true;
    });
    if (fresh.length) return fresh;
    if (!batch.length) return [];
  }
  return [];
}
