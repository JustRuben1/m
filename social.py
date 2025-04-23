# cogs/social.py – PART 1 of 3
import discord
from discord.ext import commands
from discord import app_commands
import requests
import datetime
import json
import os

from config import SERVICES, BULKMEDYA_API_URL, LOG_CHANNEL_ID

######################################################################
# Helper Functions
######################################################################

def validate_link(platform: str, service_type: str, link: str) -> bool:
    link_lower = link.lower()
    if platform == 'tiktok':
        return "tiktok" in link_lower
    if platform == 'youtube':
        return "youtube" in link_lower or "youtu.be" in link_lower
    if platform == 'instagram':
        return "instagram" in link_lower
    if platform == 'twitch':
        return "twitch" in link_lower
    if platform == 'twitter':
        return "twitter" in link_lower
    return False

def create_bulkmedya_order(service_id: int, link: str, quantity: int, api_key: str) -> dict:
    payload = {
        'key': api_key,
        'action': 'add',
        'service': service_id,
        'link': link,
        'quantity': quantity
    }
    resp = requests.post(BULKMEDYA_API_URL, data=payload, timeout=10)
    resp.raise_for_status()
    return resp.json()

def get_bulkmedya_status(order_ids: list, api_key: str) -> dict:
    payload = {'key': api_key, 'action': 'status'}
    if not order_ids:
        return {}
    if len(order_ids) == 1:
        payload['order'] = order_ids[0]
    else:
        payload['orders'] = ",".join(order_ids)
    resp = requests.post(BULKMEDYA_API_URL, data=payload, timeout=10)
    resp.raise_for_status()
    return resp.json()

