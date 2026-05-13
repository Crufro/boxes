# Copyright (C) 2013-2018 Florian Festi
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


class DualDellMicro1URackMount(Boxes):
    """Closed box with screw on top for mounting two Dell Micro PCs in a 1U 19" rack."""

    ui_group = "Box"

    def __init__(self) -> None:
        Boxes.__init__(self)
        self.addSettingsArgs(edges.FingerJointSettings, surroundingspaces=0.5)
        self.argparser.add_argument(
            "--depth", action="store", type=float, default=175.,
            help="inner depth in mm")
        self.argparser.add_argument(
            "--height", action="store", type=int, default=1,
            choices=list(range(1, 17)),
            help="height in rack units")
        self.argparser.add_argument(
            "--triangle", action="store", type=float, default=25.,
            help="Sides of the triangles holding the lid in mm")
        self.argparser.add_argument(
            "--d1", action="store", type=float, default=2.,
            help="Diameter of the inner lid screw holes in mm")
        self.argparser.add_argument(
            "--d2", action="store", type=float, default=3.,
            help="Diameter of the lid screw holes in mm")

    def wallxCB(self):
        t = self.thickness
        self.fingerHolesAt(0, self.h-1.5*t, self.triangle, 0)
        self.fingerHolesAt(self.x, self.h-1.5*t, self.triangle, 180)
        self.fingerHolesAt(self.x / 2., 0, self.h, 90)

    def bottomCB(self):
        self.fingerHolesAt(self.x / 2., 0, self.y, 90)

    def wallxbCB(self): # back
        self.wallxCB()
        power_r = 5.0      # ~10 mm hole, snug for a power barrel/cable
        ethernet_r = 7.0   # ~14 mm hole, fits an RJ45 boot
        cy = self.h / 2.
        eighth = self.x / 8.
        # Both Optiplexes oriented identically; each has power on its left
        # (viewed from behind) and ethernet on its right. Pattern across
        # the back, outer-wall to outer-wall: P - E - | - P - E
        self.hole(1. * eighth, cy, r=ethernet_r)
        self.hole(3. * eighth, cy, r=power_r)
        self.hole(5. * eighth, cy, r=ethernet_r)
        self.hole(7. * eighth, cy, r=power_r)

    def wallxfCB(self): # front
        t = self.thickness
        for x in (8.5, self.x+2*17.+2*t-8.5):
            for y in (6., self.h-6.+t):
                self.rectangularHole(x, y, 10, 6.5, r=3.25)

        slot_w, slot_h, edge_margin = 180., 31., 10.
        tab_w, tab_h, fillet_r = 18., 7., 3.
        cy = (self.h + t) / 2.
        left_cx = t + 17. + edge_margin + slot_w / 2.
        right_cx = t + 17. + self.x - edge_margin - slot_w / 2.
        # left slot: L-shape with notch at top-left, fillet at inner corner
        with self.saved_context():
            BL_x = left_cx - slot_w / 2.
            BL_y = cy - slot_h / 2.
            self.moveTo(BL_x + slot_w / 2., BL_y + self.burn, 180)
            self.polyline(
                slot_w / 2.,
                -90,
                slot_h - tab_h,
                -90,
                tab_w - fillet_r,
                (90, fillet_r),
                tab_h - fillet_r,
                -90,
                slot_w - tab_w,
                -90,
                slot_h,
                -90,
                slot_w / 2.,
            )
        # right slot: L-shape with notch at top-right, fillet at inner corner
        with self.saved_context():
            BL_x = right_cx - slot_w / 2.
            BL_y = cy - slot_h / 2.
            self.moveTo(BL_x + slot_w / 2., BL_y + self.burn, 180)
            self.polyline(
                slot_w / 2.,
                -90,
                slot_h,
                -90,
                slot_w - tab_w,
                -90,
                tab_h - fillet_r,
                (90, fillet_r),
                tab_w - fillet_r,
                -90,
                slot_h - tab_h,
                -90,
                slot_w / 2.,
            )

        self.moveTo(t+17., t)
        self.wallxCB()

    def wallyCB(self):
        t = self.thickness
        self.fingerHolesAt(0, self.h-1.5*t, self.triangle, 0)
        self.fingerHolesAt(self.y, self.h-1.5*t, self.triangle, 180)


    def _render(self, type):

        t = self.thickness
        self.h = h = self.height * 44.45 - 0.787 - t
        if type == 10:
            self.x = 219.0 - 2*t
        else:
            self.x = 448.0 - 2*t
        x = self.x
        y = self.y = self.depth

        d1, d2 =self.d1, self.d2
        tr = self.triangle
        trh = tr / 3.

        self.rectangularWall(y, h, "ffef", callback=[self.wallyCB],
                             move="right", label="right")
        self.flangedWall(x, h, "FFEF", callback=[self.wallxfCB], r=t,
                         flanges=[0., 17., -t, 17.], move="up", label="front")
        self.rectangularWall(x, h, "fFeF", callback=[self.wallxbCB],
                             label="back")
        self.rectangularWall(y, h, "ffef", callback=[self.wallyCB],
                             move="left up", label="left")

        self.rectangularWall(x, y, "fFFF", callback=[self.bottomCB],
                             move="up", label="bottom")
        self.rectangularWall(y, h, "ffef", move="up", label="middle")
        self.rectangularWall(x, y, callback=[
            lambda:self.hole(trh, trh, d=d2)] * 4, move='right', label="lid")

        self.rectangularTriangle(tr, tr, "ffe", num=4,
            callback=[None, lambda: self.hole(trh, trh, d=d1)])


    def render(self):
        self._render(type=19)
