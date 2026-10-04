from datetime import date, datetime, time

from casebreak.facts.normalize_time import parse_date, parse_datetime, parse_time, words_to_int


def test_words_to_int():
    assert words_to_int("vingt et une") == 21
    assert words_to_int("dix-sept") == 17
    assert words_to_int("deux mille vingt-six") == 2026
    assert words_to_int("cinquante-cinq") == 55


def test_numeric_times():
    assert parse_time("à 11h05") == time(11, 5)
    assert parse_time("à 14 H 20") == time(14, 20)
    assert parse_time("vers 9h") == time(9, 0)
    assert parse_time("21:40") == time(21, 40)


def test_word_times():
    assert parse_time("à onze heures cinq") == time(11, 5)
    assert parse_time("à quatorze heures vingt, nous notifions") == time(14, 20)
    assert parse_time("à vingt et une heures quarante") == time(21, 40)
    assert parse_time("à seize heures") == time(16, 0)
    assert parse_time("à dix-sept heures cinquante-cinq") == time(17, 55)


def test_unreadable_is_none():
    assert parse_time("à ##h#5") is None
    assert parse_time("dans la matinée") is None


def test_dates():
    assert parse_date("le 12/03/2026") == date(2026, 3, 12)
    assert parse_date("le 12 mars 2026") == date(2026, 3, 12)
    assert parse_date("le 1er avril 2026") == date(2026, 4, 1)
    assert parse_date("le douze mars deux mille vingt-six") == date(2026, 3, 12)


def test_datetime():
    assert parse_datetime("le 12/03/2026 à 11h05") == datetime(2026, 3, 12, 11, 5)
    assert parse_datetime("à 11h05", default_date=date(2026, 3, 12)) == datetime(2026, 3, 12, 11, 5)
