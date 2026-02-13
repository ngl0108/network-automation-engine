from app.services.oui_service import OUIService


def test_oui_service_lookup_vendor_from_override_map():
    OUIService.set_override_map_for_tests({"aabbcc": "Acme"})
    try:
        assert OUIService.lookup_vendor("aa:bb:cc:11:22:33") == "Acme"
        assert OUIService.lookup_vendor("aabb.ccdd.eeff") == "Acme"
        assert OUIService.lookup_vendor("zz") is None
    finally:
        OUIService.set_override_map_for_tests(None)
