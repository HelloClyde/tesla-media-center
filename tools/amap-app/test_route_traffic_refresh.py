import base64
import unittest
from unittest.mock import patch

from tmc_route_helper import route_traffic


class RouteTrafficRefreshTest(unittest.TestCase):
    def setUp(self):
        self.original = {'path': [[120, 30], [120.001, 30]], 'distance': 96,
                         'trafficRuns': [{'status': 2, 'start': 0, 'end': 40,
                                          'path': [[120, 30], [120.0004, 30]]}]}
        self.fresh = {'path': [[120, 30], [120.001, 30]], 'distance': 96,
                      'trafficRuns': [{'status': 3, 'start': 40, 'end': 96,
                                       'path': [[120.0004, 30], [120.001, 30]]}]}
        self.payload = {'rawRoute': base64.b64encode(b'old').decode(), 'routeIndex': 0}

    def test_only_same_app_link_sequence_refreshes_congestion(self):
        answer = {'state': 'ready', 'routes': [self.fresh],
                  'rawRoute': base64.b64encode(b'new').decode()}
        with patch('route_v51.decode', return_value=[self.original]), \
             patch('v51_dynamic_route.extract', return_value={'route_links_candidate': [1, 2]}), \
             patch('tmc_route_helper.probe', return_value=answer):
            result = route_traffic(self.payload)
        self.assertEqual(result['state'], 'ready')
        self.assertEqual(result['trafficRuns'], self.fresh['trafficRuns'])

        with patch('route_v51.decode', return_value=[self.original]), \
             patch('v51_dynamic_route.extract', side_effect=[
                 {'route_links_candidate': [1, 2]}, {'route_links_candidate': [1, 3]}]), \
             patch('tmc_route_helper.probe', return_value=answer):
            self.assertEqual(route_traffic(self.payload), {'state': 'unavailable'})


if __name__ == '__main__':
    unittest.main()
