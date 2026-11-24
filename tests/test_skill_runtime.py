import unittest

from financial_quantities import unsupported_quantities
from skill_runtime import METHODS, contextual_skill, instructions


class SkillRuntimeTests(unittest.TestCase):
    def test_explicit_routes(self):
        self.assertIsNone(contextual_skill({}))
        self.assertEqual(contextual_skill({'reader': True, 'learning': True}), 'learning-coach')
        self.assertEqual(contextual_skill({'reader': True}), 'reading-assistant')
        for name in METHODS:
            self.assertIn('description:', instructions(name))

    def test_units_and_sign(self):
        for claim in ('5个百分点', '-5%', '5亿元'):
            self.assertTrue(unsupported_quantities(claim, ['上涨5％']))
        self.assertFalse(unsupported_quantities('5.0%', ['上涨5％']))
        self.assertTrue(unsupported_quantities('5000亿元', ['5000万元']))
