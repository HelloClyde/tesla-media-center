import pytest

from dynamic_route_links import decode_link_ids, decode_v51_link_deltas, encode_link_adcodes, encode_link_boundary_properties, encode_link_ids, encode_segment_link_ids


def test_first_absolute_then_signed_deltas():
    ids = [120000000000, 120000000008, 119999999998]
    assert encode_link_ids(ids) == ["120000000000", "8", "-10"]
    assert decode_link_ids(encode_link_ids(ids)) == ids


def test_signed_64_bit_wrap_matches_native_subtraction():
    ids = [(1 << 64) - 2, 3]
    assert encode_link_ids(ids) == [str((1 << 64) - 2), "5"]
    assert decode_link_ids(encode_link_ids(ids)) == ids


def test_segment_strings_restart_from_first_link_anchor():
    assert encode_segment_link_ids([[100, 108, 105], [120, 121], [90]]) == [
        "100,8,-3", "20,1", "-10",
    ]


@pytest.mark.parametrize("segments", [[], [[]], [[1], []], [[True]], [[-1]], [[1 << 64]]])
def test_segment_strings_reject_invalid_input(segments):
    with pytest.raises(ValueError):
        encode_segment_link_ids(segments)


def test_link_boundary_properties_use_first_and_last_link_per_segment():
    assert encode_link_boundary_properties([
        [(9, 15), (8, 14), (7, 13)], [(6, -1)],
    ]) == ["9-15,7-13", "6--1"]


def test_link_adcodes_use_one_based_route_ranges_and_merge_across_segments():
    assert encode_link_adcodes([[110101, 110101], [110101, 110102, 110101]]) == {
        "110101": "1,3-5,5", "110102": "4,4",
    }


def test_link_adcodes_native_zero_run_rules():
    assert encode_link_adcodes([[0, 110101, 0]]) == {"0": "3,3", "110101": "2,2"}
    assert encode_link_adcodes([[0, 0]]) == {"0": "0,2"}


@pytest.mark.parametrize("segments", [[], [[]], [[1], []], [[True]], [[-1]], [[1 << 32]]])
def test_link_adcodes_reject_invalid_input(segments):
    with pytest.raises(ValueError):
        encode_link_adcodes(segments)


@pytest.mark.parametrize("segments", [[], [[]], [[(1, 2)], []], [[(True, 1)]], [[(1, 1 << 31)]], [[(1,)]]])
def test_link_boundary_properties_reject_invalid_input(segments):
    with pytest.raises(ValueError):
        encode_link_boundary_properties(segments)


@pytest.mark.parametrize("ids", [[-1], [1 << 64], [True]])
def test_out_of_range_link_rejected(ids):
    with pytest.raises(ValueError):
        encode_link_ids(ids)


@pytest.mark.parametrize("wire", [["-1"], ["1", str(1 << 63)], ["1 "]])
def test_invalid_wire_value_rejected(wire):
    with pytest.raises(ValueError):
        decode_link_ids(wire)


def test_saved_v51_prefix_recovers_stable_link_ids():
    # First links from the saved Beijing 5.1 route. Values above 2^32 are
    # ZigZag deltas; treating them as unsigned broke shared-link identity.
    base = 0x4712E5A9802009D3
    ids = decode_v51_link_deltas(base, [0, 2, 66, 1, 3197, 4294967679])
    assert ids == [
        0x4712E5A9802009D3,
        0x4712E5A9802009D4,
        0x4712E5A9802009F5,
        0x4712E5A9802009F4,
        0x4712E5A9802003B5,
        0x4712E5A9002002F5,
    ]
    assert decode_link_ids(encode_link_ids(ids)) == ids


@pytest.mark.parametrize("base,deltas", [(-1, [0]), (1 << 64, [0]), (0, [-1]), (0, [1 << 64])])
def test_invalid_v51_link_input_rejected(base, deltas):
    with pytest.raises(ValueError):
        decode_v51_link_deltas(base, deltas)
