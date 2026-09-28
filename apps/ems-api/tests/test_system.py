from fastapi.testclient import TestClient
from app.main import app
client=TestClient(app)
def test_health(): assert client.get('/health').json()=={'status':'ok','service':'infotech-ems-api'}
def test_info():
    payload=client.get('/api/v1/system/info').json()
    assert payload['application_name']=='InfoTech Workspace EMS API' and payload['api_version']=='v1'
