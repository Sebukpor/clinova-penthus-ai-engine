"""
Clinova Penthus AI Engine - Terminology Gateway Client
Interface client for external terminology services (SNOMED CT, ICD-11, RxNorm, LOINC).

NOTE: This is an interface/stub. The actual terminology service is built by another team.
"""

import time
from typing import Any, Dict, List, Optional

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.core.config import get_settings
from app.core.errors import TerminologyGatewayError
from app.core.logging import get_logger
from app.core.observability import record_terminology_cache_hit, terminology_span

logger = get_logger(__name__)


class TerminologyCandidate:
    """Terminology coding candidate."""

    def __init__(self, code: str, display: str, score: float = 0.0, source: str = ""):
        self.code = code
        self.display = display
        self.score = score
        self.source = source

    def to_dict(self) -> Dict[str, Any]:
        return {
            "code": self.code,
            "display": self.display,
            "score": self.score,
            "source": self.source,
        }


class TerminologyGatewayClient:
    """
    Client interface for external terminology services.

    This client calls an external terminology gateway service for:
    - SNOMED CT concept lookup
    - ICD-11 coding
    - RxNorm drug lookup
    - LOINC lab test lookup

    If the gateway is unavailable, returns empty candidates with a warning.
    """

    def __init__(self, base_url: Optional[str] = None):
        self.settings = get_settings()
        self.base_url = (base_url or self.settings.terminology.gateway_url).rstrip("/")
        self.timeout = self.settings.terminology.gateway_timeout_seconds
        self.max_retries = self.settings.terminology.gateway_max_retries
        self._http: Optional[httpx.AsyncClient] = None

    async def _get_http(self) -> httpx.AsyncClient:
        """Lazy HTTP client initialization."""
        if self._http is None:
            self._http = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=httpx.Timeout(self.timeout, connect=5.0),
                limits=httpx.Limits(max_connections=50, max_keepalive_connections=10),
            )
        return self._http

    async def search_snomed(self, normalized_terms: List[str]) -> List[Dict[str, Any]]:
        """
        Search SNOMED CT concepts for normalized terms.

        Args:
            normalized_terms: List of normalized clinical terms

        Returns:
            List of candidate dicts with code, display, score, source
        """
        if not normalized_terms:
            return []

        return await self._search_terminology("snomed", normalized_terms)

    async def search_icd(
        self,
        normalized_terms: List[str],
        soap: Optional[Dict] = None,
        entities: Optional[List[Dict]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Search ICD-11 codes for normalized terms.

        Args:
            normalized_terms: List of normalized clinical terms
            soap: Optional SOAP note for context
            entities: Optional extracted entities for context

        Returns:
            List of candidate dicts with code, display, score, source
        """
        if not normalized_terms:
            return []

        context = {}
        if soap:
            context["soap"] = soap
        if entities:
            context["entities"] = entities

        return await self._search_terminology("icd11", normalized_terms, context=context)

    async def search_rxnorm(self, medication_terms: List[str]) -> List[Dict[str, Any]]:
        """
        Search RxNorm for medication terms.

        Args:
            medication_terms: List of medication names/ingredients

        Returns:
            List of candidate dicts
        """
        if not medication_terms:
            return []

        return await self._search_terminology("rxnorm", medication_terms)

    async def search_loinc(self, lab_terms: List[str]) -> List[Dict[str, Any]]:
        """
        Search LOINC for laboratory test terms.

        Args:
            lab_terms: List of lab test names

        Returns:
            List of candidate dicts
        """
        if not lab_terms:
            return []

        return await self._search_terminology("loinc", lab_terms)

    async def _search_terminology(
        self,
        system: str,
        terms: List[str],
        context: Optional[Dict] = None,
    ) -> List[Dict[str, Any]]:
        """
        Generic terminology search with retry and error handling.

        Args:
            system: Terminology system (snomed, icd11, rxnorm, loinc)
            terms: Search terms
            context: Optional context data

        Returns:
            List of candidate dicts
        """
        start_time = time.time()

        try:
            with terminology_span(system=system, terms=terms):
                http = await self._get_http()

                payload = {
                    "system": system,
                    "terms": terms,
                    "context": context or {},
                }

                response = await self._post_with_retry("/search", payload)

                if response.status_code == 200:
                    data = response.json()
                    candidates = data.get("candidates", [])
                    elapsed_ms = int((time.time() - start_time) * 1000)
                    record_terminology_cache_hit(system, hit=True)
                    logger.debug(
                        "terminology_search_success",
                        system=system,
                        terms=len(terms),
                        candidates=len(candidates),
                        latency_ms=elapsed_ms,
                    )
                    return candidates
                else:
                    logger.warning(
                        "terminology_service_error",
                        system=system,
                        status_code=response.status_code,
                        response=response.text[:200],
                    )
                    record_terminology_cache_hit(system, hit=False)
                    return []

        except httpx.HTTPStatusError as e:
            logger.error(
                "terminology_http_error",
                system=system,
                status_code=e.response.status_code,
                error=str(e),
            )
            raise TerminologyGatewayError(
                message=f"Terminology gateway returned {e.response.status_code}",
                details={"system": system, "terms": terms},
            )

        except httpx.RequestError as e:
            logger.error(
                "terminology_request_error",
                system=system,
                error=str(e),
            )
            raise TerminologyGatewayError(
                message=f"Cannot reach terminology gateway: {str(e)}",
                details={"system": system, "gateway_url": self.base_url},
            )

        except Exception as e:
            logger.error(
                "terminology_unexpected_error",
                system=system,
                error_type=type(e).__name__,
                error=str(e),
            )
            raise TerminologyGatewayError(
                message=f"Terminology gateway error: {str(e)}",
                details={"system": system},
            )

    @retry(
        stop=stop_after_attempt(2),
        wait=wait_exponential(multiplier=1, min=1, max=5),
        retry=retry_if_exception_type((httpx.NetworkError, httpx.ConnectError, httpx.ReadTimeout)),
        reraise=True,
    )
    async def _post_with_retry(self, path: str, payload: Dict) -> httpx.Response:
        """POST request with retry logic."""
        http = await self._get_http()
        response = await http.post(path, json=payload)
        response.raise_for_status()
        return response

    async def health_check(self) -> bool:
        """Check terminology gateway health."""
        try:
            http = await self._get_http()
            response = await http.get("/health", timeout=5.0)
            return response.status_code == 200
        except Exception as e:
            logger.warning("terminology_health_check_failed", error=str(e))
            return False

    async def close(self) -> None:
        """Close HTTP client."""
        if self._http:
            await self._http.aclose()
            self._http = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
