import os
import re
from functools import lru_cache
from typing import Dict, Optional


class OUIService:
    _override_map: Optional[Dict[str, str]] = None

    @staticmethod
    def _normalize_mac_prefix(mac: str) -> Optional[str]:
        if not mac:
            return None
        s = str(mac).strip().lower()
        s = re.sub(r"[^0-9a-f]", "", s)
        if len(s) < 6:
            return None
        return s[:6]

    @staticmethod
    def _possible_paths() -> list:
        env = os.getenv("OUI_DB_PATH")
        paths = []
        if env:
            paths.append(env)
        here = os.path.dirname(os.path.abspath(__file__))
        paths.append(os.path.join(here, "..", "data", "oui.csv"))
        paths.append(os.path.join(here, "..", "data", "oui.txt"))
        return paths

    @staticmethod
    @lru_cache(maxsize=1)
    def _load_map() -> Dict[str, str]:
        if isinstance(OUIService._override_map, dict):
            return OUIService._override_map

        mapping: Dict[str, str] = {}
        for p in OUIService._possible_paths():
            try:
                if not p or not os.path.exists(p):
                    continue
                with open(p, "r", encoding="utf-8", errors="ignore") as f:
                    for line in f:
                        ln = line.strip()
                        if not ln:
                            continue
                        if ln.startswith("#"):
                            continue
                        if "," in ln:
                            parts = [x.strip() for x in ln.split(",")]
                            if len(parts) >= 2:
                                prefix = OUIService._normalize_mac_prefix(parts[0])
                                vendor = parts[1].strip()
                                if prefix and vendor:
                                    mapping[prefix] = vendor
                            continue

                        m = re.search(r"^([0-9A-Fa-f]{2}[:-]){2}[0-9A-Fa-f]{2}", ln)
                        if m:
                            prefix = OUIService._normalize_mac_prefix(m.group(0))
                            vendor = ln[m.end() :].strip()
                            vendor = re.sub(r"^\(hex\)\s*", "", vendor, flags=re.IGNORECASE).strip()
                            if prefix and vendor:
                                mapping[prefix] = vendor
                            continue
            except Exception:
                continue

        return mapping

    @staticmethod
    def lookup_vendor(mac: str) -> Optional[str]:
        prefix = OUIService._normalize_mac_prefix(mac)
        if not prefix:
            return None
        return OUIService._load_map().get(prefix)

    @staticmethod
    def set_override_map_for_tests(mapping: Optional[Dict[str, str]]) -> None:
        OUIService._override_map = mapping
        OUIService._load_map.cache_clear()
