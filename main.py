import asyncio
import json
import os
import re
from contextlib import asynccontextmanager

import discord
import httpx
import uvicorn
from discord import app_commands
from discord.ext import commands
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from openai import AsyncOpenAI
from pydantic import BaseModel, Field

CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")
REDIRECT_URI = os.getenv("REDIRECT_URI")
intents = discord.Intents.default()
intents.guilds = True
bot = commands.Bot(command_prefix="!", intents=intents)
undo_snapshots: dict[int, list[str]] = {}

# Fixed reference foundations. General intentionally ends at suggestions;
# personalized categories are separate and follow these sections.
CORE_LAYOUT = [
    {"name": "──── ⟪STAFF GENERAL⟫ ────", "private": True, "channels": [
        ("📚", "staff-rules", "text"), ("📣", "staff-announcements", "text"),
        ("💬", "staff-chat", "text"), ("🎉", "staff-promotions", "text"),
        ("🗂️", "staff-logs", "text"), ("⚠️", "staff-demotions", "text"), ("🎙️", "staff-vc", "voice")
    ]},
    {"name": "──── ⟪WELCOME⟫ ────", "private": False, "channels": [
        ("🛤️", "invite-tracker", "text"), ("👋", "welcome", "text"), ("🕊️", "goodbye", "text")
    ]},
    {"name": "──── ⟪VERIFICATION⟫ ────", "private": False, "channels": [("✅", "verification", "text")]},
    {"name": "──── ⟪IMPORTANT⟫ ────", "private": False, "channels": [
        ("📚", "rules", "text"), ("📣", "announcements", "text"), ("📊", "sab-leaks", "text"),
        ("🚀", "server-boosts", "text"), ("⚡", "boosters-rewards", "text"), ("📊", "polls", "text"),
        ("⚠️", "scammers", "text"), ("📝", "applications", "text"), ("🔄", "server-updates", "text"),
        ("🏅", "hall-of-fame", "text"), ("🎬", "content", "text"), ("🎟️", "support-ticket", "text")
    ]},
    {"name": "──── ⟪MIDDLEMAN⟫ ────", "private": False, "channels": [
        ("💫", "verified-middleman", "text"), ("🎫", "middleman-ticket", "text"), ("✅", "middleman-vouches", "text")
    ]},
    {"name": "──── ⟪GIVEAWAYS⟫ ────", "private": False, "channels": [
        ("🎉", "giveaways", "text"), ("🎰", "flash-giveaways", "text"),
        ("📸", "giveaways-vouches", "text"), ("🎮", "giveaways-vc", "voice")
    ]},
    {"name": "──── ⟪GENERAL⟫ ────", "private": False, "channels": [
        ("💬", "general", "text"), ("📸", "media", "text"), ("⚙️", "commands", "text"),
        ("📊", "levels", "text"), ("🛠️", "suggestions", "text")
    ]}
]

