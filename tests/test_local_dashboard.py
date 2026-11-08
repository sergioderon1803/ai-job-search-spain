import importlib.util
import tempfile
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location('dashboard', Path(__file__).resolve().parent.parent / 'local_dashboard' / 'server.py')
dashboard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dashboard)

class TrackerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old_root, self.old_tracker = dashboard.ROOT, dashboard.TRACKER
        dashboard.ROOT = Path(self.tmp.name)
        dashboard.TRACKER = dashboard.ROOT / 'job_search_tracker.csv'
    def tearDown(self):
        dashboard.ROOT, dashboard.TRACKER = self.old_root, self.old_tracker
        self.tmp.cleanup()
    def test_create_edit_and_stale_update(self):
        version = dashboard.read_tracker()[2]
        dashboard.write_entry({'version': version, 'index': None, 'values': {'company': 'Ejemplo', 'role': 'Python', 'status': 'drafted', 'date': '2026-11-08'}})
        fields, rows, version2, _ = dashboard.read_tracker()
        self.assertEqual(rows[0]['company'], 'Ejemplo')
        with self.assertRaises(FileExistsError):
            dashboard.write_entry({'version': version, 'index': 0, 'values': {'notes': 'stale'}})
        dashboard.write_entry({'version': version2, 'index': 0, 'values': {'status': 'applied', 'date': '2026-11-08'}})
        self.assertEqual(dashboard.read_tracker()[1][0]['status'], 'applied')
    def test_preserve_unedited_lines_and_unknown_columns(self):
        dashboard.TRACKER.write_text('date,company,role,status,notes,extra\n2026-01-01,Una,Dev,applied,x,valor\n2026-01-02,Otra,QA,applied,y,otro\n', encoding='utf-8')
        version = dashboard.read_tracker()[2]
        dashboard.write_entry({'version': version, 'index': 0, 'values': {'notes': 'cambio'}})
        result = dashboard.TRACKER.read_text(encoding='utf-8')
        self.assertIn('2026-01-01,Una,Dev,applied,cambio,valor', result)
        self.assertIn('2026-01-02,Otra,QA,applied,y,otro', result)
    def test_reject_incompatible_input(self):
        version = dashboard.read_tracker()[2]
        with self.assertRaises(ValueError):
            dashboard.write_entry({'version': version, 'index': None, 'values': {'company': 'A,B', 'role': 'Dev', 'status': 'applied'}})
        self.assertFalse(dashboard.TRACKER.exists())

class ProfileTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.original = dashboard.PROFILE
        dashboard.PROFILE = Path(self.tmp.name) / 'profile.md'
        dashboard.PROFILE.write_text(
            '# Profile\n\n## Identity\n- **Name:** Sergio\n\n### Languages\n\n'
            '| Language | Level |\n|---|---|\n| Spanish | Native |\n\n'
            '## Education\n\n| Degree | Period |\n|---|---|\n| DAW | 2025 |\n', encoding='utf-8')

    def tearDown(self):
        dashboard.PROFILE = self.original
        self.tmp.cleanup()

    def test_update_field_preserves_structure_and_other_sections(self):
        sections, version = dashboard.profile_data()
        values = {field['id']: field['value'] for field in sections[0]['fields']}
        name = next(field['id'] for field in sections[0]['fields'] if field['label'] == 'Name')
        values[name] = 'Sergio Test'
        dashboard.write_profile_section({'index': 0, 'version': version, 'values': values})
        text = dashboard.PROFILE.read_text(encoding='utf-8')
        self.assertIn('- **Name:** Sergio Test', text)
        self.assertIn('### Languages\n\n| Language | Level |', text)
        self.assertIn('## Education\n\n| Degree | Period |', text)
        with self.assertRaises(FileExistsError):
            dashboard.write_profile_section({'index': 0, 'version': version, 'values': values})

    def test_edit_table_and_reject_structure_injection(self):
        sections, version = dashboard.profile_data()
        values = {field['id']: field['value'] for field in sections[0]['fields']}
        level = next(field['id'] for field in sections[0]['fields'] if field['label'] == 'Level')
        values[level] = 'C2'
        dashboard.write_profile_section({'index': 0, 'version': version, 'values': values})
        self.assertIn('| Spanish | C2 |', dashboard.PROFILE.read_text(encoding='utf-8'))
        sections, version = dashboard.profile_data()
        values = {field['id']: field['value'] for field in sections[0]['fields']}
        values[level] = 'C2 | injected'
        with self.assertRaises(ValueError):
            dashboard.write_profile_section({'index': 0, 'version': version, 'values': values})

if __name__ == '__main__':
    unittest.main()
