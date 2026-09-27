"""Offline regression matrix; reports rejection, never equates framing with decoding."""
import argparse
import hashlib
import json
from pathlib import Path

from inspect_route_blocks import inspect


def verify(path):
    raw = path.read_bytes()
    row = {"sample": path.name, "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest(),
           "navigation_ready": False}
    try:
        result = inspect(raw)
        row.update(framing_complete=result["framing_consumed_all"],
                   geometry_candidates=result["candidate_geometry_block_count"],
                   geometry_blocks=len(result["detail_blocks"]),
                   coordinate_system=result["coordinate_system"],
                   length_units=result["length_units"],
                   rejections=[{"group": block["group"], "index": block["index"],
                                "reason": block["geometry_candidate"]["reason"]}
                               for block in result["detail_blocks"]
                               if block["geometry_candidate"]["status"] == "unsupported"])
    except ValueError as error:
        row.update(framing_complete=False, rejection=str(error))
    return row


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('samples', type=Path, nargs='+')
    args = parser.parse_args()
    print(json.dumps([verify(path) for path in args.samples], indent=2, ensure_ascii=True))
