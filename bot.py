import discord
from discord import app_commands
from discord.ext import commands
import os
import asyncio
import io
import re

try:
    import pytesseract
    from PIL import Image, ImageOps
    HAS_OCR = True
except ImportError:
    HAS_OCR = False

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

# --- DEFAULT LAYOUT (Used if no ID, Image, or Prefix is provided) ---
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

async def extract_design_from_image(image_bytes):
    if not HAS_OCR:
        return {}, None
    try:
        image = Image.open(io.BytesIO(image_bytes))
        image = image.convert('L')
        image = ImageOps.invert(image)
        image = image.resize((image.width * 2, image.height * 2), Image.Resampling.LANCZOS)
        text = pytesseract.image_to_string(image)
        lines = text.split('\n')
        
        channel_designs = {}
        category_design = None
        
        for line in lines:
            line = line.strip()
            if not line: continue
            
            for name in SAB_EMOJIS.keys():
                if name in line.lower():
                    parts = line.lower().split(name)
                    prefix = parts[0].strip()
                    suffix = parts[1].strip() if len(parts) > 1 else ""
                    
                    prefix = re.sub(r'[^\w\s\[\]\|•┃✦✨\{\}\(\)《》-]', '', prefix).strip()
                    suffix = re.sub(r'[^\w\s\[\]\|•┃✦✨\{\}\()《》-]', '', suffix).strip()

                    emoji = SAB_EMOJIS[name]
                    if "[]" in prefix: prefix = prefix.replace("[]", f"[ {emoji} ]")
                    elif "[ ]" in prefix: prefix = prefix.replace("[ ]", f"[ {emoji} ]")
                    elif "[" in prefix and "]" in prefix and emoji not in prefix:
                        prefix = prefix.replace("[", f"[ {emoji} ", 1)

                    if prefix or suffix:
                        channel_designs[name] = {
                            "prefix": prefix + " " if prefix else "",
                            "suffix": " " + suffix if suffix else ""
                        }
            
            for cat in SERVER_LAYOUT.keys():
                if cat.lower() in line.lower():
                    parts = line.lower().split(cat.lower())
                    prefix = parts[0].strip()
                    suffix = parts[1].strip() if len(parts) > 1 else ""
                    if prefix or suffix:
                        prefix = re.sub(r'[^\w\s\[\]\|•┃✦✨\{\}\(\)《》-]', '', prefix).strip()
                        suffix = re.sub(r'[^\w\s\[\]\|•┃✦✨\{\}\()《》-]', '', suffix).strip()
                        category_design = {
                            "prefix": prefix + " " if prefix else "",
                            "suffix": " " + suffix if suffix else ""
                        }
                        
        return channel_designs, category_design
    except Exception as e:
        print(f"OCR Error: {e}")
        return {}, None

