import struct
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import zstandard
from bmd_styles import style_bindings, polygon_paints, detail_paints, load_paints
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
    def test_navigation_style_uses_its_own_assets(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data = zstandard.ZstdCompressor().compress(paint_fixture())
            for theme in ('day', 'night'):
                (root / f'style-navigation-{theme}.data').write_bytes(data)
            self.assertEqual(len(load_paints(root, variant='navigation')['day']), 1)
            with self.assertRaises(FileNotFoundError):
                load_paints(root)
            with self.assertRaises(ValueError):
                load_paints(root, variant='unknown')

    def test_detail_rule_and_material_boundaries(self):
        def fixture(mode=1, condition=0, mixed=False, width=55, texture_id=None,
                    secondary_texture_id=None, material_option=None):
            f=field
            category=20007 if mode==1 else 55001
            style=f(1,category)+f(2,1)+f(3,f(1,0)+f(2,0)+f(3,5))
            group=f(1,5)+f(5,10)
            rule=f(1,10)+f(3,f(1,f(2,f(1,f(1,16)+f(2,18))+f(2,condition))+f(4 if mode==1 else 11,f(1,20))))
            paint=(f(10,f(1,0xff112233))+f(11,f(1,0xff445566))+f(19,struct.pack('<d',width))+f(20,struct.pack('<d',40))) if mode==1 else (b''.join(f(k,f(1,0xff112233 if k!=6 or not mixed else 0xff445566)) for k in range(2,7))
                +(f(7,material_option) if material_option is not None else b'')
                +(f(10,f(1,texture_id)) if texture_id is not None else b'')
                +(f(11,f(1,secondary_texture_id)) if secondary_texture_id is not None else b''))
            kind=5 if mode==1 else 8
            material=f(1,20)+f(2,kind)+f(3,f(kind,paint))
            return f(1,f(1,mode)+f(3,f(1,style)+f(2,group)+f(4,material)+f(5,rule)))
        road=detail_paints(fixture(),1)[(20007,1)][0]
        self.assertEqual(road['outer']['color'],'#112233')
        self.assertEqual(road['innerWidth'],40)
        self.assertEqual(detail_paints(fixture(condition=9),1),{})
        self.assertEqual(detail_paints(fixture(width=float('nan')),1),{})
        self.assertEqual(detail_paints(fixture(mode=8),8)[(55001,1)][0]['surface']['color'],'#112233')
        mixed=detail_paints(fixture(mode=8,mixed=True),8)[(55001,1)][0]
        self.assertEqual(mixed['colorSlots'],['#112233']*4+['#445566'])
        self.assertEqual(detail_paints(fixture(mode=8,texture_id=23000029),8)[(55001,1)][0]['textureId'],23000029)
        self.assertNotIn('textureId',detail_paints(fixture(mode=8,texture_id=0),8)[(55001,1)][0])
        secondary=detail_paints(fixture(mode=8,texture_id=23100029,
                                        secondary_texture_id=1112,material_option=4),8)[(55001,1)][0]
        self.assertEqual(secondary['secondaryTextureId'],1112)
        self.assertEqual(secondary['materialOption7Raw'],4)
        self.assertNotIn('secondaryTextureId',detail_paints(fixture(mode=8,
            secondary_texture_id=0),8)[(55001,1)][0])

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
