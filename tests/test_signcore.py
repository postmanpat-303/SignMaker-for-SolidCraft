"""Tests for signcore: the parts that decide what gets printed.

Run with:  python -m unittest discover -s tests -v

No SolidCraft, no Tk, and no display needed. Pillow and fontTools tests are skipped when
those libraries are not installed, so the suite runs anywhere.
"""
import os
import shutil
import sys
import tempfile
import time
import unittest
import xml.etree.ElementTree as ET
import zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import signcore

NS_URI = "http://schemas.microsoft.com/3dmanufacturing/core/2015/02"
NS = "{%s}" % NS_URI

FONT_TTF = {"name": "Test Sans", "family": "Test Sans", "style": "Regular",
            "path": "/fonts/TestSans.ttf", "index": 0, "weight": 400, "italic": False}
FONT_TTC = dict(FONT_TTF, path="/fonts/TestCollection.ttc", name="Test Collection")


def params(**over):
    p = dict(signcore.DEFAULTS)
    p.update(over)
    return p


def _mesh(oid, name, z=0.0, size=2.0):
    return ('<object id="%s" type="model" name="%s"><mesh><vertices>'
            '<vertex x="0" y="0" z="%s"/><vertex x="%s" y="0" z="%s"/><vertex x="0" y="%s" z="%s"/>'
            '</vertices><triangles><triangle v1="0" v2="1" v3="2"/></triangles></mesh></object>'
            % (oid, name, z, size, z, size, z))


def write_3mf(path, build_items, resources=None, model_attrs=""):
    resources = resources if resources is not None else (_mesh(2, "Plate", 0.0) + _mesh(3, "Text", 0.8))
    model = ('<?xml version="1.0" encoding="UTF-8"?>'
             '<model unit="millimeter" xmlns="%s" %s><resources>%s</resources><build>%s</build></model>'
             % (NS_URI, model_attrs, resources, build_items))
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("3D/3dmodel.model", model)
        z.writestr("Metadata/preserved.txt", "keep")


def read_model(path):
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        root = ET.fromstring(z.read("3D/3dmodel.model"))
    return root, names


def vertices(root, oid):
    for obj in root.find(NS + "resources").findall(NS + "object"):
        if obj.get("id") == str(oid) and obj.find(NS + "mesh") is not None:
            return [(float(v.get("x")), float(v.get("y")), float(v.get("z")))
                    for v in obj.iter(NS + "vertex")]
    raise AssertionError("object %s not found" % oid)


class TempDirCase(unittest.TestCase):
    """A scratch folder beside the tests, so runs never depend on the system temp folder."""

    _counter = 0

    def setUp(self):
        type(self)._counter += 1
        root = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".tmp")
        os.makedirs(root, exist_ok=True)
        self.tmp = os.path.join(root, "%s-%d" % (type(self).__name__, type(self)._counter))
        os.makedirs(self.tmp, exist_ok=True)
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def path(self, *parts):
        return os.path.join(self.tmp, *parts)


# ---------------------------------------------------------------- names
class SafeNameTests(unittest.TestCase):
    def test_plain_text_is_kept(self):
        self.assertEqual(signcore.safe_name("Welcome"), "Welcome")

    def test_surrounding_space_and_dots_are_stripped(self):
        self.assertEqual(signcore.safe_name("  spaced  "), "spaced")
        self.assertEqual(signcore.safe_name("trail."), "trail")

    def test_empty_becomes_sign(self):
        self.assertEqual(signcore.safe_name(""), "Sign")
        self.assertEqual(signcore.safe_name("   "), "Sign")

    def test_windows_reserved_names_are_escaped(self):
        for raw in ("CON", "PRN", "AUX", "NUL", "LPT1", "COM9"):
            self.assertTrue(signcore.safe_name(raw).startswith("_"), raw)

    def test_path_characters_are_removed(self):
        self.assertEqual(signcore.safe_name('bad/name:with*chars?<>|"'), "badnamewithchars")

    def test_control_characters_are_removed(self):
        self.assertEqual(signcore.safe_name("tab\there\nnewline"), "tabhere newline")

    def test_length_is_capped(self):
        self.assertEqual(len(signcore.safe_name("a" * 200)), 60)

    def test_unicode_is_preserved(self):
        self.assertEqual(signcore.safe_name("Ünïcödé"), "Ünïcödé")
        self.assertEqual(signcore.safe_name("Telefón ⁊"), "Telefón ⁊")

    def test_whitespace_is_collapsed(self):
        self.assertEqual(signcore.safe_name("hello   world"), "hello world")


