import { describe, it, expect } from 'vitest';
import { createRouteFusion } from './amapRouteFusion';
import { cumulative, meters, pointAt, type AppRoute } from './amapNavigation';
import { bearingBetween } from './amapHeading';
const route: AppRoute = { id: 1, path: [[120,30],[120.02,30]], breaks: [], steps: [{start:0,end:1,road:'测试路'}], distance: 1900, labels: [] };
const fix = (x: number, timestamp: number, accuracy = 5, speed = 10) => ({point: [120+x/96300,30] as [number,number], timestamp, accuracy, speed, heading:90});
describe('route fusion', () => {
 it('follows a looping exit ramp when GPS heading lags through the turn', () => {
  const xy = (x: number, y: number): [number,number] => [120+x/96300,30+y/111195];
  const path = [xy(0,0),xy(100,0)];
  for(let i=1;i<=32;i++) {
   const angle=-Math.PI/2+i*Math.PI/32;
   path.push(xy(100+40*Math.cos(angle),40+40*Math.sin(angle)));
  }
  path.push(xy(0,80));
  const rampLengths=cumulative({...route,path});
  const ramp: AppRoute={...route,path,distance:rampLengths[rampLengths.length-1]};
  for(const accuracy of [3,25]) for(const interval of [1,2]) {
   const engine=createRouteFusion(ramp);
   for(let i=0;i<=28;i+=interval) {
    const at=i*10;
    const result=engine.accept({point:pointAt(ramp,at),accuracy,speed:10,timestamp:i+1,
     heading:at<100?bearingBetween(pointAt(ramp,at),pointAt(ramp,at+3)):90},i*1000)!;
    expect(result.state,`ramp progress ${at}`).not.toBe('off-route');
    expect(result.state,`ramp progress ${at}`).not.toBe('waiting');
    expect(Math.abs(result.guidanceProgress!-at)).toBeLessThan(15);
   }
  }
 });
 it('still releases sustained wrong-way travel on a straight road for replanning', () => {
  const engine=createRouteFusion(route); engine.accept(fix(100,1),0);
  let result;
  for(let i=1;i<=7;i++) result=engine.accept({...fix(100-i*10,i+1,3),heading:270},i*1000);
  expect(result!.state).toBe('off-route');
 });
 it('accepts moving car fixes with repeated timestamps and guides from confirmed position before the map car catches up', () => {
  const engine=createRouteFusion(route);
  engine.accept(fix(0,1),0);
  const result=engine.accept(fix(20,1),1000)!;
  expect(result.progress).toBeLessThan(result.guidanceProgress!);
  expect(result.guidanceProgress).toBeCloseTo(20,0);
  const withoutNewGps=engine.tick(1250)!;
  expect(withoutNewGps.guidanceProgress).toBeGreaterThanOrEqual(result.guidanceProgress!);
  expect(engine.accept(fix(20,1),1250)).toBeUndefined();
 });
 it('ignores a burst of accurate fixes at a tunnel opening', () => {
  const engine=createRouteFusion(route); engine.accept(fix(0,1),0);
  engine.accept(fix(200,2,800),1000);
  for(let i=0;i<15;i++) {
   const result=engine.accept(fix(70+i,i+3,3),2000+i*100)!;
   expect(result.state).toBe('estimating');
  }
  const result=engine.tick(3500)!;
  expect(result.progress).toBeCloseTo(35,0);
  expect(result.guidanceProgress).toBe(result.progress);
 });
 it('rejects precise but slow positions inconsistent with measured speed', () => {
  const engine=createRouteFusion(route); engine.accept(fix(0,1),0);
  engine.accept(fix(200,2,800),1000);
  for(let i=2;i<=9;i++) {
   const result=engine.accept(fix(20+i,i+1,2),i*1000)!;
   expect(result.state).toBe('estimating');
  }
  expect(engine.tick(9250)!.progress).toBeCloseTo(92.5,0);
 });
 it('does not replan from a short accurate off-route burst', () => {
  const engine=createRouteFusion(route); engine.accept(fix(0,1),0);
  for(let i=1;i<=4;i++) {
   const result=engine.accept({...fix(i*10,i+1),point:[120+i*10/96300,30.0008]},i*1000)!;
   expect(result.state).not.toBe('off-route');
  }
 });
 it('handles five minutes of poor positions, braking and stopping, then recovery', () => {
  const engine = createRouteFusion({...route, path:[[120,30],[120.2,30]]});
  engine.accept(fix(0,1),0);
  let distance = 0;
  for (let i=1;i<=300;i++) {
   const speed = i < 100 ? 15 : i < 104 ? 15-(i-99)*3 : i < 120 ? 0 : Math.min(15,(i-119)*3);
   distance += speed;
   engine.accept(fix(distance+300,i+1,800,speed),i*1000);
  }
  const predicted=engine.tick(300000)!;
  expect(predicted.state).toBe('estimating'); expect(predicted.progress).toBeGreaterThan(3500);
  const progress=predicted.progress!;
  for(let i=301;i<=307;i++) engine.accept(fix(progress+(i-300)*15+20,i+1,5,15),i*1000);
  expect(engine.tick(307250)!.state).toBe('recovering');
 });
 it('rejects frozen coordinates and speed even when timestamps change', () => {
  const engine=createRouteFusion(route); engine.accept(fix(0,1),0);
  for(let i=1;i<=40;i++) engine.accept(fix(0,i+1,800),i*1000);
  expect(engine.tick(41000)!.state).toBe('waiting');
  expect(engine.tick(42000)!.speed).toBe(0);
 });
 it('stops integrating when a live degraded speed stream reports zero', () => {
  const engine=createRouteFusion(route); engine.accept(fix(0,1),0);
  for(let i=1;i<=60;i++) engine.accept(fix(i*10,i+1,800),i*1000);
  engine.accept(fix(601,62,800,0),61000);
  const atStop=engine.tick(61250)!;
  for(let i=62;i<=80;i++) engine.accept(fix(601,i+1,800,0),i*1000);
  expect(engine.tick(80250)!.progress).toBe(atStop.progress);
 });
 it('starts predicting on degraded accuracy despite continued positions', () => {
  const engine=createRouteFusion(route); engine.accept(fix(0,1),0);
  const result=engine.accept(fix(400,2,80),1000)!;
  expect(result.estimated).toBe(true); expect(result.progress).toBeCloseTo(10,0);
  expect(engine.tick(2000)!.progress).toBeCloseTo(20,0);
 });
 it('does not seed prediction from an inaccurate first fix', () => {
  const engine=createRouteFusion(route); expect(engine.accept(fix(0,1,90),0)).toBeUndefined();
  expect(engine.tick(1000)).toBeUndefined();
 });
 it('stops when speed becomes stale and ignores duplicate fixes', () => {
  const engine=createRouteFusion(route); engine.accept(fix(0,1),0);
  for(let t=1000;t<=11000;t+=1000) engine.tick(t);
  expect(engine.tick(11000)!.state).toBe('estimating');
  const before=engine.tick(13000)!; expect(before.state).toBe('waiting');
  expect(engine.accept(fix(800,1),14000)).toBeUndefined();
  expect(engine.tick(15000)!.progress).toBe(before.progress);
 });
 it('bridges a brief speed outage deep in a tunnel, then pauses and resumes safely', () => {
  const engine=createRouteFusion({...route, path:[[120,30],[120.2,30]]});
  engine.accept(fix(0,1),0);
  for(let i=1;i<=90;i++) engine.accept(fix(i*10+300,i+1,800),i*1000);
  const before=engine.tick(90000)!;
  for(let t=90250;t<=96000;t+=250) engine.tick(t);
  const bridged=engine.tick(96000)!;
  expect(bridged.state).toBe('estimating');
  expect(bridged.progress).toBeGreaterThan(before.progress!);
  expect(bridged.speed).toBeLessThan(10);
  for(let t=96250;t<=103000;t+=250) engine.tick(t);
  const paused=engine.tick(103000)!;
  expect(paused.state).toBe('waiting');
  expect(paused.progress!-before.progress!).toBeLessThanOrEqual(120);
  expect(engine.tick(110000)!.progress).toBe(paused.progress);
  for(let i=111;i<=112;i++) {
   expect(engine.accept(fix(i*10+300,i+1,800),i*1000)!.progress).toBe(paused.progress);
  }
  engine.accept(fix(1430,114,800),113000);
  expect(engine.tick(113250)!.state).toBe('estimating');
 });
 it('does not treat isolated speed updates as a continuous tunnel speed stream', () => {
  const engine=createRouteFusion({...route, path:[[120,30],[120.2,30]]});
  engine.accept(fix(0,1),0);
  for(let i=1;i<=90;i++) engine.accept(fix(i*10+300,i+1,800),i*1000);
  const before=engine.tick(90000)!.progress!;
  for(let t=90250;t<=160000;t+=250) {
   if ((t-90000)%11000===0) engine.accept(fix(t/100+300,t,800),t);
   else engine.tick(t);
  }
  const result=engine.tick(160250)!;
  expect(result.state).toBe('waiting');
  expect(result.progress!-before).toBeLessThanOrEqual(120);
 });
 it('continues beyond the short horizon with a continuous valid speed stream', () => {
  const engine=createRouteFusion(route); engine.accept(fix(0,1),0);
  for(let i=1;i<=120;i++) engine.accept(fix(i*10,i+1,700),i*1000);
  const result = engine.tick(120250)!; expect(result.state).toBe('estimating'); expect(result.progress).toBeGreaterThan(1100); expect(result.estimationSeconds).toBeGreaterThan(100);
 });
 it('accounts for two-second car speed callbacks in a long tunnel', () => {
  const engine=createRouteFusion({...route,path:[[120,30],[120.2,30]]});
  engine.accept(fix(0,1),0);
  for(let i=1;i<=30;i++) engine.accept(fix(300+i*20,i+1,800),i*2000);
  const result=engine.tick(60000)!;
  expect(result.state).toBe('estimating');
  expect(result.progress).toBeGreaterThan(550);
  expect(result.progress).toBeLessThanOrEqual(600);
 });
 it('recovers over multiple fixes without jumping straight to the fix', () => {
  const engine=createRouteFusion(route); engine.accept(fix(0,1),0);
  engine.accept(fix(30,2,80),1000);
  for(let i=2;i<=7;i++) engine.accept(fix(i*10+30,i+1),i*1000);
  const before=engine.tick(7000)!; expect(before.state).toBe('recovering');
  const after=engine.tick(7250)!; expect(meters(before.point,after.point)).toBeLessThan(5);
 });
 it('releases three accurate off-route fixes to the replanner', () => {
  const engine=createRouteFusion(route); engine.accept(fix(0,1),0);
  let result;
  for(let i=1;i<=7;i++) result=engine.accept({...fix(i*10,i+1),point:[120+i*10/96300,30.0008]},i*1000);
  expect(result!.state).toBe('off-route'); expect(result!.point[1]).toBe(30.0008);
  expect(engine.tick(7250)).toBeUndefined();
 });
 it('does not predict across a gap in route geometry', () => {
  const engine=createRouteFusion({...route,path:[[120,30],[120.0001,30],[120.001,30],[120.02,30]],breaks:[2]});
  engine.accept(fix(0,1),0); expect(engine.tick(1000)!.state).toBe('waiting');
  expect(engine.tick(2000)!.progress).toBeLessThan(10);
 });
});
