import asyncio
import json
import os
import re
from contextlib import asynccontextmanager
from difflib import SequenceMatcher

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
ARCHETYPES = {
    "trading": {"keywords": ("trade", "trading", "market", "middleman", "sell", "buy", "auction", "voucher", "crypto", "robux"), "sections": [
        ("💎 : MARKETPLACE : 💸", [("🛒", "marketplace", "text"), ("💱", "trade-chat", "text"), ("🎯", "trade-requests", "text"), ("🔎", "looking-to-buy", "text"), ("🔨", "auctions", "text"), ("📦", "deal-room", "voice")]),
        ("🤝 : MIDDLEMAN SERVICE : 🛡️", [("🤝", "request-middleman", "text"), ("📋", "active-deals", "text"), ("✅", "completed-trades", "text"), ("🎫", "deal-support", "text")]),
        ("⭐ : REPUTATION : 🏆", [("✅", "vouches", "text"), ("⚠️", "scam-reports", "text"), ("🏅", "top-traders", "text")])], "roles": [("Verified Trader", 0x57E39A), ("Middleman", 0xF7B84B), ("Trusted Seller", 0x5865F2)]},
    "gaming": {"keywords": ("game", "gaming", "esports", "clan", "minecraft", "roblox", "valorant", "fortnite", "tournament", "scrim", "lfg", "playstation", "xbox"), "sections": [
        ("🎮 : GAME LOUNGE : 🕹️", [("🎮", "game-chat", "text"), ("😂", "clips-and-memes", "text"), ("📸", "screenshots", "text"), ("🎙️", "lobby-voice", "voice")]),
        ("🔎 : FIND YOUR SQUAD : 🪖", [("🧩", "looking-for-group", "text"), ("👥", "team-up", "text"), ("🎯", "competitive", "text"), ("🧪", "playtesting", "text")]),
        ("🏆 : COMPETITIVE : ⚔️", [("📅", "match-schedule", "text"), ("📊", "leaderboards", "text"), ("🥇", "tournaments", "text"), ("🥊", "scrim-voice", "voice")])], "roles": [("Player", 0x5865F2), ("Competitor", 0xED4245), ("Team Captain", 0xFEE75C)]},
    "creator": {"keywords": ("creator", "stream", "youtube", "twitch", "tiktok", "fan", "artist", "art", "podcast", "influencer"), "sections": [
        ("📡 : LIVE & CONTENT : 🎬", [("📢", "content-drops", "text"), ("📺", "stream-notifications", "text"), ("🎞️", "latest-clips", "text"), ("🔴", "watch-party", "voice")]),
        ("🎨 : FAN WORKS : 💖", [("🖼️", "fan-art", "text"), ("✂️", "edits", "text"), ("💡", "content-ideas", "text")]),
        ("🤝 : COLLABORATIONS : ✨", [("📨", "collab-requests", "text"), ("🧑‍🎤", "creator-network", "text"), ("🎤", "guest-voice", "voice")])], "roles": [("Member", 0x5865F2), ("Creator", 0xEB459E), ("Collaborator", 0x57F287)]},
    "community": {"keywords": (), "sections": [
        ("💬 : COMMUNITY : 🎉", [("👋", "introductions", "text"), ("☕", "general-chat", "text"), ("😂", "memes", "text"), ("📸", "photo-dump", "text"), ("🗣️", "community-voice", "voice")]),
        ("💡 : IDEAS & FEEDBACK : 🧩", [("🛠️", "suggestions", "text"), ("🗳️", "community-polls", "text"), ("🎨", "feedback", "text")]),
        ("🎉 : EVENTS : 📅", [("📅", "upcoming-events", "text"), ("🎤", "event-stage", "voice"), ("📸", "event-gallery", "text")])], "roles": [("Member", 0x5865F2), ("Active Member", 0x57F287), ("Event Host", 0xEB459E)]},
}


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


def format_channel(value, emoji=None, used=None):
    slug = slug_channel(value)
    used = used if used is not None else set()
    icon = emoji or choose_emoji(slug, used)
    used.add(icon)
    return f"〔{icon}〕・{slug}"


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