EMOJI_BY_TOPIC = {
    "rule": "📚", "announce": "📣", "news": "📰", "update": "🔄", "poll": "🗳️",
    "welcome": "👋", "intro": "👋", "goodbye": "🕊️", "invite": "🛤️", "verify": "✅",
    "role": "🎭", "general": "💬", "chat": "🗨️", "discussion": "🗣️", "media": "📸",
    "photo": "📷", "video": "🎥", "clip": "🎞️", "stream": "📡", "content": "🎬",
    "meme": "😂", "suggest": "🛠️", "feedback": "📝", "help": "🆘", "support": "🎟️",
    "ticket": "🎫", "faq": "❓", "bug": "🐛", "staff": "🛡️", "mod": "🛡️",
    "log": "🗂️", "application": "📋", "apply": "📋", "promotion": "🎉", "demotion": "⚠️",
    "boost": "🚀", "reward": "🎁", "giveaway": "🎁", "flash": "⚡", "vouch": "✅",
    "middleman": "🤝", "trade": "💱", "market": "🛒", "shop": "🏪", "sell": "🏷️",
    "buy": "💰", "auction": "🔨", "scam": "🚨", "report": "🚨", "level": "📈",
    "leaderboard": "🏆", "hall": "🏅", "command": "⚙️", "bot": "🤖", "voice": "🔊",
    "vc": "🎙️", "music": "🎵", "game": "🎮", "gaming": "🎮", "lfg": "🔎",
    "team": "👥", "squad": "🪖", "match": "⚔️", "rank": "🏆", "tournament": "🥇",
    "scrim": "🥊", "minecraft": "⛏️", "roblox": "🧱", "fortnite": "🪂", "valorant": "🎯",
    "fan": "💖", "art": "🎨", "creator": "✨", "collab": "🤝", "event": "📅",
    "calendar": "📅", "resource": "🧰", "guide": "🧭", "tutorial": "🧑‍🏫", "idea": "💡",
    "introductions": "👋", "memes": "😂", "clips": "🎞️"
}
EMOJI_POOL = ["🌟", "🧩", "🪄", "🧿", "🌈", "🪐", "🦋", "🍀", "🔥", "💎", "🎯", "🧸", "🪷", "🌙", "🪄", "🎨", "🪙", "🧠", "🪁", "💫", "🔮", "🧵", "🎪", "🪸", "🪻", "🧃", "🪩", "🧊", "🧪", "🧭"]


def get_ai_client():
    key = os.getenv("GROQ_API_KEY")
    if not key:
        raise RuntimeError("GROQ_API_KEY is not configured in Railway Variables")
    return AsyncOpenAI(base_url="https://api.groq.com/openai/v1", api_key=key)


@asynccontextmanager
async def lifespan(app: FastAPI):
    token = os.getenv("DISCORD_TOKEN")
    if token:
        asyncio.create_task(bot.start(token))
    else:
        print("DISCORD_TOKEN is missing")
    yield
    if not bot.is_closed():
        await bot.close()


app = FastAPI(title="Rynnzyr Discord Architect", lifespan=lifespan)


class GuildRequest(BaseModel):
    guild_id: int
    prompt: str = ""


class PlanRequest(BaseModel):
    guild_id: int
    prompt: str = Field(min_length=3, max_length=1000)


class ApplyRequest(BaseModel):
    guild_id: int
    plan: dict


def clean_text(value, limit=100):
    text = str(value or "").replace("@everyone", "everyone").replace("@here", "here")
    text = re.sub(r"[\r\n\t\x00-\x1f]", " ", text)
    return " ".join(text.split())[:limit].strip()


def slug_channel(value):
    raw = clean_text(value, 100)
    # Strip existing decorative wrappers/emoji to derive a clean semantic slug.
    raw = re.sub(r"^[〔【\[（(].*?[〕】\]）)]\s*[・•|:：-]*\s*", "", raw)
    raw = re.sub(r"^[^\w]+", "", raw, flags=re.UNICODE)
    raw = raw.lower().replace("_", "-")
    raw = "".join(c if c.isalnum() or c in "- " else "-" for c in raw)
    return "-".join(raw.split()).strip("-")[:72] or "chat"


def smart_emoji(slug, category, used):
    words = slug.replace("-", " ").split()
    # Prefer the most specific meaning; never blindly reuse one model-generated emoji.
    ordered = sorted(EMOJI_BY_TOPIC.items(), key=lambda pair: len(pair[0]), reverse=True)
    chosen = next((emoji for key, emoji in ordered if key in slug and emoji not in used), None)
    if chosen is None:
        # Stable, category-sensitive fallback gives varied icons for novel channel concepts.
        seed = sum(ord(c) for c in f"{category}:{slug}")
        for offset in range(len(EMOJI_POOL)):
            candidate = EMOJI_POOL[(seed + offset) % len(EMOJI_POOL)]
            if candidate not in used:
                chosen = candidate
                break
    chosen = chosen or "💬"
    used.add(chosen)
    return chosen


def format_channel(value, category, used, fixed_emoji=None):
    slug = slug_channel(value)
    emoji = fixed_emoji or smart_emoji(slug, category, used)
    used.add(emoji)
    return f"〔{emoji}〕・{slug}"


