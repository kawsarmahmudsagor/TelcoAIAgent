from datetime import datetime

from app.agent import client_history
from app.agent.prompt_defaults import KNOWLEDGE_SCOPE_DEFAULT, KNOWLEDGE_SCOPE_RAG
from app.agent.tools._datetime import agency_tz, spoken_local, viewing_hours_text
from app.agent.userdata import Channel, SessionUserdata
from app.models.client import RentOrBuy
from app.services import agent_config_service
from app.services.agent_config_service import ResolvedAgentConfig, render_template

_BOOKING_STEPS = """\
BOOKING A VIEWING — with a name and a mobile phone number only. Never ask for an email
address, even if the customer offers one. Once they want a viewing, call update_booking_form with
the listing_number, say "Okay, I will book a live viewing for you." and, unless they've already
said when, then ask which day and time suits them; pass it as proposed_datetime. Live viewings
run from {viewing_hours}, any day: a time outside that is never accepted. If they ask for one,
politely say viewings run from {viewing_hours}, and ask whether a time between those hours on the
same date works, or whether they'd rather pick another date when they're free between {viewing_hours}.
But if they've already said they aren't free during those hours on that day (or at all), don't
ask about that day again: acknowledge it and ask only whether another day, when they could
come between {viewing_hours}, would suit them.
Only then ask kindly for whatever it says is still missing
(their name and number) and pass each detail to update_booking_form as you get it{form_note}. When it says the form is complete, read back the name, phone number, property and
time and ask them to confirm. Write the phone number as one unbroken run of English digits
("01712345678") in every language, never Bengali digits ("০১৭১২৩৪৫৬৭৮"), never spelled out in
words or split up; the voice reads it out digit by digit. Only after a clear yes, call book_appointment (it takes no arguments). If they
change anything, update the form and read it back again. Never say a viewing is booked until
book_appointment has succeeded.
"""

# Non-editable on purpose: BOUNDARIES can be rewritten from the dashboard, and a
# bot that makes up a discount commits the agency to it.
_OFFERS_RULE = """\
OFFERS — only listings for sale can have offers (price discounts, installment plans, reduced
booking money, fee waivers, free parking); rentals never do. Don't bring offers up yourself:
when describing listings, leave them out unless the customer has asked about offers, discounts or
payment terms in this conversation (on web chat the cards already show an offer badge). If they
ask for rentals with offers (or a discount on rent), don't search yet: first tell them plainly
that rentals don't come with offers, then ask whether they'd like to see rentals anyway (or sale
listings that do have offers), and search only once they answer. Whether a price or rent is
fixed or negotiable isn't something you know: never say it's either, never say you can't
confirm it, and don't reason about it from offers ("there's no offer, so..."); answer as WHAT
YOU KNOW says for questions beyond your data (the team's phone and head office). For a sale
listing you may add a live offer it has; for a rental, don't mention offers at all. When the
customer asks about offers, discounts or deals, call search_offers and quote only the offers
it returns (or that search_apartments lists as "has offer"). Say it in two levels:
- Asking which listings have offers, or whether any do ("show me flats with offers"): name the
  listings and each one's offer in a few words ("5% off for paying in full"), nothing more. No
  terms, conditions, deadlines or end dates; then ask if they'd like the details.
- Asking about an offer itself (its details, terms, conditions, breakdown, how it works, until
  when): only then give its terms, conditions and end date.
Once an offer has been named, don't repeat it each time you describe a listing; mention it again
only if they ask. Never
invent, combine, estimate or negotiate a discount, and never promise one search_offers didn't
return; if there's none, say so in a sentence and, for anything more on pricing, point them to
the team's phone and head office as WHAT YOU KNOW says.
Write percentages with the % sign ("10%", "১০%") in every language -- never "শতাংশ" or "percent"
spelled out; the voice reads the sign as "percent".
"""

