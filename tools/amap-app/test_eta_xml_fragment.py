"""Compare the Python fragment with observed output from the APK's iksemel."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from eta_xml_fragment import encode_active_eta_info, encode_eta_info


def test_exact_native_xml_for_json():
    # Captured by executing libiksemel.so ARM64 iks_insert_cdata/iks_string.
    assert encode_eta_info(2, '{"flag":7}') == (
        b'<ETAInfo><ETAFlag>2</ETAFlag><TRRequestData>'
        b'{&quot;flag&quot;:7}</TRRequestData></ETAInfo>'
    )


def test_native_escaping_and_utf8():
    assert encode_eta_info(2, '中文 & < > " \' /') == (
        '<ETAInfo><ETAFlag>2</ETAFlag><TRRequestData>'
        '中文 &amp; &lt; &gt; &quot; &apos; /'
        '</TRRequestData></ETAInfo>'
    ).encode('utf-8')


def test_active_native_xml_wraps_inner_json_as_escaped_text():
    # Independently captured from the APK's ARM64 iksemel with the string
    # produced by libamaptbt.so's active navigation transport preparation.
    assert encode_active_eta_info(2, '{"flag":7}') == (
        b'<ETAInfo><ETAFlag>2</ETAFlag><TRRequestData>'
        b'&lt;![CDATA[{&quot;flag&quot;:7}]]&gt;'
        b'</TRRequestData></ETAInfo>'
    )


def test_zero_flag_has_no_request_data():
    assert encode_eta_info(0, '{"flag":7}') == b'<ETAInfo><ETAFlag>0</ETAFlag></ETAInfo>'


@pytest.mark.parametrize('flag', [-1, 3, True])
def test_reject_unverified_flag(flag):
    with pytest.raises(ValueError):
        encode_eta_info(flag, '{}')
