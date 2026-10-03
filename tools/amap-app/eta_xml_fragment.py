"""Verified ETAInfo XML fragment from the pinned App's iksemel serializer.

This is only the inner navigation payload of an ETA/TMC request. The root
attributes, navigation session, optional children, and AOS transport remain
unverified; this module must not be used as a standalone live request.
"""

from xml.sax.saxutils import escape


_XML_ENTITIES = {'"': '&quot;', "'": '&apos;'}


def encode_eta_info(flag: int, request_json: str) -> bytes:
    """Match iks_insert_cdata + iks_string for ETAFlag/TRRequestData."""
    if type(flag) is not int or not 0 <= flag <= 2:
        raise ValueError("invalid ETA flag")
    if not isinstance(request_json, str) or not request_json or "\x00" in request_json:
        raise ValueError("invalid navigation JSON")
    if len(request_json.encode("utf-8")) > 65536:
        raise ValueError("navigation JSON too large")
    flag_xml = f"<ETAInfo><ETAFlag>{flag}</ETAFlag>"
    if flag:
        flag_xml += "<TRRequestData>" + escape(request_json, _XML_ENTITIES) + "</TRRequestData>"
    return (flag_xml + "</ETAInfo>").encode("utf-8")


def encode_active_eta_info(flag: int, request_json: str) -> bytes:
    """Reproduce the active navigation send's literal CDATA-marker wrapping.

    The transport prepends/appends these characters before iksemel escapes
    them as text. They are not an XML CDATA node in the resulting wire body.
    """
    if not isinstance(request_json, str) or not request_json or "\x00" in request_json:
        raise ValueError("invalid navigation JSON")
    return encode_eta_info(flag, "<![CDATA[" + request_json + "]]>")
