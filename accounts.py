# cogs/accounts.py
import discord
from discord.ext import commands
from discord import app_commands

import asyncio
import json
import os
import random
from typing import Dict, Any

from config import LOG_CHANNEL_ID

# pull helper from cogs.invites
from cogs.invites import get_server_bucket


###############################################################################
# Re-usable views
###############################################################################


class InviteTutorialView(discord.ui.View):
    """Button linking to an invite-tutorial channel/message."""

    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(
            discord.ui.Button(
                label="Invite Tutorial",
                style=discord.ButtonStyle.gray,
                url="https://discord.com/channels/1329897880806228030/1346159208071954492",
            )
        )


class CopyCredentialsView(discord.ui.View):
    """Ephemeral buttons that DM the claimed account’s email + password."""

    def __init__(self, account: str):
        super().__init__(timeout=None)
        self.account = account

    @discord.ui.button(label="Copy Credentials", style=discord.ButtonStyle.blurple)
    async def copy_button(self, inter: discord.Interaction, _):
        email, password = self.account.split(":", 1)
        await inter.response.send_message(email, ephemeral=True)
        await inter.followup.send(password, ephemeral=True)


###############################################################################
# Generator buttons
###############################################################################


class GeneratorView(discord.ui.View):
    """“Claim account” & “Check invites” buttons attached to /generator embed."""

    def __init__(self, bot: commands.Bot, guild_id: int):
        super().__init__(timeout=None)
        self.bot = bot
        self.guild_id = guild_id

    # ───────────────────────────────────────────────────────── claim
    @discord.ui.button(
        label="Claim Account",
        style=discord.ButtonStyle.primary,
        emoji="<:gift_icon_white:1347285070540701747>",
        custom_id="claim_account",  # ← makes view persistent
    )
    async def claim_button(self, inter: discord.Interaction, _):
        user_id = str(inter.user.id)
        bucket = get_server_bucket(self.bot, inter.guild.id)

        inviter_data = bucket["users"].get(
            user_id, {"regular": 0, "fake": 0, "bonus": 0}
        )
        valid = inviter_data["regular"] - inviter_data["fake"] + inviter_data["bonus"]

        if valid < 1:
            embed = discord.Embed(
                title="Not enough invites :x:",
                description="You need at least **1** invite to claim an account.",
                color=discord.Color.red(),
            )
            return await inter.response.send_message(
                embed=embed, view=InviteTutorialView(), ephemeral=True
            )

        # pull a stock account
        async with self.bot.accounts_lock:
            stock: Dict[str, Any] = self.bot.stocks.setdefault(
                str(inter.guild.id), []
            )
            if not stock:
                return await inter.response.send_message(
                    "❌ No accounts available!", ephemeral=True
                )

            account = stock.pop(random.randrange(len(stock)))
            await self.bot.save_stocks()

        # deduct 1 bonus invite
        inviter_data["bonus"] -= 1
        await self.bot.save_invites()

        await inter.response.send_message(
            f"✅ Successfully claimed an account! Your account:\n```{account}```",
            view=CopyCredentialsView(account),
            ephemeral=True,
        )

        # log
        log_ch = self.bot.get_channel(LOG_CHANNEL_ID)
        if log_ch:
            await log_ch.send(
                "🎁 **Account Claim**\n"
                f"• User: {inter.user.mention} (`{inter.user.id}`)\n"
                f"• Account: `{account}`\n"
                "• Invites Spent: 1\n"
                f"• Remaining Invites: {valid - 1}"
            )

    # ───────────────────────────────────────────────────────── check invites
    @discord.ui.button(
        label="Check Invites",
        style=discord.ButtonStyle.green,
        emoji="<:BlackUser_IDS:1347285924051947601>",
        custom_id="check_invites",  # ← makes view persistent
    )
    async def check_button(self, inter: discord.Interaction, _):
        bucket = get_server_bucket(self.bot, inter.guild.id)
        data = bucket["users"].get(
            str(inter.user.id), {"regular": 0, "fake": 0, "bonus": 0}
        )
        total = data["regular"] - data["fake"] + data["bonus"]
        await inter.response.send_message(f"You currently have **{total}** invites!", ephemeral=True)


###############################################################################
# Cog
###############################################################################


