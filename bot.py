"""ГП v3: постоянный Discord-бот с /gp, SQLite и расписанием по Москве.

Запуск: DISCORD_BOT_TOKEN=... DISCORD_GUILD_ID=... python bot.py
"""
import asyncio
from datetime import date, timedelta
import logging
import os
from typing import Optional

import discord
from discord import app_commands
from discord.ext import tasks

import generator
import storage

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("gp")

TOKEN = os.environ.get("DISCORD_BOT_TOKEN", "")
try:
    GUILD_ID = int(os.environ.get("DISCORD_GUILD_ID", "0"))
except ValueError:
    GUILD_ID = 0

rename_lock = asyncio.Lock()
last_schedule_error = {"date": None, "at": None}


def format_time(config):
    return f'{config["hour"]:02d}:{config["minute"]:02d} МСК'


def next_rename_text(config):
    return storage.next_slot(config).strftime("%d.%m.%Y, %H:%M МСК")


def decree(name, config):
    return (
        "📜 **ВЫСОЧАЙШИЙ УКАЗ О ПЕРЕИМЕНОВАНИИ**\n\n"
        "📯 **СЛУШАЙТЕ И ТРЕПЕЩИТЕ!**\n\n"
        "Прежнее имя предано забвению. По воле великого рандома "
        "наш сервер отныне и впредь именуется:\n\n"
        "**ТЕПЕРЬ НЫНЕШНЕЕ НАЗВАНИЕ:**\n"
        f"# 👑 «{name}»\n\n"
        "Да будет сие имя вписано в летописи ГП!\n\n"
        f"*Следующая церемония: {next_rename_text(config)}.*"
    )


class GPClient(discord.Client):
    async def setup_hook(self):
        # Регистрируем команды только на своём сервере: они появляются быстро.
        self.tree.add_command(gp, guild=discord.Object(id=GUILD_ID))
        synced = await self.tree.sync(guild=discord.Object(id=GUILD_ID))
        log.info("Зарегистрировано %s групп команд в Discord", len(synced))
        if not check_schedule.is_running():
            check_schedule.start()


intents = discord.Intents.none()
intents.guilds = True
bot = GPClient(intents=intents)
bot.tree = app_commands.CommandTree(bot)
gp = app_commands.Group(name="gp", description="Управление великим рандомом названий ГП")


async def require_manager(interaction):
    if (interaction.guild_id != GUILD_ID or not isinstance(interaction.user, discord.Member)
            or not interaction.user.guild_permissions.manage_guild):
        await interaction.response.send_message(
            "⛔ Изменять настройки может только участник с правом «Управлять сервером».",
            ephemeral=True)
        return False
    return True


async def send_announcement(channel_id, name, config):
    if not config["announce_enabled"] or not channel_id:
        return False
    try:
        channel = bot.get_channel(channel_id) or await bot.fetch_channel(channel_id)
        if not hasattr(channel, "send"):
            raise RuntimeError("Указанный канал не поддерживает сообщения")
        await channel.send(decree(name, config), allowed_mentions=discord.AllowedMentions.none())
        return True
    except (discord.HTTPException, RuntimeError) as exc:
        log.error("Название изменилось, но объявление не отправлено: %s", exc)
        return False


async def rename(mode):
    """Возвращает (новое_имя, объявление_отправлено).

    Сначала записываем успех переименования, лишь затем отправляем объявление.
    Ошибка объявления не вызывает повторного изменения названия.
    """
    async with rename_lock:
        config = storage.get(GUILD_ID)
        now = storage.now_msk()
        if mode == "scheduled":
            if not config["enabled"] or not storage.scheduled_today(config, now):
                return None, False
            if config["last_scheduled_date"] == now.date().isoformat():
                return None, False
        guild = bot.get_guild(GUILD_ID)
        if guild is None:
            raise RuntimeError("Сервер не найден в кеше бота; проверьте DISCORD_GUILD_ID и приглашение")
        name = generator.generate(config["explicit_percent"], previous=config["last_name"])
        await guild.edit(name=name, reason=f"GP {mode} rename")
        # Если вручную переименовали в день уже наступившего слота, второй раз
        # по расписанию в этот же день не переименовываем.
        slot_date = now.date().isoformat() if storage.scheduled_today(config, now) else None
        history_id = storage.record(GUILD_ID, name, mode, scheduled_date=slot_date)
        refreshed = storage.get(GUILD_ID)
        announced = await send_announcement(refreshed["announce_channel_id"], name, refreshed)
        if announced:
            storage.announcement_ok(history_id)
        log.info("Название изменено: %s; объявление=%s", name, announced)
        return name, announced


