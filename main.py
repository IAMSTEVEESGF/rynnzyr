import discord
from discord import app_commands
from discord.ext import commands
import os
import asyncio
import json
import random
from openai import AsyncOpenAI

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

ai_client = AsyncOpenAI(
    base_url="https://api.groq.com/openai/v1",
    api_key="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" 
)

@bot.event
async def on_ready():
    await bot.tree.sync()
    print("✅ Professional AI Architect is online!")

@bot.tree.command(name="build", description="Build a perfect, professional server layout")
async def build(interaction: discord.Interaction, prompt: str):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Administrators only.", ephemeral=True)
        return

    await interaction.response.defer()
    await interaction.edit_original_response(content="🏗️ **NoxHelper is designing your server...**")

    system_prompt = """
    You are a Discord Server Architect. You MUST follow the strict template below.
    The user will give you a theme (e.g., Minecraft, Anime, Trading).
    Output ONLY a JSON object.
    
    RULES:
    1. KEEP the exact category names, channel names, emojis, and ORDER from the template.
    2. ONLY modify the parts marked with `[ADAPT]`.
    3. For `[ADAPT]` categories, use highly relevant emojis.
    4. general MUST have 💬. announcements MUST have 📣.
    
    TEMPLATE:
    {
      "categories": [
        {
          "name": "STAFF GENERAL",
          "channels": [
            {"name": "staff-rules", "emoji": "📚", "type": "text"},
            {"name": "staff-announcements", "emoji": "📣", "type": "text"},
            {"name": "staff-logs", "emoji": "🔖", "type": "text"},
            {"name": "staff-chat", "emoji": "💬", "type": "text"},
            {"name": "staff-promotions", "emoji": "🎉", "type": "text"},
            {"name": "staff-demotions", "emoji": "⚠️", "type": "text"},
            {"name": "STAFF VC", "emoji": "🎙️", "type": "voice"}
          ]
        },
        {
          "name": "WELCOME",
          "channels": [
            {"name": "invite-tracker", "emoji": "🛤️", "type": "text"},
            {"name": "welcome", "emoji": "👋", "type": "text"},
            {"name": "goodbye", "emoji": "🕊️", "type": "text"}
          ]
        },
        {
          "name": "IMPORTANT",
          "channels": [
            {"name": "rules", "emoji": "📚", "type": "text"},
            {"name": "announcements", "emoji": "📣", "type": "text"},
            {"name": "[ADAPT]-leaks", "emoji": "📊", "type": "text"},
            {"name": "server-boosts", "emoji": "🚀", "type": "text"},
            {"name": "boosters-rewards", "emoji": "🧨", "type": "text"},
            {"name": "polls", "emoji": "🥇", "type": "text"},
            {"name": "scammers", "emoji": "⚠️", "type": "text"},
            {"name": "applications", "emoji": "📝", "type": "text"},
            {"name": "server-updates", "emoji": "🔄", "type": "text"},
            {"name": "hall-of-fame", "emoji": "🥇", "type": "text"},
            {"name": "content", "emoji": "🎥", "type": "text"},
            {"name": "support-ticket", "emoji": "🎟️", "type": "text"}
          ]
        },
        {
          "name": "[ADAPT] CATEGORY 1",
          "channels": [
            {"name": "[ADAPT]", "emoji": "🤝", "type": "text"},
            {"name": "[ADAPT]", "emoji": "🎫", "type": "text"},
            {"name": "[ADAPT]", "emoji": "✅", "type": "text"}
          ]
        },
        {
          "name": "GIVEAWAYS",
          "channels": [
            {"name": "giveaways", "emoji": "🎉", "type": "text"},
            {"name": "flash-giveaways", "emoji": "🎁", "type": "text"},
            {"name": "giveaways-vouches", "emoji": "🎁", "type": "text"},
            {"name": "GIVEAWAYS VC", "emoji": "🏆", "type": "voice"}
          ]
        },
        {
          "name": "GENERAL",
          "channels": [
            {"name": "general", "emoji": "💬", "type": "text"},
            {"name": "media", "emoji": "🖼️", "type": "text"},
            {"name": "commands", "emoji": "⚙️", "type": "text"},
            {"name": "levels", "emoji": "📈", "type": "text"},
            {"name": "suggestions", "emoji": "🛠️", "type": "text"}
          ]
        },
        {
          "name": "[ADAPT] CATEGORY 2",
          "channels": [
            {"name": "[ADAPT]", "emoji": "⚔️", "type": "text"},
            {"name": "[ADAPT]", "emoji": "👑", "type": "text"},
            {"name": "[ADAPT]", "emoji": "💰", "type": "text"},
            {"name": "[ADAPT]", "emoji": "⭐", "type": "text"},
            {"name": "[ADAPT]", "emoji": "💎", "type": "text"},
            {"name": "duel-requests", "emoji": "⚔️", "type": "text"},
            {"name": "win-or-loss", "emoji": "⚖️", "type": "text"},
            {"name": "owners-vouches", "emoji": "👑", "type": "text"},
            {"name": "staff-vouches", "emoji": "📊", "type": "text"},
            {"name": "vouches", "emoji": "✅", "type": "text"}
          ]
        },
        {
          "name": "CONTENT CREATORS",
          "channels": [
            {"name": "content-rules", "emoji": "📚", "type": "text"},
            {"name": "content-announcements", "emoji": "📣", "type": "text"},
            {"name": "creators-chat", "emoji": "🎥", "type": "text"},
            {"name": "content-ideas", "emoji": "✨", "type": "text"},
            {"name": "Creators Vc", "emoji": "🎙️", "type": "voice"}
          ]
        },
        {
          "name": "PARTNERSHIP & SELF PROMO",
          "channels": [
            {"name": "partnerships", "emoji": "🤝", "type": "text"},
            {"name": "self-promo", "emoji": "⭐", "type": "text"},
            {"name": "paid-promo", "emoji": "✨", "type": "text"},
            {"name": "SELF PROMOTERS", "emoji": "🎙️", "type": "voice"}
          ]
        },
        {
          "name": "VOICE CHATS",
          "channels": [
            {"name": "OWNERS VC", "emoji": "👑", "type": "voice"},
            {"name": "VC 1", "emoji": "🎙️", "type": "voice"},
            {"name": "VC 2", "emoji": "🎙️", "type": "voice"},
            {"name": "STAGE", "emoji": "🎪", "type": "voice"},
            {"name": "SAB VC", "emoji": "💰", "type": "voice"},
            {"name": "DUEL VC", "emoji": "⚔️", "type": "voice"},
            {"name": "MUSIC", "emoji": "🎵", "type": "voice"}
          ]
        }
      ]
    }
    """

    try:
        response = await ai_client.chat.completions.create(
            model="openai/gpt-oss-20b",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ],
            response_format={"type": "json_object"}
        )
        
        layout = json.loads(response.choices[0].message.content)
        
        # --- YOUR EXACT 4 FORMATS (NO SPACES, FULL-WIDTH CHARS) ---
        formats = [
            "〔{emoji}〕・{ch_name}",
            "{emoji}┃{ch_name}",
            "〘{emoji}〙・{ch_name}",
            "{emoji}・{ch_name}"
        ]
        chosen_format = random.choice(formats)
        # --------------------------------------------------------

        building_embed = discord.Embed(
            title="🔧 Building Your Server",
            description=f"Using format: `{chosen_format.format(emoji='💬', ch_name='channel')}`",
            color=discord.Color.green()
        )
        building_embed.add_field(name="Status", value="0 channels created", inline=False)
        await interaction.edit_original_response(embed=building_embed)

        count = 0
        
        for cat in layout.get("categories", []):
            # Category format (Using NBSP so Discord doesn't hyphenate it)
            NBSP = "\u00A0"
            cat_name = f"----{NBSP}《{cat.get('name', 'CATEGORY')}》{NBSP}----"
            
            try:
                category = await interaction.guild.create_category(cat_name)
            except discord.HTTPException:
                await asyncio.sleep(5)
                category = await interaction.guild.create_category(cat_name)
                
            await asyncio.sleep(3)
            
            for ch in cat.get("channels", []):
                ch_name = ch.get('name', 'channel').lower().replace(" ", "-")
                emoji = ch.get('emoji', '💬')
                
                # Force specific emojis
                if ch_name == "general":
                    emoji = "💬"
                elif "announcement" in ch_name and "staff" not in ch_name and "content" not in ch_name:
                    emoji = "📣"

                # Apply the chosen format
                full_name = chosen_format.format(emoji=emoji, ch_name=ch_name)
                
                try:
                    if ch.get('type') == 'voice':
                        await interaction.guild.create_voice_channel(full_name, category=category)
                    else:
                        await interaction.guild.create_text_channel(full_name, category=category)
                except discord.HTTPException:
                    await asyncio.sleep(10)
                    if ch.get('type') == 'voice':
                        await interaction.guild.create_voice_channel(full_name, category=category)
                    else:
                        await interaction.guild.create_text_channel(full_name, category=category)
                
                count += 1
                
                if count % 5 == 0:
                    building_embed.set_field_at(0, name="Status", value=f"✅ {count} channels created...", inline=False)
                    await interaction.edit_original_response(embed=building_embed)
                
                await asyncio.sleep(3.5) 

        success_embed = discord.Embed(
            title="✨ Noxhelper successfully created your server!",
            description=f"Your layout has been generated with **{count}** channels.",
            color=discord.Color.green()
        )
        success_embed.add_field(name="Design Used", value=f"`{chosen_format.format(emoji='💬', ch_name='channel')}`", inline=False)
        success_embed.add_field(name="Next Step", value="Press `Cmd + R` (Mac) or `Ctrl + R` (Windows) to refresh your Discord sidebar.", inline=False)
        
        await interaction.edit_original_response(embed=success_embed)

    except Exception as e:
        await interaction.edit_original_response(content=f"❌ **Noxhelper Error:** {str(e)}")

if __name__ == "__main__":
    bot.run(os.getenv("DISCORD_TOKEN"))
