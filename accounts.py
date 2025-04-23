import discord
from discord.ext import commands
from discord import app_commands
from config import *
import random
import asyncio

class InviteTutorialView(discord.ui.View):
    def __init__(self):
        super().__init__()
        self.add_item(discord.ui.Button(
            label="Invite Tutorial",
            style=discord.ButtonStyle.gray,
            url="https://discord.com/channels/1329897880806228030/1346159208071954492"
        ))

class CopyCredentialsView(discord.ui.View):
    def __init__(self, account: str):
        super().__init__()
        self.account = account

    @discord.ui.button(label="Copy Credentials", style=discord.ButtonStyle.blurple)
    async def copy_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        email, password = self.account.split(":", 1)
        await interaction.response.send_message(f"{email}", ephemeral=True)
        await interaction.followup.send(f"{password}", ephemeral=True)

class GeneratorView(discord.ui.View):
    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot

    @discord.ui.button(
        label="Claim Account", 
        style=discord.ButtonStyle.primary, 
        custom_id="claim_account",
        emoji='<:gift_icon_white:1347285070540701747>'
    )
    async def claim_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        user_id = str(interaction.user.id)
        try:
            inviter_data = self.bot.invites['inviters'].get(user_id, {'regular': 0, 'fake': 0, 'bonus': 0})
            valid_invites = inviter_data['regular'] - inviter_data['fake'] + inviter_data['bonus']

            if valid_invites < 1:
                embed = discord.Embed(
                    title="Not enough invites :x:",
                    description="You need at least **1** invite to claim an account.",
                    color=discord.Color.red()
                )
                return await interaction.response.send_message(
                    embed=embed,
                    view=InviteTutorialView(),
                    ephemeral=True
                )

            async with self.bot.accounts_lock:
                if not self.bot.accounts:
                    return await interaction.response.send_message("❌ No accounts available!", ephemeral=True)

                account = self.bot.accounts.pop(random.randrange(len(self.bot.accounts)))
                with open(ACCOUNTS_FILE, 'w') as f:
                    f.write("\n".join(self.bot.accounts))

            inviter_data['bonus'] -= 1
            await self.bot.save_invites()

            await interaction.response.send_message(
                f"✅ Successfully claimed an account! Your account:\n```{account}```",
                view=CopyCredentialsView(account),
                ephemeral=True
            )

            log_channel = self.bot.get_channel(LOG_CHANNEL_ID)
            if log_channel:
                remaining = valid_invites - 1
                await log_channel.send(
                    f"🎁 **Account Claim**\n"
                    f"• User: {interaction.user.mention} (`{interaction.user.id}`)\n"
                    f"• Account: `{account}`\n"
                    f"• Invites Spent: 1\n"
                    f"• Remaining Invites: {remaining}"
                )

        except Exception as e:
            print(f"Claim error: {e}")
            await interaction.response.send_message("❌ Failed to process claim", ephemeral=True)

    @discord.ui.button(
        label="Check Invites", 
        style=discord.ButtonStyle.green, 
        custom_id="check_invites",
        emoji='<:BlackUser_IDS:1347285924051947601>'
    )
    async def check_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        user_id = str(interaction.user.id)
        data = self.bot.invites['inviters'].get(user_id, {'regular': 0, 'fake': 0, 'bonus': 0})
        total = data['regular'] - data['fake'] + data['bonus']
        await interaction.response.send_message(
            f"You currently have **{total}** invites!",
            ephemeral=True
        )

class AccountGenerator(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.bot.add_view(GeneratorView(bot))

    @app_commands.command(name="generator", description="Get free accounts")
    async def generator(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="Earn Fortnite Accounts",
            description="Earn __FREE__ Exclusive Fortnite Accounts by inviting people to the server!\n# 1 Invite = 1 Account",
            color=discord.Color.from_rgb(12, 0, 182)
        ).set_image(url="https://i.imgur.com/rgRNNcU.jpeg")

        await interaction.response.send_message(embed=embed, view=GeneratorView(self.bot))

async def setup(bot):
    await bot.add_cog(AccountGenerator(bot))