def detect_archetype(prompt):
    text = prompt.casefold()
    scores = {name: sum(2 for keyword in spec["keywords"] if keyword in text) for name, spec in ARCHETYPES.items()}
    best = max(scores, key=scores.get)
    return best if scores[best] else "community"


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
        permissions = int(item.get("permissions", 0))
        if not (permissions & 0x8 or permissions & 0x20):
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
    me = guild.me
    if me is None:
        raise HTTPException(503, "Bot membership is not available")
    if not me.guild_permissions.manage_channels or not me.guild_permissions.manage_roles:
        raise HTTPException(403, "Bot needs Manage Channels and Manage Roles")
    return guild


def safe_state(guild):
    return {"name": guild.name,
            "categories": [{"name": cat.name, "channels": [{"name": ch.name, "type": "voice" if isinstance(ch, (discord.VoiceChannel, discord.StageChannel)) else "text"} for ch in cat.channels]} for cat in guild.categories[:30]],
            "roles": [role.name for role in guild.roles if not role.managed][-15:]}


def sanitize_plan(plan, archetype="community"):
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

    categories, core_keys = [], set()
    for core in CORE_LAYOUT:
        used = set()
        channels = []
        for emoji, name, kind in core["channels"]:
            channels.append({"name": format_channel(name, emoji, used), "type": kind, "topic": ""})
            core_keys.add(channel_key(name))
        categories.append({"name": core["name"], "staff_only": core["private"], "channels": channels})

    extras, seen_categories, seen_channels = [], set(), set(core_keys)
    raw_categories = plan.get("categories") if isinstance(plan.get("categories"), list) else []
    for item in raw_categories[:8]:
        if not isinstance(item, dict):
            continue
        name = clean_text(item.get("name"), 100)
        if not name or core_category_match(name):
            continue
        key = category_key(name)
        if not key or key in seen_categories:
            continue
        seen_categories.add(key)
        used, channels = set(), []
        for channel in (item.get("channels") if isinstance(item.get("channels"), list) else [])[:12]:
            if not isinstance(channel, dict):
                continue
            slug = slug_channel(channel.get("name"))
            normalized = channel_key(slug)
            if not normalized or normalized in seen_channels:
                continue
            seen_channels.add(normalized)
            emoji = choose_emoji(slug, used)
            kind = "voice" if channel.get("type") == "voice" else "text"
            channels.append({"name": f"〔{emoji}〕・{slug}", "type": kind, "topic": clean_text(channel.get("topic"), 1024) if kind == "text" else ""})
        if channels:
            extras.append({"name": name, "staff_only": False, "channels": channels})
    if not extras:
        for name, definitions in ARCHETYPES.get(archetype, ARCHETYPES["community"])["sections"]:
            used, channels = set(), []
            for emoji, slug, kind in definitions:
                if channel_key(slug) in seen_channels:
                    continue
                seen_channels.add(channel_key(slug))
                channels.append({"name": format_channel(slug, emoji, used), "type": kind, "topic": ""})
            if channels:
                extras.append({"name": name, "staff_only": False, "channels": channels})
    return {"summary": clean_text(plan.get("summary") or "A tailored, polished community layout", 500), "roles": roles, "categories": categories + extras}


