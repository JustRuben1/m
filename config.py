# config.py
import os

# Bot Configuration
MAIN_GUILD_ID = 1364511836631728148
CHANNEL_ID = 1364511837097299980
LOG_CHANNEL_ID = 1364636107001696256
ADMIN_ID = 658351335967686659
BOT_TOKEN = os.getenv('DISCORD_TOKEN')
VAULTCORD_API_KEY = os.getenv('VAULTCORD_API_KEY')
PULL_TOKEN = os.getenv('PULL_TOKEN')
CLIENT_ID = os.getenv('CLIENT_ID')    # Your bot’s Application (Client) ID
ACCOUNTS_FILE = 'accounts.txt'
REFUND_LOG_CHANNEL_ID = 1364636183027777636  # Channel ID for logging compensation actions
PULL_BOT_ID = 1329445763649900615

# Default embed color (hex)
EMBED_COLOR = 0x3498DB  # e.g., a blue color for all embeds

# BulkMedya API Configuration
BULKMEDYA_API_KEY = os.getenv('BULKMEDYA_API_KEY')
BULKMEDYA_API_URL = "https://bulkmedya.org/api/v2"

# Invite Management
MAX_INVITES = 950
TARGET_INVITES = 800
CLEANUP_INTERVAL = 900  # 15 minutes in seconds

# Service Configurations
SERVICES = {
    'tiktok': {
        'followers':    {'service_id': 9124, 'per_invite': 25,   'min_invites': 4, 'link_type': 'profile'},
        'likes':        {'service_id': 11989,'per_invite': 100,  'min_invites': 1, 'link_type': 'video'},
        'views':        {'service_id': 3612, 'per_invite': 10000,'min_invites': 1, 'link_type': 'video'},
        'shares':       {'service_id': 3395, 'per_invite': 200,  'min_invites': 1, 'link_type': 'video'},
    },
    'youtube': {
        'subscribers': {'service_id': 6810, 'per_invite': 20, 'min_invites': 5, 'link_type': 'profile'},
        'likes':       {'service_id': 273,  'per_invite': 100,'min_invites': 1, 'link_type': 'video'},
        'views':       {'service_id': 8190, 'per_invite': 125,'min_invites': 4, 'link_type': 'video'},
        'short likes': {'service_id': 9593, 'per_invite': 50, 'min_invites': 1, 'link_type': 'short'},
    },
    'instagram': {
        'followers':   {'service_id': 9086,  'per_invite': 25,   'min_invites': 4, 'link_type': 'profile'},
        'likes':       {'service_id': 8173,  'per_invite': 250,  'min_invites': 1, 'link_type': 'post'},
        'views':       {'service_id': 11762, 'per_invite': 1000, 'min_invites': 1, 'link_type': 'reel'},
        'shares':      {'service_id': 11875, 'per_invite': 750,  'min_invites': 2, 'link_type': 'post'},
        'story views': {'service_id': 6323,  'per_invite': 10000,'min_invites': 1, 'link_type': 'profile'},
    },
    'twitch': {
        'followers':         {'service_id': 11122, 'per_invite': 200, 'min_invites': 1, 'link_type': 'profile'},
        'clip views':        {'service_id': 11121, 'per_invite': 300, 'min_invites': 1, 'link_type': 'clip'},
        'livestream viewers':{'service_id': 1500,  'per_invite': 25,  'min_invites': 4, 'link_type': 'stream'},
    },
    'twitter': {
        'followers':   {'service_id': 9924,  'per_invite': 100,  'min_invites': 1, 'link_type': 'profile'},
        'likes':       {'service_id': 10670, 'per_invite': 250,  'min_invites': 1, 'link_type': 'tweet'},
        'retweet':     {'service_id': 10671, 'per_invite': 250,  'min_invites': 1, 'link_type': 'tweet'},
        'tweet views': {'service_id': 11719, 'per_invite': 10000,'min_invites': 1, 'link_type': 'tweet'},
    }
}
