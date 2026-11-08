"""Blender demo (architect, contemporary villa): replay a modeling session step by step, each step a named entry in
Edit > Undo History. Mid-session the architect deletes the pool and the wooden deck by mistake (meant to hide them),
then keeps working (carport, trees, darker cladding, sun, camera). Undo must bring the pool and deck back from the
past without losing anything done since.

run: Blender --factory-startup demo/blender/villa_martin.blend --python demo/blender/villa_demo.py
env: VILLA_SPEED, VILLA_DELAY, VILLA_AUTOSTART=0, VILLA_LOG, VILLA_SELFTEST=1, VILLA_UI_SCALE, VILLA_SHADING
"""
import math
import os
import time

import bpy

SPEED = float(os.environ.get("VILLA_SPEED", "1.0"))
LOG = os.environ.get("VILLA_LOG", "")


def log(msg):
    line = f"VILLA {time.time():.3f} {msg}"
    print(line, flush=True)
    if LOG:
        with open(LOG, "a") as f:
            f.write(line + "\n")


def mat(name, rgb, rough=0.6, metal=0.0, alpha=1.0, emit=0.0):
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    m.diffuse_color = (*rgb, alpha)
    m.roughness = rough
    m.metallic = metal
    m.use_nodes = True
    b = m.node_tree.nodes.get("Principled BSDF")
    if b:
        b.inputs["Base Color"].default_value = (*rgb, 1)
        b.inputs["Roughness"].default_value = rough
        b.inputs["Metallic"].default_value = metal
        if alpha < 1:
            b.inputs["Alpha"].default_value = alpha
            b.inputs["Transmission Weight"].default_value = 0.9
        if emit:
            b.inputs["Emission Color"].default_value = (*rgb, 1)
            b.inputs["Emission Strength"].default_value = emit
    if alpha < 1:
        try:
            m.surface_render_method = "BLENDED"
        except Exception:
            pass
    return m


def give(names, m):
    for n in names:
        o = bpy.data.objects[n]
        o.data.materials.clear()
        o.data.materials.append(m)


def active():
    return bpy.context.view_layer.objects.active


def sel(o):
    for x in bpy.context.view_layer.objects:
        x.select_set(False)
    o.select_set(True)
    bpy.context.view_layer.objects.active = o


def box(name, size, loc):
    bpy.ops.mesh.primitive_cube_add(size=1, location=loc)
    o = active()
    o.name = name
    o.scale = size
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    return o


def array(o, count, offset, name="Array"):
    m = o.modifiers.new(name, "ARRAY")
    m.count = count
    m.use_relative_offset = False
    m.use_constant_offset = True
    m.constant_offset_displace = offset
    return m


def cut(target, name, size, loc):
    c = box(name, size, loc)
    c.display_type = "WIRE"
    c.hide_render = True
    m = bpy.data.objects[target].modifiers.new(name, "BOOLEAN")
    m.operation = "DIFFERENCE"
    m.object = c
    m.solver = "EXACT"
    c.hide_set(True)


# ------------------------------------------------------------------------------------------------------------------
# dimensions (m): ground floor 20 x 11, upper floor 15 x 9 cantilevered 4 m over the pool side, 3.2 m storeys
GF_L, GF_W, GF_H = 20.0, 11.0, 3.2
UP_L, UP_W, UP_H = 15.0, 9.0, 3.0
SL = 0.35  # slab thickness
Z1 = 0.4 + GF_H  # underside of the first-floor slab
Z2 = Z1 + SL + UP_H  # underside of the roof slab
UP_X = 5.5  # upper volume shifted east -> cantilever


def s_clear():
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete()


def s_lawn():
    bpy.ops.mesh.primitive_plane_add(size=1, location=(0, -4, 0))
    o = active()
    o.name = "Ground"
    o.scale = (70, 50, 1)
    bpy.ops.object.transform_apply(scale=True)


def s_plinth():
    box("Concrete base", (GF_L + 1.0, GF_W + 1.0, 0.4), (0, 0, 0.2))


def s_gf_walls():  # ground floor: solid back (north) wall and side walls, fully glazed south
    box("North wall", (GF_L, 0.3, GF_H), (0, GF_W / 2 - 0.15, 0.4 + GF_H / 2))
    box("West wall", (0.3, GF_W - 0.3, GF_H), (-GF_L / 2 + 0.15, 0.15, 0.4 + GF_H / 2))
    box("East wall", (0.3, GF_W - 0.3, GF_H), (GF_L / 2 - 0.15, 0.15, 0.4 + GF_H / 2))


