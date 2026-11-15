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
    # 1. Permission Check
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ You must be an Administrator to use this.", ephemeral=True)
        return

    if len(prompt.strip()) < 10:
        await interaction.response.send_message("❌ Please provide a more detailed prompt (e.g., 'Make a professional Minecraft network').", ephemeral=True)
        return

    # 2. The Professional Loading Embed
    await interaction.response.defer()
    loading_embed = discord.Embed(
        title="🏗️ Architecting Your Server",
        description="**AI is analyzing your request...**\nGenerating categories, sorting channels, and selecting the perfect emojis.",
        color=discord.Color.blurple()
    )
    loading_embed.set_footer(text="This takes a few minutes to prevent Discord rate limits.")
    await interaction.edit_original_response(embed=loading_embed)

    # 3. The Master System Prompt (Humanistic & Professional)
    system_prompt = """
    You are a world-class Discord Server Architect. You build highly realistic, professional, and human-designed server layouts for top-tier communities.
    The user will give you a theme. You must output ONLY a JSON object.
    
    Format:
    {
      "categories": [
        {
          "name": "CATEGORY NAME",
          "channels": [
            {"name": "channel-name", "emoji": "💬", "type": "text"},
            {"name": "voice-channel", "emoji": "🔊", "type": "voice"}
          ]
        }
      ]
    }
    
    PROFESSIONAL RULES:
    1. PERFECT ORDER:
       - Start with "IMPORTANT" (Rules, Announcements).
       - Then "WELCOME" (Welcome, Verify).
       - Then "GENERAL" (General chat, media).
       - Then 2-4 THEME SPECIFIC categories (e.g., for Minecraft: "MINECRAFT NETWORK", "GAMEPLAY"). Adapt perfectly to the user's theme!
       - Then "VOICE CHATS".
       - ALWAYS put "STAFF" at the very bottom.
    2. EXACT EMOJIS: You MUST use highly specific, matching emojis for EVERY channel. Do not leave any emoji blank. (e.g., 📜 for rules, 🎫 for tickets, ⛏️ for mining, 💰 for economy).
    3. DENSITY: Create 5 to 8 categories, and 4 to 7 channels per category. Make the server feel massive and alive.
    4. HUMAN TOUCH: Name channels exactly how human server owners do (e.g., "general-chat", "media", "looking-for-group", "support-ticket").
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
        
        # 4. Building Embed
        building_embed = discord.Embed(
            title="🔧 Building Your Server",
            description="AI has finished designing the layout. Creating channels now...\n**Do not spam commands.**",
            color=discord.Color.green()
        )
        building_embed.add_field(name="Design Style", value="`---- 《Category》 ----`\n`[ Emoji ] • channel`", inline=False)
        await interaction.edit_original_response(embed=building_embed)

        count = 0
        
        for cat in layout.get("categories", []):
            # EXACT CATEGORY FORMAT FROM YOUR SCREENSHOT
            cat_name = f"---- 《{cat.get('name', 'CATEGORY')}》 ----"
            category = await interaction.guild.create_category(cat_name)
            await asyncio.sleep(2)
            
            for ch in cat.get("channels", []):
                emoji = ch.get('emoji', '💬') # Fallback to chat emoji if AI fails
                ch_name = ch.get('name', 'channel').lower()
                
                # EXACT CHANNEL FORMAT FROM YOUR SCREENSHOT
                full_name = f"[ {emoji} ] • {ch_name}"
                
                if ch.get('type') == 'voice':
                    await interaction.guild.create_voice_channel(full_name, category=category)
                else:
                    await interaction.guild.create_text_channel(full_name, category=category)
                
                count += 1
                await asyncio.sleep(2.5) # 2.5s delay for safety

        # 5. Success Embed
        success_embed = discord.Embed(
            title="✅ Server Built Successfully!",
            description=f"Your professional layout has been generated with **{count}** channels.",
            color=discord.Color.green()
        )
        success_embed.add_field(name="Next Step", value="Press `Cmd + R` (Mac) or `Ctrl + R` (Windows) to refresh your Discord sidebar and see the magic.", inline=False)
        success_embed.set_footer(text="Built by AI Architect")
        
        await interaction.edit_original_response(embed=success_embed)

    except Exception as e:
        await interaction.edit_original_response(content=f"❌ **AI Error:** {str(e)}\n*(If the AI hit a rate limit, wait a minute and try again).*")

if __name__ == "__main__":
    bot.run(os.getenv("DISCORD_TOKEN"))
