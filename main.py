# main.py
import discord
from discord.ext import commands
from discord import http
import os
import json
import asyncio
import random
from config import *

class RateLimitHandler(http.HTTPClient):
    async def request(self, route, *, files=None, **kwargs):
        retries = 3
        for attempt in range(retries):
            try:
                return await super().request(route, files=files, **kwargs)
            except discord.HTTPException as e:
                if e.status == 429 and attempt < retries - 1:
                    retry_after = e.response.headers.get('Retry-After', 5)
                    print(f"Rate limited. Retrying in {retry_after}s")
                    await asyncio.sleep(float(retry_after))
                    continue
                raise

discord.http.HTTPClient = RateLimitHandler

class InviteTracker(commands.Bot):
    def __init__(self):
        super().__init__(
            command_prefix="!",
            intents=discord.Intents.all(),
            help_command=None
        )
        self.invites = {'inviters': {}, 'members': {}, 'guild_invites': {}}
        self.accounts = []
        self.accounts_lock = asyncio.Lock()
        self.cleanup_running = False

    async def setup_hook(self):
        # Load initial invites
        guild = self.get_guild(MAIN_GUILD_ID)
        if guild:
            try:
                invites = await guild.invites()
                self.invites['guild_invites'] = {str(inv.id): inv.uses for inv in invites}
            except Exception as e:
                print(f"Error fetching initial invites: {e}")

        # Load saved data
        try:
            with open('invites.json') as f:
                data = json.load(f)
                self.invites['inviters'] = data.get('inviters', {})
                self.invites['members'] = data.get('members', {})
        except (FileNotFoundError, json.JSONDecodeError):
            pass

        # Load accounts
        try:
            with open(ACCOUNTS_FILE, 'r') as f:
                self.accounts = [line.strip() for line in f if line.strip()]
                random.shuffle(self.accounts)
        except FileNotFoundError:
            open(ACCOUNTS_FILE, 'w').close()

        # Load cogs
        await self.load_extension("cogs.invites")
        await self.load_extension("cogs.accounts")
        await self.load_extension("cogs.social")
        await self.load_extension("cogs.admin")
        await self.load_extension("cogs.membersfarm")

        await self.tree.sync()
        print("Bot ready")

    async def save_invites(self):
        with open('invites.json', 'w') as f:
            json.dump({
                'inviters': self.invites['inviters'],
                'members': self.invites['members']
            }, f, indent=2)

bot = InviteTracker()

if __name__ == "__main__":
    bot.run(BOT_TOKEN)