def s_gf_glass():  # 18 m glass front with mullions every 2.25 m
    box("Glass facade", (GF_L - 0.6, 0.06, GF_H - 0.1), (0, -GF_W / 2 + 0.6, 0.4 + GF_H / 2))
    m = box("Mullion", (0.08, 0.14, GF_H - 0.1), (-GF_L / 2 + 0.3, -GF_W / 2 + 0.6, 0.4 + GF_H / 2))
    array(m, 9, (2.425, 0, 0))


def s_slab1():
    box("Upper slab", (GF_L + 1.6, GF_W + 1.6, SL), (0, 0, Z1 + SL / 2))


def s_upper():
    box("Upper volume", (UP_L, UP_W, UP_H), (UP_X, 0.5, Z1 + SL + UP_H / 2))


def s_upper_window():  # long horizontal window strip on the south face of the upper volume
    cut("Upper volume", "Window cutout", (12.0, 1.0, 1.4), (UP_X + 0.5, 0.5 - UP_W / 2, Z1 + SL + 1.6))
    box("Upper glazing", (12.0, 0.05, 1.4), (UP_X + 0.5, 0.5 - UP_W / 2 + 0.15, Z1 + SL + 1.6))


def s_pillars():  # 3 steel columns under the 4 m cantilever
    bpy.ops.mesh.primitive_cylinder_add(vertices=24, radius=0.12, depth=Z1 - 0.4, location=(GF_L / 2 + 2.6, -3.5, 0.4 + (Z1 - 0.4) / 2))
    o = active()
    o.name = "Columns"
    array(o, 3, (0, 3.8, 0))


def s_cantilever():  # upper volume continues 4 m beyond the ground floor (east)
    box("Cantilever", (4.0, UP_W, UP_H), (GF_L / 2 + 2.0 + 0.8, 0.5, Z1 + SL + UP_H / 2))
    box("Cantilever slab", (4.6, UP_W + 0.6, SL), (GF_L / 2 + 2.6, 0.5, Z1 + SL / 2))


def s_roof():
    box("Roof", (UP_L + 4.0 + 1.4, UP_W + 1.4, 0.3), (UP_X + 2.0, 0.5, Z2 + 0.15))


def s_cladding():  # vertical timber slats on the south face of the cantilever and the upper volume
    slat = box("Wood cladding", (0.05, 0.1, UP_H - 0.2), (UP_X - UP_L / 2 + 0.2, 0.5 - UP_W / 2 - 0.08, Z1 + SL + UP_H / 2))
    array(slat, 79, (0.21, 0, 0))
    cut("Wood cladding", "Cladding cutout", (12.0, 1.0, 1.45), (UP_X + 0.5, 0.5 - UP_W / 2, Z1 + SL + 1.6))


def s_stairs():  # three entrance steps up to the plinth, west side
    for k in range(3):
        top = 0.4 * (k + 1) / 3
        box("Stairs" if k == 0 else f"Step {k}", (0.38, 2.4, top), (-GF_L / 2 - 0.5 - 0.38 * (2 - k) - 0.19, -2.0, top / 2))


def s_pool():  # pool basin (concrete coping) + water, south of the house
    box("Pool", (14.0, 4.4, 0.45), (-1.0, -GF_W / 2 - 6.0, 0.225))
    cut("Pool", "Basin cutout", (13.0, 3.4, 1.0), (-1.0, -GF_W / 2 - 6.0, 0.7))
    sel(bpy.data.objects["Pool"])
    bpy.ops.object.modifier_apply(modifier="Basin cutout")
    bpy.data.objects.remove(bpy.data.objects["Basin cutout"])
    box("Water", (13.0, 3.4, 0.05), (-1.0, -GF_W / 2 - 6.0, 0.38))


def s_deck():  # timber deck between the glass front and the pool, 0.14 m boards
    b = box("Wood deck", (20.0, 0.14, 0.06), (-1.0, -GF_W / 2 - 0.3, 0.37))
    array(b, 22, (0, -0.16, 0))


def s_mat_concrete():
    m = mat("Light concrete", (0.72, 0.71, 0.68), rough=0.9)
    give(["Concrete base", "Upper slab", "Roof", "Cantilever slab", "Stairs", "Step 1", "Step 2", "Pool"], m)


