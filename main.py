"""Ежедневный генератор названий Discord-сервера 'ГП'.

Запуск без токена: python main.py --preview
Запуск с переименованием: python main.py
"""

import argparse
from datetime import datetime, timedelta
import os
import random
import sys
from time import sleep
from zoneinfo import ZoneInfo

import pymorphy3
import requests


# Каждый элемент: (существительное в именительном падеже, грамматический род).
# Для существительных во множественном числе вместо рода указывайте 'plur'.
P_NOUNS = [
    ("петрушка", "femn"),
    ("пельмень", "masc"),
    ("пельмени", "plur"),
    ("пирожок", "masc"),
    ("пирожки", "plur"),
    ("пончик", "masc"),
    ("паразит", "masc"),
    ("придурок", "masc"),
    ("пельмешка", "femn"),
    ("пингвин", "masc"),
    ("помойка", "femn"),
    ("плесень", "femn"),
    ("пакет", "masc"),
    ("проблема", "femn"),
    ("пузырь", "masc"),
    ("пожар", "masc"),
    ("парадокс", "masc"),
    ("пень", "masc"),
    ("пугало", "neut"),
    ("поросёнок", "masc"),
    ("пилот", "masc"),
    ("планктон", "masc"),
    ("папоротник", "masc"),
    ("пингвины", "plur"),
    ("праздник", "masc"),
    ("проклятие", "neut"),
    ("прохвост", "masc"),
    ("пузо", "neut"),
    ("пиздец", "masc"),
    ("пирог", "masc"),
]

G_ADJECTIVES = [
    "гомосексуальный", "говённый", "грустный", "гениальный", "главный",
    "голодный", "громадный", "гнилой", "глупый", "гнусный", "грязный",
    "грозный", "гламурный", "героический", "глубинный", "грешный",
    "громкий", "горячий", "глухой", "галактический", "гадкий",
    "гневный", "грандиозный", "гиперактивный", "глобальный", "гибкий",
]

G_NOUNS = [
    ("говно", "neut"),
    ("гусь", "masc"),
    ("гуси", "plur"),
    ("гоблин", "masc"),
    ("герой", "masc"),
    ("гриб", "masc"),
    ("груша", "femn"),
    ("гадость", "femn"),
    ("галактика", "femn"),
    ("гном", "masc"),
    ("голубь", "masc"),
    ("гиппопотам", "masc"),
    ("гидра", "femn"),
    ("горилла", "femn"),
    ("грызун", "masc"),
    ("генерал", "masc"),
    ("гуманоид", "masc"),
    ("глаз", "masc"),
    ("голова", "femn"),
    ("грабли", "plur"),
    ("голод", "masc"),
    ("грохот", "masc"),
    ("гнев", "masc"),
    ("граф", "masc"),
]

P_ADJECTIVES = [
    "помойный", "потешный", "противный", "позорный", "проклятый",
    "прекрасный", "пьяный", "пушистый", "праздничный", "подозрительный",
    "педантичный", "пакостный", "пельменный", "преступный",
    "потусторонний", "политический", "пластиковый", "похотливый",
    "призрачный", "пламенный", "первобытный", "потерянный",
    "печальный", "пафосный", "пугающий", "пассивный",
]

BANNED_SUBSTRINGS = ("гей",)  # Запрет распространяется даже на часть слова.
TIMEZONE = os.getenv("TIMEZONE", "Europe/Moscow")


def adjective_in_noun_form(morph, adjective, noun_gender):
    """Согласует прилагательное с существительным в именительном падеже."""
    needed = {"nomn", "plur"} if noun_gender == "plur" else {"nomn", "sing", noun_gender}
    candidates = [analysis for analysis in morph.parse(adjective) if analysis.tag.POS == "ADJF"]
    if not candidates:
        raise ValueError(f"Не удалось разобрать прилагательное: {adjective!r}")
    result = candidates[0].inflect(needed)
    if result is None:
        raise ValueError(f"Не удалось согласовать: {adjective!r}, {noun_gender!r}")
    return result.word


def generate_name(target_date, reroll_seed=""):
    """Для обычного запуска название фиксировано на дату; для ручного — новый seed."""
    morph = pymorphy3.MorphAnalyzer()
    rng = random.Random(f"gp|{target_date.isoformat()}|{reroll_seed}")
    pairs = [
        ("adjective_first", adjective, noun, gender)
        for adjective in G_ADJECTIVES
        for noun, gender in P_NOUNS
    ] + [
        ("noun_first", adjective, noun, gender)
        for noun, gender in G_NOUNS
        for adjective in P_ADJECTIVES
    ]
    rng.shuffle(pairs)

    for kind, adjective, noun, gender in pairs:
        try:
            agreed = adjective_in_noun_form(morph, adjective, gender)
        except ValueError:
            # Слово может отсутствовать в словаре морфологии — пропускаем пару.
            continue
        if kind == "adjective_first":
            parts = (agreed, noun)
        else:
            parts = (noun, agreed)
        name = f"{parts[0].capitalize()} {parts[1]}"
        if len(name) > 100 or any(bad in name.casefold() for bad in BANNED_SUBSTRINGS):
            continue
        if not name.startswith("Г") or not parts[1].startswith("п"):
            continue
        return name

    raise RuntimeError("Не удалось составить допустимое название. Проверьте словари.")


def rename_server(token, guild_id, new_name):
    url = f"https://discord.com/api/v10/guilds/{guild_id}"
    headers = {
        "Authorization": f"Bot {token}",
        "User-Agent": "GPNameRotator/1.0 (daily guild rename)",
        "X-Audit-Log-Reason": "Daily GP name rotation",
    }
    for attempt in range(2):
        try:
            response = requests.patch(url, headers=headers, json={"name": new_name}, timeout=30)
        except requests.RequestException as exc:
            raise RuntimeError(f"Сетевая ошибка Discord API: {exc}") from exc

        if response.status_code == 429 and attempt == 0:
            try:
                delay = float(response.json().get("retry_after", 5))
            except (ValueError, AttributeError, TypeError):
                delay = 5
            if 0 <= delay <= 60:
                sleep(delay + 1)
                continue

        if response.status_code == 200:
            return
        raise RuntimeError(
            f"Discord отклонил изменение названия (HTTP {response.status_code}): "
            f"{response.text[:400]}"
        )

    raise RuntimeError("Не удалось переименовать сервер из-за ограничения частоты запросов Discord.")


def main():
    parser = argparse.ArgumentParser(description="Случайное название Discord-сервера 'ГП'.")
    parser.add_argument("--preview", action="store_true", help="Показать 10 названий на следующие дни")
    args = parser.parse_args()

    try:
        today = datetime.now(ZoneInfo(TIMEZONE)).date()
        if args.preview:
            for i in range(10):
                day = today + timedelta(days=i)
                print(f"{day.isoformat()}: {generate_name(day)}")
            return

        token = os.getenv("DISCORD_BOT_TOKEN")
        guild_id = os.getenv("DISCORD_GUILD_ID")
        if not token or not guild_id:
            raise RuntimeError("Задайте секреты DISCORD_BOT_TOKEN и DISCORD_GUILD_ID.")
        if not guild_id.isdigit():
            raise RuntimeError("DISCORD_GUILD_ID должен быть числовым ID сервера.")
        reroll_seed = os.getenv("REROLL_SEED", "")
        new_name = generate_name(today, reroll_seed)
        rename_server(token, guild_id, new_name)
        print(f"Сервер {guild_id} успешно переименован: {new_name}")
    except Exception as exc:
        print(f"ОШИБКА: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
