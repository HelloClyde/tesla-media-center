"""Quality inference contract at77770c; model execution stays injectable.

Unavailable is the native -1 sentinel, not a successful confidence estimate.
No neural model is replaced by the separate linear score.
"""
import struct


def quality_inference(features, backend=None):
    """Backend exposes ready(), model(), then set_input/run/output methods.

    Deliberately do not swallow arbitrary Python exceptions as native failures.
    The backend maps actual native/model-runtime failures to run()==False.
    """
    if backend is None or not backend.ready():
        return -1.
    model = backend.model()
    if model is None:
        return -1.
    samples = [struct.unpack('<f', struct.pack('<f', value))[0] for value in features]
    model.set_input('features', samples)
    if not model.run():
        return -1.
    output = model.output('mlp/layer_confidence/confidence')
    if not len(output):
        return -1.
    return float(struct.unpack('<f', struct.pack('<f', output[0]))[0])