# ---------------------------------------------------------------- build script
class BuildCommandTests(unittest.TestCase):
    def commands(self, p, font=FONT_TTF, cap=9.0, at=(0.0, 0.0), **kw):
        return signcore.build_commands(p, font, cap, at, **kw)["commands"]

    def named(self, cmds, name):
        hits = [c for c in cmds if c["command"] == name]
        self.assertTrue(hits, "no %s command in %s" % (name, [c["command"] for c in cmds]))
        return hits

    def test_raised_sign_has_plate_text_and_two_colours(self):
        cmds = self.commands(params(text="Hi"))
        self.assertEqual(self.named(cmds, "solid.extrude")[0]["params"]["body_name"], "Plate")
        self.assertEqual(self.named(cmds, "solid.extrude")[0]["params"]["distance"], 0.8)
        text_extrude = self.named(cmds, "solid.extrude")[1]["params"]
        self.assertEqual(text_extrude["body_name"], "Text")
        self.assertEqual(text_extrude["distance"], 1.0)
        self.assertNotIn("direction", text_extrude)
        colours = [c["params"] for c in self.named(cmds, "appearance.assign")]
        self.assertEqual(colours[0]["bodies"], ["Plate"])
        self.assertEqual(colours[1]["bodies"], ["Text"])
        # no boolean cut in the raised style
        self.assertFalse([c for c in cmds if c["command"] == "solid.combine" and c["params"].get("operation") == "cut"])

    def test_text_sketch_sits_on_top_of_the_plate(self):
        cmds = self.commands(params(text="Hi"))
        creates = self.named(cmds, "sketch.create")
        self.assertEqual(creates[1]["params"]["offset"], 0.8)
        sketch_text = self.named(cmds, "sketch.text")[0]["params"]
        self.assertEqual(sketch_text["text"], "Hi")
        self.assertEqual(sketch_text["height"], 9.0)
        self.assertEqual(sketch_text["align"], "center")
        self.assertEqual(sketch_text["font"], "/fonts/TestSans.ttf")

    def test_engraved_cuts_the_plate_and_keeps_the_tool(self):
        # the cut needs the measured body names, exactly as a real build supplies them
        cmds = self.commands(params(text="Hi", style="engraved", thickness=0.8, **{"raise": 1.0}),
                             glyph_names=["Text"])
        text_extrude = self.named(cmds, "solid.extrude")[1]["params"]
        self.assertEqual(text_extrude["direction"], "negative")
        self.assertAlmostEqual(text_extrude["distance"], 0.6)      # clamped to thickness - 0.2
        cut = [c["params"] for c in self.named(cmds, "solid.combine") if c["params"]["operation"] == "cut"]
        self.assertEqual(cut[0]["target"], "Plate")
        self.assertEqual(cut[0]["tools"], ["Text"])
        self.assertTrue(cut[0]["keep_tools"])

    def test_engrave_depth_never_exceeds_the_plate(self):
        cmds = self.commands(params(text="Hi", style="engraved", thickness=0.5, **{"raise": 50.0}))
        self.assertAlmostEqual(self.named(cmds, "solid.extrude")[1]["params"]["distance"], 0.3)

    def test_corner_radius_is_clamped_to_the_plate(self):
        cmds = self.commands(params(text="Hi", length=63.0, height=15.0, corner=99.0))
        rounded = self.named(cmds, "sketch.rectangle.rounded")[0]["params"]
        self.assertAlmostEqual(rounded["radius"], 7.45)            # height / 2 - 0.05

    def test_square_corners_use_the_plain_rectangle(self):
        cmds = self.commands(params(text="Hi", corner=0.0))
        self.named(cmds, "sketch.rectangle.center")
        self.assertFalse([c for c in cmds if c["command"] == "sketch.rectangle.rounded"])

    def test_letter_spacing_is_passed_through_only_when_set(self):
        with_spacing = self.commands(params(text="Hi", spacing=1.5))
        self.assertEqual(self.named(with_spacing, "sketch.text")[0]["params"]["letter_spacing"], 1.5)
        without = self.commands(params(text="Hi", spacing=0.0))
        self.assertNotIn("letter_spacing", self.named(without, "sketch.text")[0]["params"])

    def test_position_and_height_are_rounded(self):
        cmds = self.commands(params(text="Hi"), cap=9.123456789, at=(1.23456789, -2.3456789))
        sketch_text = self.named(cmds, "sketch.text")[0]["params"]
        self.assertEqual(sketch_text["height"], 9.1235)
        self.assertEqual(sketch_text["at"], [1.2346, -2.3457])

    def test_glyph_names_are_joined_into_one_text_body(self):
        cmds = self.commands(params(text="Hi"), glyph_names=["Text", "Text (1)", "Text (2)"])
        join = [c["params"] for c in self.named(cmds, "solid.combine") if c["params"]["operation"] == "join"][0]
        self.assertEqual(join["target"], "Text")
        self.assertEqual(join["tools"], ["Text (1)", "Text (2)"])

    def test_plate_can_be_skipped_for_measurement(self):
        cmds = self.commands(params(text="Hi"), plate=False)
        self.assertFalse([c for c in cmds if c["command"] == "solid.extrude"
                          and c["params"]["body_name"] == "Plate"])
        self.assertFalse([c for c in cmds if c["command"] == "appearance.assign"
                          and c["params"]["bodies"] == ["Plate"]])

    def test_exports_are_appended_in_order(self):
        exports = [("/w/sign.3mf", "3mf", ["Plate", "Text"]), ("/w/plate.stl", "stl", ["Plate"])]
        cmds = self.commands(params(text="Hi"), export=exports)
        got = [(c["params"]["path"], c["params"]["format"], c["params"]["bodies"])
               for c in self.named(cmds, "file.export")]
        self.assertEqual(got, exports)

    def test_collection_fonts_are_referenced_by_name(self):
        self.assertEqual(signcore.sc_font_arg(FONT_TTC), "Test Collection")
        self.assertEqual(signcore.sc_font_arg(FONT_TTF), "/fonts/TestSans.ttf")


