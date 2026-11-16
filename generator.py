"""Согласование слов, проверка словарей и генерация с точным шансом мата."""
import random
from functools import lru_cache
from collections import Counter

import pymorphy3

from words import G_ADJECTIVES, P_NOUNS, G_NOUNS, P_ADJECTIVES

BANNED_SUBSTRINGS = ("гей",)  # По просьбе владельцев ГП.


@lru_cache(maxsize=1)
def analyzer():
    return pymorphy3.MorphAnalyzer()


@lru_cache(maxsize=2048)
def agree(adjective, gender):
    gram = {"nomn", "plur"} if gender == "plur" else {"nomn", "sing", gender}
    analyses = [form for form in analyzer().parse(adjective) if form.tag.POS == "ADJF"]
    for candidate in analyses:
        result = candidate.inflect(gram)
        if result is not None:
            return result.word
    return None


def valid_name(value):
    return (len(value) <= 100 and value.startswith("Г")
            and len(value.split()) == 2 and value.split()[1].startswith("п")
            and not any(forbidden in value.casefold() for forbidden in BANNED_SUBSTRINGS))


@lru_cache(maxsize=1)
def all_names():
    """Готовые грамматически согласованные строки, классифицированные по грубости."""
    entries = {}
    for adj_level, adjectives in G_ADJECTIVES.items():
        for noun_level, nouns in P_NOUNS.items():
            for adjective in adjectives:
                for noun, gender in nouns:
                    changed = agree(adjective, gender)
                    if changed:
                        title = f"{changed.capitalize()} {noun}"
                        if valid_name(title):
                            entries[title] = max(adj_level, noun_level, entries.get(title, 0))
    for noun_level, nouns in G_NOUNS.items():
        for adj_level, adjectives in P_ADJECTIVES.items():
            for noun, gender in nouns:
                for adjective in adjectives:
                    changed = agree(adjective, gender)
                    if changed:
                        title = f"{noun.capitalize()} {changed}"
                        if valid_name(title):
                            entries[title] = max(noun_level, adj_level, entries.get(title, 0))
    grouped = {level: tuple(name for name, severity in entries.items() if severity == level)
               for level in (0, 1, 2)}
    if not grouped[2] or not (grouped[0] or grouped[1]):
        raise RuntimeError("Не получилось собрать оба типа названий — проверьте words.py")
    return grouped


def stats():
    grouped = all_names()
    return {name: len(grouped[index]) for name, index in
            (("clean", 0), ("vulgar", 1), ("explicit", 2))}


def generate(explicit_percent=45, previous=None, rng=None):
    """Шанс в процентах относится к МАТЕРНОМУ названию, не к отдельному слову.

    Грубые выражения без строгого мата остаются в нематерной категории.
    """
    if not 0 <= explicit_percent <= 100:
        raise ValueError("Процент мата должен быть от 0 до 100")
    rng = rng or random.SystemRandom()
    grouped = all_names()
    has_m = rng.random() * 100 < explicit_percent
    if has_m:
        options = grouped[2]
    else:
        options = grouped[0] + grouped[1]
    if previous is not None and len(options) > 1:
        # Сразу после повторного выбора не возвращаем то же имя.
        chosen = rng.choice(options)
        for _ in range(8):
            if chosen != previous:
                break
            chosen = rng.choice(options)
        if chosen == previous:
            chosen = next(item for item in options if item != previous)
        return chosen
    return rng.choice(options)