def s_mat_render():
    give(["North wall", "West wall", "East wall", "Upper volume", "Cantilever"], mat("White plaster", (0.9, 0.9, 0.88), rough=0.85))


def s_mat_glass():
    give(["Glass facade", "Upper glazing"], mat("Glass", (0.42, 0.56, 0.64), rough=0.05, alpha=0.45))
    give(["Mullion", "Columns"], mat("Black steel", (0.04, 0.04, 0.045), rough=0.4, metal=0.8))


def s_mat_wood():
    m = mat("Larch", (0.62, 0.43, 0.25), rough=0.75)
    give(["Wood cladding", "Wood deck"], m)


def s_mat_water_lawn():
    give(["Water"], mat("Water", (0.1, 0.45, 0.62), rough=0.02, alpha=0.75))
    give(["Ground"], mat("Lawn", (0.22, 0.36, 0.16), rough=0.95))


# --- the mistake: she meant to hide the pool and the deck (H) to work on the facade, pressed X ---------------------
MISTAKE = ("Pool", "Water", "Wood deck")


def s_select():
    for x in bpy.context.view_layer.objects:
        x.select_set(False)
    for n in MISTAKE:
        bpy.data.objects[n].select_set(True)
    bpy.context.view_layer.objects.active = bpy.data.objects["Pool"]


def s_delete():
    bpy.ops.object.delete()


# --- work done AFTER the mistake (must survive the recovery) ----------------------------------------------------
def s_carport():
    box("Carport", (7.0, 6.0, 0.25), (-GF_L / 2 - 5.5, 1.5, 2.9))
    bpy.ops.mesh.primitive_cylinder_add(vertices=16, radius=0.09, depth=2.8, location=(-GF_L / 2 - 8.6, -1.2, 1.4))
    p = active()
    p.name = "Carport posts"
    array(p, 2, (0, 5.4, 0))
    give(["Carport"], bpy.data.materials["Light concrete"])
    give(["Carport posts"], bpy.data.materials["Black steel"])


def s_trees():
    leaf = mat("Foliage", (0.18, 0.32, 0.14), rough=0.9)
    bark = mat("Bark", (0.25, 0.18, 0.12), rough=0.9)
    for k, (x, y, r) in enumerate([(-18, -12, 2.2), (-15, 9, 2.6), (19, 10, 2.4), (22, -9, 2.0), (6, 13, 2.8)]):
        bpy.ops.mesh.primitive_cylinder_add(vertices=12, radius=0.18, depth=3.0, location=(x, y, 1.5))
        t = active()
        t.name = f"Trunk {k + 1}"
        t.data.materials.append(bark)
        bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=3, radius=r, location=(x, y, 3.0 + r * 0.8))
        c = active()
        c.name = f"Tree {k + 1}"
        c.scale = (1, 1, 1.15)
        c.data.materials.append(leaf)
        bpy.ops.object.shade_smooth()


def s_move_roof():  # second mistake: G Z 3 on the roof instead of the carport roof
    t = bpy.data.objects["Roof"]
    sel(t)
    t.location.z += 3.0


def s_dark_cladding():
    give(["Wood cladding"], mat("Charred wood", (0.09, 0.075, 0.065), rough=0.7))


def s_sun():
    bpy.ops.object.light_add(type="SUN", location=(-30, 22, 14))
    active().name = "Sun"
    active().rotation_euler = (math.radians(48), 0, math.radians(30))
    active().data.energy = 4


def s_camera():
    bpy.ops.object.camera_add(location=(30, -38, 12))
    o = active()
    o.name = "Client camera"
    from mathutils import Vector

    o.rotation_euler = (Vector((0, -3, 3)) - o.location).to_track_quat("-Z", "Y").to_euler()


# (Undo History message, delay before the step in seconds, function)
def _all(*fns):
    def run():
        for f in fns:
            f()
    return run


