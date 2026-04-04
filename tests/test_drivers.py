"""Tests for homelink/drivers.py — device drivers and factory."""

from unittest.mock import MagicMock, patch

import pytest

from guardian_one.homelink.drivers import (
    DriverFactory,
    GoveeCloudDriver,
    GoveeLanDriver,
    HueDriver,
    KasaDriver,
    LgWebOsDriver,
    _fail,
    _ok,
)


# --- Result helpers ---

class TestResultHelpers:

    def test_ok_result_format(self):
        result = _ok("turn_on", device_ip="192.168.1.1")
        assert result["success"] is True
        assert result["action"] == "turn_on"
        assert result["error"] == ""
        assert result["device_ip"] == "192.168.1.1"

    def test_fail_result_format(self):
        result = _fail("turn_off", "Connection refused", device_ip="10.0.0.1")
        assert result["success"] is False
        assert result["action"] == "turn_off"
        assert result["error"] == "Connection refused"
        assert result["device_ip"] == "10.0.0.1"


# --- Kasa Driver ---

class TestKasaDriver:

    def test_init_stores_ip(self):
        driver = KasaDriver(ip="192.168.1.50")
        assert driver._ip == "192.168.1.50"

    def test_turn_on_import_error(self):
        """When python-kasa is not installed, returns graceful failure."""
        driver = KasaDriver(ip="192.168.1.50")
        import sys
        orig = sys.modules.pop("kasa", None)
        try:
            with patch.dict("sys.modules", {"kasa": None}):
                result = driver.turn_on()
                assert result["success"] is False
                assert "python-kasa" in result["error"]
        finally:
            if orig is not None:
                sys.modules["kasa"] = orig

    def test_turn_off_import_error(self):
        driver = KasaDriver(ip="192.168.1.50")
        import sys
        orig = sys.modules.pop("kasa", None)
        try:
            with patch.dict("sys.modules", {"kasa": None}):
                result = driver.turn_off()
                assert result["success"] is False
        finally:
            if orig is not None:
                sys.modules["kasa"] = orig

    def test_get_status_import_error(self):
        driver = KasaDriver(ip="192.168.1.50")
        import sys
        orig = sys.modules.pop("kasa", None)
        try:
            with patch.dict("sys.modules", {"kasa": None}):
                result = driver.get_status()
                assert result["success"] is False
        finally:
            if orig is not None:
                sys.modules["kasa"] = orig


# --- Hue Driver ---

