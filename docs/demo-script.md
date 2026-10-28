# Demo script (5 minutes)

**Setup:** run `make demo`, then open **http://localhost:8141/app/** on a phone-sized window (360–420 px wide).
The data is a fresh, seeded synthetic ledger for *Shree Ganesh Kirana Stores*: 60 customers, Jun–Nov 2025, demo clock **30 Nov 2025**.
Every flow below is also checked automatically by `tests/test_demo_script.py`.

> Voice needs Chrome or Edge (Web Speech API, `hi-IN` / `gu-IN`). Everything works with the typed box or the example chips too.

---

## Flow 1: speak a credit sale (about 45 s)

**Story:** "Suresh bhai takes biscuits and oil on credit. The shopkeeper just says it."

1. On **Ledger**, tap 🎙️ and say **"Suresh ka 3 packet Parle-G aur 1 litre tel likh do"**, or tap that example chip.
2. A green **✓ Saved** card appears: *Suresh Mehta · ₹180 · 3 packet Parle-G, 1 l Sunflower Oil*.
   - `tel` is a generic word. The ontology maps it to the shop's default oil, and the price comes from the seeded price list.
   - Every field scored ≥ 0.75 confidence, so there was no card to tap through.
3. The entry is at the top of **Live ledger**, labelled *auto (rules) · price list*.
4. Tap **↩ Undo** to show that any auto-save is one tap from being reversed. The undo is recorded with `method: human` provenance and is not deleted.

**Say:** "No forms. Hinglish in, a structured ledger entry out, with an undo button."

## Flow 2: resolve an ambiguous customer (about 60 s)

**Story:** "There are two Rameshes on the books. The app must not guess."

1. Say or tap **"Ramesh bhai ko 2 kilo chawal udhaar"**.
2. An amber **Please check ✋** card appears instead of a save:
   - Reason: *'ramesh bhai' could be 2 customers*.
   - **Which Ramesh?** shows *Ramesh Patel · Shivam Society · owes ₹…* and *Ramesh Shah · Gali 3 · owes ₹…*.
   - Items: *2 kg Rice (Kolam)* with − / + buttons. Amount: ₹120 *from price list*.
3. Tap **Ramesh Shah**, then **✓ Save**. The feed shows the entry as *confirmed by you*.
4. Optionally try **"Kavitaben na khata ma 1 kilo khand lakhi do"** (Gujarati transliteration). Kavita Shah and Kavitha Nair both match, so it asks again.

**Say:** "Low confidence never saves silently. On our labelled set the false-save rate is 0%, and every ambiguous name triggered a question (see `docs/eval-report.md`)."

## Flow 3: draft a reminder to a late payer (about 90 s)

**Story:** "Who should I nudge, and how do I say it politely?"

1. Open **Insights**. The top cards show total udhaar out against what was collected in the last 30 days.
2. Under **Who pays late**, tap **Kishore Desai**, or another red *Frequently late* customer.
3. On the customer card, tap **Why?** under *Indicative payment pattern (demo heuristic)*:
   - Every deduction is listed: average days to pay, oldest unpaid purchase, partial payments, recent payment, festival lateness.
   - Point out the **disclaimer**: this is a demo heuristic and *not a credit score*.
4. Tap **💬 Draft reminder**. You get a polite Hinglish WhatsApp message with the balance, the date it has been pending since, and a thank-you for the last payment.
5. Switch to **Gujarati** → *"Jai Shree Krishna Kishorebhai 🙏 … tamaru ₹… nu hisaab baaki chhe"*. Try **Firm** too.
6. Tap **📋 Copy text**. The note says **Draft only. Nothing has been sent.**

**Say:** "The graph knows who owes what and how they usually pay, and turns that into a respectful message. The shopkeeper stays in control of sending."

---

## Optional extras (if there is time)

| Try | Shows |
|---|---|
| "aaj Kishore ne aadha hisaab chukta kiya" | Balance expression: the card computes *half of balance ₹X = ₹Y; please confirm* |
| "Meena ben ne 500 diye" | Payment auto-saved; Meena's balance updates |
| "मीना बेन ने 500 दिए" / "મીનાબેન એ 500 આપ્યા" | Devanagari and Gujarati script, as hi-IN / gu-IN speech engines return it |
| "Kishore ka kitna baaki hai" | Query answered in place, nothing saved |
| Customer page → **✎ Edit amount** → toggle *show corrections* | Correction chain: old entry voided, new one `corrects` it |
| **Graph** tab | Cytoscape udhaar graph: size = balance, colour = payment pattern; tap a node |
| `GET /ontology?format=turtle` | Ontology plus the 162-product alias catalogue as RDF |
| `GET /docs` | OpenAPI for every endpoint |