def is_voice(channel):
    return isinstance(channel, (discord.VoiceChannel, discord.StageChannel))


def safe_state(guild):
    return {
        "name": guild.name,
        "categories": [{"name": category.name, "channels": [{"name": channel.name, "type": "voice" if is_voice(channel) else "text"} for channel in category.channels]} for category in guild.categories[:25]],
        "roles": [role.name for role in guild.roles if not role.managed][-15:]
    }


@app.get("/")
def serve_website():
    try:
        with open("index.html", encoding="utf-8") as page:
            response = HTMLResponse(page.read())
    except FileNotFoundError:
        raise HTTPException(500, "index.html is missing from the deployment")
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    return response


@app.get("/login")
def login():
    if not all((CLIENT_ID, REDIRECT_URI)):
        return HTMLResponse("Missing CLIENT_ID or REDIRECT_URI", status_code=500)
    from urllib.parse import urlencode
    query = urlencode({"client_id": CLIENT_ID, "redirect_uri": REDIRECT_URI, "response_type": "code", "scope": "identify guilds"})
    return RedirectResponse(f"https://discord.com/api/oauth2/authorize?{query}")


@app.get("/callback")
async def callback(code: str | None = None):
    if not code:
        return RedirectResponse("/?error=auth_failed")
    data = {"client_id": CLIENT_ID, "client_secret": CLIENT_SECRET, "grant_type": "authorization_code", "code": code, "redirect_uri": REDIRECT_URI}
    async with httpx.AsyncClient() as client:
        response = await client.post("https://discord.com/api/oauth2/token", data=data, headers={"Content-Type": "application/x-www-form-urlencoded"})
    token = response.json().get("access_token")
    if not token:
        return RedirectResponse("/?error=auth_failed")
    redirect = RedirectResponse("/?logged_in=true")
    redirect.set_cookie("discord_token", token, httponly=True, samesite="lax", max_age=604800)
    return redirect


@app.get("/api/user-guilds")
async def user_guilds(request: Request):
    if not bot.is_ready():
        return {"error": "The Discord bot is starting. Please try again."}
    token = request.cookies.get("discord_token")
    if not token:
        raise HTTPException(401, "Not logged in")
    async with httpx.AsyncClient() as client:
        response = await client.get("https://discord.com/api/users/@me/guilds", headers={"Authorization": f"Bearer {token}"})
    if response.status_code != 200:
        raise HTTPException(401, "Discord login expired")
    result = []
    for item in response.json():
        permissions = int(item.get("permissions", 0))
        if not (permissions & 0x8 or permissions & 0x20):
            continue
        gid = int(item["id"])
        has_bot = bot.get_guild(gid) is not None
        result.append({"id": gid, "name": item["name"], "icon": item.get("icon"), "has_bot": has_bot,
                       "invite_url": None if has_bot else f"https://discord.com/api/oauth2/authorize?client_id={CLIENT_ID}&permissions=268435472&scope=bot%20applications.commands&guild_id={gid}"})
    return {"guilds": result}


def get_guild_or_error(guild_id):
    guild = bot.get_guild(guild_id)
    if guild is None:
        raise HTTPException(404, "Bot is not in this server")
    me = guild.me
    if me is None:
        raise HTTPException(503, "Bot membership is not available yet")
    if not me.guild_permissions.manage_channels or not me.guild_permissions.manage_roles:
        raise HTTPException(403, "Bot needs Manage Channels and Manage Roles permissions")
    return guild


