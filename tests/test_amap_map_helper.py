import sys
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools/amap-app'))
import tmc_map_helper as helper
import native_signer


class MapHelperSchedulingTest(unittest.TestCase):
    def setUp(self):
        for target, name, value in [
            (helper, 'check_assets', None),
            (helper, 'load_paints', {}),
            (helper, 'version_catalog', ('https://render-prod-tile.amap.com', {k: 1 for k in [0, 1, 2, 5, 6]})),
            (native_signer, 'load_material', {}),
        ]:
            mock = patch.object(target, name, return_value=value)
            mock.start(); self.addCleanup(mock.stop)
        mock = patch.object(helper, 'unpack', return_value=b'')
        mock.start(); self.addCleanup(mock.stop)

    def test_one_tile_layers_start_together_and_total_concurrency_stays_bounded(self):
        for count, parties in [(1, 3), (4, 4)]:
            barrier = threading.Barrier(parties, timeout=2)
            lock = threading.Lock()
            active = peak = 0

            def download(_url, _params):
                nonlocal active, peak
                with lock:
                    active += 1; peak = max(peak, active)
                try:
                    barrier.wait()
                    return b''
                finally:
                    with lock:
                        active -= 1

            with patch.object(helper, 'download', side_effect=download) as request:
                result = helper.main({'level': 14, 'tiles': [[x, 2] for x in range(count)], 'format': 'bmd'})
            self.assertEqual(request.call_count, count * 3)
            self.assertEqual(peak, parties)
            self.assertTrue(all('error' not in tile and 'missingLayers' not in tile for tile in result['tiles']))
            self.assertEqual([tile['x'] for tile in result['tiles']], list(range(count)))

    def test_partial_failure_preserves_other_layers_without_caching_it_as_complete(self):
        def download(_url, params):
            if params['tileType'] == 1:
                raise RuntimeError('private upstream details')
            return b''

        with patch.object(helper, 'download', side_effect=download):
            tile = helper.main({'level': 14, 'tiles': [[1, 2]], 'format': 'bmd'})['tiles'][0]
        self.assertEqual(tile['missingLayers'], ['surfaces'])
        self.assertIn('collectionBmd', tile)
        self.assertIn('transitBmd', tile)
        self.assertNotIn('error', tile)
        self.assertNotIn('private', str(tile))

    def test_buildings_and_overview_keep_their_original_layer_selection(self):
        for level, kinds in [(15, {5}), (3, {0, 1, 2, 6})]:
            with patch.object(helper, 'download', return_value=b'') as request:
                result = helper.main({'level': level, 'tiles': [[1, 2]], 'format': 'bmd'})
            self.assertEqual({call.args[1]['tileType'] for call in request.call_args_list}, kinds)
            self.assertNotIn('error', result['tiles'][0])


if __name__ == '__main__':
    unittest.main()
