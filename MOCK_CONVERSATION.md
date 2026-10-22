# Mock conversations: voice test script

Six voice calls that cover what changed in commit `8ba3f26`, plus older behaviour that should
still work.

- Say each numbered line out loud, wait for the agent's full reply, then check the
  **Expect** note.
- The prices and areas come from the current seed data. If the listings change, the
  numbers will move, but the behaviour should not.

**On every call, check the greeting first:**
- It opens with **"আসসালামু আলাইকুম"**.
- The agent calls herself **Anika**.
- It says "ফ্ল্যাট বা বাড়ি", not "বাসা".
- It plays only once.

---

## 1. The original bug: flats around 15,000 (Banglish)

1. *(Wait for the greeting.)*
2. Amake 15000 er moddhe flat dekhao.
   - **Expect:** flats around 15,000, e.g. Uttara Sector 10, Kazipara, Lalmatia. Never
     "15000 er moddhe flat nei".
   - At most one card can be slightly over, up to 16,500. The agent must not call that one
     "within budget".
3. Aro option dekhao.
   - **Expect:** new cards, none repeated from the first set. All at or below 16,500.
4. Accha, 15000 er moddhe 2 bedroom er flat ache?
   - **Expect:** says plainly that there's no 2-bedroom under 15,000. Offers the nearest ones
     instead: Uttara Sector 7 at 15,500, then about 16,000.
5. Uttara r ta 15,500 e, oita dekhte chai.
6. Kal shondha shat tay.
   - **Expect:** refuses 7 pm politely. Viewings start between 8 am and 6 pm. Asks for another
     time.
7. Thik ache, kal bikal char tay.
8. Amar naam Rakib Hasan.
9. Number holo zero one seven zero one, zero zero one, three nine eight.
   - **Expect:** reads the number back correctly (01701001398) and asks you to confirm.
10. Ha, thik ache.
    - **Expect:** confirms the booking for tomorrow at 4 pm.
11. Dhonnobad, ar kichu lagbe na.
    - **Expect:** a short goodbye, then **the call ends by itself**.

---

## 2. বাসা / বাড়ি and a hard maximum (Bangla)

1. পনেরো হাজার টাকার মধ্যে একটা বাসা খুঁজছি।
   - **Expect:** shows flats around 15,000. It must not say "বাসা নেই" or start from 32,000
     (that is the cheapest whole house).
2. আচ্ছা, সর্বোচ্চ পনেরো হাজার, এর বেশি একদম না।
   - **Expect:** every card is at or below 15,000. Nothing at 15,500 or 16,000.
3. বাংলাদেশ ক্রিকেট টিম এবার কেমন খেলছে?
   - **Expect:** a polite refusal, then back to finding a home.
4. আচ্ছা, পুরো একটা বাড়ি ভাড়া চাই, পঞ্চাশ হাজারের মধ্যে।
   - **Expect:** homes up to 50,000, flats and houses both. পুরো বাড়ি is not a house filter.
5. ১৫ হাজারের মধ্যে পুরো বাড়ি পাওয়া যাবে?
   - **Expect:** says there's no house in that budget, then offers flats that fit. It does not
     dead-end.
6. ঠিক আছে, পরে জানাবো। আল্লাহ হাফেজ।
   - **Expect:** a short goodbye, then the call ends.

---

## 3. Two areas: "ba" vs "ebong" (Banglish + Bangla)

1. Dhanmondi ba Mirpur e 15000 er moddhe flat dekhao.
   - **Expect:**
     - Says Dhanmondi has nothing under 15,000; rents there start at 17,000.
     - Then shows Mirpur flats (Mirpur 10, Kazipara, Pallabi ...).
     - Never "দুই জায়গাতেই নেই" (none in either area).
2. Mirpur ebong Uttara te 15000 er moddhe flat dekhao.
   - **Expect:** cards from both areas, split about evenly (3+2 or 2+3). It names each card's
     area.
3. *(Interrupt: while the agent is speaking, say)* Ekto daran, ekta kotha.
   - **Expect:** the agent stops talking almost at once and listens.
4. Uttara, Dhaka te 2 bedroom er flat koto theke shuru?
   - **Expect:** Uttara only. 2-bed rents there start at 15,500. "Dhaka" must not widen the
     search to the whole city.
5. ধানমন্ডি আর গুলশান, দুই জায়গাতেই দেখান, বিশ হাজারের মধ্যে।
   - **Expect:**
     - Dhanmondi cards around 20,000.
     - For Gulshan, a sentence like "গুলশানে ২০,০০০-এর মধ্যে নেই, ৩১,৫০০ থেকে শুরু", with no
       Gulshan card.
6. আচ্ছা, ধন্যবাদ, আজ এই পর্যন্তই।
   - **Expect:** a goodbye, then the call ends.

---

## 4. Buy-to-rent switch and carried-over criteria (Banglish)

1. Assalamu alaikum. Mirpur e ekta flat kinte chai, panchash lakh er moddhe.
   - **Expect:** Mirpur flats for sale near 50 lakh. The cheapest Mirpur sale flat is 34 lakh.
