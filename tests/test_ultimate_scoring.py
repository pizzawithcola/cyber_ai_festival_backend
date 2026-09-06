"""
ARCH-01 / G5 scoring: per-question 100-point model (50 base + 50 speed) and the
normalization of a finished room into the global game5_score (0-100, best kept).
"""
from app.websocket.game import correct_answer_score, normalize_game5_to_100


class TestCorrectAnswerScore:
    def test_instant_correct_is_100(self):
        assert correct_answer_score(0, 20000, 1) == 100

    def test_at_time_limit_is_base_50(self):
        assert correct_answer_score(20000, 20000, 1) == 50

    def test_after_time_limit_clamps_to_50(self):
        # slower than the limit cannot go below the 50 base for a correct answer
        assert correct_answer_score(30000, 20000, 1) == 50

    def test_half_time_speed_points(self):
        # 10s of 20s used → half of 50 speed points
        assert correct_answer_score(10000, 20000, 1) == 75

    def test_bonus_multiplier_applied(self):
        assert correct_answer_score(0, 20000, 2) == 200
        assert correct_answer_score(0, 20000, 3) == 300
        assert correct_answer_score(20000, 20000, 3) == 150

    def test_wrong_answers_are_handled_by_caller(self):
        # correct_answer_score is only invoked for correct answers
        pass


class TestNormalizeGame5To100:
    def test_typical_room_total(self):
        # e.g. 700 of 1000 max → 70
        assert normalize_game5_to_100(700, 1000) == 70

    def test_full_score_is_100(self):
        assert normalize_game5_to_100(1000, 1000) == 100

    def test_above_max_is_clamped_to_100(self):
        assert normalize_game5_to_100(1200, 1000) == 100

    def test_zero_or_no_max_returns_0(self):
        assert normalize_game5_to_100(0, 1000) == 0
        assert normalize_game5_to_100(500, 0) == 0
        assert normalize_game5_to_100(0, 0) == 0

    def test_small_room_score_stays_positive(self):
        # 5 of 1000 → 0.5
        assert normalize_game5_to_100(5, 1000) == 0.5