class AccountGenerator(commands.Cog):
    """Handles /generator, /restock, /setup-generator, and /help."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # dummy view for any orphan embeds across restarts
        self.bot.add_view(GeneratorView(bot, 0))

    # ───────────────────────────────────────────────────────── generator
    @app_commands.command(name="generator", description="Get free accounts")
    async def generator(self, inter: discord.Interaction):
        guild_id = str(inter.guild.id)
        cfg = self.bot.generator_config.get(
            guild_id,
            {
                "title": "Earn Fortnite Accounts",
                "text": "Earn __FREE__ Exclusive Fortnite Accounts by inviting people to the server!\n# 1 Invite = 1 Account",
                "image": None,
            },
        )

        embed = discord.Embed(
            title=cfg["title"],
            description=cfg["text"],
            color=discord.Color.from_rgb(12, 0, 182),
        )
        if cfg.get("image"):
            embed.set_image(url=cfg["image"])

        await inter.response.send_message(
            embed=embed, view=GeneratorView(self.bot, inter.guild.id)
        )

    # ───────────────────────────────────────────────────────── restock
    @app_commands.command(
        name="restock",
        description="(Admin) Add new accounts into stock with email:password per line",
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def restock(self, inter: discord.Interaction):
        guild_id = str(inter.guild.id)

        class RestockModal(discord.ui.Modal, title="Restock Accounts"):
            accounts = discord.ui.TextInput(
                label="Accounts (one per line)",
                style=discord.TextStyle.paragraph,
                placeholder="email1:pass1\nemail2:pass2",
            )

            async def on_submit(modal, modal_inter: discord.Interaction):
                lines = [ln.strip() for ln in modal.accounts.value.splitlines() if ln.strip()]
                stock = self.bot.stocks.setdefault(guild_id, [])
                stock.extend(lines)
                await self.bot.save_stocks()
                await modal_inter.response.send_message(
                    f"✅ Added {len(lines)} accounts to stock.", ephemeral=True
                )

        await inter.response.send_modal(RestockModal())

    # ───────────────────────────────────────────────────────── setup-generator
    @app_commands.command(
        name="setup-generator",
        description="(Admin) Configure & publish the /generator embed",
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def setup_generator(self, inter: discord.Interaction):
        guild_id = str(inter.guild.id)
        cfg = self.bot.generator_config.setdefault(
            guild_id,
            {
                "title": "Earn Fortnite Accounts",
                "text": "Earn __FREE__ Exclusive Fortnite Accounts by inviting people to the server!\n# 1 Invite = 1 Account",
                "image": None,
            },
        )

        def build_embed(data):
            emb = discord.Embed(
                title=data["title"],
                description=data["text"],
                color=discord.Color.from_rgb(12, 0, 182),
            )
            if data.get("image"):
                emb.set_image(url=data["image"])
            return emb

        class SetupView(discord.ui.View):
            def __init__(self, bot: commands.Bot, gid: str):
                super().__init__(timeout=None)
                self.bot = bot
                self.gid = gid

            @discord.ui.button(label="Edit", style=discord.ButtonStyle.primary)
            async def edit(self, i: discord.Interaction, _):
                class EditModal(discord.ui.Modal, title="Edit /generator Embed"):
                    title = discord.ui.TextInput(label="Title", default=cfg["title"])
                    text = discord.ui.TextInput(
                        label="Text",
                        style=discord.TextStyle.paragraph,
                        default=cfg["text"],
                    )
                    image = discord.ui.TextInput(
                        label="Image URL (optional)",
                        default=cfg["image"] or "",
                        required=False,
                    )

                    async def on_submit(modal_self, _mi: discord.Interaction):
                        self.bot.generator_config[self.gid] = {
                            "title": modal_self.title.value,
                            "text": modal_self.text.value,
                            "image": modal_self.image.value.strip() or None,
                        }
                        await self.bot.save_generator_config()
                        await _mi.response.edit_message(
                            embed=build_embed(self.bot.generator_config[self.gid]),
                            view=self,
                        )

                await i.response.send_modal(EditModal())

            @discord.ui.button(label="Confirm", style=discord.ButtonStyle.success)
            async def confirm(self, i: discord.Interaction, _):
                data = self.bot.generator_config[self.gid]
                await i.response.send_message(
                    embed=build_embed(data),
                    view=GeneratorView(self.bot, int(self.gid)),
                )

        await inter.response.send_message(
            embed=build_embed(cfg), view=SetupView(self.bot, guild_id), ephemeral=True
        )

    # ───────────────────────────────────────────────────────── help
    @app_commands.command(name="help", description="Show Gamevault help")
    async def help(self, inter: discord.Interaction):
        embed = discord.Embed(
            title="Gamevault Help", color=discord.Color.from_rgb(12, 0, 182)
        )
        embed.add_field(
            name="Setup Commands",
            value=(
                "- `/setup-generator` to configure & publish the generator embed\n"
                "- `/setup-social` to configure & publish the social embed\n"
                "- `/setup-invites` to configure join-message tracking"
            ),
            inline=False,
        )
        embed.add_field(
            name="Generator",
            value="- `/restock` to add accounts\n- Users click the generator embed to claim",
            inline=False,
        )
        embed.set_footer(text="Support: discord.gg/gamevaultbot")
        await inter.response.send_message(embed=embed, ephemeral=True)


###############################################################################
# Persistence helpers wired into bot
###############################################################################


async def setup(bot: commands.Bot):
    # ensure bot.stocks + persistence helpers
    if not hasattr(bot, "stocks"):
        bot.stocks = {}
    if not hasattr(bot, "save_stocks"):

        async def _save():
            with open("stocks.json", "w") as fp:
                json.dump(bot.stocks, fp, indent=2)

        bot.save_stocks = _save
        if os.path.isfile("stocks.json"):
            try:
                with open("stocks.json") as fp:
                    bot.stocks = json.load(fp)
            except Exception:
                bot.stocks = {}

    if not hasattr(bot, "generator_config"):
        bot.generator_config = {}
    if not hasattr(bot, "save_generator_config"):

        async def _save_gen():
            with open("generator_config.json", "w") as fp:
                json.dump(bot.generator_config, fp, indent=2)

        bot.save_generator_config = _save_gen
        if os.path.isfile("generator_config.json"):
            try:
                with open("generator_config.json") as fp:
                    bot.generator_config = json.load(fp)
            except Exception:
                bot.generator_config = {}

    await bot.add_cog(AccountGenerator(bot))
