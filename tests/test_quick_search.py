import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / '.runtime/python')]
import financial_quick_research as research


class DiscoveryTests(unittest.TestCase):
    def test_pasted_question(self):
        queries = research.discovery_queries('财政部成功发:行绿色主权:\n债券意味着什么？')
        self.assertEqual(queries[0], '财政部成功发行绿色主权债券')
        self.assertIn('发行', queries[-1])

    def test_empty_feed_does_not_discard_other_searches(self):
        article = ('https://example.org/report', '公告')
        with patch.object(research, 'search', return_value=[article]), \
             patch.object(research, 'search_360', return_value=[]), \
             patch.object(research, 'fetch_public', return_value=('', '', b'')):
            results = research.discover(['测试'])
        self.assertEqual(results[0]['hits'], [article])
        self.assertIn('error', results[1])
