import discord
from discord import app_commands
from discord.ext import commands
import os
import asyncio

# --- Setup Bot ---
intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

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
    try:
        synced = await bot.tree.sync()
        print(f"✅ Synced {len(synced)} slash command(s)")
    except Exception as e:
        print(f"❌ Failed to sync commands: {e}")

# --- THE /SETUP SLASH COMMAND ---
@bot.tree.command(name="setup", description="Build the server layout")
@app_commands.describe(design="Choose the design to use (defaults to sab)")
@app_commands.choices(design=[
    app_commands.Choice(name="SAB (Emojis + Names)", value="sab"),
    app_commands.Choice(name="Plain (Just Names)", value="plain")
])
async def setup(interaction: discord.Interaction, design: app_commands.Choice[str] = None):
    await interaction.response.defer(ephemeral=False)
    
    selected_design = design.value if design else "sab"
    
    embed = discord.Embed(
        title="🛠️ Creating Server Layout",
        description="Creating your Steal a brainrot server.\n\n⚠️ **Please do not spam this command for security reasons.**\nYour srv will be done in a few mins.",
        color=discord.Color.green()
    )
    await interaction.edit_original_response(embed=embed)
    
    guild = interaction.guild
    created_count = 0
    
    for category_name, channels in SERVER_LAYOUT.items():
        # --- THIS IS THE NEW FORMATTING LINE ---
        formatted_category_name = f"〔✨ {category_name} 〕"
        
        # 1. Create the Category
        category = discord.utils.get(guild.categories, name=formatted_category_name)
        if not category:
            category = await guild.create_category(formatted_category_name)
            await asyncio.sleep(2) 
        
        # 2. Create the channels
        for channel_name, is_voice in channels:
            emoji = SAB_EMOJIS.get(channel_name, "")
            
            if selected_design == "sab" and emoji:
                full_name = f"{emoji}┃{channel_name}"
            else:
                full_name = channel_name
                
            existing_channel = discord.utils.get(guild.channels, name=full_name)
            
            if not existing_channel:
                try:
                    if is_voice:
                        await guild.create_voice_channel(name=full_name, category=category)
                    else:
                        await guild.create_text_channel(name=full_name, category=category)
                    
                    created_count += 1
                    await asyncio.sleep(3) 
                except Exception as e:
                    print(f"Failed to create {full_name}: {e}")
                    
    success_embed = discord.Embed(
        title="✅ Server Creation Complete!",
        description=f"Successfully created **{created_count}** channels and categories using the **{selected_design}** design!\n\n*Press `Cmd + R` (or `Ctrl + R`) to refresh your Discord sidebar to see the changes.*",
        color=discord.Color.green()
    )
    await interaction.edit_original_response(embed=success_embed)

if __name__ == "__main__":
    bot.run(os.getenv("DISCORD_TOKEN"))
