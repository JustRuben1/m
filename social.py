import discord
from discord.ext import commands
from discord import app_commands
import requests
import datetime
import re

from config import (
    SERVICES,
    BULKMEDYA_API_KEY,
    BULKMEDYA_API_URL,
    LOG_CHANNEL_ID
)

######################################################################
# Helper Functions
######################################################################

def validate_link(platform: str, service_type: str, link: str) -> bool:
    """Return True if the link contains the platform's name."""
    link_lower = link.lower()

    if platform == 'tiktok':
        return "tiktok" in link_lower

    elif platform == 'youtube':
        # Allow both youtube.com and youtu.be
        return "youtube" in link_lower or "youtu.be" in link_lower

    elif platform == 'instagram':
        return "instagram" in link_lower

    elif platform == 'twitch':
        return "twitch" in link_lower

    elif platform == 'twitter':
        return "twitter" in link_lower

    # Fallback: if platform not recognized, consider it invalid
    return False


def create_bulkmedya_order(service_id: int, link: str, quantity: int) -> dict:
    """Create an order on BulkMedya (action=add). Returns response as dict or raises an exception."""
    payload = {
        'key': BULKMEDYA_API_KEY,
        'action': 'add',
        'service': service_id,
        'link': link,
        'quantity': quantity
    }
    try:
        resp = requests.post(BULKMEDYA_API_URL, data=payload, timeout=10)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        raise RuntimeError(f"BulkMedya order creation failed: {e}")


def get_bulkmedya_status(order_ids: list) -> dict:
    """
    Fetch status info for one or more BulkMedya orders.
    If single ID, use 'order'; if multiple, use 'orders' with comma separation.
    Returns a dict: { '123': {...}, '456': {...} } or a single dict.
    """
    if not order_ids:
        return {}
    if len(order_ids) == 1:
        payload = {
            'key': BULKMEDYA_API_KEY,
            'action': 'status',
            'order': order_ids[0]
        }
    else:
        payload = {
            'key': BULKMEDYA_API_KEY,
            'action': 'status',
            'orders': ",".join(order_ids)
        }
    try:
        resp = requests.post(BULKMEDYA_API_URL, data=payload, timeout=10)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print(f"Error fetching BulkMedya status: {e}")
        return {}


