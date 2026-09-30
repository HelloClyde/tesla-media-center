"""Browser batch boundary for an explicitly configured VDR session.

Units and installation are handled before fixed-cadence interpolation. GPS is
attached only at/after its receipt time and is never interpolated into IMU.
"""
import copy
from vdr_browser_input import BrowserInput
from vdr_browser_resampler import BrowserResampler
from vdr_batch import NativeVdrBatch


class BrowserVdrBatch:
    input_format = 'browser'
    def __init__(self, session, *, rotation, acceleration_sign, accuracy_to_sigma, maximum_gap):
        self.native = NativeVdrBatch(session)
        self.adapter = BrowserInput(rotation, acceleration_sign, accuracy_to_sigma)
        self.resampler = BrowserResampler(maximum_gap=maximum_gap)
        self.pending_gps = []
        self.last_gps = -1

    def consume_batch(self, samples):
        if not isinstance(samples, list) or not 1 <= len(samples) <= 100:
            raise ValueError('Expected 1..100 browser samples')
        # Validate and prepare the entire batch before touching filter state.
        adapter, resampler = copy.deepcopy(self.adapter), copy.deepcopy(self.resampler)
        pending = copy.deepcopy(self.pending_gps)
        last_gps = self.last_gps
        prepared = []
        for sample in samples:
            if not isinstance(sample, dict):
                raise ValueError('Invalid browser sample')
            fix = sample.get('gps')
            if fix is not None and not isinstance(fix, dict):
                raise ValueError('Invalid browser GPS')
            native = adapter.convert(sample, fix)
            if 'gps' in native:
                gps = native['gps']
                if gps['timestamp'] <= last_gps:
                    raise ValueError('GPS receipt timestamps must increase')
                pending.append(gps)
                last_gps = gps['timestamp']
            for output in resampler.push(native):
                while pending and pending[0]['timestamp'] <= output['timestamp']:
                    output['gps'] = pending.pop(0)
                prepared.append(output)
        for start in range(0, len(prepared), 100):
            self.native.consume_batch(prepared[start:start+100])
        self.adapter, self.resampler = adapter, resampler
        self.pending_gps, self.last_gps = pending, last_gps
        session = self.native.session
        return dict(state=session.manager.state, output=copy.deepcopy(session.output),
                    accepted=len(samples), timestamp=adapter.last_timestamp,
                    integrated=len(prepared))