# ---------------------------------------------------------------- eval JSON helpers
class EvalJsonTests(unittest.TestCase):
    def test_text_bodies_include_split_glyph_groups(self):
        ev = {"bodies": [{"name": "Plate"}, {"name": "Text"}, {"name": "Text (1)"}, {"name": "Text Box"}]}
        self.assertEqual([b["name"] for b in signcore._text_bodies(ev)], ["Text", "Text (1)"])

    def test_union_bbox_spans_every_body(self):
        bodies = [{"bbox": {"min": [-1, -2, 0], "max": [1, 2, 0.8]}},
                  {"bbox": {"min": [-3, -1, 0.8], "max": [3, 1, 1.8]}}]
        mn, mx = signcore._union_bbox(bodies)
        self.assertEqual(mn, [-3, -2, 0])
        self.assertEqual(mx, [3, 2, 1.8])


# ---------------------------------------------------------------- 3MF rewrite
class ThreeMfTests(TempDirCase):
    def rewrite(self, **kw):
        src, dst = self.path("src.3mf"), self.path("out.3mf")
        write_3mf(src, **kw)
        signcore.make_multipart_3mf(src, dst, {"text": "Workshop"})
        return read_model(dst)

    def test_two_build_items_become_one_object_with_two_parts(self):
        root, names = self.rewrite(build_items='<item objectid="2"/><item objectid="3"/>')
        objects = root.find(NS + "resources").findall(NS + "object")
        merged = [o for o in objects if o.find(NS + "components") is not None]
        self.assertEqual(len(merged), 1)
        self.assertEqual([c.get("objectid") for c in merged[0].find(NS + "components")], ["2", "3"])
        items = root.find(NS + "build").findall(NS + "item")
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].get("objectid"), merged[0].get("id"))
        self.assertEqual(items[0].get("transform"), None)

    def test_other_files_in_the_archive_survive(self):
        _, names = self.rewrite(build_items='<item objectid="2"/><item objectid="3"/>')
        self.assertIn("Metadata/preserved.txt", names)
        self.assertIn("Metadata/model_settings.config", names)

    def test_slicer_part_settings_name_both_parts_and_their_filaments(self):
        _, names = self.rewrite(build_items='<item objectid="2"/><item objectid="3"/>')
        with zipfile.ZipFile(self.path("out.3mf")) as z:
            cfg = z.read("Metadata/model_settings.config").decode("utf-8")
        self.assertIn('value="Plate"', cfg)
        self.assertIn('value="Text"', cfg)
        self.assertIn('<metadata key="extruder" value="1"/>', cfg)
        self.assertIn('<metadata key="extruder" value="2"/>', cfg)
        self.assertIn('value="Workshop"', cfg)

    def test_metadata_is_written(self):
        root, _ = self.rewrite(build_items='<item objectid="2"/><item objectid="3"/>')
        meta = {m.get("name"): m.text for m in root.findall(NS + "metadata")}
        self.assertEqual(meta["Title"], "Workshop")
        self.assertEqual(meta["Designer"], "Del (postmanpat)")

    def test_build_item_transform_is_baked_into_the_mesh(self):
        # translate by (10, 5, 0)
        root, _ = self.rewrite(build_items='<item objectid="2" transform="1 0 0 0 1 0 0 0 1 10 5 0"/>'
                                           '<item objectid="3" transform="1 0 0 0 1 0 0 0 1 10 5 0.8"/>')
        self.assertEqual(vertices(root, 2), [(10.0, 5.0, 0.0), (12.0, 5.0, 0.0), (10.0, 7.0, 0.0)])
        self.assertEqual(vertices(root, 3), [(10.0, 5.0, 1.6), (12.0, 5.0, 1.6), (10.0, 7.0, 1.6)])

    def test_identity_transform_leaves_coordinates_alone(self):
        root, _ = self.rewrite(build_items='<item objectid="2" transform="1 0 0 0 1 0 0 0 1 0 0 0"/>'
                                           '<item objectid="3"/>')
        self.assertEqual(vertices(root, 2), [(0.0, 0.0, 0.0), (2.0, 0.0, 0.0), (0.0, 2.0, 0.0)])

    def test_conflicting_placements_are_refused(self):
        src = self.path("conflict.3mf")
        write_3mf(src, '<item objectid="2" transform="1 0 0 0 1 0 0 0 1 10 0 0"/>'
                       '<item objectid="2" transform="1 0 0 0 1 0 0 0 1 0 10 0"/>'
                       '<item objectid="3"/>')
        with self.assertRaises(RuntimeError):
            signcore.make_multipart_3mf(src, self.path("out.3mf"), {"text": "x"})

    def test_missing_body_is_a_clear_error(self):
        src = self.path("missing.3mf")
        write_3mf(src, '<item objectid="2"/>', resources=_mesh(2, "Plate", 0.0))
        with self.assertRaises(RuntimeError) as ctx:
            signcore.make_multipart_3mf(src, self.path("out.3mf"), {"text": "x"})
        self.assertIn("Plate or Text", str(ctx.exception))

    def test_dangling_required_extension_is_not_shipped(self):
        # the sc: prefix is declared but never used, so ElementTree drops the declaration
        root, _ = self.rewrite(build_items='<item objectid="2"/><item objectid="3"/>',
                               model_attrs='xmlns:sc="http://example.com/sc" requiredextensions="sc"')
        self.assertIsNone(root.get("requiredextensions"))

    def test_used_foreign_namespace_keeps_its_prefix_and_requirement(self):
        resources = (_mesh(2, "Plate", 0.0).replace("<mesh>", '<mesh sc:note="hi">')
                     + _mesh(3, "Text", 0.8))
        src, dst = self.path("ns.3mf"), self.path("ns-out.3mf")
        write_3mf(src, '<item objectid="2"/><item objectid="3"/>', resources=resources,
                  model_attrs='xmlns:sc="http://example.com/sc" requiredextensions="sc"')
        signcore.make_multipart_3mf(src, dst, {"text": "x"})
        with zipfile.ZipFile(dst) as z:
            xml = z.read("3D/3dmodel.model").decode("utf-8")
        self.assertIn('requiredextensions="sc"', xml)
        self.assertIn("xmlns:sc=", xml)
        self.assertIn("sc:note", xml)