2. Ei flat gulor kono offer ache?
   - **Expect:** names offers briefly (sale listings only). It doesn't invent a discount.
3. Accha thak, amake 15000 er moddhe flat dekhao.
   - **Expect:** treats this as **rent**: shows rentals around 15,000, or asks "ভাড়া খুঁজছেন?".
     It must not say "১৫,০০০ টাকার মধ্যে ফ্ল্যাট নেই" and then show 25-lakh sale flats.
4. Gulshan e dekhao.
   - **Expect:**
     - Says Gulshan rents start at 31,500, with nothing under 15,000.
     - **Offers** to show the flats under 15,000 elsewhere, but doesn't show them unasked.
5. Ha, onno jaygay dekhao.
   - **Expect:** flats around 15,000 outside Gulshan.
6. 3 bedroom er lagbe, 15000 er moddhe.
   - **Expect:** no 3-bedroom under 15,000 (they start at 38,000). It offers the cheaper
     smaller flats that fit.
7. 15 lakh e kono flat kinte pabo?
   - **Expect:** treated as buying. Nothing under 15 lakh; sale flats start at 25 lakh
     (Savar Bazar). It must not show 7,000-taka rentals.
8. Accha, thik ache. Allah Hafez.
   - **Expect:** a goodbye, then the call ends.

---

## 5. English buyer: offers, a price question, a viewing outside hours

1. Hi, I'm looking to buy a flat in Dhanmondi, up to one and a half crore.
   - **Expect:** Dhanmondi sale flats near 1.5 crore. The cheapest there is 63 lakh.
2. Which one is the cheapest?
3. Are there any offers on that one?
4. Can the price go down a bit more?
   - **Expect:** no negotiation. It points you to the agency phone number or the head office.
     It must not invent a discount.
5. Who will win the next election?
   - **Expect:** a polite refusal, back on topic.
6. Okay, I'd like to see the cheapest one at 9 tonight.
   - **Expect:** refuses 9 pm (viewings are 8 am to 6 pm). Asks for another time.
7. Then this Friday at 11 in the morning.
8. Nusrat Jahan.
9. My number is 01811110000.
10. Sorry, wrong number. It's zero one nine one one, two two three three four four.
    - **Expect:** uses the corrected number (01911223344) and reads it back.
11. Yes, please book it.
12. Thanks, that's all. Bye!
    - **Expect:** a goodbye, then the call ends.

---

## 6. Quick small-talk, silence and the idle check-in

1. *(After the greeting)* Hello? Shunte pachchen?
   - **Expect:** a short, quick answer (a quick reply, if it is on in the dashboard). No
     search.
2. Apnar naam ki?
   - **Expect:** "Anika", from the agency.
3. Mohammadpur e dui bedroom er flat, bish hajar er moddhe.
   - **Expect:**
     - If quick replies are on, a short filler line with no numbers may play while it
       searches.
     - Then 2-bed flats around 20,000 (Mohammadpur 2-beds start at 18,000).
4. *(Stay silent for 5 minutes.)*
   - **Expect:** one check-in: "আপনি কি আর কিছু জানতে চাচ্ছেন?".
5. *(Stay silent for 30 more seconds.)*
   - **Expect:** a short goodbye, then **the call ends by itself**.

---

## Pass checklist

| Check | Where it is tested |
|---|---|
| Greeting opens with "আসসালামু আলাইকুম", the name is Anika, it plays once | Every call |
| "15000 er moddhe" shows flats around 15k, with at most 1 slightly over | 1.2 |
| "Aro dekhao" shows new homes only | 1.3 |
| A near miss names the closest option instead of a flat "নেই" | 1.4, 4.6 |
| A viewing outside 8 am–6 pm is refused politely | 1.6, 5.6 |
| A spoken phone number is read back correctly; a correction is used | 1.9, 5.10 |
| বাসা / বাড়ি search flats, not only whole houses | 2.1, 2.5 |
| "সর্বোচ্চ / er beshi na" is never exceeded | 2.2 |
| "পুরো বাড়ি" is not a house filter: flats and houses both come back | 2.4 |
| "ba" shows whichever area fits; an empty area gets one sentence | 3.1 |
| "ebong" splits the cards between the areas | 3.2, 3.5 |
| Talking over the agent stops it at once | 3.3 |
| "Area, Dhaka" stays in that area | 3.4 |
| Moving from buy to a rent-size budget doesn't search sale | 4.3 |
| A kept area/bedroom count gets an offer of what fits instead | 4.4, 4.6 |
| A lakh budget means buying | 4.7 |
| Offers are named but never invented; no negotiation | 4.2, 5.3, 5.4 |
| Off-topic questions are refused politely | 2.3, 5.5 |
| A goodbye ends the call | 1.11, 2.6, 3.6, 4.8, 5.12 |
| Silence: a check-in after 5 min, then a hang-up after 30 s | 6.4, 6.5 |
