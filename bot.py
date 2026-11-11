import discord
from discord.ext import commands
import os
import re
import asyncio

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix=".", intents=intents)

# --- SMART EMOJI DICTIONARY ---
# The bot looks for these words in the channel name.
# If it finds one, it adds the emoji. You can add as many as you want here!
EMOJI_MAP = {
    "general": "💬",
    "chat": "🗣️",
    "trade": "📊",
    "trading": "📈",
    "staff": "🛡️",
    "admin": "⚙️",
    "log": "📝",
    "welcome": "👋",
    "rules": "📜",
    "announce": "📢",
    "vc": "🔊",
    "music": "🎵",
    "bot": "🤖",
    "memes": "😂",
    "polls": "📊",
    "ticket": "🎫",
    "help": "❓",
    "vip": "💎",
    "shop": "🛒",
    "buy": "🛍️",
    "sell": "💸",
    "leaks": "🥷",
    "vouch": "✅",
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

    content = message.content[1:].strip()
    parts = content.split(" ", 1)

    if parts[0].lower() == "help":
        await message.channel.send("🤖 **Bot is alive!**\nType `.design pipe` for the thick ┃ line. It will auto-add emojis.")
        return

    if parts[0].lower() == "design":
        if len(parts) < 2 or not parts[1]:
            await message.channel.send("❌ You forgot the design! Try `.design pipe`")
            return
            
        new_design = parts[1]
        
        if new_design.lower() == "pipe":
            new_design = "┃"
        elif new_design.lower() == "line":
            new_design = "│"
        elif new_design.lower() == "default":
            new_design = ""

        thinking = await message.channel.send(f"🔧 Working on it... Detected design: `{new_design}`. Smart-adding emojis...")
        
        guild = message.guild
        renamed = []
        failed = []
        
        for channel in guild.channels:
            if isinstance(channel, discord.CategoryChannel):
                continue
                
            # 1. Strip old symbols to get the raw name
            clean_name = re.sub(r'^[^\w]+', '', channel.name)
            if not clean_name:
                clean_name = "channel"

            # 2. Find the matching emoji from our dictionary
            channel_emoji = ""
            for keyword, emoji in EMOJI_MAP.items():
                if keyword in clean_name:
                    # Format: Emoji + Dot separator (e.g. 📊・)
                    channel_emoji = f"{emoji}・" 
                    break
            
            # 3. Build the final name: ┃ + 📊・ + trading
            new_name = f"{new_design}{channel_emoji}{clean_name}".lower()
            
            if channel.name != new_name:
                try:
                    await channel.edit(name=new_name)
                    renamed.append(f"`{channel.name}` ➔ `{new_name}`")
                    await asyncio.sleep(3) # Wait to avoid Discord rate limits
                except Exception as e:
                    failed.append(f"❌ `{channel.name}`: {str(e)}")
                    
        msg = ""
        if renamed:
            msg += "✅ **Done!** Channels updated:\n" + "\n".join(renamed)
        if failed:
            msg += "\n\n**Errors:**\n" + "\n".join(failed)
        if not renamed and not failed:
            msg = f"😴 All channels are already correct."
            
        await thinking.edit(content=msg)

if __name__ == "__main__":
    bot.run(os.getenv("DISCORD_TOKEN"))
