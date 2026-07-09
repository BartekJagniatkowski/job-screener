from cli import FilterBar, MainScreen


class _FakeFilterBar:
    def __init__(self):
        self.selected = []

    def select_filter(self, status):
        self.selected.append(status)


class _FakeScreen:
    def __init__(self, filter_bar):
        self._filter_bar = filter_bar

    def query_one(self, _widget_type):
        return self._filter_bar


def test_every_quick_select_key_has_a_screen_level_action():
    for status in FilterBar.QUICK_SELECT_KEYS.values():
        assert hasattr(MainScreen, f"action_quick_select_{status}")


def test_quick_select_action_selects_filter_without_filter_bar_focus():
    filter_bar = _FakeFilterBar()
    screen = _FakeScreen(filter_bar)
    MainScreen.action_quick_select_rejected(screen)
    assert filter_bar.selected == ["rejected"]
