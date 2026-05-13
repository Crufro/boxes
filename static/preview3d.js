import * as THREE from './vendor/three.module.js';
import { OrbitControls } from './vendor/OrbitControls.js';

const state = {
    canvas: null,
    renderer: null,
    scene: null,
    camera: null,
    controls: null,
    group: null,
    projection: 'ortho',
    cameraTween: null,
    gizmo: null,
    initialized: false,
};

const FACE_NAMES = ['front', 'back', 'left', 'right', 'top', 'bottom'];

function ensureInit() {
    if (state.initialized) return;
    const canvas = document.getElementById('preview_canvas_3d');
    if (!canvas) return;

    try {
        const scene = new THREE.Scene();
        scene.background = new THREE.Color(0xf7f7f7);

        const camera = new THREE.OrthographicCamera(-1, 1, 1, -1, 0.1, 100000);
        camera.position.set(1, 1, 1);
        camera.lookAt(0, 0, 0);

        const renderer = new THREE.WebGLRenderer({ canvas, antialias: true });
        renderer.setPixelRatio(window.devicePixelRatio || 1);
        renderer.autoClear = false;

        const hemi = new THREE.HemisphereLight(0xffffff, 0xcccccc, 0.9);
        scene.add(hemi);
        const dir = new THREE.DirectionalLight(0xffffff, 0.4);
        dir.position.set(1, 1.5, 1);
        scene.add(dir);

        const controls = new OrbitControls(camera, canvas);
        controls.enableDamping = true;
        controls.dampingFactor = 0.12;

        state.canvas = canvas;
        state.renderer = renderer;
        state.scene = scene;
        state.camera = camera;
        state.controls = controls;
        state.projection = 'ortho';
        state.initialized = true;

        buildGizmo();

        function animate() {
            requestAnimationFrame(animate);
            tickTween();
            state.controls.update();
            renderFrame();
        }
        animate();

        new ResizeObserver(() => resize()).observe(canvas);
        window.addEventListener('resize', resize);
        resize();
        console.log('[preview3d] initialized');
    } catch (err) {
        console.error('[preview3d] init failed', err);
        canvas.style.background = '#fee';
        const status = document.getElementById('preview_status');
        if (status) status.textContent = '3D init error (see console)';
    }
}

function renderFrame() {
    const renderer = state.renderer;
    const canvas = state.canvas;
    if (!renderer || !canvas) return;
    const W = canvas.width;
    const H = canvas.height;

    renderer.setScissorTest(false);
    renderer.setViewport(0, 0, W, H);
    renderer.clear(true, true, true);
    renderer.render(state.scene, state.camera);

    if (state.gizmo && state.gizmo.hitDiv) {
        const r = computeGizmoRect();
        if (r && r.w > 0 && r.h > 0) {
            updateGizmoOrientation();
            renderer.setScissorTest(true);
            renderer.setViewport(r.x, r.y, r.w, r.h);
            renderer.setScissor(r.x, r.y, r.w, r.h);
            renderer.clearDepth();
            renderer.render(state.gizmo.scene, state.gizmo.camera);
            renderer.setScissorTest(false);
        }
    }
}

function computeGizmoRect() {
    const renderer = state.renderer;
    const canvas = state.canvas;
    const hit = state.gizmo && state.gizmo.hitDiv;
    if (!hit) return null;
    const pr = renderer.getPixelRatio();
    const cBR = canvas.getBoundingClientRect();
    const gBR = hit.getBoundingClientRect();
    return {
        x: Math.round((gBR.left - cBR.left) * pr),
        y: Math.round((cBR.bottom - gBR.bottom) * pr),
        w: Math.round(gBR.width * pr),
        h: Math.round(gBR.height * pr),
    };
}

function resize() {
    if (!state.initialized) return;
    const w = state.canvas.clientWidth;
    const h = state.canvas.clientHeight;
    if (w === 0 || h === 0) return;
    state.renderer.setSize(w, h, false);
    fitCamera();
}

function computeFraming() {
    if (!state.group) return null;
    const box = new THREE.Box3().setFromObject(state.group);
    const size = box.getSize(new THREE.Vector3());
    const center = box.getCenter(new THREE.Vector3());
    const maxDim = Math.max(size.x, size.y, size.z, 1);
    return { box, size, center, maxDim };
}

