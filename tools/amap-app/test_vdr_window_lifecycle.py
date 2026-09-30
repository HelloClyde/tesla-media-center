import unittest
from types import SimpleNamespace
from vdr_state_transition import ManagerState
from vdr_window_dispatch import DispatchWindow
from vdr_window_lifecycle import WindowLifecycle


class LifecycleTest(unittest.TestCase):
    def test_order_reinitialization_and_reused_window(self):
        events=[]
        manager=ManagerState(1,0,0,0)
        payload=SimpleNamespace(integrated=SimpleNamespace(timestamp=1000),
            direction=0.,quality=1,gps=SimpleNamespace(speed=0.,longitude=120.,latitude=30.,altitude=0.),
            preferred=None,fallback=None,gyro_bias=None)
        records=[]
        class Observer:
            enabled=True
            replay_enabled=False
            def publish(self,p): events.append('observer')
        class Filter:
            state=None
            def before_predict(self,p): events.append('quality')
            def predict(self,p): events.append('predict')
            def handle_state(self,p):
                events.append('state')
                manager.state=8
            def adjust_for_gap(self,p): events.append('gap')
            def observe(self,p,lookahead): events.append(('observe',lookahead))
            def publish_bias(self,state): events.append('bias')
        def transition(state,timestamp,reason,forced):
            events.append(('transition',state,forced))
            manager.state=state
        lifecycle=WindowLifecycle(manager=manager,observers=[Observer()],records=records,
            filter_manager=Filter(),transition=transition,observer_tail=lambda *a:events.append('tail'),
            empty_gps_factory=lambda:None,bias_feedback=lambda *a:events.append('feedback'),
            output_status=lambda *a:events.append('status'),publish_output=lambda *a:events.append('output'))
        window=DispatchWindow(payload.gps,payload)
        lifecycle.process(window,'lookahead')
        self.assertEqual(events,[('transition',2,1),'observer','tail','quality','predict','state','gap',
                                  ('observe','lookahead'),'bias','status','output'])
        events.clear()
        manager.state=4
        lifecycle.process(window,None)
        self.assertEqual(events,['quality','predict','state',('observe',None),'bias','status','output'])
        self.assertEqual(len(records),2)


if __name__=='__main__':
    unittest.main()
