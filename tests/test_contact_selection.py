"""Exercise selection without running Streamlit or connecting to Salesforce."""
import ast
from pathlib import Path
import re
import unittest

import pandas as pd

source = ast.parse((Path(__file__).resolve().parents[1] / 'miedge-salesforce.py').read_text())
names = {'PEO_ROLE_PATTERNS', 'peo_contact_group', 'job_title_rank',
         'select_leads_per_company', 'get_company_column', 'normalize_company'}
nodes = [node for node in source.body
         if (isinstance(node, ast.FunctionDef) and node.name in names)
         or (isinstance(node, ast.Assign) and any(
             isinstance(target, ast.Name) and target.id in names for target in node.targets))]
namespace = {'pd': pd, 're': re}
exec(compile(ast.Module(body=nodes, type_ignores=[]), '<selection>', 'exec'), namespace)
select = namespace['select_leads_per_company']


def contacts(titles, company='Acme'):
    return pd.DataFrame([{'Contact Company name': company, 'Job Title': title,
                          'Contact Email': f'person{i}@example.com'}
                         for i, title in enumerate(titles)])


class ContactSelectionTests(unittest.TestCase):
    def test_department_coverage_before_extra_executives(self):
        df = contacts(['CEO', 'Owner', 'Founder', 'President', 'HR Director',
                       'CFO', 'COO', 'Payroll Manager', 'Benefits Manager'])
        result = select(df)
        self.assertEqual(len(result), 7)
        self.assertEqual(len(set(result['PEO Contact Role'])), 6)
        self.assertIn('HR Director', set(result['Job Title']))
        self.assertIn('Benefits Manager', set(result['Job Title']))
        self.assertEqual(result.iloc[-1]['Job Title'], 'Owner')

    def test_limit_applies_independently_and_fewer_available(self):
        df = pd.concat([contacts(['CEO'] * 10), contacts(['HR Manager', 'CFO'], 'Beta')])
        result = select(df, 6)
        self.assertEqual(result.groupby('Contact Company name').size().to_dict(), {'Acme': 6, 'Beta': 2})

    def test_email_validation_deduplication_and_blank_companies(self):
        df = contacts(['CEO', 'Owner', 'HR Manager', 'CFO', 'COO'])
        df.loc[1, 'Contact Email'] = ' PERSON0@example.com '
        df.loc[2, 'Contact Email'] = 'invalid'
        df.loc[3, 'Contact Company name'] = ' '
        df.loc[4, 'Contact Email'] = None
        self.assertEqual(len(select(df)), 1)

    def test_seniority_stability_and_input_unchanged(self):
        df = contacts(['HR Specialist', 'HR Manager', 'VP Human Resources', 'CHRO', 'CHRO'])
        before = df.copy(deep=True)
        result = select(df, 2)
        self.assertEqual(result['Contact Email'].tolist(), ['person3@example.com', 'person4@example.com'])
        pd.testing.assert_frame_equal(df, before)
        self.assertLess(namespace['job_title_rank']('HR Director'), namespace['job_title_rank']('HR Manager'))
        self.assertGreater(namespace['job_title_rank']('Vice President of HR'), namespace['job_title_rank']('CHRO'))

    def test_peo_title_defaults(self):
        classify = namespace['peo_contact_group']
        for title in ['Owner', 'HR Generalist', 'Chief People Officer', 'CFO', 'Office Manager', 'Payroll Specialist', 'Benefits Director']:
            self.assertIsNotNone(classify(title), title)
        for title in ['CTO', 'VP Sales', 'Vice President Marketing', 'Executive Assistant to CEO', 'Retired Owner', None]:
            self.assertIsNone(classify(title), title)

    def test_empty_missing_columns_and_manual_title(self):
        df = contacts(['IT Director'])
        self.assertEqual(select(df).iloc[0]['PEO Contact Role'], 'Other selected title')
        self.assertTrue(select(df.iloc[:0]).empty)
        with self.assertRaises(ValueError):
            select(df.drop(columns=['Contact Email']))
        with self.assertRaises(ValueError):
            select(df, 8)


if __name__ == '__main__':
    unittest.main()
