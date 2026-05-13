# Copyright (C) 2013-2014 Florian Festi
#
#   This program is free software: you can redistribute it and/or modify
#   it under the terms of the GNU General Public License as published by
#   the Free Software Foundation, either version 3 of the License, or
#   (at your option) any later version.
#
#   This program is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#   GNU General Public License for more details.
#
#   You should have received a copy of the GNU General Public License
#   along with this program.  If not, see <http://www.gnu.org/licenses/>.

from boxes import *


class OpenBox(Boxes):
    """Box with top and front open"""

    ui_group = "Box"
    supports_3d_preview = True

    def assemble3D(self):
        x, y, h = self.x, self.y, self.h
        t = self.thickness
        if not self.outside:
            x += 2 * t
            y += t   # only back face contributes thickness on Y (front is open)
            h += t   # only bottom contributes on Z (top is open)
        return {
            "kind": "cuboid",
            "dimensions": {"x": x, "y": y, "z": h},
            "thickness": t,
            "omit": ["top", "front"],
            "wall_map": [
                {"wall": 0, "face": "back"},
                {"wall": 1, "face": "left"},
                # Both side walls share the same 2D polygon (`f` on the left edge
                # mates with the back wall). When placed on the +X face the wall
                # has to be mirrored so its `f` ends up at the back of the box.
                {"wall": 2, "face": "right", "mirror_x": True},
                # Bottom panel polygon ("efff") has its flat `e` edge at the
                # polygon bottom (= front of box, which is open). The default
                # bottom placement maps polygon Y+ to world Z+ (front), so we
                # rotate 180° in-plane to swap front/back and put `e` at the
                # open front.
                {"wall": 3, "face": "bottom", "rotate": 180},
            ],
        }

    def __init__(self) -> None:
        Boxes.__init__(self)
        self.buildArgParser("x", "y", "h", "outside")
        self.argparser.add_argument(
            "--edgetype", action="store",
            type=ArgparseEdgeType("Fh"), choices=list("Fh"),
            default="F",
            help="edge type")
        self.addSettingsArgs(edges.FingerJointSettings)

    def render(self):
        x, y, h = self.x, self.y, self.h
        t = self.thickness

        if self.outside:
            x = self.adjustSize(x)
            y = self.adjustSize(y, False)
            h = self.adjustSize(h, False)

        e = self.edgetype
        self.rectangularWall(x, h, [e, e, "e", e], move="right")
        self.rectangularWall(y, h, [e, "e", "e", "f"], move="up")
        self.rectangularWall(y, h, [e, "e", "e", "f"])
        self.rectangularWall(x, y, "efff", move="left")