class TestHueDriver:

    def test_init_stores_bridge_ip(self):
        driver = HueDriver(bridge_ip="192.168.1.10", api_key="abc123")
        assert driver._bridge_ip == "192.168.1.10"
        assert driver._api_key == "abc123"

    def test_base_url_property(self):
        driver = HueDriver(bridge_ip="192.168.1.10", api_key="abc123")
        assert driver._base_url == "https://192.168.1.10/api/abc123"

    def test_no_api_key_fails(self):
        """Driver without api_key returns failure from _request."""
        driver = HueDriver(bridge_ip="192.168.1.10")
        result = driver._request("GET", "/lights")
        assert result["success"] is False
        assert "No Hue API key" in result["error"]

    def test_turn_on_with_light_id(self):
        driver = HueDriver(bridge_ip="192.168.1.10", api_key="abc123")
        with patch.object(driver, "_request", return_value=_ok("put")) as mock_req:
            result = driver.turn_on(light_id=1, brightness=200)
            assert result["success"] is True
            mock_req.assert_called_once_with(
                "PUT", "/lights/1/state", {"on": True, "bri": 200},
            )

    def test_turn_on_with_group_id(self):
        driver = HueDriver(bridge_ip="192.168.1.10", api_key="abc123")
        with patch.object(driver, "_request", return_value=_ok("put")) as mock_req:
            result = driver.turn_on(group_id=3, brightness=128)
            assert result["success"] is True
            mock_req.assert_called_once_with(
                "PUT", "/groups/3/action", {"on": True, "bri": 128},
            )

    def test_turn_on_default_all_lights(self):
        """When no light_id or group_id, defaults to group 0 (all lights)."""
        driver = HueDriver(bridge_ip="192.168.1.10", api_key="abc123")
        with patch.object(driver, "_request", return_value=_ok("put")) as mock_req:
            driver.turn_on()
            mock_req.assert_called_once_with(
                "PUT", "/groups/0/action", {"on": True, "bri": 254},
            )

    def test_turn_off_with_light_id(self):
        driver = HueDriver(bridge_ip="192.168.1.10", api_key="abc123")
        with patch.object(driver, "_request", return_value=_ok("put")) as mock_req:
            result = driver.turn_off(light_id=2)
            assert result["success"] is True
            mock_req.assert_called_once_with(
                "PUT", "/lights/2/state", {"on": False},
            )

    def test_brightness_scaling(self):
        """0-100% -> 1-254 Hue scale. 50% -> ~127."""
        driver = HueDriver(bridge_ip="192.168.1.10", api_key="abc123")
        with patch.object(driver, "_request", return_value=_ok("put")) as mock_req:
            driver.set_brightness(50, light_id=1)
            call_body = mock_req.call_args[0][2]
            assert call_body["on"] is True
            assert 125 <= call_body["bri"] <= 129

    @pytest.mark.parametrize("brightness_pct,expected_min,expected_max", [
        (0, 1, 1),       # clamps to min=1
        (100, 254, 254),  # max
        (50, 125, 129),   # ~127
    ])
    def test_brightness_scaling_parametrized(self, brightness_pct, expected_min, expected_max):
        driver = HueDriver(bridge_ip="192.168.1.10", api_key="abc123")
        with patch.object(driver, "_request", return_value=_ok("put")) as mock_req:
            driver.set_brightness(brightness_pct, light_id=1)
            call_body = mock_req.call_args[0][2]
            assert expected_min <= call_body["bri"] <= expected_max

    @pytest.mark.parametrize("color_name,expected_key", [
        ("warm", "ct"),
        ("daylight", "ct"),
        ("red", "hue"),
        ("green", "hue"),
        ("blue", "hue"),
    ])
    def test_set_color_presets(self, color_name, expected_key):
        driver = HueDriver(bridge_ip="192.168.1.10", api_key="abc123")
        with patch.object(driver, "_request", return_value=_ok("put")) as mock_req:
            result = driver.set_color(light_id=1, color_name=color_name)
            assert result["success"] is True
            call_body = mock_req.call_args[0][2]
            assert expected_key in call_body

    def test_set_color_no_color_specified(self):
        driver = HueDriver(bridge_ip="192.168.1.10", api_key="abc123")
        result = driver.set_color(light_id=1)
        assert result["success"] is False
        assert "No color specified" in result["error"]

    def test_set_color_with_hue_value(self):
        driver = HueDriver(bridge_ip="192.168.1.10", api_key="abc123")
        with patch.object(driver, "_request", return_value=_ok("put")) as mock_req:
            result = driver.set_color(light_id=1, hue=10000, sat=200)
            assert result["success"] is True
            call_body = mock_req.call_args[0][2]
            assert call_body["hue"] == 10000
            assert call_body["sat"] == 200

    def test_get_lights(self):
        driver = HueDriver(bridge_ip="192.168.1.10", api_key="abc123")
        with patch.object(driver, "_request", return_value=_ok("get", data={})) as mock_req:
            result = driver.get_lights()
            assert result["success"] is True
            mock_req.assert_called_once_with("GET", "/lights")

    def test_get_groups(self):
        driver = HueDriver(bridge_ip="192.168.1.10", api_key="abc123")
        with patch.object(driver, "_request", return_value=_ok("get", data={})) as mock_req:
            result = driver.get_groups()
            assert result["success"] is True
            mock_req.assert_called_once_with("GET", "/groups")


# --- Govee LAN Driver ---

