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

# Fixed reference order. Prompt-specific categories are appended after General.
CORE_LAYOUT = [
    {"key": "staff", "name": "──── ⟪STAFF GENERAL⟫ ────", "private": True, "channels": [
        ("📚", "staff-rules", "text"), ("📣", "staff-announcements", "text"), ("💬", "staff-chat", "text"),
        ("🎉", "staff-promotions", "text"), ("🗂️", "staff-logs", "text"), ("⚠️", "staff-demotions", "text"), ("🎙️", "staff-vc", "voice")]},
    {"key": "welcome", "name": "──── ⟪WELCOME⟫ ────", "private": False, "channels": [
        ("🛤️", "invite-tracker", "text"), ("👋", "welcome", "text"), ("🕊️", "goodbye", "text")]},
    {"key": "verification", "name": "──── ⟪VERIFICATION⟫ ────", "private": False, "channels": [("✅", "verification", "text")]},
    {"key": "important", "name": "──── ⟪IMPORTANT⟫ ────", "private": False, "channels": [
        ("📚", "rules", "text"), ("📣", "announcements", "text"), ("📊", "sab-leaks", "text"),
        ("🚀", "server-boosts", "text"), ("⚡", "boosters-rewards", "text"), ("📊", "polls", "text"),
        ("⚠️", "scammers", "text"), ("📝", "applications", "text"), ("🔄", "server-updates", "text"),
        ("🏅", "hall-of-fame", "text"), ("🎬", "content", "text"), ("🎟️", "support-ticket", "text")]},
    {"key": "middleman", "name": "──── ⟪MIDDLEMAN⟫ ────", "private": False, "channels": [
        ("💫", "verified-middleman", "text"), ("🎫", "middleman-ticket", "text"), ("✅", "middleman-vouches", "text")]},
    {"key": "giveaways", "name": "──── ⟪GIVEAWAYS⟫ ────", "private": False, "channels": [
        ("🎉", "giveaways", "text"), ("🎰", "flash-giveaways", "text"), ("📸", "giveaways-vouches", "text"), ("🎮", "giveaways-vc", "voice")]},
    {"key": "general", "name": "──── ⟪GENERAL⟫ ────", "private": False, "channels": [
        ("💬", "general", "text"), ("📸", "media", "text"), ("⚙️", "commands", "text"), ("📊", "levels", "text"), ("🛠️", "suggestions", "text")]},
]

EMOJI_RULES = {
    "announcement": "📣", "announce": "📣", "rule": "📚", "leak": "📊", "poll": "🗳️", "boost": "🚀", "reward": "🎁",
    "scam": "⚠️", "application": "📝", "update": "🔄", "hall": "🏅", "content": "🎬", "support": "🎟️", "ticket": "🎫",
    "middleman": "🤝", "verified": "✅", "vouch": "✅", "giveaway": "🎁", "flash": "⚡", "invite": "🛤️", "welcome": "👋",
    "goodbye": "🕊️", "verify": "✅", "intro": "👋", "general": "💬", "chat": "🗨️", "media": "📸", "photo": "📷",
    "video": "🎥", "clip": "🎞️", "stream": "📡", "meme": "😂", "suggest": "🛠️", "feedback": "📝", "help": "🆘",
    "faq": "❓", "bug": "🐛", "staff": "🛡️", "log": "🗂️", "promotion": "🎉", "demotion": "⚠️", "trade": "💱",
    "market": "🛒", "shop": "🏪", "sell": "🏷️", "buy": "💰", "auction": "🔨", "report": "🚨", "level": "📈",
    "leaderboard": "🏆", "command": "⚙️", "bot": "🤖", "voice": "🔊", "music": "🎵", "game": "🎮", "squad": "🪖",
    "team": "👥", "match": "⚔️", "rank": "🥇", "tournament": "🏆", "scrim": "🥊", "minecraft": "⛏️", "roblox": "🧱",
    "fortnite": "🪂", "valorant": "🎯", "fan": "💖", "art": "🎨", "creator": "✨", "collab": "🤝", "event": "📅",
    "calendar": "📅", "resource": "🧰", "guide": "🧭", "tutorial": "🧑‍🏫", "idea": "💡",
}
FALLBACK_EMOJIS = ["🌟", "🧩", "🪄", "🧿", "🌈", "🪐", "🦋", "🍀", "🔥", "💎", "🧸", "🪷", "🌙", "🎨", "🪙", "🧠", "🪁", "💫", "🔮", "🧵", "🎪", "🪸", "🪻", "🧃", "🧊", "🧪", "🧭"]