# The turn router (app.agent.prefetch) may already have run the search a turn
# needs, as a tool call in the conversation; without this the LLM searches again.
_SEARCH_RESULTS_RULE = """\
SEARCH RESULTS — if a lookup's result for the customer's latest request is already in the
conversation, answer from it; run the lookup again only if their criteria have changed since,
or they ask for more options (then search again with more=true). Follow the notes in a search
result: they say when to ask before showing other homes.
"""

_INBOUND_TASK = """\
CURRENT CALL: an inbound customer has connected. Find out what kind of place they're looking
for and help them shortlist properties.

Search as soon as they've given you anything to search on (a location, budget, type, etc.);
ask a clarifying question first only if they've given nothing at all (or, per OFFERS, they've
asked for rentals with offers). Once results are in,
offer to narrow them if there are many or broaden if there are none. Talk through the top 1-2
(on web chat they also see every result on screen). When one fits, invite them to see it as a
question ("Would you like to see the flat in person?"), and only once they say yes, start
booking it.

{booking_steps}
You can't schedule a callback or record that someone isn't interested on this call — never say
you have. If they'd rather talk later, invite them to get in touch whenever suits them, or
offer to book a viewing now.
"""

_OUTBOUND_TASK = """\
{call_opening} {client_criteria}

Goals, in order: (1) find out whether they're interested in hearing about listings and
record it with confirm_interest as soon as you know; (2) if so, search and discuss listings and
book a viewing if they want (see BOOKING A VIEWING; their name, and their number if it's on file,
are already on the form); (3) if they'd rather be contacted later, use
schedule_followup with a date they suggest and end politely. If they're not interested, thank
them, record it with confirm_interest and end the call — don't push.

The on-file criteria are a starting point, not a filter to keep reapplying. As soon as they say
anything beyond confirming the file (another area, rent instead of buy or vice versa, no
budget), search on exactly what they just said and drop the rest of the file. Rent and sale
budgets differ in scale (thousands vs. lakhs/crores), so carrying one into the other's search
returns nothing; if a search comes back empty, check for a stale on-file budget or type before
saying nothing is available.

{booking_steps}"""

# The first line of _OUTBOUND_TASK. A lead with no upcoming viewing may never
# have shown interest, so the cold call claims none.
_COLD_CALL_OPENING = """\
CURRENT CALL: an introductory cold call to {client_name}, a lead in our system. They didn't
initiate this call and may not have shown interest in anything specific; you opened by
introducing yourself and the agency and asking if it's a good time to talk."""
_FOLLOWUP_CALL_OPENING = """\
CURRENT CALL: you are calling {client_name}, an existing lead with a booked viewing (see VIEWING
FOLLOW-UP above)."""


# Put before the cold-call task when the lead has a viewing booked: the call
# follows it up (see SPOKEN_GREETINGS_VIEWING_FOLLOWUP).
_VIEWING_FOLLOWUP = """\
VIEWING FOLLOW-UP — this call follows up their booked viewing: {viewing}. You opened by naming
this viewing and asking whether it's a good time to talk.
- If they agree or sound positive (yes, okay, sure, go ahead, হ্যাঁ, বলেন, হুম, ঠিক আছে), carry
  on: check they're still coming at that time and answer their questions, then the goals below.
- If it's a bad time or they say no, that is not "not interested": don't call confirm_interest.
  Politely ask whether they'd like to change the viewing time. If yes, ask for the new day and
  time and call reschedule_viewing, then tell them the new time, speaking to them as "you".
  Their name and number are already on file: never ask for them and never mention a form; to
  move this viewing use reschedule_viewing, never update_booking_form or book_appointment. If
  they don't want to change it, ask when to call back, use schedule_followup and end politely
  (with no time given, just end politely). Use reschedule_viewing or schedule_followup, not both.
- Once reschedule_viewing has succeeded, its time replaces the one here and in WHAT YOU KNOW
  FROM EARLIER CONTACT; don't call confirm_interest after it.

"""


