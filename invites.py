# cogs/invites.py
import discord
from discord.ext import commands, tasks
from discord import app_commands

import asyncio
import datetime
import json
import os
import random
from typing import Dict, Any

from config import (
    MAIN_GUILD_ID,
    MAX_INVITES,
    TARGET_INVITES,
    CLEANUP_INTERVAL,
)

###############################################################################
# Helpers
###############################################################################


def get_server_bucket(bot: commands.Bot, guild_id: int) -> Dict[str, Any]:
    """Return the per-server invite data bucket, creating it if needed."""
    gid = str(guild_id)
    return bot.invites.setdefault("servers", {}).setdefault(
        gid,
        {
            "users": {},       # user_id -> {regular, fake, bonus}
            "members": {},     # member_id -> {...}
            "invite_cache": {},  # invite_id -> uses
            "settings": {
                "channel_id": 0,
                "join_template": (
                    "**<joinerName>** just joined.\n"
                    "**<inviterName>** now has a **<amount> invites**!\n"
                    "Keep inviting for better rewards!"
                ),
            },
        },
    )


def format_join_message(
    template: str,
    joiner: discord.Member,
    inviter: discord.Member,
    total_invites: int,
) -> str:
    """Replace placeholders in the user-defined template."""
    return (
        template.replace("<joinerName>", joiner.name)
        .replace("<joinerMention>", joiner.mention)
        .replace("<inviterName>", inviter.name if inviter else "Unknown")
        .replace("<inviterMention>", inviter.mention if inviter else "Unknown")
        .replace("<amount>", str(total_invites))
    )


###############################################################################
# Setup-Invites command (per-server settings)
###############################################################################


class SetupView(discord.ui.View):
    def __init__(self, bot: commands.Bot, guild_id: int):
        super().__init__(timeout=None)
        self.bot = bot
        self.guild_id = guild_id

    @discord.ui.button(label="Edit", style=discord.ButtonStyle.primary)
    async def edit(self, i: discord.Interaction, _):
        settings = get_server_bucket(self.bot, self.guild_id)["settings"]

        class EditModal(discord.ui.Modal, title="Edit Invite Settings"):
            channel_id = discord.ui.TextInput(
                label="Invite Tracking Channel ID (optional)",
                default=str(settings["channel_id"] or ""),
                required=False,
            )
            join_template = discord.ui.TextInput(
                label="Join Message Template",
                style=discord.TextStyle.paragraph,
                default=settings["join_template"],
                required=True,
            )

            async def on_submit(modal_self, _inter: discord.Interaction):
                try:
                    cid_val = modal_self.channel_id.value.strip()
                    settings["channel_id"] = int(cid_val) if cid_val else 0
                except ValueError:
                    settings["channel_id"] = 0
                settings["join_template"] = modal_self.join_template.value.strip()

                await self.bot.save_invites()
                await _inter.response.edit_message(
                    content="✅ Settings updated. Use **Confirm** to publish.",
                    view=self,
                )

        await i.response.send_modal(EditModal())

    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.success)
    async def confirm(self, i: discord.Interaction, _):
        settings = get_server_bucket(self.bot, self.guild_id)["settings"]
        embed = discord.Embed(
            description=(
                "**Join Message:**\n"
                f"{settings['join_template']}\n\n"
                "**Invite Tracking Channel:**\n"
                + (
                    f"<#{settings['channel_id']}>" if settings["channel_id"] else "None"
                )
            ),
            color=discord.Color.from_rgb(12, 0, 182),
        )
        await i.response.send_message(embed=embed, ephemeral=True)