function fitCamera() {
    const fr = computeFraming();
    if (!fr) return;
    const w = state.canvas.clientWidth || 1;
    const h = state.canvas.clientHeight || 1;
    const aspect = w / h;
    const dist = fr.maxDim * 2;

    if (state.projection === 'persp') {
        state.camera.aspect = aspect;
        state.camera.near = fr.maxDim * 0.01;
        state.camera.far = fr.maxDim * 100;
    } else {
        const halfH = fr.maxDim * 0.8;
        const halfW = halfH * aspect;
        state.camera.left = -halfW;
        state.camera.right = halfW;
        state.camera.top = halfH;
        state.camera.bottom = -halfH;
        state.camera.near = -fr.maxDim * 10;
        state.camera.far = fr.maxDim * 10;
    }
    state.camera.position.set(fr.center.x + dist, fr.center.y + dist, fr.center.z + dist);
    state.camera.lookAt(fr.center);
    state.camera.updateProjectionMatrix();
    state.controls.target.copy(fr.center);
    state.controls.update();
}

function clearGroup() {
    if (!state.group) return;
    state.scene.remove(state.group);
    state.group.traverse(obj => {
        if (obj.geometry) obj.geometry.dispose();
        if (obj.material) {
            if (Array.isArray(obj.material)) obj.material.forEach(m => m.dispose());
            else obj.material.dispose();
        }
    });
    state.group = null;
}

const PANEL_MATERIAL = new THREE.MeshStandardMaterial({
    color: 0xe8d9b6,
    roughness: 0.85,
    metalness: 0.0,
    flatShading: true,
    side: THREE.DoubleSide,
});

const LINE_MATERIAL = new THREE.LineBasicMaterial({ color: 0x333333 });

// Build an extruded panel from a 2D polygon (array of [x, y] points), extruded
// by `thickness` along its local +Z. Returns a Group containing the mesh +
// outline lines, with the panel centered about origin in X/Y and front face
// at local Z = +thickness/2 (so the panel sits centered on its host face).
function makePanelFromPolygon(polygon, thickness, faceName, opts = {}) {
    const group = new THREE.Group();
    group.name = faceName;

    if (!polygon || polygon.length < 3) return group;

    const sx = opts.mirrorX ? -1 : 1;
    // In-plane rotation in degrees (multiples of 90). Applied AROUND the
    // polygon's bbox center, after mirroring. Lets generators declare how
    // each captured 2D wall should be oriented relative to its 3D face.
    const rotDeg = (((opts.rotate || 0) % 360) + 360) % 360;
    const rad = rotDeg * Math.PI / 180;
    const cosR = Math.round(Math.cos(rad));
    const sinR = Math.round(Math.sin(rad));

    let bbMinX = Infinity, bbMaxX = -Infinity, bbMinY = Infinity, bbMaxY = -Infinity;
    for (const p of polygon) {
        const x = p[0] * sx;
        if (x < bbMinX) bbMinX = x;
        if (x > bbMaxX) bbMaxX = x;
        if (p[1] < bbMinY) bbMinY = p[1];
        if (p[1] > bbMaxY) bbMaxY = p[1];
    }
    const cx = (bbMinX + bbMaxX) / 2;
    const cy = (bbMinY + bbMaxY) / 2;

    // Mirroring reverses winding; flipping order keeps it consistent for
    // THREE.Shape triangulation. 90°/180° rotations preserve winding.
    const pts = opts.mirrorX ? polygon.slice().reverse() : polygon;

    function project(p) {
        const x = p[0] * sx - cx;
        const y = p[1] - cy;
        return [x * cosR - y * sinR, x * sinR + y * cosR];
    }

    const shape = new THREE.Shape();
    const first = project(pts[0]);
    shape.moveTo(first[0], first[1]);
    for (let i = 1; i < pts.length; i++) {
        const q = project(pts[i]);
        shape.lineTo(q[0], q[1]);
    }
    shape.closePath();

    const geom = new THREE.ExtrudeGeometry(shape, {
        depth: thickness,
        bevelEnabled: false,
        curveSegments: 4,
    });
    geom.translate(0, 0, -thickness / 2);

    const mesh = new THREE.Mesh(geom, PANEL_MATERIAL);
    group.add(mesh);

    const edgesGeom = new THREE.EdgesGeometry(geom, 20);
    const lines = new THREE.LineSegments(edgesGeom, LINE_MATERIAL);
    group.add(lines);

    return group;
}