def request_bulkmedya_refill(order_ids: list) -> list:
    """
    Create a refill request on BulkMedya for one or multiple orders.
    Returns a list of dicts. For single order, adapt the response to a list.
    """
    if not order_ids:
        return []
    if len(order_ids) == 1:
        payload = {
            'key': BULKMEDYA_API_KEY,
            'action': 'refill',
            'order': order_ids[0]
        }
    else:
        payload = {
            'key': BULKMEDYA_API_KEY,
            'action': 'refill',
            'orders': ",".join(order_ids)
        }
    try:
        resp = requests.post(BULKMEDYA_API_URL, data=payload, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        # unify single order result
        if len(order_ids) == 1 and isinstance(data, dict):
            # example: {"refill":"1"} => becomes [{"order": <id>, "refill":"1"}]
            return [{"order": order_ids[0], "refill": data.get("refill")}]
        return data if isinstance(data, list) else []
    except Exception as e:
        print(f"Error requesting refill: {e}")
        return []


######################################################################
# The main SocialBooster Cog for /social
######################################################################
class SocialBooster(commands.Cog):
    """Handles /social command for placing new orders using invites."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Ensure self.bot.invites['orders'] exists for storing order data
        if 'orders' not in self.bot.invites:
            self.bot.invites['orders'] = {}

    @app_commands.command(name="social", description="Boost your social media accounts")
    async def social(self, interaction: discord.Interaction):
        """
        Sends an embed with platform buttons (TikTok, YouTube, etc.).
        The user picks a platform, picks a service, and places an order.
        Currently ephemeral=False => public, if you want ephemeral, set ephemeral=True.
        """
        embed = discord.Embed(
            title="Social Media Rewards",
            description=(
                "Boost your social media accounts for __FREE__ by inviting people!\n\n"
                "Choose your favorite Platform!\n\n"
                "**Boost your accounts with Followers, Likes and Views!**"
            ),
            color=discord.Color.from_rgb(12, 0, 182)
        ).set_image(url="https://i.imgur.com/JTZc7nE.jpeg")

        await interaction.response.send_message(
            embed=embed,
            view=SocialPlatformView(self.bot),
            ephemeral=False
        )


class SocialPlatformView(discord.ui.View):
    """Buttons to select a platform (TikTok, YouTube, etc.) in /social embed."""

    def __init__(self, bot: commands.Bot):
        super().__init__(timeout=None)
        self.bot = bot

    @discord.ui.button(label="TikTok", style=discord.ButtonStyle.red, emoji='<:tiktok:1346944982048702517>')
    async def tiktok(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._send_platform_services(interaction, "tiktok")

    @discord.ui.button(label="YouTube", style=discord.ButtonStyle.red, emoji='<:Youtube:1346945481380462784>')
    async def youtube(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._send_platform_services(interaction, "youtube")

    @discord.ui.button(label="Instagram", style=discord.ButtonStyle.green, emoji='<:Instagram:1346945332084215848>')
    async def instagram(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._send_platform_services(interaction, "instagram")

    @discord.ui.button(label="Twitch", style=discord.ButtonStyle.green, emoji='<:twitch:1346945975004168244>')
    async def twitch(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._send_platform_services(interaction, "twitch")

    @discord.ui.button(label="Twitter", style=discord.ButtonStyle.blurple, emoji='<:Twitter:1346946116255485982>')
    async def twitter(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._send_platform_services(interaction, "twitter")

    async def _send_platform_services(self, interaction: discord.Interaction, platform: str):
        # Description for each platform
        desc_map = {
            'tiktok': (
                "Boost your TikTok Account with Followers, Views, Likes and Shares for __FREE!__\n\n"
                "10,000 Views = 1 invite\n"
                "100 Likes = 1 invite\n"
                "200 Shares = 1 invite\n"
                "25 Followers = 1 invite\n\n"
                "The minimum quantity for followers is 100."
            ),
            'instagram': (
                "Boost your Instagram Account with Followers, Views, Likes and Shares for __FREE!__\n\n"
                "10,000 Story Views (All Stories) = 1 invite\n"
                "1000 Views (Reel/TV) = 1 invite\n"
                "250 Likes = 1 invite\n"
                "750 Shares = 1 invite\n"
                "25 Followers = 1 invite\n\n"
                "The minimum quantity for followers is 100."
            ),
            'youtube': (
                "Boost your YouTube Account with Subscribers, Likes, Views and Short Likes for __FREE!__\n\n"
                "125 Views = 1 invite\n"
                "100 Likes = 1 invite\n"
                "20 Subscribers = 1 invite\n"
                "50 Short Likes = 1 invite\n\n"
                "The minimum quantity for subscribers is 100.\n"
                "The minimum quantity for views is 500."
            ),
            'twitch': (
                "Boost your Twitch Account with Followers, Clip Views and Livestream Viewers for __FREE!__\n\n"
                "25 Livestream Viewers (30m) = 1 invite\n"
                "300 Clip Views = 1 invite\n"
                "200 Followers = 1 invite"
            ),
            'twitter': (
                "Boost your Twitter Account with Followers, Likes, Retweets and Tweet Views for __FREE!__\n\n"
                "10,000 Tweet Views = 1 invite\n"
                "250 Likes = 1 invite\n"
                "250 Retweets = 1 invite\n"
                "100 Followers = 1 invite"
            )
        }
        embed = discord.Embed(
            title=f"{platform.capitalize()} Boost",
            description=desc_map.get(platform, "No details provided."),
            color=discord.Color.from_rgb(12, 0, 182)
        )
        await interaction.response.send_message(
            embed=embed,
            view=SocialServiceView(self.bot, platform),
            ephemeral=True  # ephemeral so only the clicking user sees the services
        )


class SocialServiceView(discord.ui.View):
    """Lists the available services (from config.SERVICES) for a chosen platform as buttons."""

    def __init__(self, bot: commands.Bot, platform: str):
        super().__init__(timeout=None)
        self.bot = bot
        self.platform = platform

        if platform not in SERVICES:
            return

        for svc_name in SERVICES[platform].keys():
            label = {
                'story views': 'Story Views',
                'tweet views': 'Tweet Views',
                'retweet': 'Retweets',
                'shares': 'Shares',
                'short likes': 'Short Likes'
            }.get(svc_name, svc_name.title())

            btn = discord.ui.Button(label=label, style=discord.ButtonStyle.blurple)
            async def button_callback(interaction: discord.Interaction, s=svc_name):
                await interaction.response.send_modal(OrderCreationModal(self.bot, self.platform, s))
            btn.callback = button_callback
            self.add_item(btn)


class OrderCreationModal(discord.ui.Modal):
    """Collects the invites to spend and the link to place an order on BulkMedya."""

    def __init__(self, bot: commands.Bot, platform: str, service_type: str):
        super().__init__(title=f"{platform.capitalize()} {service_type.title()}")
        self.bot = bot
        self.platform = platform
        self.service_type = service_type
        self.svc_data = SERVICES[platform][service_type]

        self.invites_input = discord.ui.TextInput(
            label="Invites to spend",
            placeholder=f"Min {self.svc_data['min_invites']} invites"
        )
        self.link_input = discord.ui.TextInput(
            label="Link",
            placeholder=f"https://{platform}.com/..."
        )

        self.add_item(self.invites_input)
        self.add_item(self.link_input)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            invites_spent = int(self.invites_input.value)
        except ValueError:
            return await interaction.followup.send("❌ Invalid number format.", ephemeral=True)

        if invites_spent < self.svc_data['min_invites']:
            return await interaction.followup.send(
                f"❌ You must spend at least {self.svc_data['min_invites']} invites.", ephemeral=True
            )

        link = self.link_input.value.strip()
        if not validate_link(self.platform, self.service_type, link):
            return await interaction.followup.send(
                f"❌ Invalid link for {self.platform.capitalize()} {self.service_type.title()}.",
                ephemeral=True
            )

        # Check user has enough invites
        user_data = self.bot.invites['inviters'].get(str(interaction.user.id), {'regular': 0, 'fake': 0, 'bonus': 0})
        total_inv = user_data['regular'] - user_data['fake'] + user_data['bonus']
        if total_inv < invites_spent:
            return await interaction.followup.send("❌ You do not have enough invites.", ephemeral=True)

        # Deduct from bonus first
        user_data['bonus'] -= invites_spent
        await self.bot.save_invites()

        # Place BulkMedya order
        quantity = invites_spent * self.svc_data['per_invite']
        service_id = self.svc_data['service_id']
        try:
            resp = create_bulkmedya_order(service_id, link, quantity)
            # BulkMedya returns e.g. {"order": 12345} for success
            order_id = str(resp.get("order", "N/A"))  # store internally, even if user sees no ID
        except Exception as e:
            return await interaction.followup.send(f"❌ Order failed: {e}", ephemeral=True)

        # Log
        if LOG_CHANNEL_ID:
            log_ch = self.bot.get_channel(LOG_CHANNEL_ID)
            if log_ch:
                log_msg = (
                    f"🚀 **Boost Order**\n"
                    f"• User: {interaction.user.mention}\n"
                    f"• Service: {self.platform.capitalize()} {self.service_type.title()}\n"
                    f"• Service ID: {service_id}\n"
                    f"• Quantity: {quantity}\n"
                    f"• Invites Spent: {invites_spent}\n"
                    f"• Remaining: {total_inv - invites_spent}\n"
                    f"• Order ID: {order_id}"
                )
                await log_ch.send(log_msg)

        # Store order in self.bot.invites['orders']
        user_orders = self.bot.invites['orders'].setdefault(str(interaction.user.id), [])
        record = {
            'order_id': order_id,
            'platform': self.platform,
            'service': self.service_type,
            'invites_spent': invites_spent,
            'refunded': False,
            'timestamp': datetime.datetime.utcnow().isoformat()
        }
        user_orders.append(record)

        # Show success
        await interaction.followup.send(
            "✅ Order placed!\nPlease be patient, your order may take up to 48h.",
            ephemeral=True
        )


######################################################################
# /compensation Command (like old /issues) - Large public embed + ephemeral button flows
######################################################################
class SocialCompensation(commands.Cog):
    """
    The /compensation command: posts a public embed with platform buttons.
    When a user clicks a platform, it shows ephemeral service buttons. We check:
      - If no orders => "No recent orders found for this service."
      - If canceled => refund them
      - Else => show the status of the LATEST relevant order
        * "Your order is still pending, please be patient!"
        * "Your order is still in progress, please be patient!"
        * "Your order has already been completed!"
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        if 'orders' not in self.bot.invites:
            self.bot.invites['orders'] = {}
        if not hasattr(self.bot, 'refunded_orders'):
            self.bot.refunded_orders = set()

    @app_commands.command(name="compensation", description="Request compensation for canceled orders.")
    async def compensation(self, interaction: discord.Interaction):
        """
        Posts one big embed in public with platform buttons.
        Button clicks are ephemeral, letting each user handle their own orders.
        """
        embed = discord.Embed(
            title="Social Boost Issues / Compensation",
            description=(
                "Didn’t receive what you claimed?\n"
                "Or accidentally entered the wrong link?\n\n"
                "**Get your invites back by selecting where you ran into issues!**"
            ),
            color=discord.Color.from_rgb(12, 0, 182)
        )
        await interaction.response.send_message(embed=embed, view=CompensationPlatformView(self.bot), ephemeral=False)


class CompensationPlatformView(discord.ui.View):
    """Public platform selection for /compensation. Button interactions are ephemeral."""
    def __init__(self, bot: commands.Bot):
        super().__init__(timeout=None)
        self.bot = bot

    @discord.ui.button(label="TikTok", style=discord.ButtonStyle.red, emoji='<:tiktok:1346944982048702517>')
    async def tiktok(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            embed=discord.Embed(
                title="TikTok Issues",
                description="Select which service you had an issue with.",
                color=discord.Color.from_rgb(12, 0, 182)
            ),
            view=CompensationServiceView(self.bot, "tiktok"),
            ephemeral=True
        )

    @discord.ui.button(label="YouTube", style=discord.ButtonStyle.red, emoji='<:Youtube:1346945481380462784>')
    async def youtube(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            embed=discord.Embed(
                title="YouTube Issues",
                description="Select which service you had an issue with.",
                color=discord.Color.from_rgb(12, 0, 182)
            ),
            view=CompensationServiceView(self.bot, "youtube"),
            ephemeral=True
        )

    @discord.ui.button(label="Instagram", style=discord.ButtonStyle.green, emoji='<:Instagram:1346945332084215848>')
    async def instagram(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            embed=discord.Embed(
                title="Instagram Issues",
                description="Select which service you had an issue with.",
                color=discord.Color.from_rgb(12, 0, 182)
            ),
            view=CompensationServiceView(self.bot, "instagram"),
            ephemeral=True
        )

    @discord.ui.button(label="Twitch", style=discord.ButtonStyle.green, emoji='<:twitch:1346945975004168244>')
    async def twitch(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            embed=discord.Embed(
                title="Twitch Issues",
                description="Select which service you had an issue with.",
                color=discord.Color.from_rgb(12, 0, 182)
            ),
            view=CompensationServiceView(self.bot, "twitch"),
            ephemeral=True
        )

    @discord.ui.button(label="Twitter", style=discord.ButtonStyle.blurple, emoji='<:Twitter:1346946116255485982>')
    async def twitter(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            embed=discord.Embed(
                title="Twitter Issues",
                description="Select which service you had an issue with.",
                color=discord.Color.from_rgb(12, 0, 182)
            ),
            view=CompensationServiceView(self.bot, "twitter"),
            ephemeral=True
        )


class CompensationServiceView(discord.ui.View):
    """Services for a chosen platform under /compensation. Button interactions ephemeral."""
    def __init__(self, bot: commands.Bot, platform: str):
        super().__init__(timeout=None)
        self.bot = bot
        self.platform = platform

        if platform not in SERVICES:
            return
        for svc_name in SERVICES[platform].keys():
            label = {
                'story views': 'Story Views',
                'tweet views': 'Tweet Views',
                'retweet': 'Retweets',
                'shares': 'Shares',
                'short likes': 'Short Likes'
            }.get(svc_name, svc_name.title())

            btn = discord.ui.Button(label=label, style=discord.ButtonStyle.blurple)
            async def service_callback(interaction: discord.Interaction, s=svc_name):
                await self.handle_compensation(interaction, s)
            btn.callback = service_callback
            self.add_item(btn)

    async def handle_compensation(self, interaction: discord.Interaction, service_type: str):
        """Check all orders for the user for (platform, service_type). If canceled => refund, else show status."""
        user_id_str = str(interaction.user.id)
        user_orders = self.bot.invites['orders'].get(user_id_str, [])

        # Filter orders
        relevant_orders = [o for o in user_orders if o['platform'] == self.platform and o['service'] == service_type]
        if not relevant_orders:
            # No recent orders
            return await interaction.response.send_message(
                "No recent orders found for this service.",
                ephemeral=True
            )

        # Gather all order IDs
        order_ids = [o['order_id'] for o in relevant_orders]
        status_data = get_bulkmedya_status(order_ids)

        # handle single vs multi
        if isinstance(status_data, dict) and any(k.isdigit() for k in status_data.keys()):
            pass
        else:
            # possibly single with no digit key
            status_data = {"_single": status_data}

        canceled_invites = 0
        canceled_list = []
        # track if we found any canceled
        found_canceled = False

        for rec in relevant_orders:
            oid = rec['order_id']
            info = status_data.get(oid)
            if not info and "_single" in status_data and len(order_ids) == 1:
                info = status_data["_single"]
            if not info:
                continue

            status = info.get("status", "Completed")
            if status.lower() == "partial":
                status = "Completed"  # treat partial as completed
            charge = info.get("charge", "Unknown")

            if status.lower() == "canceled" and charge == "0.00" and not rec['refunded']:
                canceled_invites += rec['invites_spent']
                canceled_list.append(oid)
                rec['refunded'] = True
                found_canceled = True

        # If any canceled => refund them
        if found_canceled and canceled_invites > 0:
            user_data = self.bot.invites['inviters'].get(user_id_str, {'regular': 0, 'fake': 0, 'bonus': 0})
            user_data['regular'] += canceled_invites
            await self.bot.save_invites()
            msg = f"<a:red:1330880623161769994> **- {canceled_invites} Invite(s) Refunded!**"
            await interaction.response.send_message(msg, ephemeral=True)

            # Log refund
            log_ch = self.bot.get_channel(1354191374269813011)
            if log_ch:
                log_msg = (
                    f"💸 **Refund Processed**\n"
                    f"• User: {interaction.user.mention}\n"
                    f"• Service: {self.platform.capitalize()} {service_type.title()}\n"
                    f"• Refunded Invites: {canceled_invites}\n"
                    f"• Order IDs: {', '.join(canceled_list)}"
                )
                await log_ch.send(log_msg)
            return

        # Otherwise, show the status of the LATEST relevant order
        # sort by timestamp descending
        relevant_orders.sort(key=lambda x: x['timestamp'], reverse=True)
        latest_order = relevant_orders[0]
        oid = latest_order['order_id']
        info = status_data.get(oid)
        if not info and "_single" in status_data and len(order_ids) == 1:
            info = status_data["_single"]
        if not info:
            # no data found
            return await interaction.response.send_message(
                "No orders found that are canceled (charge=0.00) or they have already been refunded.",
                ephemeral=True
            )

        st = info.get("status", "Completed").lower()
        if st == "partial":
            st = "completed"
        # Show user a status message
        if st == "pending":
            msg = "Your order is still pending, please be patient!"
        elif st == "in progress":
            msg = "Your order is still in progress, please be patient!"
        elif st == "completed":
            msg = "Your order has already been completed!"
        else:
            # fallback
            msg = "No orders found that are canceled (charge=0.00) or they have already been refunded."

        await interaction.response.send_message(msg, ephemeral=True)


######################################################################
# /refill Command - One big embed visible to everyone, ephemeral button interactions
######################################################################
class SocialRefill(commands.Cog):
    """Handles /refill command with platform -> service refill logic."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        if 'orders' not in self.bot.invites:
            self.bot.invites['orders'] = {}
        # track last refill time to enforce 1-day cooldown
        if not hasattr(self.bot, 'refill_cooldowns'):
            self.bot.refill_cooldowns = {}

    @app_commands.command(name="refill", description="Refill your dropped followers, likes, etc. if the service supports it.")
    async def refill(self, interaction: discord.Interaction):
        """Posts a public embed with platform buttons. Clicking them is ephemeral to the user."""
        embed = discord.Embed(
            title="Refill your Boosts",
            description=(
                "Lost any of your Followers, Likes, Views or something else since you ordered?\n\n"
                "**Some** Services have a refill option, where you can get compensated for what you lost."
            ),
            color=discord.Color.from_rgb(12, 0, 182)
        )
        await interaction.response.send_message(embed=embed, view=RefillPlatformView(self.bot), ephemeral=False)


class RefillPlatformView(discord.ui.View):
    """Public platform selection for /refill. Button interactions ephemeral."""
    def __init__(self, bot: commands.Bot):
        super().__init__(timeout=None)
        self.bot = bot

    @discord.ui.button(label="TikTok", style=discord.ButtonStyle.red, emoji='<:tiktok:1346944982048702517>')
    async def tiktok(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = discord.Embed(
            title="Tiktok Refill",
            description=(
                "Refill your Tiktok Followers, Likes or Shares **automatically.**\n\n"
                "Followers - 30 days Refill\n"
                "Shares - 30 days Refill\n"
                "Likes - 7 days Refill"
            ),
            color=discord.Color.from_rgb(12, 0, 182)
        )
        view = RefillServiceView(self.bot, "tiktok", interaction.user)
        # Tiktok: followers(30d), likes(7d), shares(30d)
        view.add_item(RefillServiceButton(self.bot, "tiktok", "followers", 30, interaction.user))
        view.add_item(RefillServiceButton(self.bot, "tiktok", "likes", 7, interaction.user))
        view.add_item(RefillServiceButton(self.bot, "tiktok", "shares", 30, interaction.user))
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @discord.ui.button(label="YouTube", style=discord.ButtonStyle.red, emoji='<:Youtube:1346945481380462784>')
    async def youtube(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = discord.Embed(
            title="YouTube Refill",
            description=(
                "Refill your Youtube Subscribers or Likes **automatically.**\n\n"
                "Subscribers - 30 days Refill\n"
                "Likes - 30 days Refill"
            ),
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
            description=(
                "Refill your Instagram Followers **automatically.**\n\n"
                "Followers - 30 days Refill"
            ),
            color=discord.Color.from_rgb(12, 0, 182)
        )
        view = RefillServiceView(self.bot, "instagram", interaction.user)
        view.add_item(RefillServiceButton(self.bot, "instagram", "followers", 30, interaction.user))
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @discord.ui.button(label="Twitch", style=discord.ButtonStyle.green, emoji='<:twitch:1346945975004168244>')
    async def twitch(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = discord.Embed(
            title="Twitch Refill",
            description=(
                "Refill your Twitch Clip Views **automatically.**\n\n"
                "Clip Views - 30 days Refill"
            ),
            color=discord.Color.from_rgb(12, 0, 182)
        )
        view = RefillServiceView(self.bot, "twitch", interaction.user)
        view.add_item(RefillServiceButton(self.bot, "twitch", "clip views", 30, interaction.user))
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


class RefillServiceView(discord.ui.View):
    """Just holds the actual service buttons. The user is enforced for ephemeral usage."""
    def __init__(self, bot: commands.Bot, platform: str, user: discord.User):
        super().__init__(timeout=None)
        self.bot = bot
        self.platform = platform
        self.user = user


class RefillServiceButton(discord.ui.Button):
    """
    Button that triggers a BulkMedya refill for all user's orders (within time window) if not on 1-day cooldown,
    if the order is 'Completed' in BulkMedya (Partial => also considered completed).
    """

    def __init__(self, bot: commands.Bot, platform: str, service: str, refill_days: int, user: discord.User):
        super().__init__(style=discord.ButtonStyle.blurple, label=service.title())
        self.bot = bot
        self.platform = platform
        self.service = service
        self.refill_days = refill_days
        self.user = user

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.user.id:
            return await interaction.response.send_message("This refill menu is not for you.", ephemeral=True)

        user_id_str = str(self.user.id)
        all_orders = self.bot.invites['orders'].get(user_id_str, [])
        now = datetime.datetime.utcnow()
        cutoff = now - datetime.timedelta(days=self.refill_days)

        if not hasattr(self.bot, 'refill_cooldowns'):
            self.bot.refill_cooldowns = {}

        # Filter for orders of this platform & service, within refill_days
        matching_orders = []
        for rec in all_orders:
            if rec['platform'] == self.platform and rec['service'] == self.service:
                order_time = datetime.datetime.fromisoformat(rec['timestamp'])
                if order_time >= cutoff:
                    matching_orders.append(rec['order_id'])

        if not matching_orders:
            # No recent orders for that service
            return await interaction.response.send_message("No recent orders found for this service.", ephemeral=True)

        # Check statuses for each
        status_data = get_bulkmedya_status(matching_orders)
        if len(matching_orders) == 1 and not any(k.isdigit() for k in status_data.keys()):
            # single response might be direct
            status_data = {"_single": status_data}

        to_refill = []
        cooldown_skipped = False
        incomplete_skipped = False

        for oid in matching_orders:
            info = status_data.get(oid)
            if not info and "_single" in status_data and len(matching_orders) == 1:
                info = status_data["_single"]
            if not info:
                continue

            st = info.get("status", "Completed").lower()
            if st == "partial":
                st = "completed"

            # Check if order is completed
            if st != "completed":
                # not completed => skip
                incomplete_skipped = True
                continue

            # check cooldown
            last_refill = self.bot.refill_cooldowns.get(oid)
            if last_refill and (now - last_refill).total_seconds() < 86400:
                cooldown_skipped = True
                continue

            to_refill.append(oid)

        if not to_refill:
            # If none are available, check reason
            if cooldown_skipped:
                return await interaction.response.send_message(
                    "Already recently refilled this service, you are still on cooldown.",
                    ephemeral=True
                )
            elif incomplete_skipped:
                return await interaction.response.send_message(
                    "Unable to refill order, your order has not been completed yet.",
                    ephemeral=True
                )
            else:
                # fallback => "No recent orders found for this service."
                return await interaction.response.send_message(
                    "No recent orders found for this service.",
                    ephemeral=True
                )

        # Attempt refill
        results = request_bulkmedya_refill(to_refill)
        if not results:
            # No response or error from API
            return await interaction.response.send_message("Error Occured - Please try again.", ephemeral=True)

        success_any = False
        fail_any = False
        for r in results:
            oid = str(r.get("order")) if "order" in r else to_refill[0]
            refill_val = r.get("refill")
            if refill_val and not isinstance(refill_val, dict):
                # success
                success_any = True
                self.bot.refill_cooldowns[oid] = now
            else:
                fail_any = True

        if not success_any:
            # all failed
            return await interaction.response.send_message("Error Occured - Please try again.", ephemeral=True)

        # At least one success => show success
        await interaction.response.send_message(
            "Successfully refilled. Your order will be refilled in up to 24-48h.",
            ephemeral=True
        )

        # Log
        log_channel = self.bot.get_channel(1354230490638319717)
        if log_channel:
            desc_lines = []
            if success_any:
                desc_lines.append(f"Refilled {self.platform.capitalize()} {self.service.title()} for: {', '.join(to_refill)}.")
            if fail_any:
                desc_lines.append("Some orders encountered an error in refill.")
            summary = "\n".join(desc_lines)
            log_embed = discord.Embed(
                title="Refill Action",
                description=f"User: {self.user.mention}\n{summary}",
                color=discord.Color.blue()
            )
            await log_channel.send(embed=log_embed)


######################################################################
# The actual setup function that the bot.load_extension() will call
######################################################################
async def setup(bot: commands.Bot):
    await bot.add_cog(SocialBooster(bot))
    await bot.add_cog(SocialCompensation(bot))
    await bot.add_cog(SocialRefill(bot))
