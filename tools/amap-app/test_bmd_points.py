import struct
import unittest
from unittest.mock import patch
from bmd_points import points, geographic_labels
from bmd_tile import lz4_block
from test_bmd_geometry import packed, v

class ExtraLayerTests(unittest.TestCase):
    def test_overview_labels_keep_native_positions_ranges_and_categories(self):
        features = [{'point': [601, 396], 'nameIndex': i, 'style': 132, 'width': 11} for i in range(3)]
        with patch('bmd_points.section', return_value=b'x'), patch('bmd_points.points', return_value=features), patch('bmd_points.names', return_value=[{'zh-Hans': '北京市'}, {'zh-Hans': '河北省'}, {'zh-Hans': '渤海'}]), patch('bmd_points.style_bindings', return_value={0:(10002,30),1:(10002,22),2:(10002,13)}):
            labels = geographic_labels(b'x', (3,6,2), places=True)
        self.assertEqual([l['name'] for l in labels], ['北京市', '河北省'])
        self.assertEqual([l['kind'] for l in labels], ['city', 'province'])
        self.assertEqual(labels[0]['point'], [116.4111328125, 39.90234375])
        self.assertEqual((labels[0]['minZoom'], labels[0]['maxZoom']), (4,4))
        self.assertLess(labels[0]['priority'], labels[1]['priority'])

    def test_point_labels_and_complete_consumption(self):
        raw=v(1)+struct.pack('<H',656)+v(1)+struct.pack('<IHB',123,0,12)+v(1)
        raw+=v(0)+bytes(8)+bytes([1])+bytes(8)+v(2)+packed((1124,12),(507,12))
        self.assertEqual(points(raw),[{'point':[1124,507],'nameIndex':2,'style':656,'width':12}])
        for end in range(len(raw)):
            with self.assertRaises(ValueError):points(raw[:end])
        with self.assertRaises(ValueError):points(raw+b'\0')

    def test_bounded_lz4_overlap_and_literals(self):
        self.assertEqual(lz4_block(b'\x35abc\x03\x00\x10!',13),b'abcabcabcabc!')
        self.assertEqual(lz4_block(b'\x30abc',3),b'abc')
        for raw,size in [(b'\x00\0\0',4),(b'\x30ab',3),(b'\x35abc\x03\x00',11),(b'\xf0\xff',100),(b'\x10a\x02\x00',5)]:
            with self.assertRaises(ValueError):lz4_block(raw,size)

if __name__=='__main__':unittest.main()