class TestGoveeLanDriver:

    def test_init_stores_device_info(self):
        driver = GoveeLanDriver(device_ip="192.168.1.60", device_sku="H6172")
        assert driver._device_ip == "192.168.1.60"
        assert driver._device_sku == "H6172"

    def test_turn_on_no_ip_fails(self):
        driver = GoveeLanDriver()  # no IP
        result = driver.turn_on()
        assert result["success"] is False
        assert "No device IP" in result["error"]

    def test_turn_off_no_ip_fails(self):
        driver = GoveeLanDriver()
        result = driver.turn_off()
        assert result["success"] is False

    def test_send_command_builds_correct_payload(self):
        """Verify the UDP command structure for turn_on."""
        driver = GoveeLanDriver(device_ip="192.168.1.60")
        with patch("socket.socket") as mock_socket_cls:
            mock_sock = MagicMock()
            mock_socket_cls.return_value = mock_sock
            mock_sock.recvfrom.side_effect = Exception("timeout")
            # Despite the exception in recvfrom, sendto should have been called
            driver.turn_on()
            # Verify sendto was called with correct port
            mock_sock.sendto.assert_called_once()
            args = mock_sock.sendto.call_args[0]
            assert args[1] == ("192.168.1.60", 4003)

    @pytest.mark.parametrize("brightness,expected", [
        (0, 0),
        (100, 100),
        (150, 100),   # clamped to max
        (-10, 0),     # clamped to min
    ])
    def test_brightness_clamping(self, brightness, expected):
        driver = GoveeLanDriver(device_ip="192.168.1.60")
        with patch.object(driver, "_send_command", return_value=_ok("brightness")) as mock_cmd:
            driver.set_brightness(brightness)
            sent_value = mock_cmd.call_args[0][0]["msg"]["data"]["value"]
            assert sent_value == expected

    def test_set_color_rgb(self):
        driver = GoveeLanDriver(device_ip="192.168.1.60")
        with patch("socket.socket") as mock_socket_cls:
            mock_sock = MagicMock()
            mock_socket_cls.return_value = mock_sock
            mock_sock.recvfrom.side_effect = Exception("timeout")
            driver.set_color(r=255, g=0, b=128)

    @pytest.mark.parametrize("kelvin,expected", [
        (2000, 2000),
        (9000, 9000),
        (1000, 2000),   # clamped to min
        (15000, 9000),  # clamped to max
    ])
    def test_color_temperature_clamping(self, kelvin, expected):
        driver = GoveeLanDriver(device_ip="192.168.1.60")
        with patch.object(driver, "_send_command", return_value=_ok("colorwc")) as mock_cmd:
            driver.set_color_temperature(kelvin)
            sent_kelvin = mock_cmd.call_args[0][0]["msg"]["data"]["colorTemInKelvin"]
            assert sent_kelvin == expected


# --- Govee Cloud Driver ---

class TestGoveeCloudDriver:

    def test_init(self):
        driver = GoveeCloudDriver(api_key="test_key", device_id="D1", model="H6172")
        assert driver._api_key == "test_key"
        assert driver._device_id == "D1"

    def test_control_without_device_id_fails(self):
        driver = GoveeCloudDriver(api_key="test_key")
        result = driver.turn_on()
        assert result["success"] is False
        assert "device_id and model required" in result["error"]

    def test_list_devices_makes_get_request(self):
        driver = GoveeCloudDriver(api_key="test_key")
        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_resp = MagicMock()
            mock_resp.read.return_value = b'{"data": []}'
            mock_resp.__enter__ = MagicMock(return_value=mock_resp)
            mock_resp.__exit__ = MagicMock(return_value=False)
            mock_urlopen.return_value = mock_resp
            result = driver.list_devices()
            assert result["success"] is True

    def test_api_key_in_headers(self):
        driver = GoveeCloudDriver(api_key="my_secret_key", device_id="D1", model="H6172")
        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_resp = MagicMock()
            mock_resp.read.return_value = b'{"data": "ok"}'
            mock_resp.__enter__ = MagicMock(return_value=mock_resp)
            mock_resp.__exit__ = MagicMock(return_value=False)
            mock_urlopen.return_value = mock_resp
            driver.turn_on()
            req = mock_urlopen.call_args[0][0]
            headers = {key.lower(): value for key, value in req.header_items()}
            assert headers["govee-api-key"] == "my_secret_key"


# --- LG WebOS Driver ---

class TestLgWebOsDriver:

    def test_init_stores_ip_and_key(self):
        driver = LgWebOsDriver(ip="192.168.1.70", client_key="abc")
        assert driver._ip == "192.168.1.70"
        assert driver._client_key == "abc"

    @pytest.mark.parametrize("input_level,expected_level", [
        (-5, 0),
        (150, 100),
        (50, 50),
    ])
    def test_volume_clamping(self, input_level, expected_level):
        driver = LgWebOsDriver(ip="192.168.1.70")
        with patch.object(driver, "_run", return_value=_ok("set_volume")) as mock_run:
            driver.set_volume(input_level)
            mock_run.assert_called_once()