@bot.tree.command(name="setup", description="Build or update the server layout")
@app_commands.describe(
    source_server_id="Copy the exact layout (names, categories) from another server using its ID",
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
    source_server_id: str = None,
    style: app_commands.Choice[str] = None, 
    custom_prefix: str = None, 
    reference_image: discord.Attachment = None
):
    # 1. Admin Check
    if not interaction.user.guild_permissions.administrator and interaction.guild.owner_id != interaction.user.id:
        await interaction.response.send_message("❌ You must be an **Administrator** or the **Server Owner**.", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=False)
    
    guild = interaction.guild
    updated_count = 0

    # --- CLONE FROM SERVER ID ---
    if source_server_id:
        try:
            source_guild = bot.get_guild(int(source_server_id))
            if not source_guild:
                source_guild = await bot.fetch_guild(int(source_server_id))
        except ValueError:
            await interaction.edit_original_response(content="❌ **Error:** Invalid Server ID. Please make sure it's a number.")
            return
        except discord.NotFound:
            await interaction.edit_original_response(content="❌ **Error:** I couldn't find that server. Make sure I am actually inside the server you are trying to copy.")
            return

        embed = discord.Embed(
            title="🛠️ Cloning Server Layout",
            description=f"Copying categories and channels exactly from **{source_guild.name}**.\n\n⚠️ **Do not spam this command.**",
            color=discord.Color.green()
        )
        await interaction.edit_original_response(content=None, embed=embed)

        # Clone Categories and Channels
        for src_cat in source_guild.categories:
            # Check if category exists, else create
            new_cat = discord.utils.get(guild.categories, name=src_cat.name)
            if not new_cat:
                new_cat = await guild.create_category(src_cat.name)
                await asyncio.sleep(2)
            
            for src_ch in src_cat.channels:
                # Check if channel exists
                existing = discord.utils.get(guild.channels, name=src_ch.name)
                if not existing:
                    if isinstance(src_ch, discord.TextChannel):
                        await guild.create_text_channel(src_ch.name, category=new_cat)
                    elif isinstance(src_ch, discord.VoiceChannel):
                        await guild.create_voice_channel(src_ch.name, category=new_cat)
                    updated_count += 1
                    await asyncio.sleep(3)

        # Clone Uncategorized Channels
        for src_ch in source_guild.channels:
            if src_ch.category is None:
                existing = discord.utils.get(guild.channels, name=src_ch.name)
                if not existing:
                    if isinstance(src_ch, discord.TextChannel):
                        await guild.create_text_channel(src_ch.name)
                    elif isinstance(src_ch, discord.VoiceChannel):
                        await guild.create_voice_channel(src_ch.name)
                    updated_count += 1
                    await asyncio.sleep(3)

        success_embed = discord.Embed(
            title="✅ Server Clone Complete!",
            description=f"Successfully cloned **{updated_count}** channels and categories.\n\n*Press `Cmd + R` to refresh your sidebar.*",
            color=discord.Color.green()
        )
        await interaction.edit_original_response(embed=success_embed)
        return # Stop here, we don't need to do the custom layout stuff

    # --- EXISTING LAYOUT LOGIC (If no ID is provided) ---
    selected_style = style.value if style else "sab"
    final_prefix = custom_prefix
    channel_designs = {}
    cat_design = None

    if reference_image:
        await interaction.edit_original_response(content="📸 Reading the specific channel designs from your image...")
        image_bytes = await reference_image.read()
        channel_designs, cat_design = await extract_design_from_image(image_bytes)
        
        if not channel_designs:
            await interaction.edit_original_response(content="❌ **Error:** I couldn't read the text from your image. Please use the `custom_prefix` option instead.")
            return

    if final_prefix and not final_prefix.endswith(" "):
        final_prefix += " "

    embed = discord.Embed(
        title="🛠️ Updating Server Layout",
        description="Applying designs and updating your server.\n\n⚠️ **Do not spam this command.**",
        color=discord.Color.green()
    )
    await interaction.edit_original_response(content=None, embed=embed)
    
    for category_name, channels in SERVER_LAYOUT.items():
        
        if cat_design:
            formatted_cat = f"{cat_design['prefix']}{category_name}{cat_design['suffix']}".strip()
        elif selected_style == "sab":
            formatted_cat = f"〔✨ {category_name} 〕"
        elif selected_style == "photo":
            formatted_cat = f"---- 《{category_name}》 ----"
        else:
            formatted_cat = category_name

        category = None
        for c in guild.categories:
            clean_c = re.sub(r'[^\w\s]', '', c.name).strip().lower()
            if category_name.lower() in clean_c:
                category = c
                break
                
        if not category:
            category = await guild.create_category(formatted_cat)
            await asyncio.sleep(2)
        elif category.name != formatted_cat:
            try:
                await category.edit(name=formatted_cat)
                await asyncio.sleep(2)
            except Exception:
                pass
        
        for channel_name, is_voice in channels:
            emoji = SAB_EMOJIS.get(channel_name, "")
            
            if channel_name in channel_designs:
                design = channel_designs[channel_name]
                full_name = f"{design['prefix']}{channel_name}{design['suffix']}".strip()
            elif final_prefix:
                full_name = f"{final_prefix}{channel_name}"
            elif selected_style == "sab":
                full_name = f"{emoji}┃{channel_name}" if emoji else channel_name
            elif selected_style == "photo":
                full_name = f"[ {emoji} ] • {channel_name}" if emoji else f"[ ] • {channel_name}"
            else:
                full_name = channel_name

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
                print(f"Error on {channel_name}: {e}")
                    
    success_embed = discord.Embed(
        title="✅ Server Layout Complete!",
        description=f"Successfully updated/created **{updated_count}** channels and categories.\n\n*Press `Cmd + R` to refresh your sidebar.*",
        color=discord.Color.green()
    )
    await interaction.edit_original_response(embed=success_embed)

if __name__ == "__main__":
    bot.run(os.getenv("DISCORD_TOKEN"))
