"""Communication agent: drafts the client-facing message (Arabic / English). The draft is validated:
every LST-id in it must be a retrieved listing, and it must cite at least one. Otherwise we fall back to a
deterministic template, so a fabricated listing can never reach the HiL gate."""
import asyncio
import re

from .. import corpus, llm, prompts, settings
from ..node_context import NodeContext

TYPE_AR = {"apartment": "شقة", "villa": "فيلا", "townhouse": "تاون هاوس"}
DIST_AR = {"New Cairo": "القاهرة الجديدة", "Sheikh Zayed": "الشيخ زايد", "6th of October": "6 أكتوبر", "Maadi": "المعادي", "North Coast": "الساحل الشمالي"}
FIN_AR = {"fully finished": "كامل التشطيب", "semi-finished": "نصف تشطيب", "core & shell": "على الطوب"}


def _lines(listings, mortgage, lang):
    out = []
    for i, l in enumerate(listings, 1):
        m = (mortgage or {}).get("results", {}).get(l["id"])
        if lang == "ar":
            s = (f"{i}) [{l['id']}] {TYPE_AR[l['property_type']]} {l['bedrooms']} غرف – {l['compound']}، {DIST_AR[l['district']]}\n"
                 f"   المساحة {l['size_sqm']} م² | السعر {l['price_egp']:,} جنيه | {FIN_AR[l['finishing']]}")
            if m:
                s += f"\n   القسط الشهري التقريبي: {m['monthly_payment_egp']:,} جنيه (مقدم {m['down_pct']:g}% – فائدة {m['rate_pct']:g}% – {m['years']} سنة)"
        else:
            s = (f"{i}) [{l['id']}] {l['bedrooms']}-bedroom {l['property_type']} – {l['compound']}, {l['district']}\n"
                 f"   {l['size_sqm']} sqm | EGP {l['price_egp']:,} | {l['finishing']}")
            if m:
                s += f"\n   Indicative monthly payment: EGP {m['monthly_payment_egp']:,} ({m['down_pct']:g}% down, {m['rate_pct']:g}% rate, {m['years']} years)"
        out.append(s)
    return "\n".join(out)


def template_draft(state: dict) -> str:
    lang, ch, plan = state["language"], state.get("channel", "whatsapp"), state["plan"]
    c = corpus.load_clients().get(state.get("client_id") or "")
    listings, mort = state.get("listings", []), state.get("mortgage")
    body = _lines(listings, mort, lang)
    if lang == "ar":
        sal = f"السلام عليكم {c['arabic_name']}،" if c else "السلام عليكم،"
        if not listings:
            core = "للأسف لا توجد حالياً وحدات متاحة تطابق المواصفات المطلوبة، وسنتواصل مع حضرتك فور توفر خيارات مناسبة."
        elif plan["intent"] == "schedule_viewing":
            core = f"يسعدنا تأكيد معاينة الوحدة التالية يوم {plan.get('date')} الساعة {plan.get('time')}:\n{body}"
        elif plan.get("followup"):
            core = f"بخصوص الوحدات التي رشحناها لحضرتك سابقاً:\n{body}\nهل تود ترتيب معاينة؟"
        else:
            core = f"بناءً على طلب حضرتك، رشحنا لك {len(listings)} وحدات مناسبة:\n{body}"
        tail = "\nملاحظة: الأرقام والأقساط تقديرية وغير ملزمة.\nمع تحياتنا، فريق سكّان العقارية"
        return ("الموضوع: ترشيحات من سكّان العقارية\n\n" if ch == "email" else "") + f"{sal}\n{core}{tail}"
    sal = f"Dear {c['name']}," if c else "Hello,"
    if not listings:
        core = "Unfortunately we currently have no available units matching your requirements. We will contact you as soon as suitable options appear."
    elif plan["intent"] == "schedule_viewing":
        core = f"We are pleased to confirm a viewing on {plan.get('date')} at {plan.get('time')} for:\n{body}"
    elif plan.get("followup"):
        core = f"Following up on the shortlist we discussed:\n{body}\nWould you like us to arrange a viewing?"
    else:
        core = f"Based on your request, here are {len(listings)} suitable options:\n{body}"
    tail = "\nNote: figures and instalments are indicative and non-binding.\nKind regards,\nSakkan Properties team"
    return ("Subject: Property options from Sakkan Properties\n\n" if ch == "email" else "") + f"{sal}\n{core}{tail}"


def validate_draft(text: str, allowed_ids: set[str]) -> bool:
    ids = set(re.findall(r"LST-\d{3}", text))
    return ids <= allowed_ids and (ids or not allowed_ids)


async def comms_node(state: dict) -> dict:
    ctx = NodeContext(state, "comms")
    listings = state.get("listings", [])
    allowed = {l["id"] for l in listings}
    ctx.emit("agent_transition", agent="comms", detail=f"drafting {state.get('channel')} message in {state['language']}")
    draft, used = template_draft(state), "template"
    if not settings.MOCK_MODE:
        facts = {"client": state.get("client_name"), "listings": listings, "mortgage": state.get("mortgage"),
                 "plan": {k: state["plan"].get(k) for k in ("intent", "date", "time", "followup")},
                 "preferences": [m["text"] for m in state.get("memories", []) if m["kind"] == "preference"]}
        sys_p = prompts.COMMS_SYSTEM.format(channel=state.get("channel"), language_name="Egyptian-friendly Modern Standard Arabic" if state["language"] == "ar" else "English")
        try:
            text = (await asyncio.to_thread(llm.generate, f"FACTS: {facts}\nBroker request: {state['request']}", sys_p, False, 0.3)).strip()
            if text and validate_draft(text, allowed):
                draft, used = text, "gemini"
            else:
                ctx.emit("tool_error", tool="draft_validation", error="LLM draft failed provenance check; template used")
        except Exception as e:
            ctx.emit("tool_error", tool="gemini_comms", error=str(e)[:200])
    ctx.emit("draft_ready", detail=f"draft ready for HiL review ({used})", chars=len(draft), cited=sorted(set(re.findall(r"LST-\d{3}", draft))))
    return ctx.update(draft=draft)