def clean_text(value, limit=100):
    text = str(value or "").replace("@everyone", "everyone").replace("@here", "here")
    text = re.sub(r"[\r\n\t\x00-\x1f]", " ", text)
    return " ".join(text.split())[:limit].strip()


def channel_key(value):
    text = clean_text(value, 120).casefold()
    text = re.sub(r"^[〔【\[（(].*?[〕】\]）)]\s*[・•|:：-]*\s*", "", text)
    return "".join(char for char in text if char.isalnum())


def slug_channel(value):
    text = clean_text(value, 120)
    text = re.sub(r"^[〔【\[（(].*?[〕】\]）)]\s*[・•|:：-]*\s*", "", text)
    text = re.sub(r"^[^\w]+", "", text, flags=re.UNICODE).casefold().replace("_", "-")
    text = "".join(char if char.isalnum() or char in "- " else "-" for char in text)
    return "-".join(text.split()).strip("-")[:72] or "channel"


def choose_emoji(slug, used):
    for keyword, emoji in sorted(EMOJI_RULES.items(), key=lambda item: len(item[0]), reverse=True):
        if keyword in slug and emoji not in used:
            used.add(emoji)
            return emoji
    seed = sum(ord(char) for char in slug)
    for offset in range(len(FALLBACK_EMOJIS)):
        emoji = FALLBACK_EMOJIS[(seed + offset) % len(FALLBACK_EMOJIS)]
        if emoji not in used:
            used.add(emoji)
            return emoji
    return "✨"


def category_key(value):
    return "".join(char for char in str(value or "").casefold() if char.isalnum())


def core_category_match(name):
    key = category_key(name)
    aliases = {"staff": ("staffgeneral", "staff", "staffonly", "staffroom"), "welcome": ("welcome", "welcomesection"),
               "verification": ("verification", "verify"), "important": ("important", "serverinformation", "information"),
               "middleman": ("middleman", "middlemanservice"), "giveaways": ("giveaways", "giveaway"),
               "general": ("general", "community", "communitychat")}
    for canonical, candidates in aliases.items():
        if key in candidates:
            return canonical
    return None


def archetype_for(prompt):
    text = prompt.casefold()
    sets = {
        "trading": ("trade", "trading", "market", "middleman", "sell", "buy", "auction", "voucher", "crypto", "robux"),
        "creators": ("creator", "stream", "youtube", "twitch", "tiktok", "fan", "artist", "art", "podcast", "influencer"),
        "content": ("content", "video", "clips", "editing", "social media", "media"),
    }
    scores = {name: sum(1 for word in words if word in text) for name, words in sets.items()}
    return max(scores, key=scores.get) if max(scores.values(), default=0) else "community"


def get_ai_client():
    key = os.getenv("GROQ_API_KEY")
    if not key:
        raise RuntimeError("GROQ_API_KEY is not configured in Railway Variables")
    return AsyncOpenAI(base_url="https://api.groq.com/openai/v1", api_key=key)


@asynccontextmanager
async def lifespan(app):
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
        perms = int(item.get("permissions", 0))
        if not (perms & 0x8 or perms & 0x20):
            continue
        gid = int(item["id"])
        has_bot = bot.get_guild(gid) is not None
        result.append({"id": gid, "name": item["name"], "icon": item.get("icon"), "has_bot": has_bot,
                       "invite_url": None if has_bot else f"https://discord.com/api/oauth2/authorize?client_id={CLIENT_ID}&permissions=268435472&scope=bot%20applications.commands&guild_id={gid}"})
    return {"guilds": result}


def get_guild(guild_id):
    guild = bot.get_guild(guild_id)
    if guild is None:
        raise HTTPException(404, "Bot is not in this server")
    if guild.me is None:
        raise HTTPException(503, "Bot membership is not available")
    if not guild.me.guild_permissions.manage_channels or not guild.me.guild_permissions.manage_roles:
        raise HTTPException(403, "Bot needs Manage Channels and Manage Roles")
    return guild


def safe_state(guild):
    return {"name": guild.name,
            "categories": [{"name": cat.name, "channels": [ch.name for ch in cat.channels]} for cat in guild.categories[:30]],
            "roles": [role.name for role in guild.roles if not role.managed][-15:]}


