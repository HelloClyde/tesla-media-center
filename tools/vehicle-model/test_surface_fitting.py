import importlib.util
from pathlib import Path
import unittest
import numpy as np

spec = importlib.util.spec_from_file_location('surface_fitting', Path(__file__).with_name('repair-surfaces.py'))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

class SurfaceFittingTests(unittest.TestCase):
    def test_plane_and_sparse_boundary(self):
        points = [[float(x), 1., float(z)] for x in np.linspace(-.06, .06, 9) for z in np.linspace(-.06, .06, 9)]
        normal = np.array([.06, 1., 0.]); normal /= np.linalg.norm(normal)
        item = dict(name='plane', material='Wheel_Graphite_Alloy', points=points, normals=[normal.tolist() for _ in points])
        result = module.fit_surface(item)
        self.assertEqual(result['points'], points)
        fitted = np.array(result['normals']).reshape(9, 9, 3)
        np.testing.assert_allclose(np.linalg.norm(fitted, axis=2), 1., atol=1e-6)
        np.testing.assert_allclose(fitted[1:-1, 1:-1, 0], 0., atol=1e-5)
        # Fewer than eight neighbors: preserve source rather than extrapolate.
        np.testing.assert_allclose(fitted[0, 0], normal)

    def test_opposite_surfaces_stay_separate(self):
        points = [[float(x), 1., float(z)] for x in np.linspace(-.02, .02, 9) for z in np.linspace(-.02, .02, 9)]
        item = dict(name='two-sides', material='Wheel_Graphite_Alloy', points=points+points,
                    normals=[[0.,1.,0.] for _ in points]+[[0.,-1.,0.] for _ in points])
        result = module.fit_surface(item)
        np.testing.assert_allclose(result['normals'], [[0.,1.,0.] for _ in points]+[[0.,-1.,0.] for _ in points], atol=1e-6)

if __name__ == '__main__':
    unittest.main()
