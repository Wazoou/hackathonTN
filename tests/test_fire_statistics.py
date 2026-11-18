import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'dashboard'))
from fire_statistics import department_fire_statistics, history_signature


class FireStatisticsTests(unittest.TestCase):
    def test_counts_zero_years_overlap_missing_coordinates_and_excludes_2025(self):
        with tempfile.TemporaryDirectory() as folder:
            header = 'Année;Numéro;Département;Code INSEE;Surface parcourue (m2)\n'
            rows = [f'{y};{y};40;;\n' for y in range(2006, 2025)]
            rows += ['2022;fire1;33;;\n', '2022;fire2;33;;-1\n', '2025;extra;33;;1\n']
            Path(folder, 'one.csv').write_text('Metadata\n' + header + ''.join(rows))
            Path(folder, 'two.csv').write_text(header + '2022;fire1;33;;\n')
            signature = history_signature(folder)
            result = department_fire_statistics(signature)
            self.assertTrue(result['complete'])
            self.assertEqual(result['departments']['33']['count'], 2)
            self.assertEqual(result['departments']['33']['annual_mean'], 2 / 19)
            self.assertEqual(result['departments']['40']['annual_mean'], 1)
            Path(folder, 'two.csv').write_text(header + '2022;fire3;33;;\n')
            self.assertNotEqual(signature, history_signature(folder))

    def test_partial_and_absent_exports(self):
        self.assertEqual(department_fire_statistics(())['years'], [])
        with tempfile.TemporaryDirectory() as folder:
            Path(folder, 'one.csv').write_text('Année;Numéro;Département\n2024;1;2A\n')
            result = department_fire_statistics(history_signature(folder))
            self.assertFalse(result['complete'])
            self.assertEqual(result['years'], [2024])
            self.assertEqual(result['departments']['2A']['annual_mean'], 1)


if __name__ == '__main__':
    unittest.main()
