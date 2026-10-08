import gc
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ffvideo import tesla


class TeslaVehicleModelTest(unittest.TestCase):
    def test_existing_vehicle_table_gets_car_type_column(self):
        with tempfile.TemporaryDirectory() as folder:
            db = str(Path(folder) / 'tesla.sqlite3')
            with sqlite3.connect(db) as conn:
                conn.execute('CREATE TABLE tesla_vehicles (vin TEXT PRIMARY KEY, updated_at INTEGER NOT NULL)')
            with patch.object(tesla, 'get_tesla_db_path', return_value=db):
                tesla.ensure_tesla_storage()
                with sqlite3.connect(db) as conn:
                    columns = {row[1] for row in conn.execute('PRAGMA table_info(tesla_vehicles)')}
                self.assertIn('car_type', columns)
                del conn
                gc.collect()

    def test_car_type_survives_products_cache_updates(self):
        with tempfile.TemporaryDirectory() as folder:
            db = str(Path(folder) / 'tesla.sqlite3')
            with patch.object(tesla, 'get_tesla_db_path', return_value=db):
                record = {'vin': 'LRWYAAAAASAAAAAAA', 'vehicleId': '1', 'displayName': 'Car',
                          'state': 'online', 'carType': 'e41Bayberry'}
                tesla.upsert_vehicle_cache(record)
                tesla.upsert_vehicle_cache({**record, 'carType': None})
                self.assertEqual(tesla.cached_vehicles()[0]['carType'], 'e41Bayberry')
                gc.collect()  # sqlite3 context managers commit but do not close on Windows.


if __name__ == '__main__':
    unittest.main()