def sanitize_plan(plan):
    roles = []
    for role in (plan.get("roles") or [])[:12]:
        if not isinstance(role, dict):
            continue
        name = clean_text(role.get("name"), 100)
        if name.lower() in {"everyone", "here", "admin", "administrator", "bot"}:
            continue
        try:
            color = int(str(role.get("color", "#5865F2")).lstrip("#"), 16)
        except (ValueError, TypeError):
            color = 0x5865F2
        roles.append({"name": name, "color": max(0, min(color, 0xFFFFFF)), "hoist": bool(role.get("hoist")), "mentionable": bool(role.get("mentionable"))})

    # Always reconstruct the core from constants so AI output cannot append channels
    # after suggestions, duplicate core sections, or change privacy/order.
    categories = []
    for core in CORE_LAYOUT:
        used = set()
        entries = []
        for emoji, channel_name, kind in core["channels"]:
            entries.append({"name": format_channel(channel_name, core["name"], used, emoji), "type": kind, "topic": ""})
        categories.append({"name": core["name"], "staff_only": core["private"], "channels": entries})

    # Only genuinely custom categories are accepted. Nothing from model output is
    # merged into the seven reference categories, so the General section ends at Suggestions.
    extras = []
    known_core = {"staff general", "staff", "welcome", "verification", "important", "server information", "middleman", "giveaways", "general", "community"}
    total = sum(len(item["channels"]) for item in categories)
    seen_categories = set()
    for item in (plan.get("categories") or [])[:15]:
        if not isinstance(item, dict):
            continue
        name = clean_text(item.get("name"), 100)
        normalized = re.sub(r"[^a-z0-9 ]", "", name.lower()).strip()
        if normalized in known_core or any(normalized == core_name for core_name in known_core):
            continue
        cat_key = re.sub(r"[^a-z0-9]", "", name.lower())
        if not cat_key or cat_key in seen_categories:
            continue
        seen_categories.add(cat_key)
        used = set()
        channels = []
        for channel in (item.get("channels") or [])[:10]:
            if not isinstance(channel, dict) or total >= 100:
                continue
            slug = slug_channel(channel.get("name"))
            emoji = smart_emoji(slug, name, used)
            kind = "voice" if channel.get("type") == "voice" else "text"
            channels.append({"name": f"〔{emoji}〕・{slug}", "type": kind,
                             "topic": clean_text(channel.get("topic"), 1024) if kind == "text" else ""})
            total += 1
        if channels:
            extras.append({"name": name, "staff_only": False, "channels": channels})
    return {"summary": clean_text(plan.get("summary") or "A custom server blueprint tailored to your community", 500), "roles": roles, "categories": categories + extras}


async def generate_plan(guild, prompt):
    instructions = f"""
Design only the CUSTOM categories for this server. The code creates the fixed reference foundation before your output, so DO NOT output or alter staff, welcome, verification, important, middleman, giveaways, or general categories. General must end at suggestions. Make 3-7 truly useful extra categories specifically for the user's request; avoid broad filler, duplicate purposes, and generic categories. Make names, channels, and topics deeply relevant to their exact community. Examples: a trading request could get 💎 MIDDLEMAN SERVICE, 💱 TRADING FLOOR, 🧾 VOUCHERS; a gaming request could get 🎮 GAME LOUNGE, 🔎 FIND A TEAM, 🏆 COMPETITIVE; a creator request could get 🎬 CONTENT STUDIO, 📡 LIVE NOW, 🎨 FAN WORKS. Use only fitting examples. Make channel names short descriptive slugs and assign a DIFFERENT semantically appropriate emoji to each channel—never reuse one emoji throughout a category. Include helpful voice rooms where appropriate. Return JSON only: {{"summary":"...","roles":[{{"name":"Moderator","color":"#5865F2","hoist":false,"mentionable":false}}],"categories":[{{"name":"🎮 : GAME LOUNGE : 🎮","channels":[{{"name":"game-chat","type":"text","topic":"Chat about the game"}},{{"name":"party-voice","type":"voice"}}]}}]}}. Max 12 safe roles, 7 custom categories, 10 channels/category, 60 custom channels. Never output the fixed foundation categories.
Current server context: {json.dumps(safe_state(guild), ensure_ascii=False)}
"""
    response = await get_ai_client().chat.completions.create(
        model=os.getenv("GROQ_MODEL", "openai/gpt-oss-20b"),
        messages=[{"role": "system", "content": instructions}, {"role": "user", "content": prompt}],
        temperature=0.8, max_tokens=5000, response_format={"type": "json_object"})
    content = response.choices[0].message.content
    if not content:
        raise RuntimeError("AI returned an empty design")
    return sanitize_plan(json.loads(content))


