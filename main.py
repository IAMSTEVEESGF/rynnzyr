import discord
from discord import app_commands
from discord.ext import commands
import os
import asyncio
from openai import AsyncOpenAI

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

ai_client = AsyncOpenAI(
    base_url="https://api.groq.com/openai/v1",
    api_key=os.getenv("GROQ_API_KEY") 
)

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
    
    state_lines = []
    for ch in guild.channels:
        if isinstance(ch, discord.CategoryChannel): 
            continue
        cat_name = ch.category.name if ch.category else "None"
        state_lines.append(f"{ch.id}:{ch.name}|{cat_name}")
        
    server_state_str = "\n".join(state_lines[:40])
    
    # --- NO JSON. PIPE SEPARATED LIST ONLY. ---
    system_prompt = f"""
    You are an AI Discord server manager. 
    Current server layout (Format: ID:channel-name|Category):
    {server_state_str}
    
    User request: "{prompt}"
    
    Output ONLY plain text commands. Do NOT output JSON. Do NOT use markdown.
    Use this exact format for renaming:
    RENAME|channel_id|new_name
    
    Use this exact format for moving:
    MOVE|channel_id|new_category_name
    
    Only output the commands, one per line. No other text.
    """

    try:
        response = await ai_client.chat.completions.create(
            model="openai/gpt-oss-20b", 
            messages=[{"role": "system", "content": system_prompt}],
            max_tokens=2000 
        )
        
        raw_content = response.choices[0].message.content.strip()
        
        # Parse the pipe-separated text
        steps_done = []
        last_actions[guild.id] = {ch.id: ch.name for ch in guild.channels if not isinstance(ch, discord.CategoryChannel)}

        for line in raw_content.split('\n'):
            line = line.strip()
            if not line: continue
            
            parts = [p.strip() for p in line.split('|')]
            
            if len(parts) == 3 and parts[0] == "RENAME":
                try:
                    ch_id = int(parts[1])
                    new_name = parts[2]
                    ch = guild.get_channel(ch_id)
                    if ch and ch.name != new_name:
                        await ch.edit(name=new_name)
                        steps_done.append(f"Renamed {ch.name} to {new_name}")
                        await asyncio.sleep(2)
                except Exception:
                    pass
                    
            elif len(parts) == 3 and parts[0] == "MOVE":
                try:
                    ch_id = int(parts[1])
                    cat_name = parts[2]
                    ch = guild.get_channel(ch_id)
                    if ch:
                        category = discord.utils.get(guild.categories, name=cat_name)
                        if not category:
                            category = await guild.create_category(cat_name)
                        await ch.edit(category=category)
                        steps_done.append(f"Moved {ch.name} to {cat_name}")
                        await asyncio.sleep(2)
                except Exception:
                    pass

        if not steps_done:
            await interaction.edit_original_response(content="😴 AI decided no changes were needed, or it failed to format the commands correctly.")
            return

        embed = discord.Embed(
            title="✅ AI Finished Task",
            description=f"**{len(steps_done)} steps done**",
            color=discord.Color.green()
        )
        embed.add_field(name="Changes made:", value="\n".join([f"✓ {s}" for s in steps_done[:10]]), inline=False)
        if len(steps_done) > 10:
            embed.set_footer(text=f"And {len(steps_done) - 10} more changes...")
        
        view = UndoView(guild.id)
        await interaction.edit_original_response(content=None, embed=embed, view=view)

    except Exception as e:
        await interaction.edit_original_response(content=f"❌ Error: {str(e)}")

if __name__ == "__main__":
    bot.run(os.getenv("DISCORD_TOKEN"))
