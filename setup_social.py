import discord
from discord.ext import commands
from discord import app_commands
import json
import os

from config import SERVICES

# Minimum total per order for each service
ORDER_MIN = {
    'tiktok': {
        'followers': 10,
        'likes': 10,
        'views': 100,
        'shares': 10
    },
    'youtube': {
        'subscribers': 20,
        'likes': 10,
        'views': 500,
        'short likes': 10
    },
    'instagram': {
        'followers': 10,
        'likes': 10,
        'views': 100,
        'shares': 100,
        'story views': 100
    },
    'twitch': {
        'followers': 10,
        'clip views': 10,
        'livestream viewers': 5
    },
    'twitter': {
        'followers': 10,
        'likes': 100,
        'retweet': 100,
        'tweet views': 100
    }
}

PLATFORM_EMOJIS = {
    'tiktok':    '<:tiktok:1346944982048702517>',
    'youtube':   '<:Youtube:1346945481380462784>',
    'instagram': '<:Instagram:1346945332084215848>',
    'twitch':    '<:twitch:1346945975004168244>',
    'twitter':   '<:Twitter:1346946116255485982>'
}


class SocialSetup(commands.Cog):
    """Handles the /setup-social command and its configuration UI."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # load or init config store on bot
        if not hasattr(bot, 'social_config'):
            bot.social_config = {}
        if not hasattr(bot, 'save_social_config'):
            async def _save():
                with open('social_config.json', 'w') as f:
                    json.dump(bot.social_config, f, indent=2)
            bot.save_social_config = _save

        # load from disk if present
        if os.path.isfile('social_config.json'):
            with open('social_config.json') as f:
                bot.social_config = json.load(f)

    @app_commands.command(
        name="setup-social",
        description="Configure & publish your /social embed"
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def setup_social(self, interaction: discord.Interaction):
        guild_id = str(interaction.guild.id)
        cfg = self.bot.social_config.setdefault(guild_id, {})

        # Base embed settings
        cfg.setdefault('title', "Social Media Rewards")
        cfg.setdefault('text', "Boost your social media accounts for __FREE__ by inviting people!\n\nChoose your favorite platform below.")
        cfg.setdefault('image', None)

        # Per-platform service settings
        plat_cfg = cfg.setdefault('platforms', {})
        for platform, services in SERVICES.items():
            pc = plat_cfg.setdefault(platform, {})
            for svc_name, svc_data in services.items():
                pc.setdefault(svc_name, {
                    'per_invite': svc_data['per_invite'],
                    'min_invites': svc_data['min_invites']
                })

        # Build preview embed
        embed = discord.Embed(
            title=cfg['title'],
            description=cfg['text'],
            color=discord.Color.from_rgb(12, 0, 182)
        )
        if cfg['image']:
            embed.set_image(url=cfg['image'])

        # Dropdown menu for configuration
        class SetupMenu(discord.ui.Select):
            def __init__(self):
                options = [
                    discord.SelectOption(
                        label="Edit Embed",
                        description="Edit the Embed that will be sent.",
                        value="edit_embed"
                    )
                ]
                for idx, platform in enumerate(SERVICES, start=2):
                    options.append(discord.SelectOption(
                        label=f"Edit {platform.capitalize()} Quantity",
                        description=f"Edit the quantity for {platform.title()}.",
                        emoji=PLATFORM_EMOJIS[platform],
                        value=f"edit_{platform}"
                    ))
                super().__init__(
                    custom_id="setup_social_menu",
                    placeholder="Configure Social...",
                    min_values=1,
                    max_values=1,
                    options=options
                )

            async def callback(self, select_inter: discord.Interaction):
                choice = self.values[0]
                guild_id = str(select_inter.guild.id)
                cfg = self.view.bot.social_config[guild_id]

                if choice == "edit_embed":
                    await select_inter.response.send_modal(EditEmbedModal(self.view.bot, guild_id))
                    return

                # editing a platform
                platform = choice.replace("edit_", "")
                # build current quantities embed
                q_embed = discord.Embed(
                    title=f"Edit {platform.capitalize()} Quantity",
                    description="Current Quantities:",
                    color=discord.Color.from_rgb(12, 0, 182)
                )
                for svc, svc_cfg in cfg['platforms'][platform].items():
                    q_embed.add_field(
                        name=svc.title(),
                        value=f"{svc_cfg['per_invite']} per invite\nMin invites: {svc_cfg['min_invites']}",
                        inline=False
                    )
                await select_inter.response.send_message(
                    embed=q_embed,
                    view=QuantityView(self.view.bot, guild_id, platform),
                    ephemeral=True
                )

        class SetupView(discord.ui.View):
            def __init__(self, bot, guild_id):
                super().__init__(timeout=None)
                self.bot = bot
                self.guild_id = guild_id
                self.add_item(SetupMenu())

        class EditEmbedModal(discord.ui.Modal):
            def __init__(self, bot, guild_id):
                super().__init__(title="Edit /social Embed")
                self.bot = bot
                self.guild_id = guild_id
                self.title_input = discord.ui.TextInput(
                    label="Title", default=cfg['title']
                )
                self.text_input = discord.ui.TextInput(
                    label="Text", style=discord.TextStyle.paragraph, default=cfg['text']
                )
                self.image_input = discord.ui.TextInput(
                    label="Image URL", required=False, default=cfg['image'] or ""
                )
                self.add_item(self.title_input)
                self.add_item(self.text_input)
                self.add_item(self.image_input)

            async def on_submit(self, modal_inter: discord.Interaction):
                c = self.bot.social_config[self.guild_id]
                c['title'] = self.title_input.value
                c['text'] = self.text_input.value
                c['image'] = self.image_input.value or None
                await self.bot.save_social_config()
                await modal_inter.response.send_message(
                    "✅ Embed settings updated! Use /setup-social to preview.",
                    ephemeral=True
                )

        class QuantityView(discord.ui.View):
            def __init__(self, bot, guild_id, platform):
                super().__init__(timeout=None)
                self.bot = bot
                self.guild_id = guild_id
                self.platform = platform
                for svc in SERVICES[platform]:
                    btn = discord.ui.Button(label=svc.title(), style=discord.ButtonStyle.blurple)
                    async def callback(i, svc_name=svc):
                        await i.response.send_modal(QuantityModal(self.bot, self.guild_id, self.platform, svc_name))
                    btn.callback = callback
                    self.add_item(btn)

        class QuantityModal(discord.ui.Modal):
            def __init__(self, bot, guild_id, platform, service):
                super().__init__(title=f"Edit {service.title()} Settings")
                self.bot = bot
                self.guild_id = guild_id
                self.platform = platform
                self.service = service
                svc_cfg = bot.social_config[guild_id]['platforms'][platform][service]
                self.per_invite = discord.ui.TextInput(
                    label="Quantity Per Invite",
                    default=str(svc_cfg['per_invite'])
                )
                self.min_invites = discord.ui.TextInput(
                    label="Minimum Invites To Spend",
                    default=str(svc_cfg['min_invites'])
                )
                self.add_item(self.per_invite)
                self.add_item(self.min_invites)

            async def on_submit(self, modal_inter: discord.Interaction):
                pi = int(self.per_invite.value)
                mi = int(self.min_invites.value)
                total_order = pi * mi
                req = ORDER_MIN[self.platform][self.service]
                if total_order < req:
                    return await modal_inter.response.send_message(
                        f"❌ The minimum quantity per order for this service is {req}.",
                        ephemeral=True
                    )
                # update config
                c = self.bot.social_config[self.guild_id]['platforms'][self.platform][self.service]
                c['per_invite']  = pi
                c['min_invites'] = mi
                await self.bot.save_social_config()
                await modal_inter.response.send_message(
                    f"✅ Updated {self.service.title()} settings.",
                    ephemeral=True
                )

        # send the setup view
        await interaction.response.send_message(
            embed=embed,
            view=SetupView(self.bot, guild_id),
            ephemeral=True
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(SocialSetup(bot))
