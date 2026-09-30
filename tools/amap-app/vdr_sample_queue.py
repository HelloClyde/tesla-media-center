"""Translation of libamaploc +788568; internal sensor identities are unknown.

Records are opaque 32-byte native records. This is research code, not a public
H5 adapter or a complete navigation engine. No interpolation is performed.
"""
import struct


def take_exact_sample(records, timestamp, output):
    """Consume through the first exact timestamp; preserve output vptr/padding.

    Returns (found, remaining_records, output_record). A miss changes nothing.
    Native compares the low 32 bits of timestamp, including wraparound.
    """
    if len(output) != 32 or any(len(record) != 32 for record in records):
        raise ValueError('Native sample records must be 32 bytes')
    target = timestamp & 0xffffffff
    for index, record in enumerate(records):
        if struct.unpack_from('<I', record, 12)[0] == target:
            result = bytearray(output)
            result[8:29] = record[8:29]
            return True, records[index + 1:], bytes(result)
    return False, records[:], output
