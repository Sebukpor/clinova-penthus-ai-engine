"""
Clinova Penthus AI Engine - Terminology Clients
Direct clients for SNOMED CT and ICD-11 terminology services.
No gateway abstraction - direct API calls with caching and retries.
"""

import hashlib
import time
from typing import Any, Dict, List, Optional

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.core.config import get_settings
from app.core.errors import TerminologyGatewayError
from app.core.logging import get_logger

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


class SNOMEDClient:
    """
    Direct SNOMED CT client using public SNOMED CT server.
    Endpoint: http://92.4.73.217:8100/csnoserv/api/search/search
    """

    BASE_URL = "http://92.4.73.217:8100/csnoserv/api/search/search"
    
    def __init__(self):
        self.settings = get_settings()
        self.timeout = 15.0  # SNOMED can be slow
        self.max_retries = 2
        self._http: Optional[httpx.AsyncClient] = None
        self._cache: Dict[str, tuple[List[Dict], float]] = {}
        self._cache_ttl = 604800  # 7 days

    async def _get_http(self) -> httpx.AsyncClient:
        """Lazy HTTP client initialization."""
        if self._http is None:
            self._http = httpx.AsyncClient(
                timeout=httpx.Timeout(self.timeout, connect=5.0),
                limits=httpx.Limits(max_connections=20, max_keepalive_connections=5),
            )
        return self._http

    def _cache_key(self, term: str) -> str:
        """Generate cache key for a search term."""
        return hashlib.sha256(term.lower().encode()).hexdigest()

    def _get_cached(self, key: str) -> Optional[List[Dict]]:
        """Get cached result if valid."""
        if key in self._cache:
            result, timestamp = self._cache[key]
            if time.time() - timestamp < self._cache_ttl:
                return result
            del self._cache[key]
        return None

    def _set_cache(self, key: str, result: List[Dict]) -> None:
        """Cache a search result."""
        self._cache[key] = (result, time.time())

    @retry(
        stop=stop_after_attempt(2),
        wait=wait_exponential(multiplier=1, min=1, max=5),
        retry=retry_if_exception_type((httpx.NetworkError, httpx.ConnectError, httpx.ReadTimeout)),
        reraise=True,
    )
    async def search(self, term: str) -> List[Dict[str, Any]]:
        """
        Search SNOMED CT for a clinical term.
        
        Args:
            term: Clinical term to search
            
        Returns:
            List of candidate dicts with code, display, score, source
        """
        # Check cache first
        cache_key = self._cache_key(term)
        cached = self._get_cached(cache_key)
        if cached is not None:
            logger.debug("snomed_cache_hit", term=term)
            return cached

        try:
            http = await self._get_http()
            
            # SNOMED CT search endpoint
            params = {"term": term}
            
            logger.debug("snomed_search_request", term=term, url=self.BASE_URL)
            
            response = await http.get(self.BASE_URL, params=params)
            response.raise_for_status()
            
            data = response.json()
            
            # Parse SNOMED CT response format
            candidates = []
            results = data.get("results", []) if isinstance(data, dict) else data
            
            for item in results[:10]:  # Limit to top 10
                if isinstance(item, dict):
                    # SNOMED CT server returns conceptId, conceptFsn, term fields
                    code = item.get("conceptId", item.get("id", item.get("code", "")))
                    display = item.get("conceptFsn", item.get("term", item.get("display", "")))
                    # Strip "(disorder)" etc from display for cleaner output
                    if display and "(" in display:
                        display = display[:display.rfind("(")].strip()
                    candidate = {
                        "code": str(code),
                        "display": display,
                        "score": float(item.get("score", item.get("matchScore", 0.9))),
                        "source": "SNOMED_CT",
                    }
                    if candidate["code"] and candidate["display"]:
                        candidates.append(candidate)
            
            # Cache the result
            self._set_cache(cache_key, candidates)
            
            logger.info(
                "snomed_search_success",
                term=term,
                candidates=len(candidates),
            )
            
            return candidates
            
        except httpx.HTTPStatusError as e:
            logger.warning(
                "snomed_http_error",
                term=term,
                status_code=e.response.status_code,
                error=str(e),
            )
            raise TerminologyGatewayError(
                message=f"SNOMED CT service returned {e.response.status_code}",
                details={"term": term},
            )
        except httpx.RequestError as e:
            logger.warning(
                "snomed_request_error",
                term=term,
                error=str(e),
            )
            raise TerminologyGatewayError(
                message=f"Cannot reach SNOMED CT service: {str(e)}",
                details={"term": term},
            )
        except Exception as e:
            logger.warning(
                "snomed_unexpected_error",
                term=term,
                error_type=type(e).__name__,
                error=str(e),
            )
            raise TerminologyGatewayError(
                message=f"SNOMED CT search error: {str(e)}",
                details={"term": term},
            )

    async def search_terms(self, terms: List[str]) -> List[Dict[str, Any]]:
        """
        Search SNOMED CT for multiple terms.
        
        Args:
            terms: List of clinical terms
            
        Returns:
            Combined list of all candidates
        """
        if not terms:
            return []
        
        all_candidates = []
        for term in terms:
            try:
                candidates = await self.search(term)
                all_candidates.extend(candidates)
            except TerminologyGatewayError as e:
                logger.warning("snomed_term_search_failed", term=term, error=str(e))
                # Continue with other terms
        
        return all_candidates

    async def close(self) -> None:
        """Close HTTP client."""
        if self._http:
            await self._http.aclose()
            self._http = None

    async def health_check(self) -> bool:
        """Check SNOMED service health."""
        try:
            http = await self._get_http()
            # Simple search to test connectivity
            response = await http.get(self.BASE_URL, params={"term": "fever"}, timeout=5.0)
            return response.status_code == 200
        except Exception:
            return False