_PHONE_CALL_NOTE = """\
PHONE CALL: the customer has no screen — never mention cards, a screen or a list. Describe at
most two or three listings aloud, briefly (area, price, bedrooms), and offer more. Keep every
turn short.
Booking a viewing works the same way, by voice only: {phone_instruction}
When the conversation is over ({end_reasons}), call end_call on its own, with no goodbye
first: it then asks you for the goodbye, and the call ends once you've said it. Never leave the
line open.
"""

# Browser sessions: the marker app.agent.listing_focus strips from the reply and
# turns into that listing's card on screen. A fixed first position is easier for
# the model to keep to than "somewhere in the reply".
_SHOW_LISTING_RULE = """\
SHOWING ONE LISTING — the customer's screen shows the cards of the latest search. Whenever a
reply is about one particular listing (they picked one, asked about one, you recommend one, or
they want to see or book one), make the very first characters of that reply [show:N], where N is
that listing's #number from search_apartments. The marker is hidden: the customer never hears or
sees it, and their screen switches to that one listing's card. Never mention the marker. Leave it
out when the reply covers several listings, presents new search results, or isn't about a
listing. Examples:
- Customer: "দ্বিতীয়টার কথা বলেন" → "[show:2] উত্তরা সেক্টর ৪-এর ফ্ল্যাটটি ২২,০০০ টাকা..."
- Customer: "Tell me more about the Gulshan one" → "[show:3] The Gulshan flat has a lake view..."
- Customer: "ওই ১৮ হাজারেরটা দেখতে চাই" → "[show:1] ঠিক আছে, আমি আপনার জন্য একটি লাইভ ভিউয়িং বুক করব।..."
- Customer: "কোনগুলো সবচেয়ে সস্তা?" (several listings) → no marker.
"""

# Browser calls: a wrap-up gets "anything else?" first; a goodbye, or a no to
# that, gets the goodbye and end_call in the same reply. end_call waits for the
# goodbye to play, then the browser ends the call (browser_end_call). Should the
# model call end_call alone, its result asks for the goodbye (run_48 did only one).
_BROWSER_END_NOTE = """ENDING THE CALL: when the customer seems to be wrapping up (thanks for the help, that's all for
now, no more help needed, ঠিক আছে ধন্যবাদ, আর কিছু লাগবে না), don't end the call yet: ask
whether they need anything else. When they then say no, or when they say goodbye outright (bye,
আল্লাহ হাফেজ, আসি তাহলে, রাখি তাহলে), say goodbye in one or two short sentences that fit what
happened (thank them and invite them back anytime), in the language of their latest message,
and call end_call in that same reply, after the goodbye. The call ends once the goodbye has
played. If a thanks comes with a question, or they clearly want to go on, just carry on and
don't end the call.
"""

# Only a cold call can schedule a callback (schedule_followup), so an inbound
# caller who wants to talk later is told to ring back instead.
_END_REASONS_OUTBOUND = (
    "they've booked, moved their viewing and need nothing else, asked to be called "
    "later, aren't interested, "
    "or stay abusive after a warning"
)
_END_REASONS_INBOUND = (
    "they've booked, said they'll call back later, aren't interested, "
    "or stay abusive after a warning"
)


def _phone_booking_instruction(client) -> str:
    # A number heard over a phone line is easily misheard, and a wrong one books
    # the viewing under a different (or a new) client.
    phone = getattr(client, "phone", None)
    if phone:
        return (
            f"the number on file is {phone} and is already on the form. Read it back "
            "and ask whether to use it; if they give another, pass it as phone, then read it "
            "back digit by digit."
        )
    return (
        "ask for their mobile number, read it back digit by digit to confirm, then pass it as "
        "phone."
    )


