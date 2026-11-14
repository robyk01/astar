import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';

export class MarsScene {
  constructor(container, onTerrainClick) {
    this.container = container;
    this.onTerrainClick = onTerrainClick;

    this.scene = new THREE.Scene();
    this.scene.background = new THREE.Color(0x07090e);
    this.scene.fog = new THREE.FogExp2(0x07090e, 0.0018);

    this.camera = new THREE.PerspectiveCamera(
      50,
      container.clientWidth / container.clientHeight,
      0.1,
      2000
    );
    this.camera.position.set(0, 140, 170);

    this.renderer = new THREE.WebGLRenderer({ antialias: true });
    this.renderer.setSize(container.clientWidth, container.clientHeight);
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    container.appendChild(this.renderer.domElement);

    this.controls = new OrbitControls(this.camera, this.renderer.domElement);
    this.controls.enableDamping = true;
    this.controls.dampingFactor = 0.07;
    this.controls.maxPolarAngle = Math.PI / 2.05;

    // Lighting
    const ambient = new THREE.AmbientLight(0xffffff, 0.65);
    this.scene.add(ambient);

    const sun = new THREE.DirectionalLight(0xffe8d6, 1.3);
    sun.position.set(120, 180, 90);
    this.scene.add(sun);

    this.terrainMesh = null;
    this.routeLine = null;
    this.waypointGroup = new THREE.Group();
    this.scene.add(this.waypointGroup);

    this.startMarker = this._createPin(0x10b981);
    this.goalMarker = this._createPin(0xf43f5e);
    this.scene.add(this.startMarker, this.goalMarker);

    this.raycaster = new THREE.Raycaster();
    this.pointerDownPos = { x: 0, y: 0 };

    this._bindEvents();
    this._animate();
  }

  _createPin(color) {
    const group = new THREE.Group();
    const sphere = new THREE.Mesh(
      new THREE.SphereGeometry(1.6, 16, 16),
      new THREE.MeshBasicMaterial({ color })
    );
    sphere.position.y = 3.0;
    const stem = new THREE.Mesh(
      new THREE.CylinderGeometry(0.2, 0.2, 3.0, 8),
      new THREE.MeshBasicMaterial({ color })
    );
    stem.position.y = 1.5;
    group.add(sphere, stem);
    group.visible = false;
    return group;
  }

  _bindEvents() {
    window.addEventListener('resize', () => {
      this.camera.aspect = this.container.clientWidth / this.container.clientHeight;
      this.camera.updateProjectionMatrix();
      this.renderer.setSize(this.container.clientWidth, this.container.clientHeight);
    });

    this.renderer.domElement.addEventListener('pointerdown', (e) => {
      this.pointerDownPos = { x: e.clientX, y: e.clientY };
    });

    this.renderer.domElement.addEventListener('pointerup', (e) => {
      const moved = Math.hypot(e.clientX - this.pointerDownPos.x, e.clientY - this.pointerDownPos.y);
      if (moved > 5 || !this.terrainMesh) return; // Ignore drags

      const rect = this.renderer.domElement.getBoundingClientRect();
      const mouse = new THREE.Vector2(
        ((e.clientX - rect.left) / rect.width) * 2 - 1,
        -((e.clientY - rect.top) / rect.height) * 2 + 1
      );
      this.raycaster.setFromCamera(mouse, this.camera);
      const hits = this.raycaster.intersectObject(this.terrainMesh);
      if (hits.length > 0 && this.onTerrainClick) {
        const { row, col } = this.worldToGrid(hits[0].point.x, hits[0].point.z);
        this.onTerrainClick(row, col);
      }
    });
  }

