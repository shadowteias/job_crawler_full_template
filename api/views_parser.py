import logging
import socket
from ipaddress import ip_address, ip_network
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup
from django.conf import settings
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from .llm_parser import _parse_job_details_with_openai
from .permissions import HasInternalAPIToken

logger = logging.getLogger(__name__)

PRIVATE_NETWORKS = [
    ip_network("0.0.0.0/8"),
    ip_network("10.0.0.0/8"),
    ip_network("127.0.0.0/8"),
    ip_network("169.254.0.0/16"),
    ip_network("172.16.0.0/12"),
    ip_network("192.168.0.0/16"),
    ip_network("224.0.0.0/4"),
    ip_network("::1/128"),
    ip_network("fc00::/7"),
    ip_network("fe80::/10"),
]


def _truthy(value) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _validate_public_http_url(url: str) -> str:
    parsed = urlparse(url.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("Only absolute http/https URLs are supported.")
    hostname = parsed.hostname
    if not hostname:
        raise ValueError("URL host is missing.")
    try:
        addr_infos = socket.getaddrinfo(hostname, None)
    except socket.gaierror as exc:
        raise ValueError("URL host could not be resolved.") from exc
    for info in addr_infos:
        resolved_ip = ip_address(info[4][0])
        if any(resolved_ip in network for network in PRIVATE_NETWORKS):
            raise ValueError("Private, local, or link-local URLs are not allowed for URL smoke tests.")
    return parsed.geturl()


def _visible_text_from_html(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg", "canvas"]):
        tag.decompose()
    text = " ".join(soup.get_text(" ").split())
    return text[:20000]


def _fetch_visible_text(url: str) -> tuple[str, dict]:
    safe_url = _validate_public_http_url(url)
    response = requests.get(
        safe_url,
        headers={"User-Agent": "JobCrawlerParserSmokeTest/1.0"},
        timeout=15,
        allow_redirects=False,
    )
    response.raise_for_status()
    content_type = response.headers.get("content-type", "")
    if "text/html" not in content_type and "text/plain" not in content_type:
        raise ValueError(f"URL returned unsupported content type: {content_type or 'unknown'}")
    text = _visible_text_from_html(response.text)
    if len(text) < 50:
        raise ValueError("Fetched page did not contain enough visible text for parser smoke test.")
    return text, {
        "requested_url": safe_url,
        "final_url": response.url,
        "status_code": response.status_code,
        "content_type": content_type,
        "text_length": len(text),
        "text_preview": text[:300],
    }


class JobParserTestView(APIView):
    permission_classes = [HasInternalAPIToken]

    def post(self, request):
        text = (request.data.get("text") or "").strip()
        url = (request.data.get("url") or "").strip()
        fetch_url = _truthy(request.data.get("fetch_url"))
        fetch_result = None
        fetch_error = ""
        if fetch_url:
            if not url:
                return Response({"detail": "field 'url' is required when fetch_url=true"}, status=status.HTTP_400_BAD_REQUEST)
            try:
                text, fetch_result = _fetch_visible_text(url)
            except Exception as exc:
                logger.warning("Parser smoke-test URL fetch failed with %s", exc.__class__.__name__)
                fetch_error = str(exc)
        if not text and not fetch_error:
            return Response({"detail": "field 'text' is required unless fetch_url=true successfully extracts text"}, status=status.HTTP_400_BAD_REQUEST)

        openai_enabled = bool(getattr(settings, "OPENAI_PARSER_ENABLED", False))
        openai_key_configured = bool(getattr(settings, "OPENAI_API_KEY", ""))
        temporary_openai_api_key = (request.data.get("openai_api_key") or "").strip()
        temporary_project_id = (request.data.get("openai_project_id") or "").strip()
        temporary_model = (request.data.get("openai_model") or "").strip()
        request_key_allowed = bool(getattr(settings, "OPENAI_ALLOW_REQUEST_API_KEY", False))
        temporary_key_used = bool(temporary_openai_api_key and request_key_allowed)

        parsed = {}
        skipped_reason = ""
        real_openai_call_attempted = False
        if fetch_error:
            skipped_reason = f"URL fetch failed: {fetch_error}"
        elif temporary_openai_api_key and not request_key_allowed:
            skipped_reason = "Temporary request API keys are disabled in this environment. Use OPENAI_API_KEY from environment/deployment secrets instead."
        elif (openai_enabled and openai_key_configured) or temporary_key_used:
            real_openai_call_attempted = True
            try:
                parsed = _parse_job_details_with_openai(
                    text=text,
                    url=url,
                    company_name=request.data.get("company_name") or "",
                    api_key=temporary_openai_api_key or None,
                    project_id=temporary_project_id or None,
                    model=temporary_model or None,
                    parser_enabled=True if temporary_key_used else None,
                )
            except Exception as exc:
                logger.warning("OpenAI parser smoke-test call failed with %s", exc.__class__.__name__)
                skipped_reason = "OpenAI parser call failed. Check that the API key, project id, model, billing, and network access are valid. The request key was not returned in this response."
        elif not skipped_reason:
            skipped_reason = "OpenAI parser is disabled or OPENAI_API_KEY is not configured. For a one-off demo, enter an OpenAI API key on /api-test/. For persistent crawler use, set OPENAI_PARSER_ENABLED=1 and OPENAI_API_KEY, then recreate app/worker."

        return Response(
            {
                "parser_config": {
                    "openai_parser_enabled": openai_enabled,
                    "openai_api_key_configured": openai_key_configured,
                    "request_openai_api_key_allowed": request_key_allowed,
                    "temporary_openai_api_key_used": temporary_key_used,
                    "openai_project_id_configured": bool(getattr(settings, "OPENAI_PROJECT_ID", "")),
                    "temporary_openai_project_id_used": bool(temporary_project_id),
                    "openai_project_configured": bool(getattr(settings, "OPENAI_PROJECT", "")),
                    "openai_model": temporary_model or getattr(settings, "OPENAI_MODEL", ""),
                },
                "parsed": parsed,
                "saved": False,
                "source": {
                    "fetch_url_requested": fetch_url,
                    "fetched": bool(fetch_result),
                    "fetch_result": fetch_result,
                    "input_text_length": len(text),
                },
                "skipped_reason": skipped_reason,
                "smoke_status": "real_openai_call_attempted" if real_openai_call_attempted else "configuration_only",
            },
            status=status.HTTP_200_OK,
        )