def _client_criteria_summary(client) -> str | None:
    parts = []
    if client.preferred_property_type:
        parts.append(client.preferred_property_type)
    if client.preferred_location:
        parts.append(f"in {client.preferred_location}")
    if client.budget_min or client.budget_max:
        parts.append(f"budget {client.budget_min or '?'}-{client.budget_max or '?'}")
    if getattr(client, "bedrooms_wanted", None):
        parts.append(f"{client.bedrooms_wanted}+ bedrooms")
    # "undecided" is the column default, not something the lead said.
    if client.rent_or_buy and client.rent_or_buy != RentOrBuy.undecided:
        parts.append(str(client.rent_or_buy.value))
    return ", ".join(parts) if parts else None


def knowledge_scope_text(config: ResolvedAgentConfig, rag_tool_available: bool) -> str:
    template = KNOWLEDGE_SCOPE_RAG if rag_tool_available else KNOWLEDGE_SCOPE_DEFAULT
    return template.format(
        agency_name=config.agency_name,
        agency_phone=config.agency_phone,
        agency_address=config.agency_address,
    )


def build_system_prompt(
    userdata: SessionUserdata,
    config: ResolvedAgentConfig | None = None,
    *,
    rag_tool_available: bool = False,
) -> str:
    """`config` None loads the saved agent config (env/code defaults if the DB
    can't be read). `rag_tool_available` must only be True when the
    search_knowledge_base tool is actually registered for the session."""
    if config is None:
        config = agent_config_service.load()
    tz = agency_tz()
    current_date = datetime.now(tz).strftime(f"%A, %Y-%m-%d %H:%M ({tz.key})")
    knowledge_scope = knowledge_scope_text(config, rag_tool_available)
    identity = render_template(
        "prompt_identity_rules",
        config.prompt_identity_rules,
        {
            "agent_name": config.assistant_name,
            "agency_name": config.agency_name,
            "current_date": current_date,
            "timezone": tz.key,
            "knowledge_scope": knowledge_scope,
        },
    )
    if knowledge_scope not in identity:
        # A custom prompt without {knowledge_scope} still gets the scope rules.
        identity = f"{identity.rstrip()}\n\n{knowledge_scope}\n"

    booking_steps = _BOOKING_STEPS.format(
        viewing_hours=viewing_hours_text(),
        form_note=(
            "" if userdata.is_phone_call else " (on web chat they can also type their name and "
            "number into the form on screen and press Confirm)"
        )
    )
    cold_call = False
    if userdata.channel == Channel.outbound_coldcall and userdata.client is not None:
        cold_call = True
        viewing = userdata.upcoming_viewing
        opening = _COLD_CALL_OPENING if viewing is None else _FOLLOWUP_CALL_OPENING
        criteria = _client_criteria_summary(userdata.client)
        task = _OUTBOUND_TASK.format(
            call_opening=opening.format(client_name=userdata.client.full_name),
            client_criteria=(
                f"Their file has: {criteria}."
                if criteria
                else "Nothing on file — find out what they're looking for."
            ),
            booking_steps=booking_steps,
        )
        if viewing is not None:
            what = viewing.property_title or "a viewing"
            followup = _VIEWING_FOLLOWUP.format(viewing=f"{what} on {spoken_local(viewing.when)}")
            task = followup + task
    else:
        task = _INBOUND_TASK.format(booking_steps=booking_steps)

    task = f"{task}\n{_OFFERS_RULE}\n{_SEARCH_RESULTS_RULE}"
    if history := client_history.render(userdata.history):
        task = f"{task}\n{history}"

    if userdata.is_phone_call:
        phone_note = _PHONE_CALL_NOTE.format(
            phone_instruction=_phone_booking_instruction(userdata.client),
            end_reasons=_END_REASONS_OUTBOUND if cold_call else _END_REASONS_INBOUND,
        )
        return f"{identity}\n{task}\n{phone_note}"
    return f"{identity}\n{_SHOW_LISTING_RULE}\n{task}\n{_BROWSER_END_NOTE}"
