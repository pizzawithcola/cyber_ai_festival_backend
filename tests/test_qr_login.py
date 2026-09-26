"""QR login pairing endpoint tests."""


class TestQrLogin:
    def test_full_pairing_flow(self, client, sample_user):
        s = client.post("/qr-login/session")
        assert s.status_code == 200
        code = s.json()["station_code"]
        assert len(code) == 6

        p = client.post("/qr-login/pair", json={
            "station_code": code,
            "nickname": sample_user["nickname"],
        })
        assert p.status_code == 200
        assert p.json()["ok"] is True

        st = client.get(f"/qr-login/status/{code}")
        assert st.status_code == 200
        body = st.json()
        assert body["ok"] is True
        assert body["user"]["nickname"] == sample_user["nickname"]
        assert body["user"]["firstname"] == "Alice"
        assert body["user"]["lastname"] == "Wang"

        # Consumed on poll → next poll is empty
        st2 = client.get(f"/qr-login/status/{code}")
        assert st2.json()["ok"] is False

    def test_pair_nickname_case_insensitive(self, client, sample_user):
        code = client.post("/qr-login/session").json()["station_code"]
        p = client.post("/qr-login/pair", json={
            "station_code": code,
            "nickname": " aw1 ",
        })
        assert p.status_code == 200
        st = client.get(f"/qr-login/status/{code}")
        assert st.json()["user"]["nickname"] == sample_user["nickname"]

    def test_pair_unknown_nickname(self, client):
        code = client.post("/qr-login/session").json()["station_code"]
        p = client.post("/qr-login/pair", json={
            "station_code": code,
            "nickname": "NOPE1",
        })
        assert p.status_code == 404

    def test_pair_unknown_station(self, client, sample_user):
        p = client.post("/qr-login/pair", json={
            "station_code": "ZZZZZZ",
            "nickname": sample_user["nickname"],
        })
        assert p.status_code == 404

    def test_status_unknown_station(self, client):
        st = client.get("/qr-login/status/ZZZZZZ")
        assert st.status_code == 404

    def test_station_reusable_fifo(self, client, sample_user):
        u2 = client.post("/users/", json={
            "firstname": "Bob", "lastname": "Brown", "region": "MENA",
        }).json()
        code = client.post("/qr-login/session").json()["station_code"]
        client.post("/qr-login/pair", json={
            "station_code": code, "nickname": sample_user["nickname"],
        })
        client.post("/qr-login/pair", json={
            "station_code": code, "nickname": u2["nickname"],
        })
        first = client.get(f"/qr-login/status/{code}").json()["user"]["nickname"]
        second = client.get(f"/qr-login/status/{code}").json()["user"]["nickname"]
        assert first == sample_user["nickname"]
        assert second == u2["nickname"]
