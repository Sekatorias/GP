from pathlib import Path
import random
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
try:
    import generator
except ImportError:
    generator = None


@unittest.skipUnless(generator is not None, 'Нужен pymorphy3 (pip install -r requirements.txt)')
class GenerationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.groups = generator.all_names()

    def test_categories_have_names(self):
        self.assertTrue(self.groups[0])
        self.assertTrue(self.groups[1])
        self.assertTrue(self.groups[2])
        for collection in self.groups.values():
            self.assertTrue(all(generator.valid_name(name) for name in collection))

    def test_probability_edges(self):
        no_mat = {generator.generate(0, rng=random.Random(i)) for i in range(200)}
        all_mat = {generator.generate(100, rng=random.Random(i)) for i in range(200)}
        self.assertTrue(no_mat.isdisjoint(self.groups[2]))
        self.assertTrue(all_mat.issubset(self.groups[2]))
        self.assertFalse(no_mat & all_mat)

    def test_does_not_repeat_previous_name(self):
        rng = random.Random(444)
        first = generator.generate(100, rng=rng)
        second = generator.generate(100, previous=first, rng=rng)
        self.assertNotEqual(first, second)


if __name__ == '__main__':
    unittest.main()
