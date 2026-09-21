from fastapi.testclient import TestClient


def create_key(client: TestClient, name: str = "ci") -> str:
    page = client.post("/keys", data={"name": name}, follow_redirects=True)
    assert page.status_code == 200
    assert "copy it now" in page.text.lower()
    start = page.text.find("laya_")
    assert start != -1
    raw = page.text[start:].split("<")[0].strip()
    assert raw.startswith("laya_")
    return raw
