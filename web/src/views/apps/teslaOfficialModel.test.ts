import { describe, expect, it } from 'vitest';
import * as THREE from 'three';
import { prepareOfficialVehicle, vehicleModelVariant, resolvedVehicleModelVariant } from './teslaOfficialModel';

const vin = (series: string, year: string) => `LRW${series}AAAAA${year}AAAAAAA`;

describe('Tesla vehicle model selection', () => {
  it('distinguishes the vehicle line and major body refreshes from the VIN', () => {
    expect(vehicleModelVariant(vin('3', 'P'))).toBe('model3-high');
    expect(vehicleModelVariant(vin('3', 'R'))).toBe('model3-highland');
    expect(vehicleModelVariant(vin('Y', 'R'))).toBe('modely-high');
    expect(vehicleModelVariant(vin('Y', 'S'))).toBe('modely-juniper');
    expect(vehicleModelVariant(vin('S', 'L'))).toBe('models-legacy');
    expect(vehicleModelVariant(vin('S', 'M'))).toBe('models-palladium');
    expect(vehicleModelVariant(vin('X', 'L'))).toBe('modelx-legacy');
    expect(vehicleModelVariant(vin('X', 'M'))).toBe('modelx-palladium');
  });

  it('uses the API car type when the year does not identify the body', () => {
    expect(vehicleModelVariant(vin('Y', 'S'), 'e41Bayberry')).toBe('modely-standard');
    expect(vehicleModelVariant(vin('Y', 'S'), 'e80Bayberry')).toBe('modely-long');
    expect(vehicleModelVariant(vin('3', 'P'), 'basePoppyseed')).toBe('model3-highland');
    expect(vehicleModelVariant(vin('3', 'R'), 'model3')).toBe('model3-highland');
    expect(vehicleModelVariant(vin('X', 'R'), 'tamarind')).toBe('modelx-palladium');
    expect(vehicleModelVariant(undefined, 'cybertruck')).toBe('cybertruck');
    expect(vehicleModelVariant(undefined, 'semitruck')).toBe('semi');
    expect(vehicleModelVariant('bad-vin')).toBe('unknown');
  });

  it('uses a manual choice only when the model cannot be identified', () => {
    expect(resolvedVehicleModelVariant('bad-vin')).toBe('modely-high');
    expect(resolvedVehicleModelVariant('bad-vin', undefined, 'model3-highland')).toBe('model3-highland');
    expect(resolvedVehicleModelVariant('bad-vin', undefined, 'unknown')).toBe('modely-high');
    expect(resolvedVehicleModelVariant(vin('Y', 'R'), undefined, 'cybertruck')).toBe('modely-high');
  });
});

describe('Tesla vehicle studio helpers', () => {
  it('removes projection and shadow variants before sizing the car, preserving body parts', () => {
    const model = new THREE.Group();
    const root = new THREE.Group();
    root.name = 'Cybertruck_Root';
    model.add(root);
    const helpers = ['Floor', 'Floor_LongRange', 'Ground_Shadow2', 'Headlights_Projections2',
      'Taillights_Projection', 'Taillights_Projections2', 'Stoplights_Projections',
      'Stoplights_Projections_LongRange', 'Parking_Light_Projection', 'BrakeLightProjection',
      'HeadLightProjection', 'Defrost_Front', 'Defrost_Rear2'];
    for (const name of [...helpers, 'Body', 'Floor_Interior', 'Headlights']) {
      const node = new THREE.Mesh(new THREE.BoxGeometry(1, 1, 1), new THREE.MeshBasicMaterial());
      node.name = name;
      root.add(node);
    }
    expect(prepareOfficialVehicle(model)).toBe(true);
    for (const name of helpers) expect(model.getObjectByName(name), name).toBeUndefined();
    for (const name of ['Body', 'Floor_Interior', 'Headlights']) expect(model.getObjectByName(name), name).toBeDefined();
    expect(model.userData.windshieldBounds).toBeInstanceOf(THREE.Box3);
  });
});
