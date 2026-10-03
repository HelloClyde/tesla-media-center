"""Decoder for the APK's ETA/TMC outer response frame.

The live-signal section in accepted frames is decoded separately by eta_live.
The frame result code alone does not establish inner-section success.
"""

from dataclasses import dataclass
import struct


_HEADER = struct.Struct("<IHHBHBBII32s")


@dataclass(frozen=True)
class EtaResponse:
    frame_length: int
    format_field: int
    data_version: int
    result_code: int
    status_field: int
    metadata: int
    flags: int
    checksum: int
    data_length: int
    navi_id: str
    data: bytes

    @property
    def accepted(self) -> bool:
        # libamaptbt.so 0x6cbc7c -> 0x6cbd74 reaches payload parsing only
        # when the response's byte-8 result code is zero.
        return self.result_code == 0


def parse_eta_response(raw: bytes) -> EtaResponse:
    if len(raw) < _HEADER.size:
        raise ValueError("ETA response is shorter than its 53-byte header")
    (frame_length, format_field, data_version, result_code, status_field,
     metadata, flags, checksum, data_length, navi_id_raw) = _HEADER.unpack_from(raw)
    if frame_length != len(raw):
        raise ValueError("ETA frame length does not match the received bytes")
    try:
        navi_id = navi_id_raw.decode("ascii")
    except UnicodeDecodeError as exc:
        raise ValueError("ETA navigation ID is not ASCII") from exc
    return EtaResponse(
        frame_length=frame_length,
        format_field=format_field,
        data_version=data_version,
        result_code=result_code,
        status_field=status_field,
        metadata=metadata,
        flags=flags,
        checksum=checksum,
        data_length=data_length,
        navi_id=navi_id,
        data=raw[_HEADER.size:],
    )
