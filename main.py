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
    print("✅ Bot is online and ready!")

@bot.tree.command(name="build", description="Tell the AI what kind of server you want")
async def build(interaction: discord.Interaction, prompt: str):
    # 1. SMART CHECK: Reject lazy prompts
    if len(prompt.strip()) < 10:
        await interaction.response.send_message("❌ **That prompt is too short!** Please describe your server properly. (e.g., 'Make a gaming server with general, staff, and voice channels')", ephemeral=True)
        return

    await interaction.response.defer()
    await interaction.edit_original_response(content="🧠 AI is thinking up a full layout...")

    # 2. SMARTER SYSTEM PROMPT
    system_prompt = """
    You are an expert Discord server designer. The user will give you a prompt describing their dream server.
    You MUST output ONLY a valid JSON object. Do not include markdown formatting, just the raw JSON.
    
    The JSON must follow this exact structure:
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
    
    STRICT RULES:
    1. ALWAYS create at least 3 to 5 categories.
    2. ALWAYS create at least 3 to 5 channels per category.
    3. The server must feel complete and professional.
    4. Always include an "IMPORTANT" category (rules, announcements) and a "GENERAL" category (general chat, media).
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
        
        # Debug print so you can see the AI's layout in Railway logs
        print("AI GENERATED LAYOUT:", layout) 
        
        await interaction.edit_original_response(content="🔧 Building channels now... (This takes a few minutes, do not spam!)")

        count = 0
        for cat in layout.get("categories", []):
            cat_name = f"〔✨ {cat.get('name', 'CATEGORY')} 〕"
            category = await interaction.guild.create_category(cat_name)
            await asyncio.sleep(2)
            
            for ch in cat.get("channels", []):
                ch_name = ch.get('name', 'channel')
                emoji = ch.get('emoji', '')
                full_name = f"{emoji}┃{ch_name}"
                
                if ch.get('type') == 'voice':
                    await interaction.guild.create_voice_channel(full_name, category=category)
                else:
                    await interaction.guild.create_text_channel(full_name, category=category)
                count += 1
                await asyncio.sleep(2) # 2 second delay per channel

        await interaction.edit_original_response(content=f"✅ Done! Built **{count}** channels and categories. Refresh Discord (Cmd+R).")

    except Exception as e:
        await interaction.edit_original_response(content=f"❌ Error: {str(e)}")

if __name__ == "__main__":
    bot.run(os.getenv("DISCORD_TOKEN"))