// Place a panel (initially in local XY plane, extruded along Z) onto one of
// the six faces of a cuboid sized {x, y, z}. World axes: X=width, Y=height,
// Z=depth (front is +Z).
function placeOnFace(panel, faceName, dims, t) {
    const { x, y, z } = dims;
    switch (faceName) {
        case 'front':
            panel.position.set(0, 0, y / 2 - t / 2);
            break;
        case 'back':
            panel.position.set(0, 0, -y / 2 + t / 2);
            panel.rotation.y = Math.PI;
            break;
        case 'right':
            panel.position.set(x / 2 - t / 2, 0, 0);
            panel.rotation.y = Math.PI / 2;
            break;
        case 'left':
            panel.position.set(-x / 2 + t / 2, 0, 0);
            panel.rotation.y = -Math.PI / 2;
            break;
        case 'top':
            panel.position.set(0, z / 2 - t / 2, 0);
            panel.rotation.x = -Math.PI / 2;
            break;
        case 'bottom':
            panel.position.set(0, -z / 2 + t / 2, 0);
            panel.rotation.x = Math.PI / 2;
            break;
    }
}

function buildCuboid(topology, walls) {
    const dims = topology.dimensions;
    const t = topology.thickness;
    const wallMap = topology.wall_map || [];
    const group = new THREE.Group();

    for (const entry of wallMap) {
        const wall = walls[entry.wall];
        if (!wall || !wall.polygon) continue;
        const panel = makePanelFromPolygon(wall.polygon, t, entry.face, {
            mirrorX: !!entry.mirror_x,
            rotate: entry.rotate || 0,
        });
        placeOnFace(panel, entry.face, dims, t);
        group.add(panel);
    }

    return group;
}

function build(payload) {
    ensureInit();
    if (!state.initialized) return;
    clearGroup();
    const topology = payload && payload.topology;
    if (!topology) {
        console.warn('[preview3d] no topology in payload', payload);
        return;
    }
    if (topology.kind === 'cuboid') {
        const walls = (payload && payload.walls) || [];
        state.group = buildCuboid(topology, walls);
        state.scene.add(state.group);
        console.log('[preview3d] built cuboid', topology.dimensions, 'walls=', walls.length);
        resize();
        requestAnimationFrame(resize);
    }
}

// === View navigation ===

const NAMED_VIEWS = {
    iso:    [1, 1, 1],
    front:  [0, 0, 1],
    back:   [0, 0, -1],
    side:   [1, 0, 0],
    right:  [1, 0, 0],
    left:   [-1, 0, 0],
    top:    [0, 1, 0],
    bottom: [0, -1, 0],
};

// Pick a screen-up vector for a given view direction. Projects world +Y onto
// the plane perpendicular to the view direction so that for most views the
// up axis matches OrbitControls' default. For straight up/down views the
// projection is degenerate, so fall back to ±Z (Blender convention: FRONT
// face at the bottom of the screen when looking down).
function computeTargetUp(viewDir) {
    const Y = new THREE.Vector3(0, 1, 0);
    const proj = Y.clone().addScaledVector(viewDir, -Y.dot(viewDir));
    if (proj.lengthSq() < 1e-4) {
        return new THREE.Vector3(0, 0, viewDir.y < 0 ? -1 : 1);
    }
    return proj.normalize();
}

