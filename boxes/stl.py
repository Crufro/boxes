from __future__ import annotations

import collections
import io
import math
import re
import struct
import zipfile
from dataclasses import dataclass
from typing import Iterable

import mapbox_earcut
import numpy as np
from shapely.geometry import MultiPolygon, Point, Polygon
from shapely.geometry.polygon import orient
from shapely.validation import make_valid

from boxes.drawing import Surface


CURVE_STEP = 0.25
EPS = 1e-9


def _distance(a: tuple[float, float], b: tuple[float, float]) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _signed_area(points: list[tuple[float, float]]) -> float:
    return sum(
        a[0] * b[1] - b[0] * a[1]
        for a, b in zip(points, points[1:] + points[:1])
    ) / 2.0


def _clean_ring(points: Iterable[tuple[float, float]]) -> list[tuple[float, float]]:
    clean: list[tuple[float, float]] = []
    for point in points:
        rounded = (round(point[0], 5), round(point[1], 5))
        if not clean or _distance(rounded, clean[-1]) > 0.005:
            clean.append(rounded)
    if len(clean) > 1 and _distance(clean[0], clean[-1]) < 0.005:
        clean.pop()
    return clean


def _cubic_point(
    p0: tuple[float, float],
    p1: tuple[float, float],
    p2: tuple[float, float],
    p3: tuple[float, float],
    t: float,
) -> tuple[float, float]:
    u = 1.0 - t
    return (
        u**3 * p0[0] + 3 * u * u * t * p1[0] + 3 * u * t * t * p2[0] + t**3 * p3[0],
        u**3 * p0[1] + 3 * u * u * t * p1[1] + 3 * u * t * t * p2[1] + t**3 * p3[1],
    )


def _sample_cubic(
    p0: tuple[float, float],
    p1: tuple[float, float],
    p2: tuple[float, float],
    p3: tuple[float, float],
) -> list[tuple[float, float]]:
    chord = _distance(p0, p3)
    controls = _distance(p0, p1) + _distance(p1, p2) + _distance(p2, p3)
    steps = max(8, min(192, math.ceil(max(chord, controls) / CURVE_STEP)))
    return [_cubic_point(p0, p1, p2, p3, i / steps) for i in range(steps + 1)]


def _path_to_rings(path) -> list[list[tuple[float, float]]]:
    rings: list[list[tuple[float, float]]] = []
    current: list[tuple[float, float]] = []
    last: tuple[float, float] | None = None
    start: tuple[float, float] | None = None

    def finish_ring() -> None:
        nonlocal current, start, last
        ring = _clean_ring(current)
        if len(ring) >= 3 and abs(_signed_area(ring)) > 0.1:
            rings.append(ring)
        current = []
        start = None
        last = None

    for command in path.path:
        cmd = command[0]
        if cmd == "T":
            continue
        if cmd == "M":
            if current:
                finish_ring()
            last = (command[1], command[2])
            start = last
            current = [last]
        elif cmd == "L":
            last = (command[1], command[2])
            current.append(last)
        elif cmd == "C" and last is not None:
            end = (command[1], command[2])
            c1 = (command[3], command[4])
            c2 = (command[5], command[6])
            samples = _sample_cubic(last, c1, c2, end)
            current.extend(samples[1:])
            last = end

            if start is not None and _distance(last, start) < 0.005:
                finish_ring()

        if start is not None and last is not None and len(current) > 2:
            if _distance(last, start) < 0.005:
                finish_ring()

    if current:
        finish_ring()

    return rings


