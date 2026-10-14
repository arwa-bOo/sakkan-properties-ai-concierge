"""Triage agent: classifies the intent, resolves the client and extracts search / mortgage / message parameters.
Deterministic parser first (fast, offline, testable); Gemini only fills in what the parser left empty."""
import asyncio
import re

from .. import corpus, llm, prompts, settings
from ..node_context import NodeContext

NUM_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}
_NUM = r"(\d{1,2}|" + "|".join(NUM_WORDS) + ")"
DISTRICTS = {"new cairo": "New Cairo", "التجمع": "New Cairo", "القاهرة الجديدة": "New Cairo",
             "sheikh zayed": "Sheikh Zayed", "الشيخ زايد": "Sheikh Zayed", "zayed": "Sheikh Zayed",
             "6th of october": "6th of October", "6th october": "6th of October", "october": "6th of October", "أكتوبر": "6th of October", "اكتوبر": "6th of October",
             "maadi": "Maadi", "المعادي": "Maadi", "north coast": "North Coast", "الساحل": "North Coast"}
TYPES = {"apartment": "apartment", "شقة": "apartment", "شقق": "apartment", "villa": "villa", "فيلا": "villa",
         "فيلات": "villa", "townhouse": "townhouse", "تاون هاوس": "townhouse"}
DRAFT_WORDS = ("draft", "write", "message", "whatsapp", "email", "compose", "follow-up", "follow up", "رسالة", "واتساب", "ايميل", "إيميل")
MORT_WORDS = ("mortgage", "loan", "instalment", "installment", "قسط", "تمويل", "قرض")
ESCALATE_WORDS = ("lawsuit", "legal advice", "sue ", "dispute", "negotiate", "discount", "complaint", "fraud", "قضية", "شكوى")
KNOWLEDGE_WORDS = ("policy", "sop", "procedure", "guideline", "how do we", "what is our", "rules", "سياسة")


def _num(tok: str) -> int:
    return NUM_WORDS.get(tok.lower()) or int(tok)


def _price(text: str):
    m = re.search(r"(?:under|below|less than|up to|within|max(?:imum)?(?: budget)?|budget(?: of)?|تحت|اقل من|أقل من)\s*(?:egp|ج\.?م\.?)?\s*([\d][\d,\.]*)\s*(m\b|mn\b|million|مليون|k\b|thousand|ألف|الف)?", text, re.I)
    if not m:
        return None
    n = float(m.group(1).replace(",", "").rstrip("."))
    unit = (m.group(2) or "").lower()
    n *= 1_000_000 if unit in ("m", "mn", "million", "مليون") else 1000 if unit in ("k", "thousand", "ألف", "الف") else 1
    return int(n)


