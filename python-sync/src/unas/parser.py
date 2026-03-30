"""XML parsing helpers for UNAS API responses."""
from __future__ import annotations
from typing import Any, Dict
import xmltodict

class UNASError(Exception):
    """Raised when the UNAS API returns an <Error> tag."""

    def __init__(self, message: str, code: str | None = None):
        super().__init__(message)
        self.code = code


def parse_xml(xml_text: str) -> Dict[str, Any]:
    """Parse XML into a Python dict and raise UNASError on <Error>.

    Args:
        xml_text: Raw XML string.
    Returns:
        Parsed dict.
    Raises:
        UNASError: If an <Error> tag is encountered.
    """
    try:
        data = xmltodict.parse(xml_text)
    except Exception as exc:  # noqa: BLE001
        raise UNASError(f"Failed to parse XML: {exc}") from exc

    # Search for Error tag anywhere deep.
    def _walk(node: Any) -> UNASError | None:
        if isinstance(node, dict):
            if "Error" in node:
                err = node["Error"]
                if isinstance(err, dict):
                    msg = err.get("Message") or err.get("#text") or "Unknown UNAS error"
                    code = err.get("Code")
                else:
                    msg = str(err)
                    code = None
                return UNASError(msg, code)
            for v in node.values():
                found = _walk(v)
                if found:
                    return found
        elif isinstance(node, list):
            for item in node:
                found = _walk(item)
                if found:
                    return found
        return None

    err = _walk(data)
    if err:
        raise err
    return data