function snapToDirection(dirVec) {
    ensureInit();
    if (!state.initialized || !state.group) return;
    const fr = computeFraming();
    if (!fr) return;
    const dist = fr.maxDim * 2;
    const offset = dirVec.clone().normalize();
    const toPos = fr.center.clone().addScaledVector(offset, dist);
    const viewDir = fr.center.clone().sub(toPos).normalize();
    const up = computeTargetUp(viewDir);
    const lookM = new THREE.Matrix4().lookAt(toPos, fr.center, up);
    const toQuat = new THREE.Quaternion().setFromRotationMatrix(lookM);

    state.cameraTween = {
        fromPos: state.camera.position.clone(),
        toPos,
        fromQuat: state.camera.quaternion.clone(),
        toQuat,
        fromTarget: state.controls.target.clone(),
        toTarget: fr.center.clone(),
        targetUp: up,
        t0: performance.now(),
        duration: 320,
    };
    state.controls.enabled = false;
}

function tickTween() {
    const tw = state.cameraTween;
    if (!tw) return;
    const k = Math.min(1, (performance.now() - tw.t0) / tw.duration);
    const e = k < 0.5 ? 2 * k * k : 1 - Math.pow(-2 * k + 2, 2) / 2;
    state.camera.position.lerpVectors(tw.fromPos, tw.toPos, e);
    state.controls.target.lerpVectors(tw.fromTarget, tw.toTarget, e);
    // Slerp orientation directly — no per-frame lookAt, so the camera rotates
    // smoothly through the up-axis pole instead of jerking around the
    // OrbitControls world-up singularity.
    state.camera.quaternion.slerpQuaternions(tw.fromQuat, tw.toQuat, e);
    if (k >= 1) {
        state.cameraTween = null;
        // Carry the new screen-up forward. If it changed materially, rebuild
        // OrbitControls so its internal world-up axis matches and the next
        // drag doesn't snap the camera back.
        if (state.camera.up.distanceToSquared(tw.targetUp) > 1e-6) {
            state.camera.up.copy(tw.targetUp);
            const target = state.controls.target.clone();
            state.controls.dispose();
            state.controls = new OrbitControls(state.camera, state.canvas);
            state.controls.enableDamping = true;
            state.controls.dampingFactor = 0.12;
            state.controls.target.copy(target);
        }
        state.controls.enabled = true;
    }
}

function setView(name) {
    const v = NAMED_VIEWS[name] || NAMED_VIEWS.iso;
    snapToDirection(new THREE.Vector3(v[0], v[1], v[2]));
}

function setProjection(mode) {
    if (!state.initialized) return;
    if (mode === state.projection) return;
    const old = state.camera;
    const w = state.canvas.clientWidth || 1;
    const h = state.canvas.clientHeight || 1;
    const aspect = w / h;
    const target = state.controls.target.clone();
    const dirVec = new THREE.Vector3().subVectors(old.position, target);
    const dist = Math.max(dirVec.length(), 1e-3);
    const fr = computeFraming();
    const maxDim = fr ? fr.maxDim : Math.max(dist, 100);

    let camNew;
    if (mode === 'persp') {
        const fov = 35;
        const halfH = (old.top - old.bottom) / 2;
        const d = halfH / Math.tan(THREE.MathUtils.degToRad(fov / 2));
        camNew = new THREE.PerspectiveCamera(fov, aspect, maxDim * 0.01, maxDim * 100);
        camNew.position.copy(target).add(dirVec.clone().normalize().multiplyScalar(d));
    } else {
        const fov = old.fov;
        const halfH = Math.tan(THREE.MathUtils.degToRad(fov / 2)) * dist;
        const halfW = halfH * aspect;
        camNew = new THREE.OrthographicCamera(-halfW, halfW, halfH, -halfH, -maxDim * 10, maxDim * 10);
        camNew.position.copy(target).add(dirVec.clone().normalize().multiplyScalar(dist));
        camNew.zoom = 1;
    }
    camNew.up.copy(old.up);
    camNew.lookAt(target);
    camNew.updateProjectionMatrix();

    state.controls.dispose();
    state.camera = camNew;
    state.controls = new OrbitControls(camNew, state.canvas);
    state.controls.enableDamping = true;
    state.controls.dampingFactor = 0.12;
    state.controls.target.copy(target);
    state.controls.update();

    state.projection = mode;
    if (state.gizmo && state.gizmo.projLabel) {
        state.gizmo.projLabel.textContent = mode === 'persp' ? 'PERSP' : 'ORTHO';
    }
    state.cameraTween = null;
}

