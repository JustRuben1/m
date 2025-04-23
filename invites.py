import discord
from discord.ext import commands, tasks
from config import *
import json
import datetime
import asyncio
import time
import random

class InviteTracking(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.invite_cleanup.start()
        self.invite_lock = asyncio.Lock()
        self.last_invites = {}

    async def fetch_invites(self, guild):
        """Fetch invites with retry logic"""
        for _ in range(3):
            try:
                return await guild.invites()
            except (discord.HTTPException, discord.NotFound):
                await asyncio.sleep(2)
        return None

    @commands.Cog.listener()
    async def on_ready(self):
        """Initialize last_invites on startup"""
        guild = self.bot.get_guild(MAIN_GUILD_ID)
        if guild:
            invites = await self.fetch_invites(guild)
            if invites:
                self.last_invites = {str(inv.id): inv.uses for inv in invites}

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        if member.guild.id != MAIN_GUILD_ID:
            return

        async with self.invite_lock:
            try:
                await asyncio.sleep(2)  # Allow Discord to update counts
                guild = member.guild

                # Check for rejoin
                member_data = self.bot.invites['members'].get(str(member.id))
                if member_data and member_data.get('left_at'):
                    inviter = guild.get_member(int(member_data['inviter'])) if member_data['inviter'] else None
                    if inviter:
                        await self.send_message(
                            f"<:sparkle:1330881429961179187> **{member.name}** rejoined.\n"
                            f"<:member:1330882686956339200> **{inviter.name}** did **__not__** get a **new invite**!"
                        )
                    return

                # Get current invites
                current_invites = await self.fetch_invites(guild)
                if not current_invites:
                    print(f"⚠️ Failed to fetch invites for {member}")
                    return

                # Find used invite by comparing with last known state
                diffs = {}
                for inv in current_invites:
                    old_uses = self.last_invites.get(str(inv.id), 0)
                    diffs[inv] = inv.uses - old_uses
                # Determine which invite increased the most
                used_invite = max(diffs, key=diffs.get)
                if diffs[used_invite] <= 0 or not used_invite.inviter:
                    print(f"🔍 No valid invite found for {member}")
                    # Update cache even if none found to avoid stale data
                    self.last_invites = {str(inv.id): inv.uses for inv in current_invites}
                    return

                # Update invite tracking before proceeding
                self.last_invites = {str(inv.id): inv.uses for inv in current_invites}

                inviter = used_invite.inviter

                # Validate invite
                if inviter.id == member.id or inviter.bot:
                    await self.send_message(
                        f"<:member:1330882686956339200> **{inviter.name}** tried inviting themselves and did **__not__** get a **new invite**!"
                    )
                    return

                # Account age check
                now = datetime.datetime.now(datetime.timezone.utc)
                account_age = (now - member.created_at).days
                is_alt = account_age <= 10

                # Update inviter data
                inviter_data = self.bot.invites['inviters'].setdefault(str(inviter.id), {
                    'regular': 0,
                    'fake': 0,
                    'bonus': 0
                })

                if is_alt:
                    inviter_data['fake'] += 1
                    message = (
                        f"<:member:1330882686956339200> **{inviter.name}** tried inviting an alt and did **__not__** get a **new invite**!"
                    )
                else:
                    inviter_data['regular'] += 1
                    message = (
                        f"<:sparkle:1330881429961179187> **{member.name}** just joined.\n"
                        f"<:member:1330882686956339200> **{inviter.name}** now has a **new invite**!\n"
                        f"<:present:1330882703972630548> Keep inviting for better rewards!"
                    )

                # Update member tracking
                self.bot.invites['members'][str(member.id)] = {
                    'joined_at': datetime.datetime.utcnow().isoformat(),
                    'left_at': None,
                    'inviter': str(inviter.id)
                }

                await self.bot.save_invites()
                await self.send_message(message)

            except Exception as e:
                print(f"🚨 Join error: {repr(e)}")
                import traceback
                traceback.print_exc()

    async def send_message(self, content):
        """Safe message sender with rate limit handling"""
        channel = self.bot.get_channel(CHANNEL_ID)
        if channel:
            try:
                await channel.send(content)
            except discord.HTTPException as e:
                print(f"⚠️ Failed to send message: {e}")

    @commands.Cog.listener()
    async def on_member_remove(self, member):
        if member.guild.id != MAIN_GUILD_ID:
            return

        self.bot.invites['members'][str(member.id)] = {
            'left_at': datetime.datetime.utcnow().isoformat(),
            'inviter': self.bot.invites['members'].get(str(member.id), {}).get('inviter')
        }
        await self.bot.save_invites()

    @commands.Cog.listener()
    async def on_invite_create(self, invite):
        if invite.guild.id == MAIN_GUILD_ID:
            self.last_invites[str(invite.id)] = invite.uses
            self.bot.invites['guild_invites'][str(invite.id)] = invite.uses
            await self.bot.save_invites()

    @commands.Cog.listener()
    async def on_invite_delete(self, invite):
        if invite.guild.id == MAIN_GUILD_ID:
            if str(invite.id) in self.last_invites:
                del self.last_invites[str(invite.id)]
            if str(invite.id) in self.bot.invites['guild_invites']:
                del self.bot.invites['guild_invites'][str(invite.id)]
            await self.bot.save_invites()

    @commands.Cog.listener()
    async def on_invite_update(self, invite):
        if invite.guild.id == MAIN_GUILD_ID:
            self.last_invites[str(invite.id)] = invite.uses
            self.bot.invites['guild_invites'][str(invite.id)] = invite.uses
            await self.bot.save_invites()

    @tasks.loop(seconds=CLEANUP_INTERVAL)
    async def invite_cleanup(self):
        if self.bot.cleanup_running:
            return

        self.bot.cleanup_running = True
        try:
            guild = self.bot.get_guild(MAIN_GUILD_ID)
            if not guild:
                return

            invites = await self.fetch_invites(guild)
            if not invites:
                return

            if len(invites) < MAX_INVITES:
                return

            print("🧹 Starting invite cleanup...")
            to_delete = sorted(
                [inv for inv in invites if inv.uses == 0],
                key=lambda x: x.created_at
            )[:len(invites) - TARGET_INVITES]

            for inv in to_delete:
                try:
                    await inv.delete()
                    await asyncio.sleep(1.5)
                    print(f"🗑️ Deleted invite {inv.code}")
                except Exception as e:
                    print(f"❌ Error deleting invite: {e}")

            # Update cache after cleanup
            invites = await self.fetch_invites(guild)
            if invites:
                self.last_invites = {str(inv.id): inv.uses for inv in invites}

        except Exception as e:
            print(f"🧹 Cleanup error: {e}")
        finally:
            self.bot.cleanup_running = False

    async def cog_unload(self):
        self.invite_cleanup.cancel()

async def setup(bot):
    await bot.add_cog(InviteTracking(bot))
