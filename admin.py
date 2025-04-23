import discord
from discord.ext import commands
from discord import app_commands
from config import *
import asyncio

def is_admin():
    async def predicate(interaction: discord.Interaction):
        if interaction.user.id == ADMIN_ID:
            return True
        await interaction.response.send_message("❌ Permission denied!", ephemeral=True)
        return False
    return app_commands.check(predicate)

class AdminCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="invites", description="Check invite counts")
    @app_commands.describe(user="User to check")
    async def invites(self, interaction: discord.Interaction, user: discord.Member = None):
        target = user or interaction.user
        data = self.bot.invites['inviters'].get(str(target.id), {'regular': 0, 'fake': 0, 'bonus': 0})
        total = data['regular'] - data['fake'] + data['bonus']

        embed = discord.Embed(
            title=f"{target.name}'s Invites",
            color=discord.Color.from_rgb(12, 0, 182)
        ).add_field(
            name="Valid Invites",
            value=f"**{total}** (Real: {data['regular']} - Fake: {data['fake']} + Bonus: {data['bonus']})",
            inline=False
        )

        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="resetserverinvites", description="[ADMIN] Reset all invites and data")
    @is_admin()
    async def resetserverinvites(self, interaction: discord.Interaction):
        try:
            self.bot.invites = {'inviters': {}, 'members': {}, 'guild_invites': {}}

            guild = self.bot.get_guild(MAIN_GUILD_ID)
            if guild:
                invites = await guild.invites()
                for invite in invites:
                    try:
                        await invite.delete()
                        await asyncio.sleep(1)
                    except Exception as e:
                        print(f"Error deleting invite: {e}")

            await self.bot.save_invites()
            await interaction.response.send_message("✅ Server invites and data reset!", ephemeral=True)

            log_channel = self.bot.get_channel(LOG_CHANNEL_ID)
            if log_channel:
                await log_channel.send(f"⚠️ Server invites reset by {interaction.user.mention}")

        except Exception as e:
            await interaction.response.send_message(f"❌ Error: {str(e)}", ephemeral=True)

    @app_commands.command(name="addbonus", description="[ADMIN] Add bonus invites")
    @app_commands.describe(user="Target user", amount="Number of invites to add")
    @is_admin()
    async def addbonus(self, interaction: discord.Interaction, user: discord.Member, amount: int):
        try:
            data = self.bot.invites['inviters'].setdefault(str(user.id), {'regular': 0, 'fake': 0, 'bonus': 0})
            data['bonus'] += amount
            await self.bot.save_invites()
            await interaction.response.send_message(
                f"✅ Added {amount} bonus invites to {user.mention}",
                ephemeral=True
            )
        except Exception as e:
            await interaction.response.send_message(f"❌ Error: {str(e)}", ephemeral=True)

    @app_commands.command(name="removebonus", description="[ADMIN] Remove bonus invites")
    @app_commands.describe(user="Target user", amount="Number of invites to remove")
    @is_admin()
    async def removebonus(self, interaction: discord.Interaction, user: discord.Member, amount: int):
        try:
            data = self.bot.invites['inviters'].setdefault(str(user.id), {'regular': 0, 'fake': 0, 'bonus': 0})
            data['bonus'] -= amount
            await self.bot.save_invites()
            await interaction.response.send_message(
                f"✅ Removed {amount} bonus invites from {user.mention}",
                ephemeral=True
            )
        except Exception as e:
            await interaction.response.send_message(f"❌ Error: {str(e)}", ephemeral=True)

    @app_commands.command(name="reloadaccounts", description="[ADMIN] Reload accounts list")
    @is_admin()
    async def reloadaccounts(self, interaction: discord.Interaction):
        try:
            async with self.bot.accounts_lock:
                with open(ACCOUNTS_FILE, 'r') as f:
                    self.bot.accounts = [line.strip() for line in f if line.strip()]
                await interaction.response.send_message(
                    f"✅ Reloaded {len(self.bot.accounts)} accounts",
                    ephemeral=True
                )
        except Exception as e:
            await interaction.response.send_message(f"❌ Error: {str(e)}", ephemeral=True)

async def setup(bot):
    await bot.add_cog(AdminCommands(bot))