function toggleProjection() {
    setProjection(state.projection === 'ortho' ? 'persp' : 'ortho');
}

// === Gizmo (ViewCube) ===

const GIZMO_FACE_BG = '#f0ebe0';
const GIZMO_FACE_BORDER = '#4A1A05';

function makeFaceTexture(label) {
    const sz = 128;
    const c = document.createElement('canvas');
    c.width = sz;
    c.height = sz;
    const ctx = c.getContext('2d');
    ctx.fillStyle = GIZMO_FACE_BG;
    ctx.fillRect(0, 0, sz, sz);
    ctx.lineWidth = 6;
    ctx.strokeStyle = GIZMO_FACE_BORDER;
    ctx.strokeRect(3, 3, sz - 6, sz - 6);
    ctx.fillStyle = GIZMO_FACE_BORDER;
    ctx.font = 'bold 26px system-ui, -apple-system, sans-serif';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText(label, sz / 2, sz / 2 + 1);
    const tex = new THREE.CanvasTexture(c);
    tex.anisotropy = 4;
    return tex;
}

const HOTSPOT_HIGHLIGHT = new THREE.MeshBasicMaterial({
    color: 0xffaa00,
    transparent: true,
    opacity: 0.45,
    side: THREE.DoubleSide,
    depthWrite: false,
});
const HOTSPOT_HIDDEN = new THREE.MeshBasicMaterial({ visible: false });

// For a hotspot direction component c ∈ {-1, 0, 1}, return the [min, max] range
// of the 3×3 face sector along that axis (cube extends ±0.5).
function sectorRange(c) {
    if (c === 0) return [-1 / 6, 1 / 6];
    if (c > 0) return [1 / 6, 0.5];
    return [-0.5, -1 / 6];
}

// Build a flat quad lying on the cube surface for one face contribution of a
// hotspot. `axis` ∈ 'x'|'y'|'z' picks which face surface; `sign` is ±1 (which
// side); `dir` is the hotspot's (i,j,k). The quad is sized to the 3×3 sector
// for that hotspot on that face, offset slightly outward to avoid z-fighting
// with the cube material.
function buildSectorQuad(axis, sign, dir) {
    const eps = 0.002;
    const xR = sectorRange(dir.x);
    const yR = sectorRange(dir.y);
    const zR = sectorRange(dir.z);
    let p1, p2, p3, p4;
    if (axis === 'x') {
        const x = sign * (0.5 + eps);
        p1 = [x, yR[0], zR[0]];
        p2 = [x, yR[1], zR[0]];
        p3 = [x, yR[1], zR[1]];
        p4 = [x, yR[0], zR[1]];
    } else if (axis === 'y') {
        const y = sign * (0.5 + eps);
        p1 = [xR[0], y, zR[0]];
        p2 = [xR[1], y, zR[0]];
        p3 = [xR[1], y, zR[1]];
        p4 = [xR[0], y, zR[1]];
    } else {
        const z = sign * (0.5 + eps);
        p1 = [xR[0], yR[0], z];
        p2 = [xR[1], yR[0], z];
        p3 = [xR[1], yR[1], z];
        p4 = [xR[0], yR[1], z];
    }
    const geom = new THREE.BufferGeometry();
    geom.setAttribute('position',
        new THREE.BufferAttribute(new Float32Array([...p1, ...p2, ...p3, ...p4]), 3));
    geom.setIndex([0, 1, 2, 0, 2, 3]);
    return new THREE.Mesh(geom, HOTSPOT_HIGHLIGHT);
}

