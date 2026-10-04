"""French spelling of dates and times, the way procès-verbaux write them."""

from __future__ import annotations

import random
from datetime import datetime

_UNITS = ["zéro", "un", "deux", "trois", "quatre", "cinq", "six", "sept", "huit", "neuf", "dix",
          "onze", "douze", "treize", "quatorze", "quinze", "seize"]
_TENS = {20: "vingt", 30: "trente", 40: "quarante", 50: "cinquante"}
MONTHS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre",
          "octobre", "novembre", "décembre"]


def int_fr(n: int, feminine: bool = False) -> str:
    if n < 0 or n > 2099:
        raise ValueError(n)
    if n >= 1000:
        rest = n - 2000 if n >= 2000 else n - 1000
        head = "deux mille" if n >= 2000 else "mille"
        return head if rest == 0 else f"{head} {int_fr(rest)}"
    if n <= 16:
        w = _UNITS[n]
        return "une" if (feminine and n == 1) else w
    if n < 20:
        return "dix-" + _UNITS[n - 10]
    if n < 60:
        t, u = (n // 10) * 10, n % 10
        if u == 0:
            return _TENS[t]
        if u == 1:
            return f"{_TENS[t]} et {'une' if feminine else 'un'}"
        return f"{_TENS[t]}-{_UNITS[u]}"
    raise ValueError(n)


def time_words(dt: datetime) -> str:
    h, m = dt.hour, dt.minute
    hw = "une heure" if h == 1 else f"{int_fr(h, feminine=True)} heures"
    return hw if m == 0 else f"{hw} {int_fr(m, feminine=True)}"


def date_words(dt: datetime) -> str:
    day = "premier" if dt.day == 1 else int_fr(dt.day)
    return f"{day} {MONTHS[dt.month - 1]} {int_fr(dt.year)}"


def time_digits(dt: datetime, rng: random.Random | None = None) -> str:
    style = rng.choice(["h", "H", " H "]) if rng else "h"
    return f"{dt.hour:02d}{style}{dt.minute:02d}".replace("  ", " ")


def date_digits(dt: datetime) -> str:
    return dt.strftime("%d/%m/%Y")


def date_long(dt: datetime) -> str:
    return f"{dt.day if dt.day > 1 else '1er'} {MONTHS[dt.month - 1]} {dt.year}"


def opener(dt: datetime, rng: random.Random) -> str:
    """The first line of a PV body: when the act starts."""
    style = rng.randrange(3)
    if style == 0:
        return f"Le {date_words(dt)}, à {time_words(dt)},"
    if style == 1:
        return f"L'an {int_fr(dt.year)}, le {date_long(dt)} à {time_digits(dt, rng)},"
    return f"Le {date_digits(dt)} à {time_digits(dt, rng)},"


def at_time(dt: datetime, rng: random.Random, same_day: bool = True) -> str:
    """'à 14h20' / 'à quatorze heures vingt' / 'le 13/03/2026 à 16h00'."""
    t = time_words(dt) if rng.random() < 0.35 else time_digits(dt, rng)
    return f"à {t}" if same_day else f"le {date_digits(dt)} à {t}"


def duration_fr(minutes: int) -> str:
    h, m = divmod(int(minutes), 60)
    if h and m:
        return f"{h} h {m:02d}"
    if h:
        return f"{h} h"
    return f"{m} min"