  loadTerrain(terrainData, textureUrl) {
    this.terrainData = terrainData;
    const { rows, cols, full_rows, full_cols, min_elev_m, max_elev_m, heights } = terrainData;

    // Normalize world units so map is ~200 units wide
    this.worldWidth = 200;
    this.worldHeight = 200 * (full_rows / full_cols);
    this.elevScale = 22.0 / (max_elev_m - min_elev_m); // 22 units vertical relief

    const geo = new THREE.PlaneGeometry(this.worldWidth, this.worldHeight, cols - 1, rows - 1);
    geo.rotateX(-Math.PI / 2);

    const pos = geo.attributes.position;
    for (let i = 0; i < pos.count; i++) {
      const h = heights[i] ?? min_elev_m;
      pos.setY(i, (h - min_elev_m) * this.elevScale);
    }
    geo.computeVertexNormals();

    const loader = new THREE.TextureLoader();
    const tex = loader.load(textureUrl);
    tex.colorSpace = THREE.SRGBColorSpace;

    const mat = new THREE.MeshStandardMaterial({
      map: tex,
      roughness: 0.9,
      metalness: 0.05,
    });

    if (this.terrainMesh) this.scene.remove(this.terrainMesh);
    this.terrainMesh = new THREE.Mesh(geo, mat);
    this.scene.add(this.terrainMesh);
  }

  setTexture(url) {
    if (!this.terrainMesh) return;
    const tex = new THREE.TextureLoader().load(url);
    tex.colorSpace = THREE.SRGBColorSpace;
    this.terrainMesh.material.map = tex;
    this.terrainMesh.material.needsUpdate = true;
  }

  gridToWorld(row, col, elevM = null) {
    const { full_rows, full_cols, min_elev_m, stride, rows, cols, heights } = this.terrainData;
    const x = (col / (full_cols - 1) - 0.5) * this.worldWidth;
    const z = (row / (full_rows - 1) - 0.5) * this.worldHeight;

    let h = elevM;
    if (h === null) {
      const sr = Math.min(rows - 1, Math.round(row / stride));
      const sc = Math.min(cols - 1, Math.round(col / stride));
      h = heights[sr * cols + sc];
    }
    const y = (h - min_elev_m) * this.elevScale;
    return new THREE.Vector3(x, y, z);
  }

  worldToGrid(x, z) {
    const { full_rows, full_cols } = this.terrainData;
    const col = Math.round(((x / this.worldWidth) + 0.5) * (full_cols - 1));
    const row = Math.round(((z / this.worldHeight) + 0.5) * (full_rows - 1));
    return {
      row: Math.max(0, Math.min(full_rows - 1, row)),
      col: Math.max(0, Math.min(full_cols - 1, col)),
    };
  }

  setMarkers(start, goal) {
    if (!this.terrainData) return;
    if (start) {
      const p = this.gridToWorld(start.row, start.col);
      this.startMarker.position.copy(p);
      this.startMarker.visible = true;
    }
    if (goal) {
      const p = this.gridToWorld(goal.row, goal.col);
      this.goalMarker.position.copy(p);
      this.goalMarker.visible = true;
    }
  }

  renderWaypoints(waypoints) {
    this.waypointGroup.clear();
    waypoints.forEach((wp) => {
      const pos = this.gridToWorld(wp.row, wp.col, wp.elevation_m);
      const color = wp.type === 'base' ? 0x38bdf8 : 0xfbbf24;
      const dot = new THREE.Mesh(
        new THREE.SphereGeometry(1.1, 12, 12),
        new THREE.MeshBasicMaterial({ color })
      );
      dot.position.set(pos.x, pos.y + 1.2, pos.z);
      this.waypointGroup.add(dot);
    });
  }

  renderRoute(path, elevations) {
    if (this.routeLine) {
      this.scene.remove(this.routeLine);
      this.routeLine.geometry.dispose();
    }
    if (!path || path.length < 2) return;

    const points = path.map(([r, c], idx) => {
      const p = this.gridToWorld(r, c, elevations[idx]);
      p.y += 0.45; // Hover slightly above surface to prevent z-fighting
      return p;
    });

    const curve = new THREE.CatmullRomCurve3(points);
    const tubeGeo = new THREE.TubeGeometry(curve, Math.min(points.length * 2, 600), 0.45, 6, false);
    const tubeMat = new THREE.MeshBasicMaterial({ color: 0x22d3ee });
    this.routeLine = new THREE.Mesh(tubeGeo, tubeMat);
    this.scene.add(this.routeLine);
  }

  _animate() {
    requestAnimationFrame(() => this._animate());
    this.controls.update();
    this.renderer.render(this.scene, this.camera);
  }
}
