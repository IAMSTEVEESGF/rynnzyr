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
        await interaction.response.send_message("❌ Admin only.", ephemeral=True)
        return

    await interaction.response.defer()
    await interaction.edit_original_response(content="🏗️ **AI is designing your server...**")

    # --- THE ULTIMATE PROMPT ---
    system_prompt = """
    You are a world-class Discord Server Architect. 
    Output ONLY JSON: {"categories": [{"name": "CATEGORY", "channels": [{"name": "channel-name", "emoji": "💬", "type": "text"}]}]}
    
    RULES FOR CATEGORIES (STRICT ORDER):
    1. IMPORTANT (Rules, Announcements, Updates)
    2. WELCOME (Welcome, Verify)
    3. GENERAL (General, Media, Bots)
    4. THEME SPECIFIC (Game/Community specific channels)
    5. VOICE CHATS (All VCs)
    6. STAFF (Staff Chat, Mod Logs, Admin Chat) - ALWAYS AT THE BOTTOM.
    
    RULES FOR CHANNELS & EMOJIS:
    - You MUST create a channel named exactly "general". It MUST have the emoji 💬.
    - You MUST create a channel named exactly "announcements". It MUST have the emoji 📣.
    - DO NOT use the same emoji for every channel. 
    - For all other channels, analyze the channel name and generate a highly specific, cool, and sensible emoji (e.g., for "mod-logs" use 🛡️, for "trading" use 💰, for "rules" use 📜, for "polls" use 📊).
    - Make sure "mod-logs" or any log channels are inside the STAFF category, NOT in IMPORTANT/Announcements.
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
        
        # Pick ONE design for the whole server
        NBSP = "\u00A0"
        formats = [
            f"〔{{emoji}}〕・{NBSP}{{name}}",
            f"{{emoji}}┃{{name}}",
            f"〘{{emoji}}〙・{NBSP}{{name}}",
            f"{{emoji}}・{NBSP}{{name}}"
        ]
        chosen_format = random.choice(formats)

        building_embed = discord.Embed(
            title="🔧 Building Your Server",
            description=f"AI is creating channels logically.\nUsing design: `{chosen_format.format(emoji='💬', name='channel')}`",
            color=discord.Color.green()
        )
        building_embed.add_field(name="Status", value="0 channels created", inline=False)
        await interaction.edit_original_response(embed=building_embed)

        count = 0
        
        for cat in layout.get("categories", []):
            cat_name = f"----{NBSP}《{cat.get('name', 'CATEGORY')}》{NBSP}----"
            
            try:
                category = await interaction.guild.create_category(cat_name)
            except discord.HTTPException:
                await asyncio.sleep(5)
                category = await interaction.guild.create_category(cat_name)
                
            await asyncio.sleep(3)
            
            for ch in cat.get("channels", []):
                ch_name = ch.get('name', 'channel').lower()
                emoji = ch.get('emoji', '💬')
                
                # --- PYTHON FAILSAFE FOR SPECIFIC EMOJIS ---
                if "general" in ch_name:
                    emoji = "💬"
                elif "announcement" in ch_name:
                    emoji = "📣"
                # -------------------------------------------

                full_name = chosen_format.format(emoji=emoji, name=ch_name)
                
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
                
                await asyncio.sleep(4) 

        success_embed = discord.Embed(
            title="✅ Server Built Successfully!",
            description=f"Your professional layout has been generated with **{count}** channels.",
            color=discord.Color.green()
        )
        success_embed.add_field(name="Design Used", value=f"`{chosen_format.format(emoji='💬', name='channel')}`", inline=False)
        success_embed.add_field(name="Next Step", value="Press `Cmd + R` (Mac) or `Ctrl + R` (Windows) to refresh your Discord sidebar.", inline=False)
        
        await interaction.edit_original_response(embed=success_embed)

    except Exception as e:
        await interaction.edit_original_response(content=f"❌ **AI Error:** {str(e)}")

if __name__ == "__main__":
    bot.run(os.getenv("DISCORD_TOKEN"))
