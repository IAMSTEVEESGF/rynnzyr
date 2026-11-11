import discord
from discord.ext import commands
import os
import asyncio

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix=".", intents=intents)

# --- YOUR CUSTOM SAB EMOJI DICTIONARY ---
SAB_EMOJIS = {
    "staff-rules": "📚", "staff-announcements": "📣", "staff-logs": "🔖",
    "staff-chat": "💬", "staff-promotions": "🎉", "staff-demotions": "⚠️",
    "staff-vc": "🎙️", "invite-tracker": "🛤️", "welcome": "👋",
    "goodbye": "🕊️", "rules": "📚", "announcements": "📣",
    "sab-leaks": "📊", "server-boosts": "🚀", "boosters-rewards": "🧨",
    "polls": "🥇", "scammers": "⚠️", "applications": "📝",
    "server-updates": "🔄", "hall-of-fame": "🥇", "content": "🎥",
    "support-ticket": "🎟️", "verified-middleman": "🤝", "middleman-ticket": "🎫",
    "middleman-vouches": "✅", "giveaways": "🎉", "flash-giveaways": "🎁",
    "giveaways-vouches": "🎁", "giveaways-vc": "🏆", "general": "💬",
    "media": "🖼️", "commands": "⚙️", "levels": "📈",
    "trading-forum": "⚔️", "owners-trading": "👑", "trading": "💰",
    "mid-trading": "⭐", "og-trading": "💎", "duel-requests": "⚔️",
    "win-or-loss": "⚖️", "owners-vouches": "👑", "staff-vouches": "📊",
    "vouches": "✅", "content-rules": "📚", "content-announcements": "📣",
    "creators-chat": "🎥", "content-ideas": "✨", "creators-vc": "🎙️",
    "partnerships": "🤝", "self-promo": "⭐", "paid-promo": "✨",
    "self-promoters": "🎙️", "owners-vc": "👑", "vc-1": "🎙️",
    "vc-2": "🎙️", "stage": "🎪", "sab-vc": "💰", "duel-vc": "⚔️",
    "music": "🎵"
}

# --- SERVER LAYOUT TEMPLATE ---
SERVER_LAYOUT = {
    "STAFF GENERAL": [
        ("staff-rules", False), ("staff-announcements", False), ("staff-logs", False),
        ("staff-chat", False), ("staff-promotions", False), ("staff-demotions", False),
        ("staff-vc", True)
    ],
    "WELCOME": [
        ("invite-tracker", False), ("welcome", False), ("goodbye", False)
    ],
    "IMPORTANT": [
        ("rules", False), ("announcements", False), ("sab-leaks", False),
        ("server-boosts", False), ("boosters-rewards", False), ("polls", False),
        ("scammers", False), ("applications", False), ("server-updates", False),
        ("hall-of-fame", False), ("content", False), ("support-ticket", False)
    ],
    "MIDDLEMAN": [
        ("verified-middleman", False), ("middleman-ticket", False), ("middleman-vouches", False)
    ],
    "GIVEAWAYS": [
        ("giveaways", False), ("flash-giveaways", False), ("giveaways-vouches", False),
        ("giveaways-vc", True)
    ],
    "GENERAL": [
        ("general", False), ("media", False), ("commands", False), ("levels", False)
    ],
    "TRADING & DUELING": [
        ("trading-forum", False), ("owners-trading", False), ("trading", False),
        ("mid-trading", False), ("og-trading", False), ("duel-requests", False),
        ("win-or-loss", False), ("owners-vouches", False), ("staff-vouches", False),
        ("vouches", False)
    ],
    "CONTENT CREATORS": [
        ("content-rules", False), ("content-announcements", False), ("creators-chat", False),
        ("content-ideas", False), ("creators-vc", True)
    ],
    "PARTNERSHIP": [
        ("partnerships", False), ("self-promo", False), ("paid-promo", False),
        ("self-promoters", True)
    ],
    "VOICE CHATS": [
        ("owners-vc", True), ("vc-1", True), ("vc-2", True), ("stage", True),
        ("sab-vc", True), ("duel-vc", True), ("music", True)
    ]
}

@bot.event
async def on_ready():
    print(f"✅ Assistant bot online as {bot.user}")

@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return
    if not message.content.startswith("."):
        return

    content = message.content[1:].strip().lower()
    guild = message.guild

    if content == "create":
        # --- COOL GREEN EMBED ---
        embed = discord.Embed(
            title="🛠️ Creating Server Layout",
            description="Creating your Steal a brainrot server.\n\n⚠️ **Please do not spam this command for security reasons.**\nYour srv will be done in a few mins.",
            color=discord.Color.green() # Cool green
        )
        
        thinking = await message.channel.send(embed=embed)
        
        created_count = 0
        
        for category_name, channels in SERVER_LAYOUT.items():
            # 1. Create the Category
            category = discord.utils.get(guild.categories, name=category_name)
            if not category:
                category = await guild.create_category(category_name)
                await asyncio.sleep(2) # Prevent rate limit
            
            # 2. Create the channels inside the category
            for channel_name, is_voice in channels:
                emoji = SAB_EMOJIS.get(channel_name, "")
                
                # Format: Emoji┃Name
                full_name = f"{emoji}┃{channel_name}" if emoji else channel_name
                
                # Check if channel already exists to prevent duplicates
                existing_channel = discord.utils.get(guild.channels, name=full_name)
                
                if not existing_channel:
                    try:
                        if is_voice:
                            await guild.create_voice_channel(name=full_name, category=category)
                        else:
                            await guild.create_text_channel(name=full_name, category=category)
                        
                        created_count += 1
                        # Wait 3 seconds between every channel to avoid Discord 429 Errors
                        await asyncio.sleep(3) 
                    except Exception as e:
                        await message.channel.send(f"❌ Failed to create `{full_name}`: {str(e)}")
                        
        # --- SUCCESS EMBED ---
        success_embed = discord.Embed(
            title="✅ Server Creation Complete!",
            description=f"Successfully created **{created_count}** channels and categories!\n\n*Press `Cmd + R` (or `Ctrl + R`) to refresh your Discord sidebar to see the changes.*",
            color=discord.Color.green()
        )
        await thinking.edit(embed=success_embed)

if __name__ == "__main__":
    bot.run(os.getenv("DISCORD_TOKEN"))