class TransformParsingTests(unittest.TestCase):
    def test_parses_twelve_numbers(self):
        self.assertEqual(signcore._parse_transform("1 0 0 0 1 0 0 0 1 10 5 0"),
                         [1, 0, 0, 0, 1, 0, 0, 0, 1, 10, 5, 0])

    def test_missing_identity_and_junk(self):
        self.assertIsNone(signcore._parse_transform(None))
        self.assertIsNone(signcore._parse_transform("   "))
        self.assertIsNone(signcore._parse_transform("1 0 0"))
        self.assertIsNone(signcore._parse_transform("a b c"))

    def test_rotation_matrix(self):
        # 90 degrees about Z: x -> y, y -> -x  (rows of the 4x3 matrix)
        m = signcore._parse_transform("0 1 0 -1 0 0 0 0 1 0 0 0")
        self.assertEqual(m, [0, 1, 0, -1, 0, 0, 0, 0, 1, 0, 0, 0])


# ---------------------------------------------------------------- work folders
class PruneWorkTests(TempDirCase):
    def test_only_old_folders_are_removed(self):
        old, new = self.path("old"), self.path("new")
        os.makedirs(old)
        os.makedirs(new)
        ancient = time.time() - 30 * 86400
        os.utime(old, (ancient, ancient))
        real = signcore.WORK_DIR
        signcore.WORK_DIR = self.tmp
        self.addCleanup(setattr, signcore, "WORK_DIR", real)
        removed = signcore.prune_work_dirs(max_age_days=7)
        self.assertEqual(removed, 1)
        self.assertFalse(os.path.exists(old))
        self.assertTrue(os.path.exists(new))

    def test_missing_work_folder_is_not_an_error(self):
        real = signcore.WORK_DIR
        signcore.WORK_DIR = self.path("does-not-exist")
        self.addCleanup(setattr, signcore, "WORK_DIR", real)
        self.assertEqual(signcore.prune_work_dirs(), 0)

    def test_new_work_dir_is_unique_and_inside_work_dir(self):
        real = signcore.WORK_DIR
        signcore.WORK_DIR = self.tmp
        self.addCleanup(setattr, signcore, "WORK_DIR", real)
        a, b = signcore.new_work_dir("x-"), signcore.new_work_dir("x-")
        self.assertNotEqual(a, b)
        self.assertTrue(os.path.isdir(a) and os.path.isdir(b))
        self.assertEqual(os.path.dirname(a), os.path.abspath(self.tmp))


