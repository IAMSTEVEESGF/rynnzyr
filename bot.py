import discord
from discord import app_commands
from discord.ext import commands
import os
import asyncio
import io

try:
    import pytesseract
    from PIL import Image
    HAS_OCR = True
except ImportError:
    HAS_OCR = False

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

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
    print("✅ Synced slash commands")

# --- OCR HELPER FUNCTION ---
async def extract_design_from_image(image_bytes):
    if not HAS_OCR:
        return None, "OCR libraries not installed."
    try:
        image = Image.open(io.BytesIO(image_bytes))
        text = pytesseract.image_to_string(image)
        
        # Look through the extracted text for our known channel names
        lines = text.split('\n')
        all_known_names = list(SAB_EMOJIS.keys())
        
        for line in lines:
            for name in all_known_names:
                if name in line:
                    # Found a channel name! Now extract what's before it.
                    # Example text: "[ 📚 ] • general"
                    # Split by the name to get the prefix
                    parts = line.split(name)
                    prefix = parts[0].strip()
                    
                    if prefix:
                        # Return the prefix with a space at the end
                        return prefix + " ", None
        return None, "Could not find a recognizable channel name in the image."
    except Exception as e:
        return None, f"OCR Error: {e}"

# --- THE SMART /SETUP SLASH COMMAND ---
@bot.tree.command(name="setup", description="Build the server layout")
@app_commands.describe(
    style="Choose a default design style",
    custom_prefix="Type the exact prefix (e.g. [ 📚 ] • )",
    reference_image="Upload an image to copy the text design from it"
)
@app_commands.choices(style=[
    app_commands.Choice(name="SAB Style (┃ & 〔✨ 〕)", value="sab"),
    app_commands.Choice(name="Photo Style ([ ] • & ---- 《》 ----)", value="photo"),
    app_commands.Choice(name="Plain (No symbols)", value="plain")
])
async def setup(
    interaction: discord.Interaction, 
    style: app_commands.Choice[str] = None, 
    custom_prefix: str = None, 
    reference_image: discord.Attachment = None
):
    # 1. Admin Check
    if not interaction.user.guild_permissions.administrator and interaction.guild.owner_id != interaction.user.id:
        await interaction.response.send_message("❌ You must be an **Administrator** or the **Server Owner**.", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=False)
    
    selected_style = style.value if style else "sab"
    final_prefix = None
    error_msg = None

    # 2. Check if they uploaded an image
    if reference_image:
        await interaction.edit_original_response(content="📸 Reading the design from your image... (This takes a second)")
        image_bytes = await reference_image.read()
        final_prefix, error_msg = await extract_design_from_image(image_bytes)
        if error_msg:
            await interaction.edit_original_response(content=f"⚠️ {error_msg}\nFalling back to default style.")
            selected_style = "sab"

    # 3. If they typed a custom prefix manually, use that instead
    if custom_prefix:
        final_prefix = custom_prefix
        if not final_prefix.endswith(" "):
            final_prefix += " " # Ensure there's a space before the name

    embed = discord.Embed(
        title="🛠️ Creating Server Layout",
        description="Creating your server.\n\n⚠️ **Do not spam this command.**\nYour srv will be done in a few mins.",
        color=discord.Color.green()
    )
    await interaction.edit_original_response(content=None, embed=embed)
    
    guild = interaction.guild
    created_count = 0
    
    for category_name, channels in SERVER_LAYOUT.items():
        
        # Format Categories (Image OCR doesn't do categories well, so we stick to styles)
        if selected_style == "sab":
            formatted_cat = f"〔✨ {category_name} 〕"
        elif selected_style == "photo":
            formatted_cat = f"---- 《{category_name}》 ----"
        else:
            formatted_cat = category_name

        category = discord.utils.get(guild.categories, name=formatted_cat)
        if not category:
            category = await guild.create_category(formatted_cat)
            await asyncio.sleep(2) 
        
        for channel_name, is_voice in channels:
            emoji = SAB_EMOJIS.get(channel_name, "")
            
            # --- FORMATTING CHANNELS ---
            if final_prefix:
                # If they used an image or custom prefix, apply it exactly
                full_name = f"{final_prefix}{channel_name}"
            elif selected_style == "sab":
                full_name = f"{emoji}┃{channel_name}" if emoji else channel_name
            elif selected_style == "photo":
                full_name = f"[ {emoji} ] • {channel_name}" if emoji else f"[ ] • {channel_name}"
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
        description=f"Successfully created **{created_count}** channels.\n\n*Press `Cmd + R` to refresh your sidebar.*",
        color=discord.Color.green()
    )
    await interaction.edit_original_response(embed=success_embed)

if __name__ == "__main__":
    bot.run(os.getenv("DISCORD_TOKEN"))
