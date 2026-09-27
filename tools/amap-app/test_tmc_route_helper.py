import unittest
from unittest.mock import patch

from tmc_route_helper import point, summarize


class HelperTest(unittest.TestCase):
    def test_rejects_unknown_response_instead_of_fabricating_route(self):
        self.assertEqual(summarize(b'{"error":3}'),
                         {'state': 'unsupported-response', 'navigationAvailable': False})

    def test_summary_fallback_does_not_claim_geometry_was_checked(self):
        with patch('inspect_route_blocks.inspect', side_effect=ValueError('unknown field')):
            with patch('inspect_route_prefix.inspect', return_value={'groups': [[{'text': '示例道路'}]]}):
                result = summarize(b'synthetic')
        self.assertEqual(result['routes'][0]['roads'], ['示例道路'])
        self.assertIsNone(result['checks']['geometryTotal'])
        self.assertFalse(result['checks']['framing'])
        self.assertFalse(result['navigationAvailable'])

    def test_point_validation(self):
        self.assertEqual(point([116.3975, 39.9087]), ['116.397500', '39.908700'])
        for value in ([True, 1], [float('nan'), 0], [10**400, 0], [0, 100], ['1', 2]):
            with self.subTest(value=value), self.assertRaises(ValueError):
                point(value)


if __name__ == '__main__':
    unittest.main()
