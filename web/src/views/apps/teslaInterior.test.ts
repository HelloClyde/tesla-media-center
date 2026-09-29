import { expect, it } from 'vitest';
import * as T from 'three';
import { repairFramelessRearDoors } from './teslaInterior';

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
    expect(trim.geometry.boundingBox!.max.y).toBeCloseTo(1.12, 5);
    trim.parent!.rotation.y = .8;
  }
  model.updateMatrixWorld(true);
  seals.forEach((seal, i) => { expect(seal.parent).toBe(model); expect(seal.matrixWorld.equals(sealBefore[i])).toBe(true); });
  windows.forEach((glass, i) => expect(glass.getWorldPosition(new T.Vector3()).distanceTo(glassBefore[i])).toBeGreaterThan(.1));
  repairFramelessRearDoors(model);
  expect(model.children.filter(child => child.name.startsWith('Rear_Window_Body_Seal_'))).toHaveLength(2);
});