@tasks.loop(seconds=30, reconnect=True)
async def check_schedule():
    config = storage.get(GUILD_ID)
    now = storage.now_msk()
    if (not config["enabled"] or not storage.scheduled_today(config, now)
            or config["last_scheduled_date"] == now.date().isoformat()):
        return
    # После ошибки пробуем повторить не чаще чем через пять минут.
    stamp = now.date().isoformat()
    if (last_schedule_error["date"] == stamp and last_schedule_error["at"]
            and (now - last_schedule_error["at"]).total_seconds() < 300):
        return
    try:
        await rename("scheduled")
    except (discord.HTTPException, RuntimeError, ValueError) as exc:
        log.error("Плановая смена названия не удалась: %s", exc)
        last_schedule_error["date"] = stamp
        last_schedule_error["at"] = now


@check_schedule.before_loop
async def before_schedule():
    await bot.wait_until_ready()


@gp.command(name="help", description="Список команд управления ГП")
async def gp_help(interaction: discord.Interaction):
    await interaction.response.send_message(
        "**📖 Команды ГП**\n"
        "`/gp settings` — текущие настройки и следующая дата\n"
        "`/gp preview` — примеры названий\n"
        "`/gp stats` — статистика словарей\n"
        "**Для управляющих сервером:**\n"
        "`/gp rename` — сменить имя прямо сейчас\n"
        "`/gp schedule` — интервал, часы, минуты, дата начала\n"
        "`/gp channel` — канал для торжественных объявлений\n"
        "`/gp profanity` — вероятность настоящего мата\n"
        "`/gp announce` — включить/выключить объявления\n"
        "`/gp enabled` — включить/поставить на паузу расписание",
        ephemeral=True)


@gp.command(name="settings", description="Показать параметры ротации имени")
async def gp_settings(interaction: discord.Interaction):
    s = storage.get(GUILD_ID)
    channel = f'<#{s["announce_channel_id"]}>' if s["announce_channel_id"] else "не выбран"
    await interaction.response.send_message(
        "**⚙️ Настройки ГП**\n"
        f"Расписание: **раз в {s['interval_days']} дн. в {format_time(s)}**\n"
        f"Начало цикла: **{s['anchor_date']}**\n"
        f"Следующая смена: **{next_rename_text(s)}**\n"
        f"Автоматическая смена: **{'включена' if s['enabled'] else 'приостановлена'}**\n"
        f"Настоящий мат: **{s['explicit_percent']}%**\n"
        f"Объявления: **{'включены' if s['announce_enabled'] else 'выключены'}**\n"
        f"Канал: {channel}\n"
        f"Последнее название: **{s['last_name'] or 'ещё не менялось'}**",
        allowed_mentions=discord.AllowedMentions.none(), ephemeral=True)


@gp.command(name="stats", description="Сколько названий доступно и сколько из них матерных")
async def gp_stats(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True, thinking=True)
    counts = generator.stats()
    total = sum(counts.values())
    percent = counts["explicit"] / total * 100
    await interaction.followup.send(
        "**📊 Словарь ГП**\n"
        f"Всего уникальных допустимых названий: **{total}**\n"
        f"Обычных: **{counts['clean']}**\n"
        f"Грубых без строгого мата: **{counts['vulgar']}**\n"
        f"Матерных: **{counts['explicit']}** ({percent:.1f}% словаря)\n"
        f"Текущая заданная вероятность выпадения мата: **{storage.get(GUILD_ID)['explicit_percent']}%**\n"
        f"Переименований этим ботом: **{storage.rename_count(GUILD_ID)}**")


@gp.command(name="preview", description="Показать случайные названия, не меняя сервер")
@app_commands.describe(count="Число вариантов от 1 до 10")
async def gp_preview(interaction: discord.Interaction, count: app_commands.Range[int, 1, 10] = 5):
    await interaction.response.defer(ephemeral=True, thinking=True)
    percent = storage.get(GUILD_ID)["explicit_percent"]
    names = [generator.generate(percent) for _ in range(count)]
    await interaction.followup.send(
        "🎲 **Вот что может выпасть:**\n" +
        "\n".join(f"{i}. **{name}**" for i, name in enumerate(names, 1)))


