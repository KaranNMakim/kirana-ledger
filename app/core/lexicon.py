"""Hinglish / Gujarati / Marathi lexicon: number words, currency, intent cues, postpositions, fillers.

Everything is stored in `canon()` form so that spelling variants (udhaar/udhar, chukta/chuktaa) collapse.
"""

from __future__ import annotations

from app.kg.names import canon


def _c(words: str | list[str]) -> set[str]:
    items = words.split() if isinstance(words, str) else words
    return {canon(w) for w in items}


# ---------------------------------------------------------------- numbers
_NUMBER_WORDS_RAW = {
    "ek": 1, "ik": 1, "one": 1, "do": 2, "two": 2, "be": 2, "teen": 3, "tin": 3, "tran": 3, "three": 3,
    "char": 4, "chaar": 4, "four": 4, "panch": 5, "paanch": 5, "five": 5, "chhe": 6, "chhah": 6, "chha": 6,
    "six": 6, "saat": 7, "seven": 7, "aath": 8, "eight": 8, "nau": 9, "nine": 9, "das": 10, "dus": 10,
    "ten": 10, "gyarah": 11, "barah": 12, "baarah": 12, "twelve": 12, "pandrah": 15, "bees": 20, "vees": 20,
    "twenty": 20, "pachees": 25, "pachchis": 25, "tees": 30, "thirty": 30, "chalis": 40, "chaalis": 40,
    "pachas": 50, "pachaas": 50, "fifty": 50, "sau": 100, "hundred": 100, "hazaar": 1000, "hajar": 1000,
    "hazar": 1000, "thousand": 1000,
    # fractions
    "aadha": 0.5, "adha": 0.5, "aadhu": 0.5, "adhu": 0.5, "aadhi": 0.5, "half": 0.5,
    "dedh": 1.5, "dodh": 1.5, "dhai": 2.5, "adhai": 2.5, "sava": 1.25, "pauna": 0.75, "paune": 0.75,
}
NUMBER_WORDS: dict[str, float] = {canon(k): float(v) for k, v in _NUMBER_WORDS_RAW.items()}
MULTIPLIERS = {canon("sau"): 100, canon("hundred"): 100, canon("hazaar"): 1000, canon("hajar"): 1000,
               canon("hazar"): 1000, canon("thousand"): 1000}
# number words that are also common function words; only numbers when followed by unit/product/number
WEAK_NUMBERS = _c("do be ek")
HALF_WORDS = _c("aadha adha aadhu adhu aadhi half")

CURRENCY = _c("₹ rs rs. rupay rupaye rupaiye rupiya rupiye rupee rupees ru inr rupya rupia rupaya rupe")

# ---------------------------------------------------------------- intent cues (canon form)
SALE_CUES = _c("udhaar udhar udhari udhaari likh likho likhdo likhna likhlo likhiye likhe lakho lakhi lakhjo "
               "lakhvu lakhvanu khata khate khaate credit le liya liye legaya legaye lai laigaya "
               "lidhu lidha leva")
GIVE_CUES = _c("diya diye di de dena dediya dediye diyo aapya aapyu aapi aapo didhu didha dila dile")
PAYMENT_CUES = _c("jama jamaa chukta chuktaa chukaya chukaye chukavya chukvya chukvi chukave bhara bhare "
                  "bharya bharyu payment paid pay upi gpay paytm phonepe online cash nakad rokda mile mila "
                  "milgaye received bhugtan")
RETURN_CUES = _c("vapas vaapas wapas wapis return returned lauta lautaya lautaye lotaya pachu pacha pachha "
                 "parat ferat")
QUERY_CUES = _c("kitna kitne kitni kitnu ketla ketlu ketli kitla kiti balance batao bata batav batavo "
                "bataiye dikhao dekho kya kab how much what")

POSTPOSITIONS = _c("ko ne ka ki ke nu na ni no e pase taraf se kade")
STRONG_POSTPOSITIONS = _c("ko ne ka ki ke nu e pase")
CONJUNCTIONS = _c("aur or and ane ani va tatha plus n")
BALANCE_WORDS = _c("hisab hisaab hishab hisaab-kitab baaki baki udhaar udhar khata bill paise paisa")
FULL_WORDS = _c("pura poora pure poore sara saara sab badha badhu full total poora-poora")

DATE_TODAY = _c("aaj aj aje aaje today abhi")
DATE_YESTERDAY = _c("kal kaal yesterday gaikal gaikale")
DATE_DAY_BEFORE = _c("parso parson parsu parsoon")
DAYS_AGO_MARKERS = _c("din divas day days")
AGO_MARKERS = _c("pehle pahle pehele pela pehla pehlaa pahela ago purve")
LAST_WEEK = [(_c("pichhle pichle last gaya"), _c("hafte hafta week athvadiye athvadiya"))]
WEEKDAYS = {
    **dict.fromkeys(_c("somvar monday som"), 0), **dict.fromkeys(_c("mangalvar tuesday mangal"), 1),
    **dict.fromkeys(_c("budhvar wednesday budh"), 2), **dict.fromkeys(_c("guruvar thursday brihaspativar"), 3),
    **dict.fromkeys(_c("shukravar friday shukra"), 4), **dict.fromkeys(_c("shanivar saturday shani"), 5),
    **dict.fromkeys(_c("ravivar itvar sunday ravi"), 6),
}

FILLERS = _c(
    "aaj aj kal parso abhi to toh bhi hai he hain tha thi the hua hui hue kar karo kiya kiye kari karna "
    "karke karvanu karjo do lo diya saman samaan maal saamaan cheez wala wali wale vala vali vale mera meri "
    "hamara uska uski unka unki unke ji please plz bhaiya jara zara ek baar entry note account ledger "
    "mein me ma maa par pe upar thoda thodi aur bhi aapna aapnu taro tamaru maaru chhe che hatu hata "
    "naam name ke liye mate vaste kitna baaki baki pending sab diye de rahe raha rahi gaya gayi gaye "
    "dijiye dena lena hisab hisaab rupaye"
) | CURRENCY

ALL_CUES = SALE_CUES | GIVE_CUES | PAYMENT_CUES | RETURN_CUES | QUERY_CUES