async def generate_plan(guild, prompt):
    archetype = detect_archetype(prompt)
    examples = ARCHETYPES[archetype]
    response = await get_ai_client().chat.completions.create(
        model=os.getenv("GROQ_MODEL", "openai/gpt-oss-20b"),
        messages=[{"role": "system", "content": f"""
You are a senior Discord community architect. Return only JSON containing summary, roles, and categories.
Create up to 5 custom categories only. The app creates an exact fixed foundation in this order: Staff General, Welcome, Verification, Important, Middleman, Giveaways, General. Do not output these categories, duplicate their channels, or add anything to them. General ends at Suggestions. Never duplicate any current channel.
Topic archetype: {archetype}. Adapt these examples to the user's exact audience and purpose; do not copy irrelevant items: {json.dumps(examples['sections'], ensure_ascii=False)}
Use stylish category divider names, descriptive channel slugs, semantic varied emoji, and appropriate text/voice types. Safe role suggestions only. Example schema: {{"summary":"...","roles":[{{"name":"Moderator","color":"5865F2"}}],"categories":[{{"name":"🎮 : GAME LOUNGE : 🎮","channels":[{{"name":"game-chat","type":"text","topic":"..."}}]}}]}}
Current layout (avoid duplicating): {json.dumps(safe_state(guild), ensure_ascii=False)}
"""}, {"role": "user", "content": prompt}],
        temperature=0.65, max_tokens=5000, response_format={"type": "json_object"})
    content = response.choices[0].message.content
    if not content:
        raise RuntimeError("AI returned an empty design")
    return sanitize_plan(json.loads(content), archetype)


def is_category(channel):
    return isinstance(channel, discord.CategoryChannel)


def is_voice(channel):
    return isinstance(channel, (discord.VoiceChannel, discord.StageChannel))


def is_usable_channel(channel):
    return not is_category(channel) and isinstance(channel, discord.abc.GuildChannel)


def find_category(guild, spec):
    core = next((entry for entry in CORE_LAYOUT if entry["name"] == spec["name"]), None)
    if core:
        found = next((cat for cat in guild.categories if core_category_match(cat.name) == core["key"]), None)
        if found:
            return found
    wanted = category_key(spec["name"])
    exact = next((cat for cat in guild.categories if category_key(cat.name) == wanted), None)
    if exact:
        return exact
    # Only fuzzy-match longer custom category names; never fuzzy-match core categories.
    candidates = [(SequenceMatcher(None, wanted, category_key(cat.name)).ratio(), cat) for cat in guild.categories
                  if core_category_match(cat.name) is None and len(wanted) >= 12]
    score, match = max(candidates, default=(0, None), key=lambda pair: pair[0])
    return match if score >= 0.90 else None


def find_existing_channel(channels, desired, expected_type):
    key = channel_key(desired)
    for channel in channels:
        if not is_usable_channel(channel) or channel_key(channel.name) != key:
            continue
        if (expected_type == "voice") == is_voice(channel):
            return channel
    return None


async def set_channel_position(channel, position, reason):
    # Supported by discord.py's GuildChannel.edit; there is no Guild.edit_channel_positions API.
    await channel.edit(position=position, reason=reason)


async def apply_guild_plan(guild, plan):
    plan = sanitize_plan(plan)
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

    resolved = []
    for spec in plan["categories"]:
        overwrites = {}
        if spec["staff_only"]:
            overwrites = {guild.default_role: discord.PermissionOverwrite(view_channel=False),
                          staff_role: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True, connect=True, speak=True)}
        category = find_category(guild, spec)
        if category is None:
            # Parent is deliberately omitted: all planned categories are top-level.
            category = await guild.create_category(spec["name"], overwrites=overwrites, reason="Rynnzyr server blueprint")
            created_ids.append(f"category:{category.id}")
            created.append(f"Category: {category.name}" + (" (staff-only)" if spec["staff_only"] else ""))
        else:
            changes = {}
            if category.name != spec["name"]:
                changes["name"] = spec["name"]
            if spec["staff_only"]:
                changes["overwrites"] = overwrites
            if changes:
                await category.edit(reason="Update blueprint category", **changes)
        resolved.append((category, spec))

    # discord.py has no Guild.edit_channel_positions. Move each planned category
    # to its target index via CategoryChannel.edit, then order its child channels.
    for target_position, (category, _) in enumerate(resolved):
        if category.position != target_position:
            await set_channel_position(category, target_position, "Arrange blueprint category order")

    for category, spec in resolved:
        for target_position, channel_spec in enumerate(spec["channels"]):
            # Prefer a matching channel already in the right category.
            channel = find_existing_channel(category.channels, channel_spec["name"], channel_spec["type"])
            if channel is None:
                # Reuse an existing channel across the server but never a category.
                channel = next((candidate for candidate in guild.channels
                                if is_usable_channel(candidate)
                                and candidate.category != category
                                and channel_key(candidate.name) == channel_key(channel_spec["name"])
                                and ((channel_spec["type"] == "voice") == is_voice(candidate))
                                and not (candidate.category and core_category_match(candidate.category.name) == "staff")), None)
                if channel is not None:
                    await channel.edit(category=category, sync_permissions=bool(spec["staff_only"]), reason="Reuse existing blueprint channel")
            if channel is None:
                if channel_spec["type"] == "voice":
                    channel = await guild.create_voice_channel(channel_spec["name"], category=category, reason="Rynnzyr server blueprint")
                else:
                    channel = await guild.create_text_channel(channel_spec["name"], category=category, topic=channel_spec["topic"] or None, reason="Rynnzyr server blueprint")
                created_ids.append(f"channel:{channel.id}")
                created.append(f"{channel_spec['type'].title()}: {channel_spec['name']}")
            if channel.position != target_position or channel.category != category:
                await channel.edit(category=category, position=target_position, sync_permissions=bool(spec["staff_only"]), reason="Arrange blueprint channel order")
            await asyncio.sleep(0.15)

    undo_snapshots[guild.id] = created_ids
    return created


