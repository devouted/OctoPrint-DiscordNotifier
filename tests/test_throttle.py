"""Testy throttle/deduplikacji powiadomień. Czas wstrzykiwany — deterministyczne."""

from octoprint_discord.throttle import EventThrottle


class Clock:
    """Sterowalny zegar do testów."""

    def __init__(self, start=0.0):
        self.t = start

    def __call__(self):
        return self.t

    def advance(self, seconds):
        self.t += seconds


def test_first_event_always_passes():
    th = EventThrottle(min_interval=10, time_func=Clock())
    assert th.should_send("PrintFailed") is True


def test_second_event_blocked_within_window():
    clock = Clock()
    th = EventThrottle(min_interval=10, time_func=clock)
    assert th.should_send("PrintFailed") is True
    clock.advance(3)
    assert th.should_send("PrintFailed") is False  # zbyt wcześnie


def test_event_passes_after_window():
    clock = Clock()
    th = EventThrottle(min_interval=10, time_func=clock)
    assert th.should_send("PrintFailed") is True
    clock.advance(10)
    assert th.should_send("PrintFailed") is True  # minął odstęp


def test_window_boundary_exclusive():
    clock = Clock()
    th = EventThrottle(min_interval=10, time_func=clock)
    assert th.should_send("E") is True
    clock.advance(9.999)
    assert th.should_send("E") is False
    clock.advance(0.001)  # dokładnie 10s
    assert th.should_send("E") is True


def test_different_event_types_independent():
    clock = Clock()
    th = EventThrottle(min_interval=10, time_func=clock)
    assert th.should_send("PrintFailed") is True
    # inny typ nie jest blokowany przez PrintFailed
    assert th.should_send("PrintPaused") is True
    # ten sam typ jeszcze w oknie — zablokowany
    assert th.should_send("PrintFailed") is False


def test_zero_disables_throttle():
    th = EventThrottle(min_interval=0, time_func=Clock())
    for _ in range(5):
        assert th.should_send("PrintFailed") is True


def test_negative_disables_throttle():
    th = EventThrottle(min_interval=-1, time_func=Clock())
    assert th.should_send("x") is True
    assert th.should_send("x") is True


def test_changing_min_interval_takes_effect():
    clock = Clock()
    th = EventThrottle(min_interval=10, time_func=clock)
    assert th.should_send("E") is True
    clock.advance(5)
    assert th.should_send("E") is False
    # użytkownik obniża próg do 2s — teraz 5s wystarcza
    th.min_interval = 2
    assert th.should_send("E") is True


def test_reset_clears_history():
    clock = Clock()
    th = EventThrottle(min_interval=10, time_func=clock)
    assert th.should_send("E") is True
    assert th.should_send("E") is False
    th.reset("E")
    assert th.should_send("E") is True


def test_reset_all():
    th = EventThrottle(min_interval=10, time_func=Clock())
    th.should_send("A")
    th.should_send("B")
    th.reset()
    assert th.should_send("A") is True
    assert th.should_send("B") is True


def test_explicit_now_overrides_time_func():
    th = EventThrottle(min_interval=10)  # domyślny time.monotonic
    assert th.should_send("E", now=100.0) is True
    assert th.should_send("E", now=105.0) is False
    assert th.should_send("E", now=110.0) is True
