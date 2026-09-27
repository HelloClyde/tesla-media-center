import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools' / 'amap-app'))
from bmd_buildings import BuildingReader, building_point, building_section


def bits(fields):
    raw = ''.join(format(value & ((1 << width)-1), f'0{width}b') for value, width in fields)
    raw += '0' * (-len(raw) % 8)
    return int(raw, 2).to_bytes(len(raw)//8, 'big')


def fixture():
    shape = bytes([18, 1, 1, 3])
    shape += bits([(100,18),(100,18),(0,1),(0,1),(8,5)])
    shape += bits([(20,8),(0,8),(0,1),(-20,8),(20,8),(0,1)]) + b'\x00'
    return shape + b'\x01' + (0).to_bytes(4,'little') + b'\x01' + (7).to_bytes(8,'little') + b'\x00\x20\x00\x00'


class BuildingTest(unittest.TestCase):
    def test_native_signed_varint_stops_at_fifth_byte(self):
        reader=BuildingReader(b'\xff\xff\xff\xff\xff\x04')
        self.assertEqual(reader.v32(signed=True), -1)
        self.assertEqual(reader.v32(), 4)

    def test_default_part_and_signed_shape_deltas(self):
        width, shapes, features=building_section(fixture())
        self.assertEqual(width,18)
        self.assertEqual(shapes[0]['points'], [[100,100],[120,100],[100,120]])
        self.assertEqual(features[0]['parts'][0]['height'],32)
        self.assertEqual(features[0]['id'],'7')

    def test_truncation_and_trailing_data_rejected(self):
        data=fixture()
        for end in range(len(data)):
            with self.assertRaises(ValueError): building_section(data[:end])
        with self.assertRaises(ValueError): building_section(data+b'\x00')

    def test_tile_seams_and_north_orientation(self):
        extent=1<<17
        self.assertEqual(building_point([extent,0],(15,100,100),18),building_point([0,0],(15,101,100),18))
        self.assertGreater(building_point([0,100],(15,100,100),18)[1],building_point([0,0],(15,100,100),18)[1])


if __name__ == '__main__': unittest.main()
