import logging
import os

import discord
from discord.ext import commands
from discord import app_commands

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("application_bot")

GUILD_ID = None
APPLICATION_CHANNEL_ID = 0
REQUESTS_REVIEW_CHANNEL_ID = 0
APPROVED_ROLE_ID = 0
LOG_CHANNEL_ID = 0

TOKEN = os.getenv("803aac93afdc774ecdd83e45b689bdcfd7f68a80fb26f1679e073fa81d1fb6dc", "")

intents = discord.Intents.default()
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)


class ApplicationModal(discord.ui.Modal, title="Заявка"):
    def __init__(self, review_channel_id: int, log_channel_id: int):
        super().__init__()
        self.review_channel_id = review_channel_id
        self.log_channel_id = log_channel_id

        self.ign = discord.ui.TextInput(label="Ник в игре", placeholder="Введите ваш ник", max_length=100)
        self.age = discord.ui.TextInput(label="Возраст", placeholder="Введите ваш возраст", max_length=10)
        self.about = discord.ui.TextInput(label="О себе", style=discord.TextStyle.paragraph, placeholder="Кратко о себе", max_length=500)

        self.add_item(self.ign)
        self.add_item(self.age)
        self.add_item(self.about)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        user = interaction.user
        review_channel = interaction.client.get_channel(self.review_channel_id)
        log_channel = interaction.client.get_channel(self.log_channel_id) if self.log_channel_id else None

        embed = discord.Embed(title="Новая заявка", color=discord.Color.blurple())
        embed.add_field(name="Пользователь", value=f"{user.mention} ({user.id})", inline=False)
        embed.add_field(name="Ник в игре", value=self.ign.value, inline=False)
        embed.add_field(name="Возраст", value=self.age.value, inline=False)
        embed.add_field(name="О себе", value=self.about.value, inline=False)

        view = ApplicationModerationView(target_user_id=user.id)

        if review_channel is not None:
            await review_channel.send(embed=embed, view=view)
        else:
            logger.warning("Review channel not found or not set")

        await interaction.response.send_message("Ваша заявка отправлена на рассмотрение.", ephemeral=True)

        logger.info("Application submitted by %s (%s)", user, user.id)
        if log_channel is not None:
            await log_channel.send(f"Заявка отправлена: {user.mention} ({user.id})")


class ApplicationButtonView(discord.ui.View):
    def __init__(self, review_channel_id: int, log_channel_id: int):
        super().__init__(timeout=None)
        self.review_channel_id = review_channel_id
        self.log_channel_id = log_channel_id

    @discord.ui.button(label="Оставить заявку", style=discord.ButtonStyle.primary, custom_id="application_button")
    async def application_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = ApplicationModal(review_channel_id=self.review_channel_id, log_channel_id=self.log_channel_id)
        await interaction.response.send_modal(modal)


class ApplicationModerationView(discord.ui.View):
    def __init__(self, target_user_id: int):
        super().__init__(timeout=None)
        self.target_user_id = target_user_id

    @discord.ui.button(label="Принять", style=discord.ButtonStyle.success, custom_id="application_accept")
    async def accept_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message("Ошибка: сервер не найден.", ephemeral=True)
            return

        member = guild.get_member(self.target_user_id)
        if member is None:
            await interaction.response.send_message("Пользователь не найден на сервере.", ephemeral=True)
            return

        role = guild.get_role(APPROVED_ROLE_ID) if APPROVED_ROLE_ID else None
        if role is None:
            await interaction.response.send_message("Роль для выдачи не настроена.", ephemeral=True)
            return

        try:
            await member.add_roles(role, reason=f"Заявка одобрена модератором {interaction.user}")
            await interaction.response.send_message(f"Заявка одобрена, роль {role.mention} выдана {member.mention}.")
            logger.info("Application accepted via button: %s -> %s", interaction.user, member)
        except discord.Forbidden:
            await interaction.response.send_message("Нет прав для выдачи роли.", ephemeral=True)
        except discord.HTTPException:
            await interaction.response.send_message("Ошибка при выдаче роли.", ephemeral=True)

    @discord.ui.button(label="Отклонить", style=discord.ButtonStyle.danger, custom_id="application_reject")
    async def reject_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("Заявка отклонена.")
        logger.info("Application rejected via button by %s for user_id=%s", interaction.user, self.target_user_id)


