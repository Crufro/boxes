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

import copy

from boxes import *


class CenterDividerFingerEdge(edges.FingerJointEdge):
    """Finger edge matching the two centered divider slots."""

    def __init__(self, boxes, settings, offset=0.0) -> None:
        super().__init__(boxes, settings)
        self.offset = offset

    def __call__(self, length, bedBolts=None, bedBoltSettings=None, **kw):
        s, f = self.settings.space, self.settings.finger
        style = self.settings.style

        start = 0.5 * (length - (s + f)) + self.offset
        end = length - start - 2 * f - s
        l1, l2 = self.fingerLength(self.settings.angle)
        h = l1 - l2

        self.edge(start, tabs=1)
        self.draw_finger(f, h, style, True, True)
        self.edge(s)
        self.draw_finger(f, h, style, True, False)
        self.edge(end, tabs=1)


class DualDellMicro1URackMount(Boxes):
    """Closed box with screw on top for mounting two Dell Micro PCs in a 1U 19" rack."""

    ui_group = "Box"

    def __init__(self) -> None:
        Boxes.__init__(self)
        self.addSettingsArgs(edges.FingerJointSettings, surroundingspaces=0.5)
        self.argparser.add_argument(
            "--depth", action="store", type=float, default=200.,
            help="inner depth in mm")
        self.argparser.add_argument(
            "--front_thickness", action="store", type=float, default=0.0,
            help="thickness of the front panel in mm (defaults to material thickness)")
        self.argparser.add_argument(
            "--height", action="store", type=int, default=1,
            choices=list(range(1, 17)),
            help="height in rack units")
        self.argparser.add_argument(
            "--triangle", action="store", type=float, default=25.,
            help="Sides of the corner support triangles in mm")

    def _setup_front_finger_joints(self):
        front_t = self.front_thickness or self.thickness
        self.front_t = front_t

        front_finger_settings = copy.deepcopy(self.edges["f"].settings)
        front_finger_settings.thickness = front_t
        front_finger_edge = front_finger_settings.edgeObjects(self, add=False)[0]
        front_finger_edge.char = "g"
        self.addPart(front_finger_edge)

        front_panel_settings = copy.deepcopy(self.edges["f"].settings)
        front_panel_edges = front_panel_settings.edgeObjects(self, add=False)
        front_panel_edges[1].char = "G"
        front_panel_edges[2].char = "H"
        self.addPart(front_panel_edges[1])
        self.addPart(front_panel_edges[2])
        self.frontPanelFingerHolesAt = edges.FingerHoles(self, front_panel_settings)

        self.centerDividerBackEdge = CenterDividerFingerEdge(
            self, self.edges["f"].settings)
        self.centerDividerFrontEdge = CenterDividerFingerEdge(
            self, front_finger_settings, -front_finger_settings.finger)

    def wallxCB(self, fingerHoles=None):
        t = self.thickness
        fingerHoles = fingerHoles or self.fingerHolesAt
        self.fingerHolesAt(0, self.h-1.5*t, self.triangle, 0)
        self.fingerHolesAt(self.x, self.h-1.5*t, self.triangle, 180)
        self.centerDividerFingerHoles(fingerHoles)

    def wallxFrontCB(self):
        ht = self.frontPanelFingerHolesAt.settings.thickness
        edge_width = self.frontPanelFingerHolesAt.settings.edge_width
        corner_y = self.h - edge_width - 0.5 * ht
        self.frontPanelFingerHolesAt(0, corner_y, self.triangle, 0)
        self.frontPanelFingerHolesAt(self.x, corner_y, self.triangle, 180)
        self.centerDividerFingerHoles(self.frontPanelFingerHolesAt)

    def centerDividerFingerHoles(self, fingerHoles):
        settings = fingerHoles.settings
        hole_spacing = settings.finger + settings.space
        start = 0.5 * (self.h - hole_spacing)
        with self.saved_context():
            self.moveTo(self.x / 2., start, 90)
            for pos in (0.0, hole_spacing):
                self.rectangularHole(
                    pos + 0.5 * settings.finger,
                    0,
                    settings.finger + settings.play,
                    settings.width + settings.play)

    def bottomCB(self):
        self.fingerHolesAt(self.x / 2., 0, self.y, 90)

    def wallxbCB(self): # back
        self.wallxCB()
        cable_hex_r = 9.0  # about 15.6 mm across flats for power barrels and RJ45 boots
        cable_corner_r = 1.5
        cy = self.h / 2.
        eighth = self.x / 8.
        # Both Optiplexes oriented identically; each has power on its left
        # (viewed from behind) and ethernet on its right. Pattern across
        # the back, outer-wall to outer-wall: P - E - | - P - E
        self.regularPolygonHole(
            1. * eighth, cy, r=cable_hex_r, n=6, corner_radius=cable_corner_r)
        self.regularPolygonHole(
            3. * eighth, cy, r=cable_hex_r, n=6, corner_radius=cable_corner_r)
        self.regularPolygonHole(
            5. * eighth, cy, r=cable_hex_r, n=6, corner_radius=cable_corner_r)
        self.regularPolygonHole(
            7. * eighth, cy, r=cable_hex_r, n=6, corner_radius=cable_corner_r)

    def wallxfCB(self): # front
        t = self.thickness
        for x in (8.5, self.x + 2 * 17. + 2 * t - 8.5):
            for y in (6., self.h-6.+t):
                self.rectangularHole(x, y, 10, 6.5, r=3.25)

        slot_w, slot_h, edge_margin = 184., 31., 10.
        tab_w, tab_h, fillet_r = 18., 7., 3.
        cy = (self.h + t) / 2. + 2.0
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
        self.wallxFrontCB()

    def wallyCB(self):
        t = self.thickness
        self.fingerHolesAt(0, self.h-1.5*t, self.triangle, 0)
        self.fingerHolesAt(self.y, self.h-1.5*t, self.triangle, 180)

    def _frontFlangedWall(self, x, y, edges="FFFF", flanges=None, r=0.0,
                          callback=None, move=None, label="", part_thickness=None):
        t = self.thickness

        if not flanges:
            flanges = [0.0] * 4

        while len(flanges) < 4:
            flanges.append(0.0)

        edges = [self.edges.get(e, e) for e in edges]
        edges = edges + edges
        flanges = flanges + flanges

        tw = x + edges[1].spacing() + flanges[1] + edges[3].spacing() + flanges[3]
        th = y + edges[0].spacing() + flanges[0] + edges[2].spacing() + flanges[2]

        if self.move(tw, th, move, True):
            return

        if part_thickness is not None:
            self.ctx.set_part_thickness(part_thickness)

        rl = min(r, max(flanges[-1], flanges[0]))
        self.moveTo(rl + edges[-1].margin(), edges[0].margin())

        for i in range(4):
            l = y if i % 2 else x

            rl = min(r, max(flanges[i-1], flanges[i]))
            rr = min(r, max(flanges[i], flanges[i+1]))
            self.cc(callback, i, x=-rl)
            if flanges[i]:
                if edges[i] in (self.edges["G"], self.edges["H"]):
                    self.frontPanelFingerHolesAt(
                        flanges[i-1] + edges[i-1].endWidth() - rl,
                        0.5*t + flanges[i], l, angle=0)
                self.edge(l + flanges[i-1] + flanges[i+1] +
                          edges[i-1].endWidth() + edges[i+1].startWidth() -
                          rl - rr)
            else:
                self.edge(flanges[i-1] + edges[i-1].endWidth() - rl)
                edges[i](l)
                self.edge(flanges[i+1] + edges[i+1].startWidth() - rr)
            self.corner(90, rr)
        self.move(tw, th, move, label=label)


    def _render(self, type):

        self._setup_front_finger_joints()
        t = self.thickness
        self.h = h = self.height * 44.45 - 0.787 - t
        if type == 10:
            self.x = 219.0 - 2*t
        else:
            self.x = 448.0 - 2*t
        x = self.x
        y = self.y = self.depth

        tr = self.triangle

        self.rectangularWall(y, h, "ffeg", callback=[self.wallyCB],
                             move="right", label="right")
        self._frontFlangedWall(x, h, "GGEG", callback=[self.wallxfCB], r=t,
                               flanges=[0., 17., -t, 17.], move="up", label="front",
                               part_thickness=self.front_t)
        self.rectangularWall(x, h, "fFeF", callback=[self.wallxbCB],
                             label="back")
        self.rectangularWall(y, h, "ffeg", callback=[self.wallyCB],
                             move="left up", label="left")

        self.rectangularWall(x, y, "gFFF", callback=[self.bottomCB],
                             move="up", label="bottom")
        self.rectangularWall(
            y, h,
            [self.edges["f"], self.centerDividerBackEdge,
             self.edges["e"], self.centerDividerFrontEdge],
            move="up", label="middle")

        support_r = tr
        self.rectangularTriangle(tr, tr, "gfe", r=support_r, num=2, move="right",
            callback=[None, None])
        self.rectangularTriangle(tr, tr, "ffe", r=support_r, num=2)


    def render(self):
        self._render(type=19)
