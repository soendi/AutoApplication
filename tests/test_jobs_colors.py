from autoapplication.ui.jobs import hit_color


def test_highest_hit_is_green_and_lowest_red() -> None:
    low = hit_color(0, 0, 100)
    high = hit_color(100, 0, 100)
    assert low.hueF() < 0.02
    assert high.hueF() > 0.36


def test_middle_hit_is_between_red_and_green() -> None:
    middle = hit_color(50, 0, 100)
    assert 0.1 < middle.hueF() < 0.3


def test_single_value_uses_absolute_scale() -> None:
    assert hit_color(100, 100, 100).hueF() > 0.36
    assert hit_color(0, 0, 0).hueF() < 0.02