def parse_request(text: str) -> dict:
    low = text.lower()
    p: dict = {k: None for k in ("district", "property_type", "bedrooms", "max_price_egp", "language", "channel",
                                 "rate_pct", "down_pct", "years", "date", "time", "remember_text")}
    for k in sorted(DISTRICTS, key=len, reverse=True):
        if k in low:
            p["district"] = DISTRICTS[k]; break
    for k, v in TYPES.items():
        if k in low:
            p["property_type"] = v; break
    m = re.search(rf"\b{_NUM}\s*-?\s*(?:bed(?:room)?s?|br)\b", low) or re.search(r"(\d+)\s*(?:غرف|غرفة)", low)
    p["bedrooms"] = _num(m.group(1)) if m else None
    m = re.search(rf"\b{_NUM}\s+(?!\s*-?\s*(?:bed|br))(?:\w+\s+)?(?:apartments?|villas?|townhouses?|units|options|listings|properties|شقق|فيلات)", low)
    p["count"] = min(_num(m.group(1)), 5) if m else 3
    p["max_price_egp"] = _price(text)
    p["listing_ids"] = list(dict.fromkeys(re.findall(r"LST-\d{3}", text.upper())))
    # mortgage terms
    pcts = [(float(x.group(1)), low[x.end():x.end() + 14]) for x in re.finditer(r"(\d+(?:\.\d+)?)\s*%", low)]
    down = [v for v, after in pcts if "down" in after or "مقدم" in after]
    rate = [v for v, after in pcts if "down" not in after and "مقدم" not in after]
    p["down_pct"] = down[0] if down else None
    p["rate_pct"] = rate[0] if rate else None
    m = re.search(r"(\d{1,2})\s*[- ]?\s*(?:years?|yrs?|سنة|سنين|سنوات)", low)
    p["years"] = int(m.group(1)) if m else None
    # viewing
    m = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", text); p["date"] = m.group(1) if m else None
    m = re.search(r"\b([01]?\d|2[0-3]):([0-5]\d)\b", text); p["time"] = f"{int(m.group(1)):02d}:{m.group(2)}" if m else None
    # language / channel
    if "arabic" in low or "بالعربي" in low or "بالعربية" in low: p["language"] = "ar"
    elif "english" in low or "بالانجليزي" in low or "بالإنجليزي" in low: p["language"] = "en"
    p["channel"] = "whatsapp" if ("whatsapp" in low or "واتساب" in low) else "email" if ("email" in low or "ايميل" in low or "إيميل" in low) else None
    m = re.search(r"remember (?:that )?(.+)$", text, re.I | re.S)
    p["remember_text"] = m.group(1).strip().rstrip(".") if m else None
    # client
    p["client_id"] = None
    for cid, c in corpus.load_clients().items():
        toks = [t for t in re.findall(r"[\w\u0600-\u06FF]+", c["name"] + " " + c["arabic_name"]) if len(t) > 3 and t.lower() not in ("mrs", "dr", "eng", "الأستاذ", "السيدة", "المهندس", "الدكتورة", "الآنسة")]
        if cid.lower() in low or any(re.search(rf"(?<!\w){re.escape(t.lower())}(?!\w)", low) for t in toks):
            p["client_id"] = cid; break
    # flags & intent
    wants_draft = any(w in low for w in DRAFT_WORDS)
    wants_mort = any(w in low for w in MORT_WORDS)
    wants_view = bool(re.search(r"\b(schedule|book)\b|viewing|معاينة", low)) and bool(p["listing_ids"])
    has_filter = any(p[k] for k in ("district", "property_type", "bedrooms", "max_price_egp"))
    if any(w in low for w in ESCALATE_WORDS): intent = "escalate"
    elif wants_view: intent = "schedule_viewing"
    elif wants_draft: intent = "draft_message"
    elif wants_mort: intent = "mortgage"
    elif p["remember_text"]: intent = "remember_note"
    elif has_filter or p["listing_ids"]: intent = "find_properties"
    else: intent = "knowledge_question"
    if intent == "find_properties" and any(w in low for w in KNOWLEDGE_WORDS) and not has_filter: intent = "knowledge_question"
    p["intent"] = intent
    p["needs_draft"] = intent in ("draft_message", "schedule_viewing")
    p["needs_mortgage"] = wants_mort and intent != "escalate"
    p["needs_search"] = has_filter and not p["listing_ids"] and intent in ("find_properties", "draft_message", "mortgage")
    p["followup"] = "follow-up" in low or "follow up" in low or "متابعة" in low
    if intent == "schedule_viewing": p["channel"] = "viewing_offer"
    elif p["needs_draft"] and not p["channel"]: p["channel"] = "whatsapp"
    return p


async def triage_node(state: dict) -> dict:
    ctx = NodeContext(state, "triage")
    plan = parse_request(state["request"])
    if not settings.MOCK_MODE:                       # let Gemini fill what the parser could not
        try:
            raw = await asyncio.to_thread(llm.generate, state["request"], prompts.TRIAGE_SYSTEM, True)
            guess = llm.extract_json(raw)
            for k in ("district", "property_type", "bedrooms", "max_price_egp", "language", "channel"):
                if plan.get(k) is None and guess.get(k) is not None:
                    plan[k] = guess[k]
        except Exception as e:
            ctx.emit("tool_error", tool="gemini_triage", error=str(e)[:200])
    client = corpus.load_clients().get(plan["client_id"]) if plan["client_id"] else None
    language = plan["language"] or ("ar" if re.search(r"[\u0600-\u06FF]", state["request"]) else None)
    if not language and client:
        language = "ar" if client["language"] in ("Arabic", "both") else "en"
    language = language or "en"
    ctx.emit("agent_transition", agent="triage", intent=plan["intent"], client_id=plan["client_id"], language=language,
             plan={k: v for k, v in plan.items() if v not in (None, [], False)})
    return ctx.update(plan=plan, client_id=plan["client_id"], client_name=client["name"] if client else None,
                      language=language, channel=plan["channel"])
