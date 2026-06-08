"""Constants for the Felicity Battery integration."""

DOMAIN = "felicity_battery"

CONF_USERNAME = "username"
CONF_PASSWORD = "password"
CONF_DEVICE_SN = "device_sn"
CONF_SCAN_INTERVAL = "scan_interval"

DEFAULT_SCAN_INTERVAL = 60

API_BASE_URL = "https://shine-api.felicitysolar.com"
API_HEADERS = {
    "Content-Type": "application/json",
    "source": "IOS",
    "version": "3.2.3",
    "lang": "en_US",
}

LOGIN_URL = "/app/base/userlogin"
ENDPOINT_DEVICE_SNAPSHOT = "/app/device/get_device_snapshot"
ENDPOINT_DEVICE_LIST = "/app/device/list_device_all_type"

RSA_PUBLIC_KEY = "MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAnAJE68pjWZmtSg6ZJs9FZugJXC6bBSluTW6mJttOLOaljrdErVnM5DNN+YFzpB9pAysTErjY1bnSVuEwQSwptnqUji7Ch2qMj2n+0eCp8p6vtSh7/tFr2ul8nDRtkoswLANAIwtUk/G85ipMpmY1W642LImnEJmGkkddlbjbjxJTZWR5hc/d9cPWb+AR77LxFFrMik3c+44v1kQlIPFP6EjIbOvt/Lv7fHWD9JI/YzN4y1gK7C/VQdNGuikQyNg+5W3rg9ecYf9I5uLAQwY/hxeI3lbNsErebqKe2EbJ8AwcNIC0lDBz53Sq0ML89QapEuy3fB+upuctxLULVDCbNwIDAQAB"  # noqa: E501

# Number of real cells/temps (rest are padding)
REAL_CELL_COUNT = 8
REAL_TEMP_COUNT = 4
CELL_PADDING_VALUE = 32767
TEMP_PADDING_VALUE = 3276.7
