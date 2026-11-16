"""Read-only public staging HTTPS smoke from CI, outside workstation TLS interception."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'firmware'))
from http_client import request_json
status, response = request_json('GET', 'https://staging.rcdrift.ro/api/version', timeout=10)
assert status == 200 and response.get('versionTag'), 'Public staging TLS/read failed'
print('Verified public staging TLS with bundled CA:', response['versionTag'])
