import struct
import unittest

from model_index import decode_index, index_summary


def vint(value):
    out = bytearray()
    while value >= 128:
        out.append((value & 127) | 128)
        value >>= 7
    return bytes(out + bytes([value]))


def f(number, value):
    if isinstance(value, int):
        return vint(number * 8) + vint(value)
    if isinstance(value, float):
        return vint(number * 8 + 5) + struct.pack('<f', value)
    if isinstance(value, str):
        value = value.encode()
    return vint(number * 8 + 2) + vint(len(value)) + value


IDENTITY = 0xfedcba9876543210


def fixture(model_id=IDENTITY, reference='model.dat', duplicate=False):
    model = f(1, model_id) + f(2, f(1, reference)) + f(7, f(1, 2.0) + f(2, 3.0))
    placement = f(1, IDENTITY) + f(3, f(1, 123) + f(2, 45) + f(3, 67))
    group = f(1, 5) + f(2, f(1, 'fixture') + f(2, placement))
    section = f(1, 1) + f(2, 2) + f(6, group) + f(7, model)
    if duplicate:
        section += f(7, model)
    return f(1, 1) + f(2, 2) + f(3, section)


class ModelIndexTests(unittest.TestCase):
    def test_reference_join_preserves_64_bit_id(self):
        summary = index_summary(fixture())
        section = summary['sections'][0]
        self.assertEqual(section['models'][0]['id'], str(IDENTITY))
        self.assertEqual(section['models'][0]['references'][0][1], 'model.dat')
        self.assertTrue(section['instances'][0]['resolved'])
        self.assertFalse(summary['georeferenced'])

    def test_unresolved_model_is_not_invented(self):
        section = index_summary(fixture(model_id=1))['sections'][0]
        self.assertEqual(section['unresolvedInstances'], 1)

    def test_duplicate_model_rejected(self):
        with self.assertRaisesRegex(ValueError, 'duplicate model'):
            index_summary(fixture(duplicate=True))

    def test_wrong_wire_and_duplicate_singular(self):
        for raw in [f(1, b'1') + f(2, 2), f(1, 1) + f(1, 2) + f(2, 3)]:
            with self.assertRaises(ValueError):
                decode_index(raw)

    def test_required_fields_and_truncation(self):
        for raw in [b'', f(1, 1), fixture()[:-1], f(1, 1) + f(2, 2) + f(3, b'')]:
            with self.assertRaises(ValueError):
                decode_index(raw)

    def test_nonfinite_and_oversized_strings(self):
        for raw in [fixture(reference='a' * 8193),
                    f(1, 1) + f(2, 2) + f(3, f(1, 1) + f(2, 2) + f(7,
                        f(1, 1) + f(7, f(1, float('nan')) + f(2, 0.0))))]:
            with self.assertRaises(ValueError):
                decode_index(raw)

    def test_unknown_fields_do_not_change_model_association(self):
        self.assertEqual(index_summary(fixture()), index_summary(fixture() + f(100, b'unknown')))


if __name__ == '__main__':
    unittest.main()