async def apply_guild_plan(guild, plan):
    plan = sanitize_plan(plan)
    created_ids, created = [], []
    created_roles = {}
    for spec in plan["roles"]:
        role = discord.utils.get(guild.roles, name=spec["name"])
        if role is None:
            role = await guild.create_role(name=spec["name"], colour=discord.Colour(spec["color"]), hoist=spec["hoist"], mentionable=spec["mentionable"], reason="Created by Rynnzyr")
            created_ids.append(f"role:{role.id}")
            created.append(f"Role: {role.name}")
        created_roles[role.name.lower()] = role
    staff_role = next((role for name, role in created_roles.items() if "staff" in name or "moderator" in name or name == "mod"), None)
    staff_role = staff_role or discord.utils.get(guild.roles, name="Staff")
    if staff_role is None:
        staff_role = await guild.create_role(name="Staff", colour=discord.Colour(0x5865F2), reason="Private staff category access")
        created_ids.append(f"role:{staff_role.id}")
        created.append("Role: Staff — assign to trusted staff members")

    # First create/find every category in blueprint order, then explicitly reorder.
    resolved = []
    for spec in plan["categories"]:
        private = spec["staff_only"]
        overwrites = {}
        if private:
            overwrites = {guild.default_role: discord.PermissionOverwrite(view_channel=False),
                          staff_role: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True, connect=True, speak=True)}
        category = discord.utils.get(guild.categories, name=spec["name"])
        if category is None:
            category = await guild.create_category(spec["name"], overwrites=overwrites, reason="Rynnzyr server blueprint")
            created_ids.append(f"category:{category.id}")
            created.append(f"Category: {category.name}")
        elif private:
            await category.edit(overwrites=overwrites, reason="Secure staff category")
        resolved.append((category, spec, private))

    for position, (category, _, _) in enumerate(resolved):
        await category.edit(position=position, reason="Arrange categories in blueprint order")

    for category, spec, private in resolved:
        for position, channel_spec in enumerate(spec["channels"]):
            channel = discord.utils.get(category.channels, name=channel_spec["name"])
            if channel is None:
                if channel_spec["type"] == "voice":
                    channel = await guild.create_voice_channel(channel_spec["name"], category=category, reason="Rynnzyr server blueprint")
                else:
                    channel = await guild.create_text_channel(channel_spec["name"], category=category, topic=channel_spec["topic"] or None, reason="Rynnzyr server blueprint")
                created_ids.append(f"channel:{channel.id}")
                created.append(f"{channel_spec['type'].title()}: {channel_spec['name']}")
            else:
                await channel.edit(position=position, sync_permissions=private, reason="Arrange channels in blueprint order")
            await asyncio.sleep(0.2)
    undo_snapshots[guild.id] = created_ids
    return created


def make_plan_embed(guild, plan):
    embed = discord.Embed(title=f"✨ {guild.name} — Server blueprint", description=plan["summary"], color=0x7C83FF)
    for category in plan["categories"]:
        if len(embed.fields) >= 24:
            break
        lines = [("🔊 " if ch["type"] == "voice" else "# ") + ch["name"] for ch in category["channels"]]
        if category["staff_only"]:
            lines.append("🔒 Staff-only — access through the Staff role")
        embed.add_field(name=category["name"], value=("\n".join(lines) or "No channels")[:1024], inline=True)
    embed.set_footer(text="Reference categories first; custom channels are tailored to your prompt. Review, then build or cancel.")
    return embed


