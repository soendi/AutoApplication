from __future__ import annotations

from autoapplication.core import embed


def test_frame_urls_reads_the_source() -> None:
    page = (
        '<iframe title="vacancyDetailIFrame" '
        'src="https://recruitingapp-2800.umantis.com/Vacancies/6463/Description/1?lang=ger" '
        'width="100%"></iframe>'
    )
    assert embed.frame_urls(page) == [
        "https://recruitingapp-2800.umantis.com/Vacancies/6463/Description/1?lang=ger"
    ]


def test_relative_frames_are_made_absolute() -> None:
    page = '<iframe src="//host.ch/a"></iframe><iframe src="/rahmen/b"></iframe>'
    assert embed.frame_urls(page, "https://www.ostjob.ch/job/x/1") == [
        "https://host.ch/a",
        "https://www.ostjob.ch/rahmen/b",
    ]


def test_advertising_frames_are_ignored() -> None:
    page = (
        '<iframe src="https://www.youtube.com/embed/abc"></iframe>'
        '<iframe src="about:blank"></iframe>'
        '<iframe src="javascript:void(0)"></iframe>'
    )
    assert embed.frame_urls(page, "https://www.ostjob.ch/job/x/1") == []


def test_same_frame_is_only_read_once() -> None:
    page = '<iframe src="https://host.ch/a"></iframe><iframe src="https://host.ch/a"></iframe>'
    assert embed.frame_urls(page) == ["https://host.ch/a"]
