"""UNAS XML API client implementation."""
from __future__ import annotations
from typing import Any, Dict, Optional
import os
import requests
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from loguru import logger
from .parser import parse_xml, UNASError
import datetime

DEFAULT_TIMEOUT = int(os.getenv("UNAS_TIMEOUT", "15"))
DEFAULT_DEBUG_FILE = os.path.join(os.getcwd(), "unas_debug.log")


class UNASClient:
    """Client for interacting with the UNAS XML API.

    Implements a PHP-like flow: POST <Params><ApiKey>..</ApiKey></Params> to login
    and receive a <Token>. Subsequent calls use either a body-inserted token or
    a header (e.g. Authorization: Bearer <Token>) depending on configuration.
    """

    def __init__(
        self,
        base_url: str,
        token: str | None = None,
        auth_mode: str = "body",
        token_field: str = "Token",
        header_name: Optional[str] = None,
        header_prefix: Optional[str] = None,
        body_field: Optional[str] = None,
        products_endpoint: str | None = None,
        stock_endpoint: str | None = None,
        categories_endpoint: str | None = None,
        xml_root: str | None = None,
        login_endpoint: str | None = None,
        api_key: str | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.token: Optional[str] = token or None
        self.api_key: Optional[str] = api_key or os.getenv("UNAS_API_KEY") or os.getenv("UNAS_API_TOKEN") or None
        self.auth_mode = auth_mode.lower().strip()
        self.token_field = token_field
        self.header_name = header_name
        self.header_prefix = header_prefix
        self.body_field = body_field or token_field
        self.products_endpoint = (products_endpoint or os.getenv("UNAS_PRODUCTS_ENDPOINT") or "getProduct").strip()
        self.stock_endpoint = (stock_endpoint or os.getenv("UNAS_STOCK_ENDPOINT") or "getStock").strip()
        self.categories_endpoint = (categories_endpoint or os.getenv("UNAS_CATEGORIES_ENDPOINT") or "getCategory").strip()
        self.xml_root = (xml_root or os.getenv("UNAS_XML_ROOT") or "Request").strip()
        self.login_endpoint = (login_endpoint or os.getenv("UNAS_LOGIN_ENDPOINT") or "login").strip()
        # TLS / debug / timeout settings
        self.insecure_ssl = os.getenv("UNAS_INSECURE_SSL", "false").lower() == "true"
        self.ca_path = os.getenv("UNAS_CA_PATH") or None
        self.timeout = int(os.getenv("UNAS_TIMEOUT", DEFAULT_TIMEOUT))
        self.debug_log = os.getenv("UNAS_DEBUG_LOG", "false").lower() == "true"
        self.debug_file = os.getenv("UNAS_DEBUG_FILE") or DEFAULT_DEBUG_FILE

        if self.auth_mode not in {"body", "header"}:
            raise ValueError("UNAS auth_mode must be 'body' or 'header'")

    @classmethod
    def from_env(cls) -> "UNASClient":
        return cls(
            base_url=os.getenv("UNAS_API_BASE", ""),
            token=None,
            auth_mode=os.getenv("UNAS_AUTH_MODE", "body"),
            token_field=os.getenv("UNAS_TOKEN_FIELD", "Token"),
            header_name=os.getenv("UNAS_AUTH_HEADER_NAME") or None,
            header_prefix=os.getenv("UNAS_AUTH_HEADER_PREFIX") or None,
            body_field=os.getenv("UNAS_AUTH_BODY_FIELD") or None,
            products_endpoint=os.getenv("UNAS_PRODUCTS_ENDPOINT") or None,
            stock_endpoint=os.getenv("UNAS_STOCK_ENDPOINT") or None,
            categories_endpoint=os.getenv("UNAS_CATEGORIES_ENDPOINT") or None,
            xml_root=os.getenv("UNAS_XML_ROOT") or None,
            login_endpoint=os.getenv("UNAS_LOGIN_ENDPOINT") or None,
            api_key=os.getenv("UNAS_API_KEY") or os.getenv("UNAS_API_TOKEN") or None,
        )

    def _build_headers(self) -> Dict[str, str]:
        headers: Dict[str, str] = {"Content-Type": "application/xml"}
        if self.auth_mode == "header":
            if not self.header_name:
                raise ValueError("header_name must be set for header auth mode")
            # Do not auto-login here to avoid recursion; callers should ensure token
            token_value = f"{self.header_prefix}{self.token}" if (self.header_prefix and self.token) else (self.token or "")
            if token_value:
                headers[self.header_name] = token_value
        return headers

    def _mask_token(self, text: str) -> str:
        if not text or not self.token:
            return text
        return text.replace(self.token, '***')

    def _append_debug(self, url: str, req_headers: Dict[str, str], req_xml: str, status: Optional[int], resp_text: Optional[str], err: Optional[str] = None) -> None:
        if not self.debug_log:
            return
        try:
            entry = {
                "ts": datetime.datetime.utcnow().isoformat() + "Z",
                "url": url,
                "status": status,
                "error": err,
                "request": {
                    "headers": {k: (v if k.lower() != (self.header_name or '').lower() else '***') for k, v in req_headers.items()},
                    "xml": self._mask_token(req_xml),
                },
                "response": self._mask_token(resp_text or "")
            }
            with open(self.debug_file, "a", encoding="utf-8") as fh:
                fh.write(str(entry) + "\n")
        except Exception:
            logger.exception("Failed writing UNAS debug log")

    def _ensure_token(self) -> None:
        """Login if token is missing and api_key present."""
        if self.token:
            return
        if not self.api_key:
            raise UNASError("Missing UNAS API key for login")
        # Build login Params XML
        xml = self.build_params_xml({"ApiKey": self.api_key, "WebshopInfo": "true"})
        url = f"{self.base_url.rstrip('/')}/{self.login_endpoint.lstrip('/')}"
        headers = {"Content-Type": "application/xml"}
        try:
            resp = requests.post(
                url,
                headers=headers,
                data=xml.encode("utf-8"),
                timeout=self.timeout,
                verify=(False if self.insecure_ssl else (self.ca_path if self.ca_path else True)),
            )
        except requests.RequestException as exc:
            logger.error(f"UNAS login network error: {exc}")
            self._append_debug(url, headers, xml, None, None, str(exc))
            raise UNASError("Login network error") from exc
        raw_login_xml = resp.text
        logger.debug("UNAS raw login XML (truncated 500 chars): " + raw_login_xml[:500].replace(self.api_key or "", "***"))
        self._append_debug(url, headers, xml, resp.status_code, raw_login_xml)
        data = parse_xml(raw_login_xml)
        # Extract token and shopid
        token = None
        shop_id = None
        def _walk(node: Any):
            nonlocal token, shop_id
            if isinstance(node, dict):
                for k, v in node.items():
                    if k.lower() == self.token_field.lower():
                        token_val = v if not isinstance(v, dict) else v.get("#text")
                        token = str(token_val) if token_val else None
                    if k.lower() == "shopid":
                        shop_id_val = v if not isinstance(v, dict) else v.get("#text")
                        shop_id = str(shop_id_val) if shop_id_val else None
                    _walk(v)
            elif isinstance(node, list):
                for item in node:
                    _walk(item)
        _walk(data)
        if not token:
            raise UNASError("Login succeeded but token not found in response")
        self.token = token
        self.shop_id = shop_id
        logger.debug("UNAS login succeeded; token and ShopId acquired")
        try:
            os.environ["UNAS_API_TOKEN"] = self.token
        except Exception:
            pass

    def _dict_to_xml(self, data: Dict[str, Any]) -> str:
        """Convert a flat dict to a simple XML under configured root element."""
        root_name = self.xml_root
        parts = [f"<?xml version=\"1.0\" encoding=\"UTF-8\"?>", f"<{root_name}>"]
        for k, v in data.items():
            parts.append(f"  <{k}>{v}</{k}>")
        parts.append(f"</{root_name}>")
        return "\n".join(parts)

    def build_params_xml(self, params: Dict[str, Any]) -> str:
        """Build XML wrapped in <Params> with given key/value pairs."""
        parts = ['<?xml version="1.0" encoding="UTF-8"?>', '<Params>']
        for k, v in params.items():
            parts.append(f"  <{k}>{v}</{k}>")
        parts.append('</Params>')
        return "\n".join(parts)

    def build_request(self, endpoint: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Utility for tests: returns headers and xml body without executing.
        This will NOT auto-login; it builds the XML using Params root to match PHP flow.
        """
        url = f"{self.base_url.rstrip('/')}/{endpoint.lstrip('/')}"
        xml = self.build_params_xml(dict(payload))
        headers = {"Content-Type": "application/xml"}
        if self.auth_mode == "header" and self.token and self.header_name:
            headers[self.header_name] = f"{self.header_prefix or ''}{self.token}"
        return {"url": url, "headers": headers, "xml": xml}

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=4), reraise=True,
           retry=retry_if_exception_type((requests.RequestException, UNASError)))
    def _post_xml(self, endpoint: str, params: Optional[Dict[str, Any]] = None, require_auth: bool = True) -> Dict[str, Any]:
        """Post XML to endpoint using Params body. If require_auth=True and header auth is used,
        ensure token and send Authorization header. For body auth, token is injected into params.
        """
        params = params or {}
        # ensure token if required for header auth
        if require_auth and self.auth_mode == "header":
            self._ensure_token()
        # inject token for body auth
        if require_auth and self.auth_mode == "body":
            if not self.token:
                self._ensure_token()
            params = dict(params)
            params[self.body_field] = self.token

        xml = self.build_params_xml(params)
        url = f"{self.base_url.rstrip('/')}/{endpoint.lstrip('/')}"
        headers = {"Content-Type": "application/xml"}
        if require_auth and self.auth_mode == "header" and self.token and self.header_name:
            headers[self.header_name] = f"{self.header_prefix or ''}{self.token}"

        try:
            resp = requests.post(
                url,
                headers=headers,
                data=xml.encode("utf-8"),
                timeout=self.timeout,
                verify=(False if self.insecure_ssl else (self.ca_path if self.ca_path else True)),
            )
        except requests.RequestException as exc:  # noqa: BLE001
            logger.error(f"UNAS network error: {exc}")
            self._append_debug(url, headers, xml, None, None, str(exc))
            raise
        # append debug
        self._append_debug(url, headers, xml, resp.status_code, resp.text)
        if resp.status_code >= 400:
            logger.error(f"UNAS HTTP {resp.status_code}: {resp.text[:200]}")
            body_text = resp.text or ""
            if "expired token" in body_text.lower():
                self.token = None
            raise UNASError(f"UNAS HTTP {resp.status_code} error: {body_text[:200]}")
        try:
            parsed = parse_xml(resp.text)
        except UNASError as exc:
            # If token expired, clear it so the next attempt forces a fresh login
            if "expired token" in str(exc).lower():
                self.token = None
            raise
        except Exception as exc:  # noqa: BLE001
            logger.error(f"UNAS parse error: {exc}")
            raise UNASError(str(exc)) from exc
        return parsed

    def get_products(self) -> Dict[str, Any]:
        """Fetch products list using configured products endpoint."""
        # Default to a small paginated request to avoid fetching full catalog by accident.
        return self.get_products_page(limit=20, offset=0)

    def get_products_page(self, limit: int = 20, offset: int = 0, extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Fetch a single page of products. Always use pagination to avoid large exports.

        Parameters:
        - limit: maximum items to return (API may accept 'Limit')
        - offset: pagination offset (API may accept 'Offset')
        - extra: additional params (e.g., filters) to merge into the request
        """
        params: Dict[str, Any] = {"Action": "GetProducts", "Limit": str(limit), "Offset": str(offset)}
        if extra:
            params.update(extra)
        return self._post_xml(self.products_endpoint, params, require_auth=True)

    def get_stock(self) -> Dict[str, Any]:
        """Fetch stock information using configured stock endpoint."""
        params = {"Action": "GetStock"}
        return self._post_xml(self.stock_endpoint, params, require_auth=True)

    def get_categories(self) -> Dict[str, Any]:
        """Fetch categories using configured categories endpoint."""
        return self._post_xml(self.categories_endpoint, {}, require_auth=True)

    def get_product_detail(self, product_id: str) -> Dict[str, Any]:
        """Fetch detailed product information for a single product Id.

        Uses Action=GetProduct with Id to retrieve full product data where supported.
        """
        params = {"Action": "GetProduct", "Id": str(product_id)}
        return self._post_xml(self.products_endpoint, params, require_auth=True)


__all__ = ["UNASClient", "UNASError"]