def sanitize_plan(plan, prompt=""):
    if not isinstance(plan, dict):
        plan = {}
    roles = []
    for item in (plan.get("roles") or [])[:10]:
        if not isinstance(item, dict):
            continue
        name = clean_text(item.get("name"), 100)
        if not name or name.casefold() in {"everyone", "here", "admin", "administrator", "bot"}:
            continue
        try:
            color = int(str(item.get("color", "5865F2")).lstrip("#"), 16)
        except (ValueError, TypeError):
            color = 0x5865F2
        roles.append({"name": name, "color": max(0, min(color, 0xFFFFFF)), "hoist": bool(item.get("hoist")), "mentionable": bool(item.get("mentionable"))})

    categories, used_channels = [], set()
    for core in CORE_LAYOUT:
        channels = []
        for emoji, name, kind in core["channels"]:
            channels.append({"name": f"〔{emoji}〕・{name}", "type": kind, "topic": ""})
            used_channels.add(channel_key(name))
        categories.append({"name": core["name"], "staff_only": core["private"], "channels": channels})

    extras, used_categories = [], set()
    raw = plan.get("categories") if isinstance(plan.get("categories"), list) else []
    for item in raw[:8]:
        if not isinstance(item, dict):
            continue
        name = clean_text(item.get("name"), 100)
        if not name or core_category_match(name):
            continue
        key = category_key(name)
        if not key or key in used_categories:
            continue
        used_categories.add(key)
        used_emojis, text_channels, voice_channels = set(), [], []
        for channel in (item.get("channels") if isinstance(item.get("channels"), list) else [])[:12]:
            if not isinstance(channel, dict):
                continue
            slug = slug_channel(channel.get("name"))
            ck = channel_key(slug)
            if not ck or ck in used_channels:
                continue
            used_channels.add(ck)
            emoji = next((value for word, value in sorted(EMOJI_RULES.items(), key=lambda pair: len(pair[0]), reverse=True) if word in slug and value not in used_emojis), None)
            if emoji is None:
                seed = sum(map(ord, slug))
                emoji = next((FALLBACK_EMOJIS[(seed + i) % len(FALLBACK_EMOJIS)] for i in range(len(FALLBACK_EMOJIS)) if FALLBACK_EMOJIS[(seed + i) % len(FALLBACK_EMOJIS)] not in used_emojis), "✨")
            used_emojis.add(emoji)
            entry = {"name": f"〔{emoji}〕・{slug}", "type": "voice" if channel.get("type") == "voice" else "text",
                     "topic": clean_text(channel.get("topic"), 1024) if channel.get("type") != "voice" else ""}
            (voice_channels if entry["type"] == "voice" else text_channels).append(entry)
        if text_channels:
            extras.append({"name": name, "staff_only": False, "channels": text_channels})
        if voice_channels:
            # Voice category is always the last section, after prompt-selected content/trading/etc.
            extras.append({"name": "🎙️ : VOICE LOUNGE : 🎧", "staff_only": False, "channels": voice_channels})

    # Stable section priority requested by the user; absent topics are simply omitted.
    def priority(category):
        key = category_key(category["name"])
        if "content" in key:
            return 0
        if "creator" in key or "fanworks" in key or "collaboration" in key:
            return 1
        if "trading" in key or "marketplace" in key or "middlemanservice" in key:
            return 2
        if "voice" in key:
            return 99
        return 10
    extras.sort(key=priority)
    categories.extend(extras)
    return {"summary": clean_text(plan.get("summary") or "A custom layout tailored to your prompt", 500), "roles": roles, "categories": categories}


async def generate_plan(guild, prompt):
    archetype = archetype_for(prompt)
    state = safe_state(guild)
    response = await get_ai_client().chat.completions.create(
        model=os.getenv("GROQ_MODEL", "openai/gpt-oss-20b"),
        messages=[{"role": "system", "content": f"""
You are an expert Discord community architect. Return JSON only with summary, roles, categories.
Create up to 5 prompt-specific categories after the app's fixed seven sections: STAFF GENERAL, WELCOME, VERIFICATION, IMPORTANT, MIDDLEMAN, GIVEAWAYS, GENERAL. Do not output or change those. General ends at Suggestions. Add content/creator/trading sections only when the user's prompt actually calls for them; code orders relevant custom sections content, creators, trading, then any other custom categories. Voice channels are moved to one final VOICE LOUNGE by code.
Make categories purposeful, channels concise, and emoji semantically varied. Don't duplicate any channel from this existing server: {json.dumps(state, ensure_ascii=False)}
Detected topic hint: {archetype}. Interpret the full user prompt; this hint does not override it. Schema: {{"summary":"...","roles":[{{"name":"Member","color":"5865F2"}}],"categories":[{{"name":"🎬 : CONTENT : ✨","channels":[{{"name":"content-drops","type":"text","topic":"..."}},{{"name":"creator-hangout","type":"voice"}}]}}]}}
No role permissions, max 8 custom categories and 12 channels/category. Do not return fixed sections or duplicates.
"""}, {"role": "user", "content": prompt}],
        temperature=0.65, max_tokens=5000, response_format={"type": "json_object"})
    content = response.choices[0].message.content
    if not content:
        raise RuntimeError("AI returned an empty design")
    return sanitize_plan(json.loads(content), prompt)