@gp.command(name="rename", description="Немедленно провести церемонию переименования")
async def gp_rename(interaction: discord.Interaction):
    if not await require_manager(interaction):
        return
    await interaction.response.defer(ephemeral=True, thinking=True)
    try:
        name, announced = await rename("manual")
        note = "Указ опубликован." if announced else "Объявление отключено или не отправлено."
        await interaction.followup.send(f"✅ Новое имя: **{name}**. {note}")
    except (discord.HTTPException, RuntimeError, ValueError) as exc:
        await interaction.followup.send(f"❌ Не удалось сменить имя: `{str(exc)[:450]}`")


@gp.command(name="schedule", description="Задать интервал, время по Москве и необязательную дату начала")
@app_commands.describe(days="Раз в сколько дней (1–365)", hour="Час МСК (0–23)",
                       minute="Минуты (0–59)", start_date="Необязательно: YYYY-MM-DD")
async def gp_schedule(interaction: discord.Interaction,
                      days: app_commands.Range[int, 1, 365],
                      hour: app_commands.Range[int, 0, 23],
                      minute: app_commands.Range[int, 0, 59],
                      start_date: Optional[str] = None):
    if not await require_manager(interaction):
        return
    today = storage.now_msk()
    if start_date:
        try:
            first = date.fromisoformat(start_date)
        except ValueError:
            await interaction.response.send_message("❌ Дата должна быть в формате YYYY-MM-DD.", ephemeral=True)
            return
    else:
        first = today.date()
        if (today.hour, today.minute) >= (hour, minute):
            first += timedelta(days=1)
    storage.change(GUILD_ID, interval_days=days, hour=hour, minute=minute,
                   anchor_date=first.isoformat())
    s = storage.get(GUILD_ID)
    await interaction.response.send_message(
        f"🗓️ Принято: **раз в {days} дн. в {format_time(s)}**. "
        f"Первая дата цикла: **{first:%d.%m.%Y}**. "
        f"Следующая церемония: **{next_rename_text(s)}**.", ephemeral=True)


@gp.command(name="channel", description="Выбрать текстовый канал для указов ГП")
async def gp_channel(interaction: discord.Interaction, channel: discord.TextChannel):
    if not await require_manager(interaction):
        return
    bot_member = interaction.guild.me if interaction.guild else None
    if bot_member:
        perms = channel.permissions_for(bot_member)
        if not perms.view_channel or not perms.send_messages:
            await interaction.response.send_message(
                "❌ У бота нет прав Просматривать канал и Отправлять сообщения здесь.", ephemeral=True)
            return
    storage.change(GUILD_ID, announce_channel_id=channel.id)
    await interaction.response.send_message(f"📜 Объявления пойдут в {channel.mention}.", ephemeral=True)


@gp.command(name="profanity", description="Настроить вероятность матерного названия (0–100%)")
@app_commands.describe(percent="Процент случайных названий с настоящим матом")
async def gp_profanity(interaction: discord.Interaction,
                       percent: app_commands.Range[int, 0, 100]):
    if not await require_manager(interaction):
        return
    storage.change(GUILD_ID, explicit_percent=percent)
    await interaction.response.send_message(
        f"🤬 Теперь шанс **матерного названия — {percent}%**. "
        "Грубые слова без строгого мата могут встречаться и в остальных названиях.", ephemeral=True)


@gp.command(name="announce", description="Включить или отключить торжественные указы")
async def gp_announce(interaction: discord.Interaction, enabled: bool):
    if not await require_manager(interaction):
        return
    storage.change(GUILD_ID, announce_enabled=int(enabled))
    await interaction.response.send_message(
        f"📜 Объявления **{'включены' if enabled else 'выключены'}**.", ephemeral=True)


@gp.command(name="enabled", description="Включить или приостановить автоматическое расписание")
async def gp_enabled(interaction: discord.Interaction, enabled: bool):
    if not await require_manager(interaction):
        return
    storage.change(GUILD_ID, enabled=int(enabled))
    await interaction.response.send_message(
        f"⏳ Автоматическая смена имени **{'включена' if enabled else 'приостановлена'}**. "
        "Ручная команда /gp rename продолжит работать.", ephemeral=True)


@bot.event
async def on_ready():
    log.info("Бот запущен: %s; сервер=%s", bot.user, GUILD_ID)


def main():
    if not TOKEN or not GUILD_ID:
        raise SystemExit("Укажите DISCORD_BOT_TOKEN и DISCORD_GUILD_ID в переменных окружения")
    storage.init(GUILD_ID)
    bot.run(TOKEN, log_handler=None)


if __name__ == "__main__":
    main()
