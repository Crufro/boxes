from __future__ import annotations

import collections
import io
import struct
import sys
import zipfile
from pathlib import Path

try:
    import boxes
except ImportError:
    sys.path.append(Path(__file__).resolve().parent.parent.__str__())
    import boxes

from boxes.generators.regularbox import RegularBox
from boxes.generators.rack19box import Rack19Box


def _stl_edge_stats(data: bytes) -> tuple[int, int]:
    triangle_count = struct.unpack("<I", data[80:84])[0]
    vertices: dict[tuple[float, float, float], int] = {}
    edges: collections.Counter[tuple[int, int]] = collections.Counter()
    offset = 84

    def vertex_id(vertex: tuple[float, float, float]) -> int:
        key = tuple(round(v, 5) for v in vertex)
        if key not in vertices:
            vertices[key] = len(vertices)
        return vertices[key]

    for _ in range(triangle_count):
        values = struct.unpack("<12fH", data[offset:offset + 50])
        offset += 50
        triangle = [values[3:6], values[6:9], values[9:12]]
        ids = [vertex_id(vertex) for vertex in triangle]
        for a, b in ((ids[0], ids[1]), (ids[1], ids[2]), (ids[2], ids[0])):
            edges[tuple(sorted((a, b)))] += 1

    nonmanifold_edges = sum(1 for count in edges.values() if count != 2)
    return triangle_count, nonmanifold_edges


def _render_regular_box_stl() -> bytes:
    box = RegularBox()
    box.parseArgs(["--format=stl", "--reference=0", "--labels=false"])
    box.metadata["reproducible"] = True
    box.open()
    box.render()
    return box.close().getvalue()


def test_stl_format_is_available() -> None:
    box = boxes.Boxes()
    assert "stl" in box.formats.getFormats()
    box.parseArgs(["--format=stl"])
    assert box.output == "box.zip"


def test_stl_export_returns_zip_with_binary_stls() -> None:
    data = _render_regular_box_stl()

    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        names = archive.namelist()
        assert names
        assert all(name.endswith(".stl") for name in names)
        assert len(names) == len(set(names))
        assert any(name.startswith("part_") for name in names)

        for name in names:
            stl = archive.read(name)
            assert len(stl) > 84
            triangle_count, nonmanifold_edges = _stl_edge_stats(stl)
            assert triangle_count > 0
            assert nonmanifold_edges == 0


def test_stl_export_uses_part_labels_for_filenames() -> None:
    box = Rack19Box()
    box.parseArgs(["--format=stl", "--reference=0"])
    box.metadata["reproducible"] = True
    box.open()
    box.render()
    data = box.close().getvalue()

    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        names = set(archive.namelist())
        assert {"front.stl", "back.stl", "bottom.stl"} <= names