class ICD11Client:
    """
    Direct ICD-11 client using NIH Clinical Tables API.
    Endpoint: https://clinicaltables.nlm.nih.gov/api/icd11_codes/v3/search
    """

    BASE_URL = "https://clinicaltables.nlm.nih.gov/api/icd11_codes/v3/search"
    
    def __init__(self):
        self.settings = get_settings()
        self.timeout = 10.0
        self.max_retries = 2
        self._http: Optional[httpx.AsyncClient] = None
        self._cache: Dict[str, tuple[List[Dict], float]] = {}
        self._cache_ttl = 604800  # 7 days

    async def _get_http(self) -> httpx.AsyncClient:
        """Lazy HTTP client initialization."""
        if self._http is None:
            self._http = httpx.AsyncClient(
                timeout=httpx.Timeout(self.timeout, connect=5.0),
                limits=httpx.Limits(max_connections=20, max_keepalive_connections=5),
            )
        return self._http

    def _cache_key(self, term: str) -> str:
        """Generate cache key for a search term."""
        return hashlib.sha256(term.lower().encode()).hexdigest()

    def _get_cached(self, key: str) -> Optional[List[Dict]]:
        """Get cached result if valid."""
        if key in self._cache:
            result, timestamp = self._cache[key]
            if time.time() - timestamp < self._cache_ttl:
                return result
            del self._cache[key]
        return None

    def _set_cache(self, key: str, result: List[Dict]) -> None:
        """Cache a search result."""
        self._cache[key] = (result, time.time())

    @retry(
        stop=stop_after_attempt(2),
        wait=wait_exponential(multiplier=1, min=1, max=5),
        retry=retry_if_exception_type((httpx.NetworkError, httpx.ConnectError, httpx.ReadTimeout)),
        reraise=True,
    )
    async def search(self, term: str, count: int = 10) -> List[Dict[str, Any]]:
        """
        Search ICD-11 for a clinical term.
        
        Args:
            term: Clinical term to search
            count: Maximum number of results to return
            
        Returns:
            List of candidate dicts with code, display, score, source
        """
        # Check cache first
        cache_key = self._cache_key(f"{term}:{count}")
        cached = self._get_cached(cache_key)
        if cached is not None:
            logger.debug("icd11_cache_hit", term=term)
            return cached

        try:
            http = await self._get_http()
            
            # NIH Clinical Tables ICD-11 search
            params = {
                "terms": term,
                "count": count,
            }
            
            logger.debug("icd11_search_request", term=term, url=self.BASE_URL)
            
            response = await http.get(self.BASE_URL, params=params)
            response.raise_for_status()
            
            data = response.json()
            
            # Parse NIH Clinical Tables response format
            # Format: [version, count, array_of_results, metadata]
            candidates = []
            
            # NIH Clinical Tables format: [total_count, [codes], null, [[code, display, type], ...]]
            if isinstance(data, list) and len(data) >= 4 and isinstance(data[3], list):
                details = data[3]  # Detailed results in index 3
                for item in details:
                    if isinstance(item, list) and len(item) >= 2:
                        candidate = {
                            "code": str(item[0]),
                            "display": str(item[1]),
                            "score": 0.9,
                            "source": "ICD11",
                        }
                        if candidate["code"] and candidate["display"]:
                            candidates.append(candidate)
            elif isinstance(data, list) and len(data) >= 2 and isinstance(data[1], list):
                # Fallback: codes in index 1
                codes = data[1]
                for code in codes:
                    candidate = {
                        "code": str(code),
                        "display": str(code),
                        "score": 0.9,
                        "source": "ICD11",
                    }
                    candidates.append(candidate)
            elif isinstance(data, dict):
                results = data.get("results", data.get("codes", []))
                for item in results:
                    if isinstance(item, dict):
                        candidate = {
                            "code": item.get("code", item.get("id", "")),
                            "display": item.get("description", item.get("name", "")),
                            "score": float(item.get("score", 0.9)),
                            "source": "ICD11",
                        }
                        if candidate["code"] and candidate["display"]:
                            candidates.append(candidate)
            
            # Cache the result
            self._set_cache(cache_key, candidates)
            
            logger.info(
                "icd11_search_success",
                term=term,
                candidates=len(candidates),
            )
            
            return candidates
            
        except httpx.HTTPStatusError as e:
            logger.warning(
                "icd11_http_error",
                term=term,
                status_code=e.response.status_code,
                error=str(e),
            )
            raise TerminologyGatewayError(
                message=f"ICD-11 service returned {e.response.status_code}",
                details={"term": term},
            )
        except httpx.RequestError as e:
            logger.warning(
                "icd11_request_error",
                term=term,
                error=str(e),
            )
            raise TerminologyGatewayError(
                message=f"Cannot reach ICD-11 service: {str(e)}",
                details={"term": term},
            )
        except Exception as e:
            logger.warning(
                "icd11_unexpected_error",
                term=term,
                error_type=type(e).__name__,
                error=str(e),
            )
            raise TerminologyGatewayError(
                message=f"ICD-11 search error: {str(e)}",
                details={"term": term},
            )

    async def search_terms(self, terms: List[str]) -> List[Dict[str, Any]]:
        """
        Search ICD-11 for multiple terms.
        
        Args:
            terms: List of clinical terms
            
        Returns:
            Combined list of all candidates
        """
        if not terms:
            return []
        
        all_candidates = []
        for term in terms:
            try:
                candidates = await self.search(term)
                all_candidates.extend(candidates)
            except TerminologyGatewayError as e:
                logger.warning("icd11_term_search_failed", term=term, error=str(e))
                # Continue with other terms
        
        return all_candidates

    async def close(self) -> None:
        """Close HTTP client."""
        if self._http:
            await self._http.aclose()
            self._http = None

    async def health_check(self) -> bool:
        """Check ICD-11 service health."""
        try:
            http = await self._get_http()
            response = await http.get(self.BASE_URL, params={"terms": "heart", "count": 1}, timeout=5.0)
            return response.status_code == 200
        except Exception:
            return False


class TerminologyService:
    """
    Unified terminology service providing both SNOMED CT and ICD-11 lookups.
    Replaces the gateway abstraction with direct service clients.
    """

    def __init__(self):
        self.snomed = SNOMEDClient()
        self.icd11 = ICD11Client()

    async def search_snomed(self, terms: List[str]) -> List[Dict[str, Any]]:
        """Search SNOMED CT for multiple terms."""
        return await self.snomed.search_terms(terms)

    async def search_icd(
        self,
        terms: List[str],
        soap: Optional[Dict] = None,
        entities: Optional[List[Dict]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Search ICD-11 for multiple terms.
        
        Note: SOAP and entities parameters are kept for API compatibility
        but are not used in direct ICD-11 searches.
        """
        return await self.icd11.search_terms(terms)

    async def close(self) -> None:
        """Close all clients."""
        await self.snomed.close()
        await self.icd11.close()

    async def health_check(self) -> Dict[str, bool]:
        """Check health of all terminology services."""
        return {
            "snomed": await self.snomed.health_check(),
            "icd11": await self.icd11.health_check(),
        }
