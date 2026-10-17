import { describe, expect, it } from 'vitest';
import { createFlightRenderBudget } from './teslaFlightRenderBudget';

describe('flight pixel budget', () => {
  it('keeps full resolution at smooth frame rates and ignores isolated stalls', () => {
    const budget = createFlightRenderBudget();
    for (let i = 0; i < 300; i++) budget.sample(1000 / 60);
    budget.sample(1200); budget.sample(NaN); budget.sample(0);
    for (let i = 0; i < 30; i++) budget.sample(1000 / 60);
    expect(budget.scale).toBe(1);
  });

  it('steps down gradually on sustained slow frames and restores quality for the next flight', () => {
    const budget = createFlightRenderBudget();
    for (let i = 0; i < 34; i++) budget.sample(40);
    expect(budget.scale).toBe(.85);
    for (let i = 0; i < 10; i++) budget.sample(40);
    expect(budget.scale).toBe(.85);
    for (let i = 0; i < 40; i++) budget.sample(40);
    expect(budget.scale).toBe(.7);
    for (let i = 0; i < 100; i++) budget.sample(1000 / 60);
    expect(budget.scale).toBe(.7);
    budget.reset();
    expect(budget.scale).toBe(1);
    for (let i = 0; i < 10; i++) budget.sample(40);
    expect(budget.scale).toBe(1);
  });

  it('avoids a second reduction once the first adjustment makes frames smooth', () => {
    const budget = createFlightRenderBudget();
    for (let i = 0; i < 34; i++) budget.sample(40);
    for (let i = 0; i < 300; i++) budget.sample(1000 / 60);
    expect(budget.scale).toBe(.85);
  });
});
