import { expect, it } from 'vitest';
import * as T from 'three';
import { repairFramelessRearDoors, repairVehicleInterior } from './teslaInterior';

it('keeps rear upper seals on the body while retaining glass and lower trim on both hinges', () => {
  const model = new T.Group(); model.position.set(2, 3, 4); model.rotation.y = .3;
  const trims: T.Mesh[] = [], windows: T.Mesh[] = [];
  for (const [i, id] of ['RL', 'RR'].entries()) {
    const door = new T.Group(); door.name = 'Door_' + id; door.position.x = i ? .7 : -.7; model.add(door);
    const material = new T.MeshStandardMaterial(); material.name = 'Satin_Black_Trim';
    const geometry = new T.PlaneGeometry(.2, .4); geometry.translate(0, 1.12, 0);
    const trim = new T.Mesh(geometry, material); door.add(trim); trims.push(trim);
    const glass = new T.Mesh(new T.PlaneGeometry(.7, .5), new T.MeshStandardMaterial());
    glass.position.set(0, 1.4, .2); door.add(glass); windows.push(glass);
  }
  repairFramelessRearDoors(model); model.updateMatrixWorld(true);
  const seals = ['RL', 'RR'].map(id => model.getObjectByName('Rear_Window_Body_Seal_' + id)!);
  const sealBefore = seals.map(seal => seal.matrixWorld.clone());
  const glassBefore = windows.map(glass => glass.getWorldPosition(new T.Vector3()));
  for (const trim of trims) {
    expect(trim.geometry.boundingBox!.max.y).toBeCloseTo(1.158, 5);
    trim.parent!.rotation.y = .8;
  }
  model.updateMatrixWorld(true);
  seals.forEach((seal, i) => { expect(seal.parent).toBe(model); expect(seal.matrixWorld.equals(sealBefore[i])).toBe(true); });
  windows.forEach((glass, i) => expect(glass.getWorldPosition(new T.Vector3()).distanceTo(glassBefore[i])).toBeGreaterThan(.1));
  repairFramelessRearDoors(model);
  expect(model.children.filter(child => child.name.startsWith('Rear_Window_Body_Seal_'))).toHaveLength(2);
});

it('keeps the rising rear belt rail on the door instead of across the opening', () => {
  const model = new T.Group();
  for (const id of ['RL', 'RR']) {
    const door = new T.Group(); door.name = 'Door_' + id; model.add(door);
    const material = new T.MeshStandardMaterial(); material.name = 'Satin_Black_Trim';
    const geometry = new T.BufferGeometry();
    // Actual asset belt-line envelope: front ~1.16 m, rear ~1.21 m.
    const x = id === 'RL' ? -.7 : .7;
    geometry.setAttribute('position', new T.Float32BufferAttribute([
      x,1.16,-.36, x,1.17,-.36, x,1.21,-1.17,
      x,1.16,-.36, x,1.21,-1.17, x,1.20,-1.17,
      x,1.45,-.4, x,1.46,-.4, x,1.5,-1.1,
    ], 3));
    door.add(new T.Mesh(geometry, material));
  }
  repairFramelessRearDoors(model);
  for (const id of ['RL', 'RR']) {
    const door = model.getObjectByName('Door_' + id)!;
    const rail = door.children[0] as T.Mesh;
    expect(rail.geometry.attributes.position.count).toBe(6);
    const seal = model.getObjectByName('Rear_Window_Body_Seal_' + id) as T.Mesh;
    expect(seal.geometry.boundingBox!.min.y).toBeGreaterThan(1.4);
    const before = new T.Vector3().fromBufferAttribute(rail.geometry.attributes.position, 0);
    door.rotation.y = 1; model.updateMatrixWorld(true);
    expect(before.clone().applyMatrix4(rail.matrixWorld).distanceTo(before)).toBeGreaterThan(.5);
  }
});

it('removes the static inner belt rail without removing cabin or roof geometry', () => {
  const model = new T.Group();
  const material = new T.MeshStandardMaterial(); material.name = 'PaletteMaterial001';
  const geometry = new T.BufferGeometry();
  geometry.setAttribute('position', new T.Float32BufferAttribute([
    -.63,1.15,-.6, -.63,1.18,-.6, -.63,1.21,-1.1,
    .63,1.15,-.6, .63,1.18,-.6, .63,1.21,-1.1,
    -.3,.8,-.6, -.3,.9,-.6, -.3,.9,-1,
    -.63,1.4,-.6, -.63,1.5,-.6, -.63,1.5,-1,
  ], 3));
  const mesh = new T.Mesh(geometry, material); model.add(mesh);
  repairVehicleInterior(model);
  expect(mesh.geometry.attributes.position.count).toBe(6);
  const positions = mesh.geometry.attributes.position;
  for (let i = 0; i < positions.count; i++) {
    expect(Math.abs(positions.getX(i)) < .54 || positions.getY(i) > 1.23).toBe(true);
  }
});

it('anchors each inner door panel into the painted door shell', () => {
  const model = new T.Group();
  for (const [i, id] of ['FL', 'FR', 'RL', 'RR'].entries()) {
    const door = new T.Group(); door.name = 'Door_' + id; door.position.x = i % 2 ? .76 : -.76; model.add(door);
  }
  repairVehicleInterior(model);
  for (const [i, id] of ['FL', 'FR', 'RL', 'RR'].entries()) {
    const door = model.getObjectByName('Door_' + id)!;
    const panel = door.getObjectByName('Door_Inner_Trim') as T.Group;
    expect(panel.parent).toBe(door);
    const skin = panel.children[0] as T.Mesh;
    const bounds = new T.Box3().setFromObject(skin);
    const shellX = (i % 2 ? 1 : -1) * .8;
    expect(bounds.min.x).toBeLessThan(shellX);
    expect(bounds.max.x).toBeGreaterThan(shellX);
    door.rotation.y = i % 2 ? -.8 : .8;
    model.updateMatrixWorld(true);
    expect(new T.Box3().setFromObject(skin).isEmpty()).toBe(false);
  }
});