class InviteSetup(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(
        name="setup-invites", description="Configure invite-tracking settings"
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def setup_invites(self, inter: discord.Interaction):
        bucket = get_server_bucket(self.bot, inter.guild.id)
        settings = bucket["settings"]

        embed = discord.Embed(
            description=(
                "**Join Message:**\n"
                f"{settings['join_template']}\n\n"
                "**Invite Tracking Channel:**\n"
                + (
                    f"<#{settings['channel_id']}>" if settings["channel_id"] else "None"
                )
            ),
            color=discord.Color.from_rgb(12, 0, 182),
        )

        await inter.response.send_message(
            embed=embed, view=SetupView(self.bot, inter.guild.id), ephemeral=True
        )


###############################################################################
# Invite-tracking listener
###############################################################################


class InviteTracking(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.invite_lock = asyncio.Lock()
        self.invite_cleanup.start()

    #
    # Utility to fetch invites with retries
    #
    async def _safe_invites(self, guild: discord.Guild):
        for _ in range(3):
            try:
                return await guild.invites()
            except (discord.HTTPException, discord.Forbidden):
                await asyncio.sleep(2)
        return None

    # ────────────────────────────────────────────────────────────────
    # on_ready – cache existing invites
    # ────────────────────────────────────────────────────────────────
    @commands.Cog.listener()
    async def on_ready(self):
        for guild in self.bot.guilds:
            bucket = get_server_bucket(self.bot, guild.id)
            invites = await self._safe_invites(guild)
            if invites:
                bucket["invite_cache"] = {str(inv.id): inv.uses for inv in invites}

    # ────────────────────────────────────────────────────────────────
    # on_member_join
    # ────────────────────────────────────────────────────────────────
    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        if member.bot:
            return  # ignore bot joins entirely

        bucket = get_server_bucket(self.bot, member.guild.id)

        async with self.invite_lock:
            await asyncio.sleep(2)  # give Discord a moment to update counts

            invites_now = await self._safe_invites(member.guild)
            if not invites_now:
                return

            cache_before = bucket["invite_cache"]
            # pick invite whose uses increased
            used_invite = None
            for inv in invites_now:
                before = cache_before.get(str(inv.id), 0)
                if inv.uses > before:
                    used_invite = inv
                    break

            # refresh cache
            bucket["invite_cache"] = {str(inv.id): inv.uses for inv in invites_now}

            if not used_invite or not used_invite.inviter:
                return  # couldn't determine inviter

            inviter = used_invite.inviter
            now_ts = datetime.datetime.now(datetime.timezone.utc)

            # account-age check
            is_alt = (now_ts - member.created_at).days <= 10

            user_stats = bucket["users"].setdefault(
                str(inviter.id), {"regular": 0, "fake": 0, "bonus": 0}
            )

            if is_alt:
                user_stats["fake"] += 1
            else:
                user_stats["regular"] += 1

            total_inv = user_stats["regular"] - user_stats["fake"] + user_stats["bonus"]

            # store join info
            bucket["members"][str(member.id)] = {
                "inviter": str(inviter.id),
                "joined_at": now_ts.isoformat(),
            }

            await self.bot.save_invites()

            # send message if tracking channel configured
            ch_id = bucket["settings"]["channel_id"]
            if ch_id:
                ch = self.bot.get_channel(ch_id)
                if ch:
                    await ch.send(
                        format_join_message(
                            bucket["settings"]["join_template"],
                            member,
                            inviter,
                            total_inv,
                        )
                    )

    # ────────────────────────────────────────────────────────────────
    # on_member_remove – mark leave
    # ────────────────────────────────────────────────────────────────
    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        bucket = get_server_bucket(self.bot, member.guild.id)
        entry = bucket["members"].setdefault(str(member.id), {})
        entry["left_at"] = datetime.datetime.now(
            datetime.timezone.utc
        ).isoformat()
        await self.bot.save_invites()

    # ────────────────────────────────────────────────────────────────
    # housekeeping: delete zero-use invites if we’re over the soft cap
    # ────────────────────────────────────────────────────────────────
    @tasks.loop(seconds=CLEANUP_INTERVAL)
    async def invite_cleanup(self):
        for guild in self.bot.guilds:
            bucket = get_server_bucket(self.bot, guild.id)

            invites = await self._safe_invites(guild)
            if not invites or len(invites) < MAX_INVITES:
                continue

            zero_use = [inv for inv in invites if inv.uses == 0]
            excess = len(invites) - TARGET_INVITES
            to_delete = zero_use[: excess]

            for inv in to_delete:
                try:
                    await inv.delete()
                    await asyncio.sleep(1.5)
                except Exception:
                    pass

            updated = await self._safe_invites(guild)
            if updated:
                bucket["invite_cache"] = {str(inv.id): inv.uses for inv in updated}

    async def cog_unload(self):
        self.invite_cleanup.cancel()


###############################################################################
# Cog setup
###############################################################################


async def setup(bot: commands.Bot):
    # ensure top-level structures exist
    if not hasattr(bot, "invites"):
        bot.invites = {}
    if not hasattr(bot, "save_invites"):

        async def _save_invites():
            with open("invites.json", "w") as fp:
                json.dump(bot.invites, fp, indent=2)

        bot.save_invites = _save_invites

        # load existing file once
        if os.path.isfile("invites.json"):
            try:
                with open("invites.json") as fp:
                    bot.invites = json.load(fp)
            except Exception:
                bot.invites = {}

    await bot.add_cog(InviteSetup(bot))
    await bot.add_cog(InviteTracking(bot))