function buildGizmo() {
    if (state.gizmo) return;
    const viewport = document.getElementById('preview_viewport');
    if (!viewport) return;

    let overlay = document.getElementById('preview_gizmo');
    if (!overlay) {
        overlay = document.createElement('div');
        overlay.id = 'preview_gizmo';
        overlay.innerHTML =
            '<div id="preview_gizmo_hit"></div>' +
            '<div id="preview_gizmo_proj" role="button" title="Toggle orthographic/perspective">ORTHO</div>';
        viewport.appendChild(overlay);
    }
    const hitDiv = overlay.querySelector('#preview_gizmo_hit');
    const projLabel = overlay.querySelector('#preview_gizmo_proj');

    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(28, 1, 0.1, 100);
    camera.position.set(0, 0, 3.4);
    camera.lookAt(0, 0, 0);

    // BoxGeometry material order: +X, -X, +Y, -Y, +Z, -Z
    const labels = ['RIGHT', 'LEFT', 'TOP', 'BOTTOM', 'FRONT', 'BACK'];
    const materials = labels.map(l => new THREE.MeshBasicMaterial({ map: makeFaceTexture(l) }));
    const cubeGeom = new THREE.BoxGeometry(1, 1, 1);
    const cube = new THREE.Mesh(cubeGeom, materials);
    const edges = new THREE.LineSegments(
        new THREE.EdgesGeometry(cubeGeom),
        new THREE.LineBasicMaterial({ color: 0x4A1A05 })
    );
    cube.add(edges);
    scene.add(cube);

    // 26 hotspot cubelets arranged on a 3x3x3 grid (center omitted). Each
    // occupies its own face/edge/corner region — the cubelet itself is
    // invisible (raycast-only), and a sibling highlight group renders flat
    // quads on just the relevant cube face(s) when hovered.
    const hotspots = new THREE.Group();
    const cubeletGeom = new THREE.BoxGeometry(0.34, 0.34, 0.34);
    for (let i = -1; i <= 1; i++) {
        for (let j = -1; j <= 1; j++) {
            for (let k = -1; k <= 1; k++) {
                if (i === 0 && j === 0 && k === 0) continue;
                const mesh = new THREE.Mesh(cubeletGeom, HOTSPOT_HIDDEN);
                mesh.position.set(i * 0.34, j * 0.34, k * 0.34);
                const dir = new THREE.Vector3(i, j, k);
                mesh.userData.dir = dir;
                const highlight = new THREE.Group();
                if (i !== 0) highlight.add(buildSectorQuad('x', i, dir));
                if (j !== 0) highlight.add(buildSectorQuad('y', j, dir));
                if (k !== 0) highlight.add(buildSectorQuad('z', k, dir));
                highlight.visible = false;
                cube.add(highlight);
                mesh.userData.highlight = highlight;
                hotspots.add(mesh);
            }
        }
    }
    cube.add(hotspots);

    state.gizmo = { scene, camera, cube, hotspots, hoverMesh: null, hitDiv, projLabel };

    const raycaster = new THREE.Raycaster();
    function pickHotspot(ev) {
        const rect = hitDiv.getBoundingClientRect();
        if (rect.width === 0 || rect.height === 0) return null;
        const x = (ev.clientX - rect.left) / rect.width;
        const y = (ev.clientY - rect.top) / rect.height;
        const ndc = new THREE.Vector2(x * 2 - 1, -(y * 2 - 1));
        raycaster.setFromCamera(ndc, camera);
        const hits = raycaster.intersectObjects(hotspots.children, false);
        return hits[0] || null;
    }
    function clearHover() {
        if (state.gizmo.hoverMesh) {
            state.gizmo.hoverMesh.userData.highlight.visible = false;
            state.gizmo.hoverMesh = null;
        }
    }
    hitDiv.addEventListener('pointermove', ev => {
        const hit = pickHotspot(ev);
        if (!hit) { clearHover(); return; }
        if (state.gizmo.hoverMesh === hit.object) return;
        clearHover();
        hit.object.userData.highlight.visible = true;
        state.gizmo.hoverMesh = hit.object;
    });
    hitDiv.addEventListener('pointerleave', clearHover);
    hitDiv.addEventListener('pointerdown', ev => {
        ev.preventDefault();
        ev.stopPropagation();
        const hit = pickHotspot(ev);
        if (!hit) return;
        snapToDirection(hit.object.userData.dir);
    });
    projLabel.addEventListener('pointerdown', ev => {
        ev.preventDefault();
        ev.stopPropagation();
        toggleProjection();
    });
}

function updateGizmoOrientation() {
    if (!state.gizmo) return;
    state.gizmo.cube.quaternion.copy(state.camera.quaternion).invert();
}

function show() {
    ensureInit();
    if (state.initialized) resize();
}

window.preview3d = { build, setView, show, setProjection };
window.preview3dView = setView;