# ---------------------------------------------------------------- optional deps
try:
    from PIL import Image      # noqa: F401
    HAVE_PIL = True
except ImportError:
    HAVE_PIL = False

try:
    from fontTools.ttLib import TTFont      # noqa: F401
    HAVE_FONTTOOLS = True
except ImportError:
    HAVE_FONTTOOLS = False

SOME_FONT = next((p for p in (
    os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts", "arial.ttf"),
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/Library/Fonts/Arial.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
) if os.path.exists(p)), None)


@unittest.skipUnless(HAVE_PIL and SOME_FONT, "needs Pillow and a TrueType font")
class PreviewTests(TempDirCase):
    def font(self):
        return {"name": "Test", "family": "Test", "style": "Regular", "path": SOME_FONT,
                "index": 0, "weight": 400, "italic": False}

    def test_preview_renders_and_fits_inside_the_margins(self):
        img, info = signcore.preview_image(params(text="Workshop"), self.font())
        self.assertTrue(info["ok"])
        self.assertTrue(info["fits"], info)
        self.assertLessEqual(info["text_w"], 63.0 - 2 * 1.5 + 0.01)
        self.assertLessEqual(info["text_h"], 15.0 - 2 * 1.5 + 0.01)
        self.assertGreater(img.size[0], 0)

    def test_long_text_shrinks_instead_of_overflowing(self):
        _, info = signcore.preview_image(params(text="Ballydehob Community Workshop"), self.font())
        self.assertTrue(info["fits"])
        self.assertLess(info["cap_mm"], 4.0)

    def test_empty_text_is_reported_not_drawn(self):
        _, info = signcore.preview_image(params(text="   "), self.font())
        self.assertFalse(info["ok"])

    def test_engraved_and_raised_both_draw(self):
        for style in ("raised", "engraved"):
            _, info = signcore.preview_image(params(text="No 7", style=style), self.font())
            self.assertTrue(info["ok"], style)


@unittest.skipUnless(HAVE_PIL, "needs Pillow")
class AnnotationFontTests(unittest.TestCase):
    def test_annotation_font_honours_the_size(self):
        f = signcore.annotation_font(26, bold=True)
        self.assertTrue(hasattr(f, "getbbox"))
        f2 = signcore.annotation_font(52)
        # the default bitmap font ignores size; a real face responds to it
        if f.__class__.__name__ == "FreeTypeFont" and f2.__class__.__name__ == "FreeTypeFont":
            self.assertGreater(f2.size, f.size)


if __name__ == "__main__":
    unittest.main(verbosity=2)
