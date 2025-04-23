# cogs/membersfarm.py
import discord
from discord.ext import commands
from discord import app_commands
import requests
import json
from config import VAULTCORD_API_KEY, LOG_CHANNEL_ID, PULL_BOT_ID

VAULTCORD_BASE_URL = "https://api.vaultcord.com"

class MembersFarm(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="members", description="Add members from farm")
    async def members(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="Members Farm",
            description=(
                "__REAL__ Discord Members to your server for __FREE__ by using invites.\n\n"
                "Before adding any members, add the bot to your designated server:\n"
                "https://discord.com/oauth2/authorize?client_id=1329445763649900615&permissions=268437507&scope=bot\n"
                "**# 1 Invite = 10 Members**"
            ),
            color=discord.Color.blurple()
        )
        view = MembersView(self.bot)
        await interaction.response.send_message(embed=embed, view=view)

class MembersView(discord.ui.View):
    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot

    @discord.ui.button(label="Add Members", style=discord.ButtonStyle.primary, emoji='<:gift_icon_white:1347285070540701747>')
    async def add_members(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(AddMembersModal(self.bot))

    @discord.ui.button(label="Tutorial", style=discord.ButtonStyle.green, emoji='<:Discord:1330190471170883736>')
    async def tutorial(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed1 = discord.Embed(
            title="Step 1",
            description=(
                "Start off by adding your PULL bot to your designated server.\n\n"
                "Use the '**Add Bot**' button below to add it."
            ),
            color=discord.Color.green()
        )
        add_bot_view = AddBotView()
        await interaction.response.send_message(embed=embed1, view=add_bot_view, ephemeral=True)

        embed2 = discord.Embed(
            title="Step 2",
            description=(
                "Enable **Developer Mode**\n\n"
                "1: Head over to your Discord Settings\n"
                "2: Click on ‘Advanced’\n"
                "3: Enable Developer Mode"
            )
        ).set_image(url="https://cdn.discordapp.com/attachments/987753155360079903/1364355714138636380/IMG_3103.jpg")
        embed3 = discord.Embed(
            title="Step 3",
            description=(
                "Get your server ID.\n\n"
                "1: Click on your Server’s Name\n"
                "2: Scroll down to ‘Copy Server ID’\n\n"
                "Paste that Server ID into the form, and you’re done!"
            )
        ).set_image(url="https://cdn.discordapp.com/attachments/987753155360079903/1364355705238196345/IMG_3106.jpg")
        await interaction.followup.send(embeds=[embed2, embed3], ephemeral=True)

class AddBotView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(discord.ui.Button(
            label="Add PULL Bot",
            style=discord.ButtonStyle.secondary,
            url="https://discord.com/oauth2/authorize?client_id=1329445763649900615&permissions=268437507&scope=bot"
        ))

class AddMembersModal(discord.ui.Modal):
    def __init__(self, bot):
        super().__init__(title="Add Members")
        self.bot = bot
        self.invites_input = discord.ui.TextInput(
            label="Invites to spend",
            placeholder="Min 1 invite"
        )
        self.server_input = discord.ui.TextInput(
            label="Server ID",
            placeholder="The Tutorial will explain how to get this"
        )
        self.display_name_input = discord.ui.TextInput(
            label="Server Display Name",
            placeholder="Name to show in VaultCord"
        )
        self.add_item(self.invites_input)
        self.add_item(self.server_input)
        self.add_item(self.display_name_input)

    async def on_submit(self, interaction: discord.Interaction):
        # Validate invites
        try:
            invites_spent = int(self.invites_input.value)
        except ValueError:
            return await interaction.response.send_message("❌ Invalid number format.", ephemeral=True)
        if not 1 <= invites_spent <= 10:
            return await interaction.response.send_message("❌ You can spend between 1 and 10 invites.", ephemeral=True)

        # Check invite balance
        user_id = str(interaction.user.id)
        inviter_data = self.bot.invites['inviters'].get(user_id, {'regular':0,'fake':0,'bonus':0})
        total_inv = inviter_data['regular'] - inviter_data['fake'] + inviter_data['bonus']
        if total_inv < invites_spent:
            return await interaction.response.send_message("❌ You do not have enough invites.", ephemeral=True)

        # Validate server ID
        try:
            server_id = int(self.server_input.value.strip())
        except ValueError:
            return await interaction.response.send_message("❌ Invalid Server ID.", ephemeral=True)

        # Confirm PULL bot is in guild
        guild = self.bot.get_guild(server_id)
        if guild is None or guild.get_member(int(PULL_BOT_ID)) is None:
            embed = discord.Embed(
                description="The PULL bot is not added to that server yet. Please add it first.",
                color=discord.Color.red()
            )
            return await interaction.response.send_message(embed=embed, view=AddBotView(), ephemeral=True)

        # Use provided display name
        display_name = self.display_name_input.value.strip()
        if not display_name:
            return await interaction.response.send_message("❌ Server Display Name cannot be empty.", ephemeral=True)

        # Register server via VaultCord API
        try:
            reg_resp = requests.put(
                f"{VAULTCORD_BASE_URL}/servers",
                headers={
                    "Authorization": f"Bearer {VAULTCORD_API_KEY}",
                    "Content-Type": "application/json"
                },
                json={
                    "name":     display_name,
                    "botId":    int(PULL_BOT_ID),
                    "serverId": str(server_id)
                }
            )
            reg_data = reg_resp.json()
        except Exception as e:
            print(f"[VaultCord:Register] Exception: {e}")
            return await interaction.response.send_message(f"❌ Failed to register server ({e}).", ephemeral=True)

        # Detailed logging
        print(f"[VaultCord:Register] HTTP {reg_resp.status_code}")
        print(f"[VaultCord:Register] Response text: {reg_resp.text}")
        print(f"[VaultCord:Register] JSON: {reg_data}")

        if not ((reg_resp.ok and reg_data.get("success")) or reg_resp.status_code == 409):
            return await interaction.response.send_message(
                f"❌ VaultCord registration error: {reg_data.get('message', reg_resp.text)}",
                ephemeral=True
            )

        # Defer for pull
        await interaction.response.defer(thinking=True, ephemeral=True)

        # Deduct invites
        inviter_data['bonus'] -= invites_spent
        await self.bot.save_invites()

        # Trigger VaultCord pull
        limit = invites_spent * 10
        try:
            pull_resp = requests.put(
                f"{VAULTCORD_BASE_URL}/members/pull/{server_id}",
                headers={
                    "Authorization": f"Bearer {VAULTCORD_API_KEY}",
                    "Content-Type": "application/json"
                },
                json={"guildid": str(server_id), "limit": limit}
            )
            pull_data = pull_resp.json()
        except Exception as e:
            print(f"[VaultCord:Pull] Exception: {e}")
            return await interaction.followup.send(f"❌ Failed to start pull ({e}).", ephemeral=True)

        # Logging pull response
        print(f"[VaultCord:Pull] HTTP {pull_resp.status_code}")
        print(f"[VaultCord:Pull] Response text: {pull_resp.text}")
        print(f"[VaultCord:Pull] JSON: {pull_data}")

        if not (pull_resp.ok and pull_data.get("success")):
            return await interaction.followup.send(
                f"❌ VaultCord pull error: {pull_data.get('message', pull_resp.text)}",
                ephemeral=True
            )

        # Success
        await interaction.followup.send(
            f"✅ Pull started! {invites_spent} invite(s) spent for up to {limit} members.", ephemeral=True
        )

        # Log action
        log_ch = self.bot.get_channel(LOG_CHANNEL_ID)
        if log_ch:
            await log_ch.send(
                f"👥 Members Pull • User: {interaction.user.mention} • Server: {server_id} • Invites: {invites_spent}"
            )

async def setup(bot):
    await bot.add_cog(MembersFarm(bot))