@bot.event
async def on_ready():
    logger.info("Logged in as %s (%s)", bot.user, bot.user.id)
    try:
        synced = await bot.tree.sync(guild=discord.Object(id=GUILD_ID)) if GUILD_ID else await bot.tree.sync()
        logger.info("Synced %s app commands", len(synced))
    except Exception as e:
        logger.exception("Failed to sync app commands: %s", e)


@bot.tree.command(name="заявка", description="Отправить сообщение с кнопкой для заявок")
@app_commands.checks.has_permissions(manage_guild=True)
async def send_application_message(interaction: discord.Interaction):
    channel = interaction.guild.get_channel(APPLICATION_CHANNEL_ID) if APPLICATION_CHANNEL_ID else interaction.channel
    if channel is None:
        await interaction.response.send_message("Канал для заявок не найден.", ephemeral=True)
        return

    view = ApplicationButtonView(review_channel_id=REQUESTS_REVIEW_CHANNEL_ID, log_channel_id=LOG_CHANNEL_ID)
    await channel.send("Нажмите кнопку ниже, чтобы подать заявку.", view=view)
    await interaction.response.send_message("Сообщение с кнопкой отправлено.", ephemeral=True)


@send_application_message.error
async def send_application_message_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    logger.exception("Error in /заявка: %s", error)
    if isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message("У вас нет прав для этой команды.", ephemeral=True)
    else:
        await interaction.response.send_message("Произошла ошибка при выполнении команды.", ephemeral=True)


@bot.command(name="заявка")
@commands.has_permissions(manage_guild=True)
async def text_send_application_message(ctx: commands.Context):
    channel = ctx.channel

    view = ApplicationButtonView(review_channel_id=REQUESTS_REVIEW_CHANNEL_ID, log_channel_id=LOG_CHANNEL_ID)
    await channel.send("Нажмите кнопку ниже, чтобы подать заявку.", view=view)
    logger.info("Text command !заявка used by %s in #%s", ctx.author, channel)


@text_send_application_message.error
async def text_send_application_message_error(ctx: commands.Context, error: commands.CommandError):
    logger.exception("Error in !заявка: %s", error)
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("У вас нет прав для этой команды.")
    else:
        await ctx.send("Произошла ошибка при выполнении команды.")


@bot.command(name="принять")
@commands.has_permissions(manage_roles=True)
async def accept_command(ctx: commands.Context, member: discord.Member):
    role = ctx.guild.get_role(APPROVED_ROLE_ID) if APPROVED_ROLE_ID else None
    if role is None:
        await ctx.send("Роль для выдачи не настроена.")
        return

    try:
        await member.add_roles(role, reason=f"Заявка одобрена модератором {ctx.author}")
        await ctx.send(f"Заявка одобрена, роль {role.mention} выдана {member.mention}.")
        logger.info("Application accepted via command: %s -> %s", ctx.author, member)
    except discord.Forbidden:
        await ctx.send("Нет прав для выдачи роли.")
    except discord.HTTPException:
        await ctx.send("Ошибка при выдаче роли.")


@bot.command(name="отклонить")
@commands.has_permissions(manage_roles=True)
async def reject_command(ctx: commands.Context, member: discord.Member):
    await ctx.send(f"Заявка {member.mention} отклонена.")
    logger.info("Application rejected via command by %s for %s", ctx.author, member)


@accept_command.error
async def accept_command_error(ctx: commands.Context, error: commands.CommandError):
    logger.exception("Error in !принять: %s", error)
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("У вас нет прав для этой команды.")
    elif isinstance(error, commands.BadArgument):
        await ctx.send("Укажите пользователя: !принять @пользователь")
    else:
        await ctx.send("Произошла ошибка при выполнении команды.")


@reject_command.error
async def reject_command_error(ctx: commands.Context, error: commands.CommandError):
    logger.exception("Error in !отклонить: %s", error)
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("У вас нет прав для этой команды.")
    elif isinstance(error, commands.BadArgument):
        await ctx.send("Укажите пользователя: !отклонить @пользователь")
    else:
        await ctx.send("Произошла ошибка при выполнении команды.")


def main() -> None:
    if not TOKEN:
        logger.error("DISCORD_BOT_TOKEN is not set. Set environment variable DISCORD_BOT_TOKEN.")
        return
    if APPLICATION_CHANNEL_ID == 0 or REQUESTS_REVIEW_CHANNEL_ID == 0 or APPROVED_ROLE_ID == 0:
        logger.warning("One or more IDs (APPLICATION_CHANNEL_ID, REQUESTS_REVIEW_CHANNEL_ID, APPROVED_ROLE_ID) are not set.")
    bot.run(TOKEN)


if __name__ == "__main__":
    main()
