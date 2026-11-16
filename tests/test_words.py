from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from words import G_ADJECTIVES, G_NOUNS, P_NOUNS, P_ADJECTIVES


class WordsTests(unittest.TestCase):
    def test_word_categories(self):
        for wordlist, initial, nouns in [
            (G_ADJECTIVES, 'г', False), (G_NOUNS, 'г', True),
            (P_NOUNS, 'п', True), (P_ADJECTIVES, 'п', False),
        ]:
            all_items = []
            for severity, items in wordlist.items():
                self.assertIn(severity, (0, 1, 2))
                for item in items:
                    word = item[0] if nouns else item
                    self.assertTrue(word.startswith(initial), word)
                    self.assertFalse(' ' in word, word)
                    if nouns:
                        self.assertIn(item[1], ('masc', 'femn', 'neut', 'plur'))
                    all_items.append(word)
            self.assertEqual(len(all_items), len(set(all_items)), 'Повторяющиеся слова')
        self.assertGreaterEqual(len(P_NOUNS[2]), 10)
        self.assertGreaterEqual(len(P_ADJECTIVES[2]), 10)


if __name__ == '__main__':
    unittest.main()