def make_embed(guild, plan):
    embed = discord.Embed(title=f"✨ {guild.name} — Smart server blueprint", description=plan["summary"], color=0x7C83FF)
    for category in plan["categories"]:
        if len(embed.fields) >= 24:
            break
        lines = [("🔊 " if item["type"] == "voice" else "# ") + item["name"] for item in category["channels"]]
        if category["staff_only"]:
            lines.append("🔒 Staff-only — access through Staff role")
        embed.add_field(name=category["name"], value=("\n".join(lines) or "No channels")[:1024], inline=True)
    embed.set_footer(text="Ordered reference foundations first • Prompt-specific sections after • Review before build")
    return embed


class BlueprintView(discord.ui.View):
    def __init__(self, guild, plan, author_id):
        super().__init__(timeout=180)
        self.guild, self.plan, self.author_id, self.finished = guild, plan, author_id, False

    async def interaction_check(self, interaction):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("Only the requesting server manager can use these buttons.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Build this server", style=discord.ButtonStyle.success, emoji="🏗️")
    async def build_button(self, interaction, button):
        if self.finished:
            await interaction.response.send_message("This blueprint was already handled.", ephemeral=True)
            return
        self.finished = True
        button.disabled = True
        self.cancel_button.disabled = True
        await interaction.response.edit_message(view=self)
        try:
            changes = await apply_guild_plan(self.guild, self.plan)
            report = "\n".join(f"• {line}" for line in changes[:35]) or "No duplicate channels were created; the layout already exists."
            await interaction.followup.send(f"✅ **Server built!**\n{report}\n\nAssign trusted members to **Staff** for private staff channels.", ephemeral=True)
        except discord.Forbidden:
            await interaction.followup.send("Discord denied a change. Check Manage Channels and Manage Roles permissions.", ephemeral=True)
        except Exception as exc:
            print(f"Blueprint apply failed: {type(exc).__name__}: {exc}")
            await interaction.followup.send(f"Build failed: {type(exc).__name__}: {str(exc)[:700]}", ephemeral=True)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary, emoji="✖️")
    async def cancel_button(self, interaction, button):
        self.finished = True
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(content="Blueprint cancelled — no changes made.", embed=None, view=self)


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
    try:
        return {"success": True, "created": await apply_guild_plan(get_guild(req.guild_id), req.plan)}
    except discord.Forbidden:
        raise HTTPException(403, "Bot is missing Discord permissions")
    except discord.HTTPException as exc:
        raise HTTPException(502, f"Discord rejected a change: {exc.text}")


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


@bot.tree.command(name="design", description="Preview and build a custom AI-designed server")
@app_commands.describe(prompt="Describe your community and the server you want")
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
        await interaction.followup.send(embed=make_embed(interaction.guild, plan), view=BlueprintView(interaction.guild, plan, interaction.user.id), ephemeral=True)
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
