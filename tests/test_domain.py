import unittest
from workbench.domain import *

class DomainBoundaryTests(unittest.TestCase):
    def test_boundaries(self):
        self.assertEqual(group_sizes([{'p':'a','x':1},{'p':'a','x':1},{'p':'b','x':1}],['x'],'p'),[{'key':[1],'people':2}])
        with self.assertRaises(KeyError):project([{'a':1}],['missing'])
        with self.assertRaises(ValueError):project([{'a':1}],['a','a'])
        self.assertEqual(lineage([], 'x'),[])