def request_bulkmedya_refill(order_ids: list, api_key: str) -> list:
    if not order_ids:
        return []
    payload = {'key': api_key, 'action': 'refill'}
    if len(order_ids) == 1:
        payload['order'] = order_ids[0]
    else:
        payload['orders'] = ",".join(order_ids)
    resp = requests.post(BULKMEDYA_API_URL, data=payload, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    if len(order_ids) == 1 and isinstance(data, dict):
        return [{"order": order_ids[0], "refill": data.get("refill")}]
    return data if isinstance(data, list) else []

######################################################################
# /setup-social & /social
######################################################################

class SocialBooster(commands.Cog):
    """Handles /setup-social (admin) and /social (public)."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        if not hasattr(bot, 'social_config'):
            bot.social_config = {}
        if 'orders' not in bot.invites:
            bot.invites['orders'] = {}

    @app_commands.command(
        name="setup-social",
        description="Configure & publish your /social embed (API key at discord.gg/gamevaultbot)"
    )
    @app_commands.describe(api_key="Your BulkMedya API key")
    @app_commands.checks.has_permissions(administrator=True)
    async def setup_social(self, interaction: discord.Interaction, api_key: str):
        guild_id = str(interaction.guild.id)
        cfg = self.bot.social_config.setdefault(guild_id, {})
        cfg['api_key'] = api_key
        cfg.setdefault('title', "Social Media Rewards")
        cfg.setdefault('text', "Boost your social media accounts for __FREE__ by inviting people!\n\nChoose your favorite platform below.")
        cfg.setdefault('image', None)

        embed = discord.Embed(
            title=cfg['title'],
            description=cfg['text'],
            color=discord.Color.from_rgb(12, 0, 182)
        )
        if cfg.get('image'):
            embed.set_image(url=cfg['image'])

        class SetupSocView(discord.ui.View):
            def __init__(self, bot, guild_id):
                super().__init__(timeout=None)
                self.bot = bot
                self.guild_id = guild_id

            @discord.ui.button(label="Edit", style=discord.ButtonStyle.blurple)
            async def edit(self, interaction: discord.Interaction, button: discord.ui.Button):
                class SocModal(discord.ui.Modal):
                    def __init__(self, bot, guild_id):
                        super().__init__(title="Edit /social Embed")
                        self.bot = bot
                        self.guild_id = guild_id
                        self.title_input = discord.ui.TextInput(
                            label="Title",
                            placeholder="Embed Title"
                        )
                        self.text_input = discord.ui.TextInput(
                            label="Text",
                            style=discord.TextStyle.paragraph,
                            placeholder="Embed Text"
                        )
                        self.image_input = discord.ui.TextInput(
                            label="Image URL",
                            required=False,
                            placeholder="Leave blank for no image"
                        )
                        self.add_item(self.title_input)
                        self.add_item(self.text_input)
                        self.add_item(self.image_input)

                    async def on_submit(self, modal_interaction: discord.Interaction):
                        cfg = self.bot.social_config[self.guild_id]
                        cfg.update({
                            'title': self.title_input.value,
                            'text': self.text_input.value,
                            'image': self.image_input.value or None
                        })
                        await self.bot.save_social_config()
                        new_embed = discord.Embed(
                            title=self.title_input.value,
                            description=self.text_input.value,
                            color=discord.Color.from_rgb(12, 0, 182)
                        )
                        if self.image_input.value:
                            new_embed.set_image(url=self.image_input.value)
                        await modal_interaction.response.edit_message(embed=new_embed, view=SetupSocView(self.bot, self.guild_id))

                await interaction.response.send_modal(SocModal(self.bot, guild_id))

            @discord.ui.button(label="Confirm", style=discord.ButtonStyle.green)
            async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
                cfg = self.bot.social_config[guild_id]
                public_embed = discord.Embed(
                    title=cfg['title'],
                    description=cfg['text'],
                    color=discord.Color.from_rgb(12, 0, 182)
                )
                if cfg.get('image'):
                    public_embed.set_image(url=cfg['image'])
                await interaction.response.send_message(embed=public_embed, view=SocialPlatformView(self.bot), ephemeral=False)

        await interaction.response.send_message(embed=embed, view=SetupSocView(self.bot, guild_id), ephemeral=True)

    @app_commands.command(name="social", description="Boost your social media accounts")
    async def social(self, interaction: discord.Interaction):
        guild_id = str(interaction.guild.id)
        cfg = self.bot.social_config.get(guild_id)
        if not cfg or not cfg.get('api_key'):
            return await interaction.response.send_message("❌ No API key configured—run /setup-social first.", ephemeral=True)
        embed = discord.Embed(
            title=cfg['title'],
            description=cfg['text'],
            color=discord.Color.from_rgb(12, 0, 182)
        )
        if cfg.get('image'):
            embed.set_image(url=cfg['image'])
        await interaction.response.send_message(embed=embed, view=SocialPlatformView(self.bot), ephemeral=False)

######################################################################
# Platform selection & Order modal
######################################################################

class SocialPlatformView(discord.ui.View):
    def __init__(self, bot: commands.Bot):
        super().__init__(timeout=None)
        self.bot = bot

    @discord.ui.button(label="TikTok", style=discord.ButtonStyle.red, emoji='<:tiktok:1346944982048702517>')
    async def tiktok(self, interaction: discord.Interaction, button: discord.ui.Button):
        desc = (
            "Boost your TikTok Account with Followers, Views, Likes and Shares for __FREE!__\n\n"
            "10,000 Views = 1 invite\n"
            "100 Likes = 1 invite\n"
            "200 Shares = 1 invite\n"
            "25 Followers = 1 invite\n\n"
            "The minimum quantity for followers is 100."
        )
        embed = discord.Embed(
            title="TikTok Boost",
            description=desc,
            color=discord.Color.from_rgb(12, 0, 182)
        )
        await interaction.response.send_message(embed=embed, view=SocialServiceView(self.bot, "tiktok"), ephemeral=True)
# cogs/social.py – PART 2 of 3

    @discord.ui.button(label="YouTube", style=discord.ButtonStyle.red, emoji='<:Youtube:1346945481380462784>')
    async def youtube(self, interaction: discord.Interaction, button: discord.ui.Button):
        desc = (
            "Boost your YouTube Account with Subscribers, Likes, Views and Short Likes for __FREE!__\n\n"
            "125 Views = 1 invite\n"
            "100 Likes = 1 invite\n"
            "20 Subscribers = 1 invite\n"
            "50 Short Likes = 1 invite\n\n"
            "The minimum quantity for subscribers is 100.\n"
            "The minimum quantity for views is 500."
        )
        embed = discord.Embed(title="YouTube Boost", description=desc, color=discord.Color.from_rgb(12, 0, 182))
        await interaction.response.send_message(embed=embed, view=SocialServiceView(self.bot, "youtube"), ephemeral=True)

    @discord.ui.button(label="Instagram", style=discord.ButtonStyle.green, emoji='<:Instagram:1346945332084215848>')
    async def instagram(self, interaction: discord.Interaction, button: discord.ui.Button):
        desc = (
            "Boost your Instagram Account with Followers, Views, Likes and Shares for FREE!\n\n"
            "10,000 Story Views (All Stories) = 1 invite\n"
            "1000 Views (Reel/TV) = 1 invite\n"
            "250 Likes = 1 invite\n"
            "750 Shares = 1 invite\n"
            "25 Followers = 1 invite\n\n"
            "The minimum quantity for followers is 100."
        )
        embed = discord.Embed(title="Instagram Boost", description=desc, color=discord.Color.from_rgb(12, 0, 182))
        await interaction.response.send_message(embed=embed, view=SocialServiceView(self.bot, "instagram"), ephemeral=True)

    @discord.ui.button(label="Twitch", style=discord.ButtonStyle.green, emoji='<:twitch:1346945975004168244>')
    async def twitch(self, interaction: discord.Interaction, button: discord.ui.Button):
        desc = (
            "Boost your Twitch Account with Followers, Clip Views and Livestream Viewers for __FREE!__\n\n"
            "25 Livestream Viewers (30m) = 1 invite\n"
            "300 Clip Views = 1 invite\n"
            "200 Followers = 1 invite\n\n"
            "Please note that Twitch services can be extremely slow."
        )
        embed = discord.Embed(title="Twitch Boost", description=desc, color=discord.Color.from_rgb(12, 0, 182))
        await interaction.response.send_message(embed=embed, view=SocialServiceView(self.bot, "twitch"), ephemeral=True)

    @discord.ui.button(label="Twitter", style=discord.ButtonStyle.blurple, emoji='<:Twitter:1346946116255485982>')
    async def twitter(self, interaction: discord.Interaction, button: discord.ui.Button):
        desc = (
            "Boost your Twitter Account with Followers, Likes, Retweets and Tweet Views for __FREE!__\n\n"
            "10,000 Tweet Views = 1 invite\n"
            "250 Likes = 1 invite\n"
            "250 Retweets = 1 invite\n"
            "100 Followers = 1 invite"
        )
        embed = discord.Embed(title="Twitter Boost", description=desc, color=discord.Color.from_rgb(12, 0, 182))
        await interaction.response.send_message(embed=embed, view=SocialServiceView(self.bot, "twitter"), ephemeral=True)


class SocialServiceView(discord.ui.View):
    """Buttons for each service under a platform."""
    def __init__(self, bot: commands.Bot, platform: str):
        super().__init__(timeout=None)
        self.bot = bot
        self.platform = platform
        for svc in SERVICES.get(platform, {}):
            btn = discord.ui.Button(label=svc.title(), style=discord.ButtonStyle.blurple)
            async def cb(i, s=svc):
                # intercept to require confirm
                await i.response.send_message("Please click confirm to use this feature.", ephemeral=True)
            btn.callback = cb
            self.add_item(btn)


class OrderCreationModal(discord.ui.Modal):
    """Collect invites & link, then place a BulkMedya order."""
    def __init__(self, bot, platform: str, service: str):
        super().__init__(title=f"{platform.capitalize()} {service.title()}")
        self.bot = bot
        self.platform = platform
        self.service = service
        data = SERVICES[platform][service]
        self.invites = discord.ui.TextInput(
            label="Invites to spend",
            placeholder=f"Min {data['min_invites']} invites"
        )
        self.link = discord.ui.TextInput(
            label="Link",
            placeholder=f"https://{platform}.com/..."
        )
        self.add_item(self.invites)
        self.add_item(self.link)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            cnt = int(self.invites.value)
        except ValueError:
            return await interaction.followup.send("❌ Invalid number.", ephemeral=True)
        data = SERVICES[self.platform][self.service]
        if cnt < data['min_invites']:
            return await interaction.followup.send(f"❌ You need at least {data['min_invites']} invites.", ephemeral=True)
        if not validate_link(self.platform, self.service, self.link.value):
            return await interaction.followup.send("❌ Invalid link.", ephemeral=True)
        uid = str(interaction.user.id)
        inv = self.bot.invites['inviters'].get(uid, {'regular':0,'fake':0,'bonus':0})
        total = inv['regular'] - inv['fake'] + inv['bonus']
        if total < cnt:
            return await interaction.followup.send("❌ Not enough invites.", ephemeral=True)
        inv['bonus'] -= cnt
        await self.bot.save_invites()
        qty = cnt * data['per_invite']
        resp = create_bulkmedya_order(data['service_id'], self.link.value, qty, self.bot.social_config[str(interaction.guild.id)]['api_key'])
        oid = str(resp.get("order", "N/A"))
        if LOG_CHANNEL_ID:
            lc = self.bot.get_channel(LOG_CHANNEL_ID)
            if lc:
                await lc.send(f"🚀 {interaction.user.mention} ordered {self.platform} {self.service} qty={qty}, oid={oid}")
        self.bot.invites['orders'].setdefault(uid, []).append({
            'order_id': oid,
            'platform': self.platform,
            'service': self.service,
            'invites_spent': cnt,
            'refunded': False,
            'timestamp': datetime.datetime.utcnow().isoformat()
        })
        await interaction.followup.send("✅ Order placed! May take up to 48h.", ephemeral=True)


class SocialCompensation(commands.Cog):
    """Handles /compensation for refunded or completed orders."""
    def __init__(self, bot):
        self.bot = bot
        if 'orders' not in bot.invites:
            bot.invites['orders'] = {}
        if not hasattr(bot, 'refunded_orders'):
            bot.refunded_orders = set()

    @app_commands.command(name="compensation", description="Get your invites back for failed orders")
    async def compensation(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="Social Boost Issues / Compensation",
            description=(
                "Didn’t receive what you claimed?\n"
                "Accidentally used the wrong link?\n\n"
                "**Select your platform to refund invites!**"
            ),
            color=discord.Color.from_rgb(12, 0, 182)
        )
        await interaction.response.send_message(embed=embed, view=CompensationPlatformView(self.bot), ephemeral=False)


class CompensationPlatformView(discord.ui.View):
    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot

    @discord.ui.button(label="TikTok", style=discord.ButtonStyle.red, emoji='<:tiktok:1346944982048702517>')
    async def tiktok(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._show(interaction, "tiktok")
    @discord.ui.button(label="YouTube", style=discord.ButtonStyle.red, emoji='<:Youtube:1346945481380462784>')
    async def youtube(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._show(interaction, "youtube")
# cogs/social.py – PART 3 of 3

    async def _show(self, interaction: discord.Interaction, platform: str):
        embed = discord.Embed(
            title=f"{platform.capitalize()} Issues",
            description="Which service had an issue?",
            color=discord.Color.from_rgb(12, 0, 182)
        )
        await interaction.response.send_message(embed=embed, view=CompensationServiceView(self.bot, platform), ephemeral=True)


class CompensationServiceView(discord.ui.View):
    def __init__(self, bot, platform: str):
        super().__init__(timeout=None)
        self.bot = bot
        self.platform = platform

        for svc in SERVICES.get(platform, {}):
            btn = discord.ui.Button(label=svc.title(), style=discord.ButtonStyle.blurple)
            async def cb(i, s=svc):
                await self.handle(i, s)
            btn.callback = cb
            self.add_item(btn)

    async def handle(self, interaction: discord.Interaction, service: str):
        gid = str(interaction.guild.id)
        api_key = self.bot.social_config[gid]['api_key']
        uid = str(interaction.user.id)
        orders = self.bot.invites['orders'].get(uid, [])
        relevant = [o for o in orders if o['platform'] == self.platform and o['service'] == service]
        if not relevant:
            return await interaction.response.send_message("No recent orders.", ephemeral=True)

        oids = [o['order_id'] for o in relevant]
        status = get_bulkmedya_status(oids, api_key)
        if not isinstance(status, dict) or not any(k.isdigit() for k in status):
            status = {"_single": status}

        refunded = 0
        to_refund = []
        for o in relevant:
            info = status.get(o['order_id']) or status.get("_single")
            if info and info.get("status", "").lower() == "canceled" and info.get("charge", "") == "0.00" and not o['refunded']:
                refunded += o['invites_spent']
                o['refunded'] = True
                to_refund.append(o['order_id'])

        if refunded:
            inv = self.bot.invites['inviters'].setdefault(uid, {'regular':0,'fake':0,'bonus':0})
            inv['regular'] += refunded
            await self.bot.save_invites()
            await interaction.response.send_message(f"💸 Refunded {refunded} invites.", ephemeral=True)
            lc = self.bot.get_channel(LOG_CHANNEL_ID)
            if lc:
                await lc.send(f"Refunded {refunded} invites for {interaction.user.mention} (orders: {', '.join(to_refund)})")
            return

        # No refunds -> show latest status
        relevant.sort(key=lambda x: x['timestamp'], reverse=True)
        latest = relevant[0]
        info = status.get(latest['order_id']) or status.get("_single")
        if not info:
            return await interaction.response.send_message("No refundable orders found.", ephemeral=True)

        st = info.get("status", "").lower()
        if st == "partial":
            st = "completed"

        msg_map = {
            "pending": "Still pending—please wait.",
            "in progress": "Still in progress—please wait.",
            "completed": "Already completed!"
        }
        await interaction.response.send_message(msg_map.get(st, "No refundable orders found."), ephemeral=True)


class SocialRefill(commands.Cog):
    """Handles /refill to top up completed orders."""
    def __init__(self, bot):
        self.bot = bot
        if 'orders' not in bot.invites:
            bot.invites['orders'] = {}
        if not hasattr(bot, 'refill_cooldowns'):
            bot.refill_cooldowns = {}

    @app_commands.command(name="refill", description="Refill your dropped boosts")
    async def refill(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="Refill your Boosts",
            description=(
                "Lost any Followers, Likes, Views?\n"
                "**Select your platform to refill!**"
            ),
            color=discord.Color.from_rgb(12, 0, 182)
        )
        await interaction.response.send_message(embed=embed, view=RefillPlatformView(self.bot), ephemeral=False)


class RefillPlatformView(discord.ui.View):
    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot

    @discord.ui.button(label="TikTok", style=discord.ButtonStyle.red, emoji='<:tiktok:1346944982048702517>')
    async def tiktok(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = discord.Embed(
            title="TikTok Refill",
            description="Followers(30d), Shares(30d), Likes(7d)",
            color=discord.Color.from_rgb(12, 0, 182)
        )
        view = RefillServiceView(self.bot, "tiktok", interaction.user)
        view.add_item(RefillServiceButton(self.bot, "tiktok", "followers", 30, interaction.user))
        view.add_item(RefillServiceButton(self.bot, "tiktok", "shares", 30, interaction.user))
        view.add_item(RefillServiceButton(self.bot, "tiktok", "likes", 7, interaction.user))
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @discord.ui.button(label="YouTube", style=discord.ButtonStyle.red, emoji='<:Youtube:1346945481380462784>')
    async def youtube(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = discord.Embed(
            title="YouTube Refill",
            description="Subscribers & Likes (30d)",
            color=discord.Color.from_rgb(12, 0, 182)
        )
        view = RefillServiceView(self.bot, "youtube", interaction.user)
        view.add_item(RefillServiceButton(self.bot, "youtube", "subscribers", 30, interaction.user))
        view.add_item(RefillServiceButton(self.bot, "youtube", "likes", 30, interaction.user))
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @discord.ui.button(label="Instagram", style=discord.ButtonStyle.green, emoji='<:Instagram:1346945332084215848>')
    async def instagram(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = discord.Embed(
            title="Instagram Refill",
            description="Followers (30d)",
            color=discord.Color.from_rgb(12, 0, 182)
        )
        view = RefillServiceView(self.bot, "instagram", interaction.user)
        view.add_item(RefillServiceButton(self.bot, "instagram", "followers", 30, interaction.user))
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @discord.ui.button(label="Twitch", style=discord.ButtonStyle.green, emoji='<:twitch:1346945975004168244>')
    async def twitch(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = discord.Embed(
            title="Twitch Refill",
            description="Clip Views (30d)",
            color=discord.Color.from_rgb(12, 0, 182)
        )
        view = RefillServiceView(self.bot, "twitch", interaction.user)
        view.add_item(RefillServiceButton(self.bot, "twitch", "clip views", 30, interaction.user))
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


class RefillServiceView(discord.ui.View):
    def __init__(self, bot, platform: str, user: discord.User):
        super().__init__(timeout=None)
        self.bot = bot
        self.platform = platform
        self.user = user


class RefillServiceButton(discord.ui.Button):
    def __init__(self, bot, platform: str, service: str, days: int, user: discord.User):
        super().__init__(style=discord.ButtonStyle.blurple, label=service.title())
        self.bot = bot
        self.platform = platform
        self.service = service
        self.days = days
        self.user = user

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.user.id:
            return await interaction.response.send_message("This menu isn’t for you.", ephemeral=True)
        gid = str(interaction.guild.id)
        api_key = self.bot.social_config[gid]['api_key']
        now = datetime.datetime.utcnow()
        cutoff = now - datetime.timedelta(days=self.days)
        orders = self.bot.invites['orders'].get(str(self.user.id), [])
        eligible = [
            o['order_id'] for o in orders
            if o['platform'] == self.platform
               and o['service'] == self.service
               and datetime.datetime.fromisoformat(o['timestamp']) >= cutoff
        ]
        if not eligible:
            return await interaction.response.send_message("No recent orders to refill.", ephemeral=True)
        status = get_bulkmedya_status(eligible, api_key)
        if len(eligible) == 1 and not any(k.isdigit() for k in status):
            status = {"_single": status}
        to_refill, cd_skipped, inc_skipped = [], False, False
        for oid in eligible:
            info = status.get(oid) or status.get("_single")
            if not info:
                continue
            st = info.get("status", "").lower()
            if st == "partial":
                st = "completed"
            if st != "completed":
                inc_skipped = True
                continue
            last = self.bot.refill_cooldowns.get(oid)
            if last and (now - last).total_seconds() < 86400:
                cd_skipped = True
                continue
            to_refill.append(oid)
        if not to_refill:
            if cd_skipped:
                return await interaction.response.send_message("Refilled recently—cooldown.", ephemeral=True)
            if inc_skipped:
                return await interaction.response.send_message("Order not completed yet.", ephemeral=True)
            return await interaction.response.send_message("Nothing to refill.", ephemeral=True)
        results = request_bulkmedya_refill(to_refill, api_key)
        if not results:
            return await interaction.response.send_message("Error—try again later.", ephemeral=True)
        any_success = False
        for r in results:
            oid = str(r.get("order", to_refill[0]))
            if r.get("refill"):
                any_success = True
                self.bot.refill_cooldowns[oid] = now
        if not any_success:
            return await interaction.response.send_message("Error—try again later.", ephemeral=True)
        await interaction.response.send_message("Successfully requested refill! Up to 24–48h.", ephemeral=True)
        lc = self.bot.get_channel(LOG_CHANNEL_ID)
        if lc:
            await lc.send(f"Refill requested for {self.platform}/{self.service}: {', '.join(to_refill)}")


async def setup(bot: commands.Bot):
    # ensure social_config load/save exist
    if not hasattr(bot, 'social_config'):
        bot.social_config = {}
    if not hasattr(bot, 'save_social_config'):
        async def _ss():
            with open('social_config.json', 'w') as f:
                json.dump(bot.social_config, f, indent=2)
        bot.save_social_config = _ss
    if os.path.isfile('social_config.json'):
        with open('social_config.json') as f:
            bot.social_config = json.load(f)
    await bot.add_cog(SocialBooster(bot))
    await bot.add_cog(SocialCompensation(bot))
    await bot.add_cog(SocialRefill(bot))
