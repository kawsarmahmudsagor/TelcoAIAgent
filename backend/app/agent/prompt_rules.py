"""Wording rules shared by several prompts, written once.

The main prompt (prompt_defaults), the quick-reply prompts (quick_reply) and
the idle check-in prompt (idle_checkin) all insert these instead of restating
them. Plain text with no braces: they go into str.format templates. Kept free of
livekit/DB imports, like prompt_defaults.
"""

PACKAGE_WORD = (
    'Say "প্যাকেজ", never "প্যাক", in every form: "প্যাকেজগুলো" not "প্যাকগুলো", '
    '"প্যাকেজটা" not "প্যাকটা".'
)

BANGLA_WORDS = (
    "Use the English words Bangla speakers use (চেক, প্যাকেজ, ব্যালেন্স, রিচার্জ, ডাটা, মিনিট, "
    'অফার, কোড, ওকে) and "দাম", not "প্রাইস"; never bookish words (তথ্য অনুযায়ী, উক্ত, '
    "অবশিষ্ট, মিলিয়ে, ঘেঁটে, খুলছি, অনুগ্রহপূর্বক)."
)

BRAND = 'The operator is "telco", never "telco.".'