def is_category(item):
    return isinstance(item, discord.CategoryChannel)


def is_channel(item):
    return not is_category(item) and isinstance(item, discord.abc.GuildChannel)


def find_category(guild, spec):
    desired_core = next((entry for entry in CORE_LAYOUT if entry["name"] == spec["name"]), None)
    if desired_core:
        return next((cat for cat in guild.categories if core_category_match(cat.name) == desired_core["key"]), None)
    wanted = category_key(spec["name"])
    exact = next((cat for cat in guild.categories if category_key(cat.name) == wanted), None)
    if exact:
        return exact
    return None


def existing_channel(guild, category, desired, kind):
    key = channel_key(desired)
    for item in guild.channels:
        if not is_channel(item) or channel_key(item.name) != key:
            continue
        is_voice = isinstance(item, (discord.VoiceChannel, discord.StageChannel))
        if (kind == "voice") != is_voice:
            continue
        if item.category == category:
            return item
    return None


async def delete_existing_layout(guild):
    """Delete all server channels/categories as requested; this cannot be undone."""
    # Delete leaf channels first; categories are then empty and safe to delete.
    channels = [item for item in list(guild.channels) if is_channel(item)]
    categories = list(guild.categories)
    for item in channels:
        await item.delete(reason="User-confirmed Rynnzyr server rebuild")
        await asyncio.sleep(0.25)
    for category in reversed(categories):
        await category.delete(reason="User-confirmed Rynnzyr server rebuild")
        await asyncio.sleep(0.25)


async def build_fresh_layout(guild, plan):
    # Destructive reset is only invoked after a dedicated explicit confirmation button.
    await delete_existing_layout(guild)
    created_ids, created = [], []
    roles = {}
    for spec in plan["roles"]:
        role = discord.utils.get(guild.roles, name=spec["name"])
        if role is None:
            role = await guild.create_role(name=spec["name"], colour=discord.Colour(spec["color"]), hoist=spec["hoist"], mentionable=spec["mentionable"], reason="Created by Rynnzyr")
            created_ids.append(f"role:{role.id}")
            created.append(f"Role: {role.name}")
        roles[role.name.casefold()] = role
    staff_role = next((role for name, role in roles.items() if "staff" in name or "moderator" in name or name == "mod"), None)
    staff_role = staff_role or discord.utils.get(guild.roles, name="Staff")
    if staff_role is None:
        staff_role = await guild.create_role(name="Staff", colour=discord.Colour(0x5865F2), reason="Private staff category access")
        created_ids.append(f"role:{staff_role.id}")
        created.append("Role: Staff — assign to trusted staff members")

    # Categories and their channels are created sequentially, so order is deterministic
    # without unsupported bulk-position APIs or moving a category under another category.
    for spec in plan["categories"]:
        overwrites = {}
        if spec["staff_only"]:
            overwrites = {guild.default_role: discord.PermissionOverwrite(view_channel=False),
                          staff_role: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True, connect=True, speak=True)}
        category = await guild.create_category(spec["name"], overwrites=overwrites, reason="Fresh Rynnzyr layout")
        created_ids.append(f"category:{category.id}")
        created.append(f"Category: {category.name}" + (" (staff-only)" if spec["staff_only"] else ""))
        for item in spec["channels"]:
            if item["type"] == "voice":
                channel = await guild.create_voice_channel(item["name"], category=category, reason="Fresh Rynnzyr layout")
            else:
                channel = await guild.create_text_channel(item["name"], category=category, topic=item["topic"] or None, reason="Fresh Rynnzyr layout")
            created_ids.append(f"channel:{channel.id}")
            created.append(f"{item['type'].title()}: {item['name']}")
            await asyncio.sleep(0.25)
    undo_snapshots[guild.id] = created_ids
    return created


