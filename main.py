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

# Store the last action so we can Undo it
last_actions = {}

class UndoView(discord.ui.View):
    def __init__(self, guild_id):
        super().__init__(timeout=300)
        self.guild_id = guild_id

    @discord.ui.button(label="Undo", style=discord.ButtonStyle.danger)
    async def undo_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.guild_id in last_actions:
            await interaction.response.defer()
            guild = interaction.guild
            
            for channel_id, old_name in last_actions[self.guild_id].items():
                channel = guild.get_channel(channel_id)
                if channel:
                    try:
                        await channel.edit(name=old_name)
                        await asyncio.sleep(2)
                    except:
                        pass
            
            del last_actions[self.guild_id]
            await interaction.edit_original_response(content="✅ Successfully undid the last action.", view=None)
        else:
            await interaction.response.send_message("❌ Nothing to undo!", ephemeral=True)

@bot.event
async def on_ready():
    await bot.tree.sync()
    print("✅ Bot online!")

@bot.tree.command(name="tidy", description="Use AI to tidy up your channels")
@app_commands.describe(prompt="E.g., 'Move all old channels to an ARCHIVE category'")
async def tidy(interaction: discord.Interaction, prompt: str):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Admin only.", ephemeral=True)
        return

    await interaction.response.defer()
    await interaction.edit_original_response(content="🧠 **AI is analyzing your server...**")

    guild = interaction.guild
    
    # Create a clean JSON list of current channels for the AI to read
    server_state = []
    for ch in guild.channels:
        if isinstance(ch, discord.CategoryChannel): continue
        cat_name = ch.category.name if ch.category else "None"
        server_state.append({
            "id": ch.id, 
            "name": ch.name, 
            "category": cat_name
        })
        
    system_prompt = f"""
    You are an AI Discord server manager. The user wants to tidy up their server. 
    
    Here is the current server layout in JSON:
    {json.dumps(server_state)}
    
    The user's request: "{prompt}"
    
    Output ONLY a valid JSON object with a list of "actions" to perform.
    Do NOT wrap it in markdown. Do NOT add any other text.
    
    Formats allowed:
    1. Rename: {{"action": "rename", "channel_id": 12345, "new_name": "new-name"}}
    2. Move: {{"action": "move", "channel_id": 12345, "new_category": "ARCHIVE"}}
    """

    try:
        # Using a much smarter model for this specific task
        response = await ai_client.chat.completions.create(
            model="llama-3.3-70b-versatile", 
            messages=[{"role": "system", "content": system_prompt}],
            response_format={"type": "json_object"}
        )
        
        raw_content = response.choices[0].message.content
        
        # CLEANER: Strip out accidental markdown blocks
        if "```json" in raw_content:
            raw_content = raw_content.split("```json")[1].split("```")[0].strip()
        elif "```" in raw_content:
            raw_content = raw_content.split("```")[1].split("```")[0].strip()

        ai_data = json.loads(raw_content)
        actions = ai_data.get("actions", [])
        
        if not actions:
            await interaction.edit_original_response(content="😴 AI decided no changes were needed.")
            return

        # Save state for UNDO
        last_actions[guild.id] = {ch.id: ch.name for ch in guild.channels if not isinstance(ch, discord.CategoryChannel)}

        steps_done = []
        
        for act in actions:
            ch_id = act.get("channel_id")
            ch = guild.get_channel(ch_id)
            if not ch: continue

            if act.get("action") == "rename":
                new_name = act.get("new_name", "renamed")
                await ch.edit(name=new_name)
                steps_done.append(f"Renamed {ch.name} to {new_name}")
                await asyncio.sleep(2)

            elif act.get("action") == "move":
                cat_name = act.get("new_category", "ARCHIVE")
                category = discord.utils.get(guild.categories, name=cat_name)
                if not category:
                    category = await guild.create_category(cat_name)
                await ch.edit(category=category)
                steps_done.append(f"Moved {ch.name} to {cat_name}")
                await asyncio.sleep(2)

        # Create the final success embed
        embed = discord.Embed(
            title="✅ AI Finished Task",
            description=f"**{len(steps_done)} steps done**",
            color=discord.Color.green()
        )
        # Show up to 10 steps to keep the message clean
        embed.add_field(name="Changes made:", value="\n".join([f"✓ {s}" for s in steps_done[:10]]), inline=False)
        if len(steps_done) > 10:
            embed.set_footer(text=f"And {len(steps_done) - 10} more changes...")
        
        # Add the Undo Button
        view = UndoView(guild.id)
        await interaction.edit_original_response(content=None, embed=embed, view=view)

    except Exception as e:
        await interaction.edit_original_response(content=f"❌ Error: {str(e)}")

if __name__ == "__main__":
    bot.run(os.getenv("DISCORD_TOKEN"))
