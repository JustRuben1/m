# cogs/admin.py
import discord
from discord.ext import commands
from discord import app_commands
import asyncio

from config import ADMIN_ID, MAIN_GUILD_ID, LOG_CHANNEL_ID, ACCOUNTS_FILE
from cogs.invites import get_server_bucket


def is_admin():
    """Check if user is global owner or guild administrator."""
    async def predicate(inter: discord.Interaction) -> bool:
        if inter.user.id == ADMIN_ID or inter.user.guild_permissions.administrator:
            return True
        await inter.response.send_message("❌ You need administrator rights.", ephemeral=True)
        return False
    return app_commands.check(predicate)


class AdminCommands(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(
        name="invites",
        description="Check a member’s invites for this server"
    )
    @app_commands.describe(user="User to check (optional)")
    async def invites(
        self,
        inter: discord.Interaction,
        user: discord.Member | None = None
    ):
        bucket = get_server_bucket(self.bot, inter.guild.id)
        target = user or inter.user
        data = bucket["users"].get(str(target.id), {"regular": 0, "fake": 0, "bonus": 0})
        total = data["regular"] - data["fake"] + data["bonus"]

        embed = discord.Embed(
            title=f"{target.display_name}'s Invites",
            color=discord.Color.blue()
        ).add_field(
            name="Valid Invites",
            value=f"**{total}** (Real: {data['regular']} - Fake: {data['fake']} + Bonus: {data['bonus']})",
            inline=False
        )

        await inter.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(
        name="resetserverinvites",
        description="[ADMIN] Reset all invites and data for this server"
    )
    @is_admin()
    async def resetserverinvites(self, inter: discord.Interaction):
        bucket = get_server_bucket(self.bot, inter.guild.id)
        # clear per-server invite data
        bucket["users"].clear()
        bucket["guild_invites"].clear()
        await self.bot.save_invites()

        # optionally delete all Discord invites in the guild
        try:
            for inv in await inter.guild.invites():
                await inv.delete()
                await asyncio.sleep(1)
        except Exception:
            pass

        await inter.response.send_message("✅ Server invite data reset!", ephemeral=True)
        log_ch = self.bot.get_channel(LOG_CHANNEL_ID)
        if log_ch:
            await log_ch.send(
                f"⚠️ Invites reset for **{inter.guild.name}** by {inter.user.mention}"
            )

    @app_commands.command(
        name="addbonus",
        description="[ADMIN] Add bonus invites"
    )
    @app_commands.describe(user="Target user", amount="How many invites to add")
    @is_admin()
    async def addbonus(
        self,
        inter: discord.Interaction,
        user: discord.Member,
        amount: int
    ):
        bucket = get_server_bucket(self.bot, inter.guild.id)
        rec = bucket["users"].setdefault(str(user.id), {"regular": 0, "fake": 0, "bonus": 0})
        rec["bonus"] += max(amount, 0)
        await self.bot.save_invites()

        await inter.response.send_message(
            f"✅ Added **{amount}** bonus invite(s) to {user.mention}.",
            ephemeral=True
        )

    @app_commands.command(
        name="removebonus",
        description="[ADMIN] Remove bonus invites"
    )
    @app_commands.describe(user="Target user", amount="How many invites to remove")
    @is_admin()
    async def removebonus(
        self,
        inter: discord.Interaction,
        user: discord.Member,
        amount: int
    ):
        bucket = get_server_bucket(self.bot, inter.guild.id)
        rec = bucket["users"].setdefault(str(user.id), {"regular": 0, "fake": 0, "bonus": 0})
        rec["bonus"] -= max(amount, 0)
        await self.bot.save_invites()

        await inter.response.send_message(
            f"✅ Removed **{amount}** bonus invite(s) from {user.mention}.",
            ephemeral=True
        )

    @app_commands.command(
        name="reloadaccounts",
        description="[ADMIN] Reload accounts list from file"
    )
    @is_admin()
    async def reloadaccounts(self, inter: discord.Interaction):
        async with self.bot.accounts_lock:
            try:
                with open(ACCOUNTS_FILE, "r") as f:
                    self.bot.accounts = [line.strip() for line in f if line.strip()]
                await inter.response.send_message(
                    f"✅ Reloaded **{len(self.bot.accounts)}** accounts.",
                    ephemeral=True
                )
            except Exception as e:
                await inter.response.send_message(
                    f"❌ Error reloading accounts: {e}", 
                    ephemeral=True
                )


async def setup(bot: commands.Bot):
    await bot.add_cog(AdminCommands(bot))