STEPS = [
    ("Add Plane", 0.0, _all(s_lawn, s_plinth)),
    ("Add Cube", 1.4, _all(s_gf_walls, s_gf_glass)),
    ("Add Cube", 1.4, _all(s_slab1, s_upper)),
    ("Add Boolean Modifier", 1.4, s_upper_window),
    ("Add Cube", 1.4, _all(s_cantilever, s_roof)),
    ("Add Cylinder", 1.3, s_pillars),
    ("Add Array Modifier", 1.5, s_cladding),
    ("Add Cube", 1.2, s_stairs),
    ("Boolean", 1.5, s_pool),
    ("Add Array Modifier", 1.4, s_deck),
    ("Material: White plaster", 1.3, _all(s_mat_concrete, s_mat_render, s_mat_glass)),
    ("Material: Larch", 1.3, _all(s_mat_wood, s_mat_water_lawn, s_select)),  # just textured: selected
    ("Select", 2.0, s_select),
    ("Delete", 1.0, s_delete),
    ("Add Cube", 2.2, s_carport),
    ("Add Ico Sphere", 1.6, s_trees),
    ("Material: Charred wood", 1.6, s_dark_cladding),
    ("Add Sun", 1.4, s_sun),
    ("Add Camera", 1.3, s_camera),
]


def selftest():
    """Recover the deleted objects the way the agent should: history back to 'Select', copy, history to the top, paste."""
    names = lambda: sorted(o.name for o in bpy.data.objects if o.visible_get())  # noqa: E731
    n = len(STEPS)
    sel_idx = [i for i, (m, _, _) in enumerate(STEPS) if m == "Select"][0]
    log(f"before: {len(names())} {[x for x in MISTAKE if x in names()]}")
    bpy.ops.ed.undo_history(item=sel_idx + 1)
    log(f"at Select: selected={[o.name for o in bpy.context.selected_objects]}")
    bpy.ops.view3d.copybuffer()
    bpy.ops.ed.undo_history(item=n)
    log(f"back at top: {len(names())} carport={'Carport' in names()}")
    bpy.ops.view3d.pastebuffer()
    log(f"after paste: {len(names())} {[x for x in MISTAKE if x in names()]} carport={'Carport' in names()}")
    log(f"roof z={bpy.data.objects['Roof'].location.z:.2f}")


def setup_view(area):
    from mathutils import Euler

    sp = area.spaces.active
    sh = sp.shading
    sh.type = os.environ.get("VILLA_SHADING", "SOLID")
    if sh.type == "SOLID":
        sh.color_type = "MATERIAL"
        sh.light = "STUDIO"
        sh.show_cavity = True
        sh.show_shadows = True
        sh.shadow_intensity = 0.6
    sp.overlay.show_floor = True
    r3d = sp.region_3d
    r3d.view_location = (1.0, -3.0, 2.5)
    r3d.view_distance = 37
    r3d.view_rotation = Euler((math.radians(64), 0, math.radians(33)), "XYZ").to_quaternion()
    r3d.view_perspective = "PERSP"
    sp.lens = 40


class VILLA_OT_demo(bpy.types.Operator):
    bl_idname = "wm.villa_demo"
    bl_label = "Villa demo"

    def invoke(self, context, event):
        self.i = 0
        self.next = time.time() + 0.5
        self._t = context.window_manager.event_timer_add(0.05, window=context.window)
        context.window_manager.modal_handler_add(self)
        log("start")
        return {"RUNNING_MODAL"}

    def modal(self, context, event):
        if event.type == "ESC":
            return self.finish(context)
        if event.type != "TIMER" or time.time() < self.next:
            return {"PASS_THROUGH"}
        msg, _, fn = STEPS[self.i]
        fn()
        bpy.ops.ed.undo_push(message=msg)
        log(f"step {self.i} {msg}")
        self.i += 1
        if self.i >= len(STEPS):
            return self.finish(context)
        self.next = time.time() + STEPS[self.i][1] * SPEED
        return {"PASS_THROUGH"}

    def finish(self, context):
        context.window_manager.event_timer_remove(self._t)
        log("done")
        if os.environ.get("VILLA_SELFTEST") == "1":
            selftest()
        return {"FINISHED"}


def kickoff():
    bpy.context.preferences.view.ui_scale = float(os.environ.get("VILLA_UI_SCALE", "1.25"))
    win = bpy.context.window_manager.windows[0]
    area = next(a for a in win.screen.areas if a.type == "VIEW_3D")
    region = next(r for r in area.regions if r.type == "WINDOW")
    with bpy.context.temp_override(window=win, area=area, region=region, screen=win.screen):
        setup_view(area)
        if os.environ.get("VILLA_AUTOSTART", "1") == "1":
            bpy.ops.wm.villa_demo("INVOKE_DEFAULT")
    return None


if not bpy.app.background:
    bpy.utils.register_class(VILLA_OT_demo)
    bpy.app.timers.register(kickoff, first_interval=float(os.environ.get("VILLA_DELAY", "2.0")))