class BlueprintView(discord.ui.View):
    def __init__(self, guild, plan, author_id):
        super().__init__(timeout=180)
        self.guild, self.plan, self.author_id, self.finished = guild, plan, author_id, False

    async def interaction_check(self, interaction):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("Only the person who requested this blueprint can use these buttons.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Build this server", style=discord.ButtonStyle.success, emoji="🏗️")
    async def build_button(self, interaction, button):
        if self.finished:
            await interaction.response.send_message("This blueprint has already been handled.", ephemeral=True)
            return
        self.finished = True
        button.disabled = True
        self.cancel_button.disabled = True
        await interaction.response.edit_message(view=self)
        try:
            changes = await apply_guild_plan(self.guild, self.plan)
            report = "\n".join(f"• {line}" for line in changes[:35]) or "The blueprint already exists."
            await interaction.followup.send(f"✅ **Server built!**\n{report}\n\nAssign trusted members to **Staff** for private staff channels.", ephemeral=True)
        except discord.Forbidden:
            await interaction.followup.send("Discord denied a change. Check Manage Channels/Manage Roles permissions and role position.", ephemeral=True)
        except Exception as exc:
            print(f"Blueprint apply failed: {type(exc).__name__}: {exc}")
            await interaction.followup.send("Build failed; check Railway logs. Some earlier changes may already have applied.", ephemeral=True)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary, emoji="✖️")
    async def cancel_button(self, interaction, button):
        self.finished = True
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(content="Blueprint cancelled — no changes made.", embed=None, view=self)


@app.post("/api/plan")
async def create_plan(req: PlanRequest):
    try:
        return {"plan": await generate_plan(get_guild_or_error(req.guild_id), req.prompt)}
    except Exception as exc:
        raise HTTPException(502, f"AI planning failed: {exc}")


@app.post("/api/apply")
async def apply_plan(req: ApplyRequest):
    try:
        return {"success": True, "created": await apply_guild_plan(get_guild_or_error(req.guild_id), req.plan)}
    except discord.Forbidden:
        raise HTTPException(403, "Bot is missing Discord permissions")
    except discord.HTTPException as exc:
        raise HTTPException(502, f"Discord rejected a change: {exc.text}")


@app.post("/api/undo")
async def undo(req: GuildRequest):
    guild = get_guild_or_error(req.guild_id)
    ids = undo_snapshots.pop(guild.id, [])
    deleted = 0
    for entry in reversed(ids):
        kind, raw_id = entry.split(":", 1)
        item_id = int(raw_id)
        item = discord.utils.get(guild.roles, id=item_id) if kind == "role" else guild.get_channel(item_id)
        if item:
            try:
                await item.delete(reason="Undo by Rynnzyr")
                deleted += 1
                await asyncio.sleep(0.2)
            except discord.Forbidden:
                pass
    return {"success": True, "deleted": deleted}


@bot.tree.command(name="ping", description="Check that Rynnzyr is online")
async def ping(interaction: discord.Interaction):
    await interaction.response.send_message("Rynnzyr is online and ready.", ephemeral=True)


@bot.tree.command(name="design", description="Preview and build a custom AI-designed server")
@app_commands.describe(prompt="Describe your community and the server you want")
async def design(interaction: discord.Interaction, prompt: str):
    if interaction.guild is None:
        await interaction.response.send_message("Use this command inside a server.", ephemeral=True)
        return
    member = interaction.user
    if not isinstance(member, discord.Member) or not (member.guild_permissions.manage_guild or member.guild_permissions.administrator):
        await interaction.response.send_message("You need Manage Server permission to use this command.", ephemeral=True)
        return
    me = interaction.guild.me
    if me is None or not (me.guild_permissions.manage_channels and me.guild_permissions.manage_roles):
        await interaction.response.send_message("I need Manage Channels and Manage Roles permissions.", ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True, thinking=True)
    try:
        plan = await generate_plan(interaction.guild, prompt[:1000])
        await interaction.followup.send(embed=make_plan_embed(interaction.guild, plan), view=BlueprintView(interaction.guild, plan, interaction.user.id), ephemeral=True)
    except Exception as exc:
        print(f"/design failed: {type(exc).__name__}: {exc}")
        message = str(exc) if "GROQ_API_KEY" in str(exc) else "I couldn't design that layout. Check Railway logs and AI API configuration."
        await interaction.followup.send(message[:1800], ephemeral=True)


@bot.event
async def on_ready():
    try:
        synced = await bot.tree.sync()
        print(f"Bot online as {bot.user}; synced {len(synced)} application commands")
    except Exception as exc:
        print(f"Command sync failed: {type(exc).__name__}: {exc}")


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8080")))
