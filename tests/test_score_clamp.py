"""
SEC-05A: server-side per-game score range guard (clamp 0-100).
All games normalize to 0-100 on the leaderboard; the backend must never store
out-of-range values even if a client submits them.
"""
import pytest


class TestScoreClamp:
    def test_update_clamps_above_range(self, client, sample_user):
        uid = sample_user["id"]
        r = client.put(f"/scores/{uid}", json={"game1_score": 150})
        assert r.status_code == 200
        d = r.json()
        assert d["game1_score"] == 100
        assert d["total_score"] == 100

    def test_update_clamps_negative_to_zero(self, client, sample_user):
        uid = sample_user["id"]
        r = client.put(f"/scores/{uid}", json={"game2_score": -50})
        assert r.status_code == 200
        d = r.json()
        assert d["game2_score"] == 0
        assert d["total_score"] == 0

    def test_update_keeps_valid_decimal(self, client, sample_user):
        uid = sample_user["id"]
        r = client.put(f"/scores/{uid}", json={"game3_score": 0.5})
        assert r.status_code == 200
        d = r.json()
        assert d["game3_score"] == pytest.approx(0.5)

    def test_update_recalculates_total_with_clamped_values(self, client, sample_user):
        uid = sample_user["id"]
        client.put(f"/scores/{uid}", json={"game1_score": 80})
        r = client.put(f"/scores/{uid}", json={"game1_score": 120, "game4_score": -3})
        assert r.status_code == 200
        d = r.json()
        assert d["game1_score"] == 100
        assert d["game4_score"] == 0
        assert d["total_score"] == 100
