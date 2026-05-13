import * as THREE from './vendor/three.module.js';
import { OrbitControls } from './vendor/OrbitControls.js';

const state = {
    canvas: null,
    renderer: null,
    scene: null,
    camera: null,
    controls: null,
    group: null,
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
        state.initialized = true;

        function animate() {
            requestAnimationFrame(animate);
            controls.update();
            renderer.render(scene, camera);
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

function resize() {
    if (!state.initialized) return;
    const w = state.canvas.clientWidth;
    const h = state.canvas.clientHeight;
    if (w === 0 || h === 0) return;
    state.renderer.setSize(w, h, false);
    fitCamera();
}

function fitCamera() {
    if (!state.group) return;
    const box = new THREE.Box3().setFromObject(state.group);
    const size = box.getSize(new THREE.Vector3());
    const center = box.getCenter(new THREE.Vector3());
    const maxDim = Math.max(size.x, size.y, size.z, 1);
    const w = state.canvas.clientWidth || 1;
    const h = state.canvas.clientHeight || 1;
    const aspect = w / h;
    const halfH = maxDim * 0.8;
    const halfW = halfH * aspect;
    state.camera.left = -halfW;
    state.camera.right = halfW;
    state.camera.top = halfH;
    state.camera.bottom = -halfH;
    state.camera.near = -maxDim * 10;
    state.camera.far = maxDim * 10;
    const dist = maxDim * 2;
    state.camera.position.set(center.x + dist, center.y + dist, center.z + dist);
    state.camera.lookAt(center);
    state.camera.updateProjectionMatrix();
    state.controls.target.copy(center);
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
function makePanelFromPolygon(polygon, thickness, faceName) {
    const group = new THREE.Group();
    group.name = faceName;

    if (!polygon || polygon.length < 3) return group;

    // Compute bounding box so we can center the polygon about origin.
    let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
    for (const p of polygon) {
        if (p[0] < minX) minX = p[0];
        if (p[0] > maxX) maxX = p[0];
        if (p[1] < minY) minY = p[1];
        if (p[1] > maxY) maxY = p[1];
    }
    const cx = (minX + maxX) / 2;
    const cy = (minY + maxY) / 2;

    const shape = new THREE.Shape();
    shape.moveTo(polygon[0][0] - cx, polygon[0][1] - cy);
    for (let i = 1; i < polygon.length; i++) {
        shape.lineTo(polygon[i][0] - cx, polygon[i][1] - cy);
    }
    shape.closePath();

    const geom = new THREE.ExtrudeGeometry(shape, {
        depth: thickness,
        bevelEnabled: false,
        curveSegments: 4,
    });
    // Center extrusion along Z so panel mid-plane is at Z=0.
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
        const panel = makePanelFromPolygon(wall.polygon, t, entry.face);
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

function setView(name) {
    ensureInit();
    if (!state.initialized || !state.group) return;
    const box = new THREE.Box3().setFromObject(state.group);
    const size = box.getSize(new THREE.Vector3());
    const center = box.getCenter(new THREE.Vector3());
    const dist = Math.max(size.x, size.y, size.z) * 2;
    const positions = {
        iso: [dist, dist, dist],
        front: [0, 0, dist],
        side: [dist, 0, 0],
        top: [0, dist, 0.0001],
    };
    const p = positions[name] || positions.iso;
    state.camera.position.set(center.x + p[0], center.y + p[1], center.z + p[2]);
    state.controls.target.copy(center);
    state.camera.lookAt(center);
}

function show() {
    ensureInit();
    if (state.initialized) resize();
}

window.preview3d = { build, setView, show };
window.preview3dView = setView;