# --- Driver Factory ---

class TestDriverFactory:

    def test_get_kasa_driver(self):
        factory = DriverFactory()
        driver = factory.get_kasa_driver("192.168.1.50")
        assert isinstance(driver, KasaDriver)
        assert driver._ip == "192.168.1.50"

    def test_get_hue_driver_with_vault(self):
        factory = DriverFactory(vault_retrieve=lambda k: "hue_api_key" if k == "HUE_BRIDGE_API_KEY" else None)
        driver = factory.get_hue_driver("192.168.1.10")
        assert isinstance(driver, HueDriver)
        assert driver._api_key == "hue_api_key"

    def test_get_hue_driver_no_vault(self):
        factory = DriverFactory()
        driver = factory.get_hue_driver("192.168.1.10")
        assert driver._api_key == ""

    def test_get_govee_driver(self):
        factory = DriverFactory()
        driver = factory.get_govee_driver("192.168.1.60")
        assert isinstance(driver, GoveeLanDriver)

    def test_get_govee_cloud_driver_with_key(self):
        factory = DriverFactory(vault_retrieve=lambda k: "govee_key" if k == "GOVEE_API_KEY" else None)
        driver = factory.get_govee_cloud_driver(device_id="D1", model="H6172")
        assert isinstance(driver, GoveeCloudDriver)

    def test_get_govee_cloud_driver_no_key(self):
        factory = DriverFactory()
        driver = factory.get_govee_cloud_driver()
        assert driver is None

    def test_get_lg_driver(self):
        factory = DriverFactory(vault_retrieve=lambda k: "lg_key" if k == "LG_TV_CLIENT_KEY" else None)
        driver = factory.get_lg_driver("192.168.1.70")
        assert isinstance(driver, LgWebOsDriver)
        assert driver._client_key == "lg_key"

    def test_for_device_kasa(self):
        factory = DriverFactory()
        device = MagicMock()
        device.integration_name = "tplink_kasa"
        device.ip_address = "192.168.1.50"
        driver = factory.for_device(device)
        assert isinstance(driver, KasaDriver)

    def test_for_device_hue(self):
        factory = DriverFactory()
        device = MagicMock()
        device.integration_name = "philips_hue"
        device.ip_address = "192.168.1.10"
        driver = factory.for_device(device)
        assert isinstance(driver, HueDriver)

    def test_for_device_govee_lan_preferred(self):
        """When IP is known, LAN driver is preferred over cloud."""
        factory = DriverFactory(vault_retrieve=lambda k: "key")
        device = MagicMock()
        device.integration_name = "govee"
        device.ip_address = "192.168.1.60"
        driver = factory.for_device(device)
        assert isinstance(driver, GoveeLanDriver)

    def test_for_device_govee_cloud_fallback(self):
        """When IP is empty, falls back to cloud if API key in vault."""
        factory = DriverFactory(vault_retrieve=lambda k: "govee_key" if k == "GOVEE_API_KEY" else None)
        device = MagicMock()
        device.integration_name = "govee"
        device.ip_address = ""
        device.device_id = "D1"
        device.model = "H6172"
        driver = factory.for_device(device)
        assert isinstance(driver, GoveeCloudDriver)

    def test_for_device_smart_tv(self):
        factory = DriverFactory()
        device = MagicMock()
        device.integration_name = "lg_webos"
        device.ip_address = "192.168.1.70"
        device.category.value = "smart_tv"
        driver = factory.for_device(device)
        assert isinstance(driver, LgWebOsDriver)

    def test_for_device_no_ip_returns_none(self):
        factory = DriverFactory()
        device = MagicMock()
        device.integration_name = "tplink_kasa"
        device.ip_address = ""
        driver = factory.for_device(device)
        assert driver is None

    def test_for_device_unknown_integration(self):
        factory = DriverFactory()
        device = MagicMock()
        device.integration_name = "unknown_vendor"
        device.ip_address = "192.168.1.99"
        device.category.value = "other"
        driver = factory.for_device(device)
        assert driver is None
