import struct
import unittest
from unittest.mock import patch
from bmd_styles import style_bindings, polygon_paints
from bmd_surfaces import geographic_surfaces
from bmd_geometry import geographic_point
import test_bmd_tile
from test_bmd_tile import field, vint


def tile(raw):
    return test_bmd_tile.BmdTests().make_bmd([(41, 0, len(raw))], raw)


def paint_fixture(condition=0):
    f = field
    style = f(1,30001)+f(2,2)+f(3,f(1,0)+f(2,0)+f(3,5))
    group = f(1,5)+f(3,2)+f(5,10)
    limits = f(1,12)+f(2,18)+f(3,100)
    rule = f(1,10)+f(3,f(1,f(1,2)+f(2,f(1,limits)+f(2,condition))+f(5,f(1,20)+f(2,0))))
    material = f(1,20)+f(2,6)+f(3,f(6,f(2,100)+f(18,f(1,0xff80dfff))))
    return f(1,f(1,2)+f(3,f(1,style)+f(2,group)+f(4,material)+f(5,rule)))


class StyleTests(unittest.TestCase):
    def test_shared_and_individual_attribute_binding(self):
        shared = bytes([2,1,2,0,2])+struct.pack('<II',2,30001)
        individual = bytes([1,2,0])+struct.pack('<II',2,30001)+bytes([2])+struct.pack('<II',3,30001)
        for block, expected in [(shared,{0:(30001,2),2:(30001,2)}),(individual,{0:(30001,2),2:(30001,3)})]:
            self.assertEqual(style_bindings(tile(bytes([1,1,0])+block),41,3),expected)
        for block in [shared[:-1], shared+b'\0', bytes([2,1,2,0,0])+struct.pack('<II',2,30001),bytes([2,1,1,3])+struct.pack('<II',2,30001)]:
            with self.assertRaises(ValueError):
                style_bindings(tile(bytes([1,1,0])+block),41,3)

    def test_style_chain_and_unknown_conditions(self):
        self.assertEqual(polygon_paints(paint_fixture())[(30001,2)],
                         [{'minZoom':12,'maxZoom':18,'color':'#80dfff','opacity':1}])
        self.assertEqual(polygon_paints(paint_fixture(9)),{})

    def test_multi_precision_seams_all_supported_levels(self):
        for level in [3,6,8,10,12,14]:
            for width in [11,12,13]:
                size = 1 << (width-1)
                self.assertEqual(geographic_point([size,100],(level,4,2),width), geographic_point([0,100],(level,5,2),width))
                self.assertEqual(geographic_point([100,0],(level,4,2),width),geographic_point([100,size//2],(level,4,3),width))
                self.assertEqual(geographic_point([100,200],(level,4,2),12),geographic_point([200,400],(level,4,2),13))

    def test_unknown_style_omitted_and_rings_preserved(self):
        feature={'coordinateBits':12,'style':655,'rings':[{'points':[[0,0],[100,0],[100,100]]}]}
        with patch('bmd_surfaces.decode',return_value=[feature]), patch('bmd_styles.section',return_value=b'x'), patch('bmd_styles.style_bindings',return_value={0:(30001,2)}):
            self.assertEqual(geographic_surfaces(b'',(14,13489,4559),{'day':{}}),[])
            result=geographic_surfaces(b'',(14,13489,4559),{'day':polygon_paints(paint_fixture())})
            self.assertEqual(len(result[0]['rings'][0]),3)
            self.assertEqual(result[0]['rings'][0][2],geographic_point([200,200],(14,13489,4559)))

if __name__=='__main__':
    unittest.main()