def make_embed(guild, plan):
    embed = discord.Embed(title=f"✨ {guild.name} — Server blueprint", description=plan["summary"], color=0x7C83FF)
    for category in plan["categories"]:
        if len(embed.fields) >= 24:
            break
        lines = [("🔊 " if item["type"] == "voice" else "# ") + item["name"] for item in category["channels"]]
        if category["staff_only"]:
            lines.append("🔒 Staff-only — access through Staff role")
        embed.add_field(name=category["name"], value=("\n".join(lines) or "No channels")[:1024], inline=True)
    embed.set_footer(text="WARNING: Build permanently deletes all existing channels and categories, then recreates this layout.")
    return embed


class ConfirmRebuildView(discord.ui.View):
    def __init__(self, guild, plan, author_id):
        super().__init__(timeout=180)
        self.guild, self.plan, self.author_id, self.finished = guild, plan, author_id, False

    async def interaction_check(self, interaction):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("Only the requesting server manager can confirm this rebuild.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Delete all channels & rebuild", style=discord.ButtonStyle.danger, emoji="🗑️")
    async def rebuild(self, interaction, button):
        if self.finished:
            await interaction.response.send_message("This rebuild was already handled.", ephemeral=True)
            return
        self.finished = True
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(content="⚠️ Rebuild confirmed. Deleting existing channels and creating the new layout…", view=self)
        try:
            changes = await build_fresh_layout(self.guild, self.plan)
            summary = "\n".join(f"• {line}" for line in changes[:35]) or "Layout created."
            await interaction.followup.send(f"✅ **Fresh layout created.**\n{summary}", ephemeral=True)
        except Exception as exc:
            print(f"Fresh rebuild failed: {type(exc).__name__}: {exc}")
            await interaction.followup.send(f"Rebuild stopped after an error: {type(exc).__name__}: {str(exc)[:700]}. Some old channels may already be deleted; inspect the server before retrying.", ephemeral=True)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary, emoji="✖️")
    async def cancel(self, interaction, button):
        self.finished = True
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(content="Rebuild cancelled. No server changes were made.", embed=None, view=self)


@app.post("/api/plan")
async def create_plan(req: PlanRequest):
    try:
        return {"plan": await generate_plan(get_guild(req.guild_id), req.prompt)}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(502, f"AI planning failed: {exc}")


@app.post("/api/apply")
async def apply_plan(req: ApplyRequest):
    # API apply retains non-destructive create/reuse semantics; destructive reset is via explicit Discord confirmation.
    raise HTTPException(409, "Use the preview confirmation in Discord to run a fresh rebuild; this endpoint will not delete server channels.")


@app.post("/api/undo")
async def undo(req: GuildRequest):
    guild = get_guild(req.guild_id)
    ids = undo_snapshots.pop(guild.id, [])
    deleted = 0
    for entry in reversed(ids):
        kind, raw_id = entry.split(":", 1)
        item = discord.utils.get(guild.roles, id=int(raw_id)) if kind == "role" else guild.get_channel(int(raw_id))
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


@bot.tree.command(name="design", description="Preview and rebuild your server with an AI layout")
@app_commands.describe(prompt="Describe what your community is about and the layout you want")
async def design(interaction: discord.Interaction, prompt: str):
    if interaction.guild is None:
        await interaction.response.send_message("Use this inside a server.", ephemeral=True)
        return
    member = interaction.user
    if not isinstance(member, discord.Member) or not (member.guild_permissions.manage_guild or member.guild_permissions.administrator):
        await interaction.response.send_message("You need Manage Server permission.", ephemeral=True)
        return
    me = interaction.guild.me
    if me is None or not (me.guild_permissions.manage_channels and me.guild_permissions.manage_roles):
        await interaction.response.send_message("I need Manage Channels and Manage Roles.", ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True, thinking=True)
    try:
        plan = await generate_plan(interaction.guild, prompt[:1000])
        view = ConfirmRebuildView(interaction.guild, plan, interaction.user.id)
        await interaction.followup.send(
            "**Review carefully:** pressing the red button permanently deletes every existing channel and category in this server, then creates the blueprint. Discord cannot restore deleted channel messages. Roles are kept. Nothing changes until you confirm.",
            embed=make_embed(interaction.guild, plan), view=view, ephemeral=True)
    except Exception as exc:
        print(f"/design failed: {type(exc).__name__}: {exc}")
        message = str(exc) if "GROQ_API_KEY" in str(exc) else "I couldn't design that layout. Check Railway logs and AI configuration."
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