def _rings_to_polygons(rings: list[list[tuple[float, float]]]) -> list[Polygon]:
    if not rings:
        return []

    by_area = sorted(rings, key=lambda ring: abs(_signed_area(ring)), reverse=True)
    exteriors: list[list[tuple[float, float]]] = []
    holes_by_exterior: dict[int, list[list[tuple[float, float]]]] = {}

    exterior_polys: list[Polygon] = []
    for ring in by_area:
        point = Point(ring[0])
        container = None
        for i, poly in enumerate(exterior_polys):
            if poly.contains(point):
                container = i
                break
        if container is None:
            exteriors.append(ring)
            exterior_polys.append(Polygon(ring))
            holes_by_exterior[len(exteriors) - 1] = []
        else:
            holes_by_exterior[container].append(ring)

    polygons: list[Polygon] = []
    for i, exterior in enumerate(exteriors):
        polygon = Polygon(exterior, holes_by_exterior[i]).buffer(0)
        if polygon.is_empty:
            polygon = make_valid(Polygon(exterior, holes_by_exterior[i]))

        if isinstance(polygon, Polygon):
            polygons.append(orient(polygon, 1.0))
        elif isinstance(polygon, MultiPolygon):
            polygons.extend(orient(poly, 1.0) for poly in polygon.geoms if poly.area > 0.1)
        else:
            polygons.extend(
                orient(poly, 1.0)
                for poly in getattr(polygon, "geoms", [])
                if isinstance(poly, Polygon) and poly.area > 0.1
            )

    return polygons


def _normal(
    a: tuple[float, float, float],
    b: tuple[float, float, float],
    c: tuple[float, float, float],
) -> tuple[float, float, float]:
    ux, uy, uz = b[0] - a[0], b[1] - a[1], b[2] - a[2]
    vx, vy, vz = c[0] - a[0], c[1] - a[1], c[2] - a[2]
    nx, ny, nz = uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx
    length = math.sqrt(nx * nx + ny * ny + nz * nz)
    if length < EPS:
        return (0.0, 0.0, 0.0)
    return (nx / length, ny / length, nz / length)


def _triangle_area_xy(
    a: tuple[float, float],
    b: tuple[float, float],
    c: tuple[float, float],
) -> float:
    return ((b[0] - a[0]) * (c[1] - a[1]) -
            (b[1] - a[1]) * (c[0] - a[0])) / 2.0


def _polygon_facets(
    polygon: Polygon,
    thickness: float,
) -> list[tuple[tuple[float, float, float], ...]]:
    rings: list[list[tuple[float, float]]] = []
    exterior = _clean_ring(list(polygon.exterior.coords)[:-1])
    if _signed_area(exterior) < 0:
        exterior.reverse()
    rings.append(exterior)

    for interior in polygon.interiors:
        hole = _clean_ring(list(interior.coords)[:-1])
        if _signed_area(hole) > 0:
            hole.reverse()
        rings.append(hole)

    points: list[tuple[float, float]] = []
    ring_ends: list[int] = []
    for ring in rings:
        points.extend(ring)
        ring_ends.append(len(points))

    coords = np.array(points, dtype=np.float64)
    indices = [int(i) for i in mapbox_earcut.triangulate_float64(
        coords, np.array(ring_ends, dtype=np.uint32))]

    facets: list[tuple[tuple[float, float, float], ...]] = []
    boundary_directions: dict[tuple[int, int], tuple[int, int]] = {}
    edge_counts: collections.Counter[tuple[int, int]] = collections.Counter()

    for i in range(0, len(indices), 3):
        ia, ib, ic = indices[i:i + 3]
        a = tuple(coords[ia])
        b = tuple(coords[ib])
        c = tuple(coords[ic])
        if _triangle_area_xy(a, b, c) < 0:
            ib, ic = ic, ib
            b, c = c, b

        facets.append(((a[0], a[1], thickness), (b[0], b[1], thickness), (c[0], c[1], thickness)))
        facets.append(((a[0], a[1], 0.0), (c[0], c[1], 0.0), (b[0], b[1], 0.0)))

        for u, v in ((ia, ib), (ib, ic), (ic, ia)):
            key = tuple(sorted((u, v)))
            edge_counts[key] += 1
            boundary_directions[key] = (u, v)

    for key, count in edge_counts.items():
        if count != 1:
            continue
        u, v = boundary_directions[key]
        p0 = tuple(coords[u])
        p1 = tuple(coords[v])
        b0 = (p0[0], p0[1], 0.0)
        b1 = (p1[0], p1[1], 0.0)
        t0 = (p0[0], p0[1], thickness)
        t1 = (p1[0], p1[1], thickness)
        facets.append((b0, b1, t1))
        facets.append((b0, t1, t0))

    return facets


