import unittest
from tunnel_mode_selection import Selection, enforce_tunnel_dr


class TunnelSelectionTest(unittest.TestCase):
    def test_guard_branches_preserve_all_original_fields(self):
        original = Selection(9, 10, 23)
        for state, types, context in ((4, {10: 1, 20: 2}, True),
                                      (5, {20: 2}, True),
                                      (5, {10: 2, 20: 2}, True),
                                      (5, {10: 1, 20: 2}, False)):
            self.assertEqual(enforce_tunnel_dr(original, state, [20], types, context), original)

    def test_first_matching_candidate_and_low_byte_type(self):
        result = enforce_tunnel_dr(Selection(9, 10, 23), 5,
                                   [999, 30, 20, 40], {10: 1, 30: 3, 20: 258, 40: 2})
        self.assertEqual(result, Selection(1, 20, 0))

    def test_no_match_does_not_invent_selection(self):
        original = Selection(9, 10, 23)
        self.assertEqual(enforce_tunnel_dr(original, 5, [20], {10: 1, 20: 3}), original)


if __name__ == '__main__':
    unittest.main()
