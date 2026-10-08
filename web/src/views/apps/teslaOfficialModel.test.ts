import { describe, expect, it } from 'vitest';
import { vehicleModelVariant, resolvedVehicleModelVariant } from './teslaOfficialModel';

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
