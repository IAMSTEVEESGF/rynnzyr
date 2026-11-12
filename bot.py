import discord
from discord import app_commands
from discord.ext import commands
import os
import asyncio
import re

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

# --- THIS IS YOUR PERFECT DESIGN ---
# Just type the exact prefix and suffix you want for every channel!
# If you want [ 📚 ] • rules, you put prefix: "[ ", suffix: " ] • "
CHANNEL_DESIGN = {
    "prefix": "[ ",
    "suffix": " ] • "
}

# This is how you want the categories to look
# Example: ---- 《IMPORTANT》 ----
CATEGORY_DESIGN = {
    "prefix": "---- 《",
    "suffix": "》 ----"
}

# Your emojis (You can add more here)
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

SERVER_LAYOUT = {
    "STAFF GENERAL": [("staff-rules", False), ("staff-announcements", False), ("staff-logs", False), ("staff-chat", False), ("staff-promotions", False), ("staff-demotions", False), ("staff-vc", True)],
    "WELCOME": [("invite-tracker", False), ("welcome", False), ("goodbye", False)],
    "IMPORTANT": [("rules", False), ("announcements", False), ("sab-leaks", False), ("server-boosts", False), ("boosters-rewards", False), ("polls", False), ("scammers", False), ("applications", False), ("server-updates", False), ("hall-of-fame", False), ("content", False), ("support-ticket", False)],
    "MIDDLEMAN": [("verified-middleman", False), ("middleman-ticket", False), ("middleman-vouches", False)],
    "GIVEAWAYS": [("giveaways", False), ("flash-giveaways", False), ("giveaways-vouches", False), ("giveaways-vc", True)],
    "GENERAL": [("general", False), ("media", False), ("commands", False), ("levels", False)],
    "TRADING & DUELING": [("trading-forum", False), ("owners-trading", False), ("trading", False), ("mid-trading", False), ("og-trading", False), ("duel-requests", False), ("win-or-loss", False), ("owners-vouches", False), ("staff-vouches", False), ("vouches", False)],
    "CONTENT CREATORS": [("content-rules", False), ("content-announcements", False), ("creators-chat", False), ("content-ideas", False), ("creators-vc", True)],
    "PARTNERSHIP": [("partnerships", False), ("self-promo", False), ("paid-promo", False), ("self-promoters", True)],
    "VOICE CHATS": [("owners-vc", True), ("vc-1", True), ("vc-2", True), ("stage", True), ("sab-vc", True), ("duel-vc", True), ("music", True)]
}

@bot.event
async def on_ready():
    print(f"✅ Assistant bot online as {bot.user}")
    await bot.tree.sync()

@bot.tree.command(name="setup", description="Apply the perfect design to your server")
async def setup(interaction: discord.Interaction):
    
    if not interaction.user.guild_permissions.administrator and interaction.guild.owner_id != interaction.user.id:
        await interaction.response.send_message("❌ Admin only.", ephemeral=True)
        return

    await interaction.response.defer()
    
    embed = discord.Embed(
        title="🛠️ Applying Perfect Design",
        description="Applying your custom design layout to every channel.\n\n⚠️ **Do not spam.**",
        color=discord.Color.green()
    )
    await interaction.edit_original_response(embed=embed)
    
    guild = interaction.guild
    updated_count = 0
    
    for category_name, channels in SERVER_LAYOUT.items():
        
        # 1. CATEGORY DESIGN (e.g. ---- 《IMPORTANT》 ----)
        formatted_cat = f"{CATEGORY_DESIGN['prefix']}{category_name}{CATEGORY_DESIGN['suffix']}"
        
        # Find existing category
        category = None
        for c in guild.categories:
            if category_name.lower() in c.name.lower():
                category = c
                break
                
        if not category:
            category = await guild.create_category(formatted_cat)
            await asyncio.sleep(2)
        elif category.name != formatted_cat:
            await category.edit(name=formatted_cat)
            await asyncio.sleep(2)
        
        # 2. CHANNEL DESIGN (e.g. [ 📚 ] • rules)
        for channel_name, is_voice in channels:
            emoji = SAB_EMOJIS.get(channel_name, "")
            
            # The exact name format you want
            full_name = f"{CHANNEL_DESIGN['prefix']}{emoji}{CHANNEL_DESIGN['suffix']}{channel_name}"

            # Find existing channel
            existing_channel = None
            for ch in guild.channels:
                clean_ch = re.sub(r'[^\w\s-]', '', ch.name).strip().lower()
                if clean_ch == channel_name:
                    existing_channel = ch
                    break
            
            try:
                if existing_channel:
                    if existing_channel.name != full_name:
                        await existing_channel.edit(name=full_name)
                        updated_count += 1
                        await asyncio.sleep(3)
                else:
                    if is_voice:
                        await guild.create_voice_channel(name=full_name, category=category)
                    else:
                        await guild.create_text_channel(name=full_name, category=category)
                    updated_count += 1
                    await asyncio.sleep(3)
            except Exception as e:
                print(f"Error: {e}")
                    
    success_embed = discord.Embed(
        title="✅ Layout Complete!",
        description=f"Successfully applied the design to **{updated_count}** channels and categories.\n\n*Press `Cmd + R` to refresh your sidebar.*",
        color=discord.Color.green()
    )
    await interaction.edit_original_response(embed=success_embed)

if __name__ == "__main__":
    bot.run(os.getenv("DISCORD_TOKEN"))
