import discord
from discord.ext import commands
import os
import re
import asyncio

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix=".", intents=intents)

# --- SAB EMOJI DICTIONARY ---
SAB_EMOJIS = {
    "staff-rules": "📚", "staff-announcements": "📣", "staff-logs": "🗄️",
    "staff-chat": "💬", "staff-promotions": "🎉", "staff-demotions": "⚠️",
    "staff-vc": "🎙️", "invite-tracker": "📈", "welcome": "👋",
    "goodbye": "🕊️", "rules": "📚", "announcements": "📣",
    "sab-leaks": "📊", "server-boosts": "🚀", "boosters-rewards": "⚡",
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

def get_clean_name(name):
    # Strips old [ 📚 ] · or ┃📚┃ or - etc. to get JUST the channel name
    name = re.sub(r'^\[.*?\]\s*[^\w\s]*\s*', '', name) # Strips [ Emoji ] · 
    name = re.sub(r'^[^\w]+', '', name)               # Strips ┃📚┃ or -
    name = re.sub(r'[^\w\s-]', '', name)              # Removes weird characters
    return name.replace(" ", "-").strip().lower()

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

    if content in ("help", "commands"):
        await message.channel.send("🤖 **Bot is alive!**\nType `.sab` to apply the `┃emoji┃name` design.")
        return

    # --- THE .SAB COMMAND ---
    if content in ("sab", "design sab"):
        thinking = await message.channel.send("🔧 Working on it... Applying `┃emoji┃name` to all channels.")
        
        guild = message.guild
        renamed = []
        failed = []
        
        for channel in guild.channels:
            if isinstance(channel, discord.CategoryChannel):
                continue
                
            clean_name = get_clean_name(channel.name)
            
            if clean_name in SAB_EMOJIS:
                emoji = SAB_EMOJIS[clean_name]
                
                # THIS IS THE EXACT FORMAT YOU ASKED FOR: ┃emoji┃name
                new_name = f"┃{emoji}┃{clean_name}"
                
                if channel.name != new_name:
                    try:
                        await channel.edit(name=new_name)
                        renamed.append(f"`{channel.name}` ➔ `{new_name}`")
                        await asyncio.sleep(3) # Rate limit protection
                    except Exception as e:
                        failed.append(f"❌ `{channel.name}`: {str(e)}")
            
        msg = ""
        if renamed:
            msg += "✅ **Done!** Applied SAB design:\n" + "\n".join(renamed)
        if failed:
            msg += "\n\n**Errors:**\n" + "\n".join(failed)
        if not renamed and not failed:
            msg = "😴 All channels are already matching the SAB design."
            
        await thinking.edit(content=msg)

    # --- RESET COMMAND ---
    if content == "reset":
        thinking = await message.channel.send("🔧 Working on it... Resetting channels to default names.")
        renamed = []
        
        for channel in message.guild.channels:
            if isinstance(channel, discord.CategoryChannel):
                continue
                
            clean_name = get_clean_name(channel.name)
            if channel.name != clean_name:
                try:
                    await channel.edit(name=clean_name)
                    renamed.append(f"`{channel.name}` ➔ `{clean_name}`")
                    await asyncio.sleep(3)
                except Exception:
                    pass
                    
        if renamed:
            await thinking.edit(content="✅ **Done!** Channels reset:\n" + "\n".join(renamed))
        else:
            await thinking.edit(content="😴 Channels are already clean.")

if __name__ == "__main__":
    bot.run(os.getenv("DISCORD_TOKEN"))
