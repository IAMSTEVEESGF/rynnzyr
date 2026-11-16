import discord
from discord import app_commands
from discord.ext import commands
import os
import asyncio
import json
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
        await interaction.response.send_message("❌ You must be an Administrator to use this.", ephemeral=True)
        return

    if len(prompt.strip()) < 10:
        await interaction.response.send_message("❌ Please provide a more detailed prompt.", ephemeral=True)
        return

    await interaction.response.defer()
    loading_embed = discord.Embed(
        title="🏗️ Architecting Your Server",
        description="**AI is analyzing your request...**\nGenerating categories, sorting channels, and selecting the perfect emojis.",
        color=discord.Color.blurple()
    )
    await interaction.edit_original_response(embed=loading_embed)

    system_prompt = """
    You are a world-class Discord Server Architect. 
    Output ONLY a JSON object: {"categories": [{"name": "CATEGORY NAME", "channels": [{"name": "channel-name", "emoji": "💬", "type": "text"}]}]}
    
    RULES:
    1. PERFECT ORDER: IMPORTANT -> WELCOME -> GENERAL -> THEME SPECIFIC -> VOICE CHATS -> STAFF (bottom).
    2. SPECIFIC EMOJIS: Match the theme perfectly (e.g., Minecraft = ⛏️, 🐷).
    3. DENSITY: Create 5 to 8 categories, and 4 to 7 channels per category.
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
        
        building_embed = discord.Embed(
            title="🔧 Building Your Server (Please Wait)",
            description="Starting build process...",
            color=discord.Color.green()
        )
        building_embed.add_field(name="Design Style", value="`---- 《Category》 ----`\n`[ Emoji ] • channel`", inline=False)
        building_embed.add_field(name="Status", value="0 channels created", inline=False)
        await interaction.edit_original_response(embed=building_embed)

        count = 0
        
        for cat in layout.get("categories", []):
            cat_name = f"---- 《{cat.get('name', 'CATEGORY')}》 ----"
            
            # TRY/CATCH FOR CATEGORY CREATION
            try:
                category = await interaction.guild.create_category(cat_name)
            except discord.HTTPException:
                await asyncio.sleep(5) # Wait if rate limited
                category = await interaction.guild.create_category(cat_name)
                
            await asyncio.sleep(4) # Breathe between categories
            
            for ch in cat.get("channels", []):
                emoji = ch.get('emoji', '💬')
                ch_name = ch.get('name', 'channel').lower()
                full_name = f"[ {emoji} ] • {ch_name}"
                
                # TRY/CATCH FOR CHANNEL CREATION
                try:
                    if ch.get('type') == 'voice':
                        await interaction.guild.create_voice_channel(full_name, category=category)
                    else:
                        await interaction.guild.create_text_channel(full_name, category=category)
                except discord.HTTPException as e:
                    # If Discord says "Slow down", we wait 10 seconds and try again
                    print(f"Rate limited! Waiting 10s... {e}")
                    await asyncio.sleep(10)
                    if ch.get('type') == 'voice':
                        await interaction.guild.create_voice_channel(full_name, category=category)
                    else:
                        await interaction.guild.create_text_channel(full_name, category=category)
                
                count += 1
                
                # UPDATE THE EMBED EVERY 5 CHANNELS
                if count % 5 == 0:
                    building_embed.set_field_at(1, name="Status", value=f"✅ {count} channels created...", inline=False)
                    await interaction.edit_original_response(embed=building_embed)
                
                # MAXIMUM SAFETY DELAY
                await asyncio.sleep(5) 

        # Success Embed
        success_embed = discord.Embed(
            title="✅ Server Built Successfully!",
            description=f"Your professional layout has been generated with **{count}** channels.",
            color=discord.Color.green()
        )
        success_embed.add_field(name="Next Step", value="Press `Cmd + R` (Mac) or `Ctrl + R` (Windows) to refresh your Discord sidebar.", inline=False)
        
        await interaction.edit_original_response(embed=success_embed)

    except Exception as e:
        await interaction.edit_original_response(content=f"❌ **AI Error:** {str(e)}")

if __name__ == "__main__":
    bot.run(os.getenv("DISCORD_TOKEN"))