def _validate_facets(
    facets: list[tuple[tuple[float, float, float], ...]],
    name: str,
) -> None:
    vertices: dict[tuple[float, float, float], int] = {}
    edges: collections.Counter[tuple[int, int]] = collections.Counter()

    def vertex_id(vertex: tuple[float, float, float]) -> int:
        key = tuple(round(v, 5) for v in vertex)
        if key not in vertices:
            vertices[key] = len(vertices)
        return vertices[key]

    for facet in facets:
        ids = [vertex_id(vertex) for vertex in facet]
        for a, b in ((ids[0], ids[1]), (ids[1], ids[2]), (ids[2], ids[0])):
            edges[tuple(sorted((a, b)))] += 1

    bad_edges = sum(1 for count in edges.values() if count != 2)
    if bad_edges:
        raise ValueError(f"Could not create watertight STL for {name}: {bad_edges} non-manifold edges")


def _write_binary_stl(
    facets: list[tuple[tuple[float, float, float], ...]],
    name: str,
) -> bytes:
    data = io.BytesIO()
    header = f"{name} generated by Boxes.py; units mm".encode("ascii", "replace")[:80]
    data.write(header + b" " * (80 - len(header)))
    data.write(struct.pack("<I", len(facets)))
    for a, b, c in facets:
        data.write(struct.pack("<12fH", *(_normal(a, b, c) + a + b + c), 0))
    return data.getvalue()


def _safe_name(name: str, used: set[str], index: int) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", name.strip()).strip("._")
    if not cleaned or cleaned == "part":
        cleaned = f"part_{index:03d}"
    candidate = cleaned
    suffix = 2
    while candidate in used:
        candidate = f"{cleaned}_{suffix}"
        suffix += 1
    used.add(candidate)
    return candidate


@dataclass
class STLPart:
    name: str
    facets: list[tuple[tuple[float, float, float], ...]]


class STLSurface(Surface):
    def __init__(self) -> None:
        super().__init__()
        self.thickness = 3.0

    def set_thickness(self, thickness: float) -> None:
        self.thickness = thickness

    def _part_to_stl(self, part, index: int, used: set[str]) -> STLPart | None:
        rings: list[list[tuple[float, float]]] = []
        for path in part.pathes:
            rings.extend(_path_to_rings(path))

        polygons = _rings_to_polygons(rings)
        if not polygons:
            return None

        min_x = min(poly.bounds[0] for poly in polygons)
        min_y = min(poly.bounds[1] for poly in polygons)
        normalized = [
            Polygon(
                [(x - min_x, y - min_y) for x, y in poly.exterior.coords],
                [[(x - min_x, y - min_y) for x, y in interior.coords]
                 for interior in poly.interiors],
            )
            for poly in polygons
        ]

        facets: list[tuple[tuple[float, float, float], ...]] = []
        thickness = getattr(part, "thickness", None) or self.thickness
        for polygon in normalized:
            facets.extend(_polygon_facets(polygon, thickness))

        name = _safe_name(getattr(part, "name", ""), used, index)
        _validate_facets(facets, name)
        return STLPart(name, facets)

    def finish(self, inner_corners="loop"):
        parts: list[STLPart] = []
        used: set[str] = set()
        for i, part in enumerate(self.parts, start=1):
            stl_part = self._part_to_stl(part, i, used)
            if stl_part is not None:
                parts.append(stl_part)

        if not parts:
            raise ValueError("No closed geometry found for STL export")

        data = io.BytesIO()
        with zipfile.ZipFile(data, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
            for part in parts:
                archive.writestr(f"{part.name}.stl", _write_binary_stl(part.facets, part.name))
        data.seek(0)
        return data
