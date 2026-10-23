"""Theme colors written as lists — the only form a TOML manifest has — are built
into tuples, since PuiKit hashes colors (issue #708). Pure theme-builder checks."""

import os
import sys
import types
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, ".."))

from xefm import app as xefm_app  # noqa: E402


def _themes(**themes):
    return dict(xefm_app._build_theme_list(types.SimpleNamespace(THEMES=themes)))


class ListColors(unittest.TestCase):
    def test_top_level_colors_become_tuples(self):
        t = _themes(**{"List Theme": {"base": "Dark+", "background": [0, 0, 128],
                                      "foreground": [85, 255, 255]}})["List Theme"]
        self.assertEqual(t.surfaces["content"], (0, 0, 128))
        self.assertEqual(t.text, (85, 255, 255))
        hash(t.text)
        for color in t.surfaces.values():
            hash(color)

    def test_colors_inside_sub_dicts_become_tuples(self):
        override = xefm_app._merge_theme_override({}, {
            "file_types": {"directory": [250, 189, 47]},
            "cursor": {"active": [1, 2, 3, 255]},
            "syntax": {"keyword": [251, 73, 52]},
        })
        self.assertEqual(override["file_types"], {"directory": (250, 189, 47)})
        self.assertEqual(override["cursor"], {"active": (1, 2, 3, 255)})
        self.assertEqual(override["syntax"], {"keyword": (251, 73, 52)})

    def test_lists_that_are_not_colors_are_left_alone(self):
        self.assertEqual(xefm_app._tuple_colors(["a", "b", "c"]), ["a", "b", "c"])
        self.assertEqual(xefm_app._tuple_colors([1, 2]), [1, 2])
        self.assertEqual(xefm_app._tuple_colors([True, False, True]), [True, False, True])
        self.assertEqual(xefm_app._tuple_colors({"x": [[1, 2, 3]]}), {"x": [(1, 2, 3)]})


if __name__ == "__main__":
    unittest.main()
