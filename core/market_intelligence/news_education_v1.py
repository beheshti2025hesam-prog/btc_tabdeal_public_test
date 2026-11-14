"""Free-first, evidence-grounded multilingual explanations for individual news items.

This is a deterministic educational layer, not a generative LLM or a price predictor.
One canonical interpretation is shared by the dashboard and Mother Agent.
"""
from __future__ import annotations

from typing import Mapping

SCHEMA_VERSION = "hes.news_item_interpretation.v1"
LOCALES = ("fa", "en", "de", "fr")

_CATEGORY = {
    "monetary_policy": {
        "channel": {"fa": "سیاست پولی و نقدینگی", "en": "Monetary policy and liquidity", "de": "Geldpolitik und Liquidität", "fr": "Politique monétaire et liquidité"},
        "why": {"fa": "تصمیم بانک مرکزی می‌تواند هزینه تأمین مالی، بازده اوراق، ارزش ارزها و اشتهای ریسک را تغییر دهد. اثر نهایی به جزئیات تصمیم و واکنش بازار بستگی دارد.", "en": "Central-bank decisions can change funding costs, bond yields, currencies and risk appetite. The net effect depends on the decision details and the market reaction.", "de": "Entscheidungen von Zentralbanken können Finanzierungskosten, Anleiherenditen, Währungen und die Risikobereitschaft verändern. Die Nettoauswirkung hängt von den Details und der Marktreaktion ab.", "fr": "Les décisions des banques centrales peuvent modifier les coûts de financement, les rendements obligataires, les devises et l'appétit pour le risque. L'effet net dépend des détails et de la réaction du marché."},
        "monitor": {"fa": "متن رسمی تصمیم، بازده اوراق، شاخص دلار، نوسان و واکنش قیمت و حجم دارایی مرتبط را بررسی کن.", "en": "Check the official statement, bond yields, the dollar index, volatility, and price/volume reaction in the relevant asset.", "de": "Prüfe die offizielle Erklärung, Anleiherenditen, den Dollarindex, die Volatilität sowie die Preis- und Volumenreaktion des betroffenen Assets.", "fr": "Surveillez le communiqué officiel, les rendements obligataires, l'indice du dollar, la volatilité et la réaction des prix et volumes de l'actif concerné."},
        "education": {"fa": "نرخ بهره هزینه وام‌گرفتن را نشان می‌دهد. تغییر آن می‌تواند جذابیت دارایی‌های کم‌ریسک را در مقایسه با دارایی‌های پرریسک جابه‌جا کند.", "en": "An interest rate is the cost of borrowing. A change can shift the relative appeal of lower-risk assets versus riskier assets.", "de": "Der Zinssatz ist der Preis für geliehenes Geld. Eine Änderung kann die relative Attraktivität risikoärmerer und riskanterer Anlagen verschieben.", "fr": "Le taux d'intérêt représente le coût de l'emprunt. Sa variation peut modifier l'attrait relatif des actifs moins risqués et plus risqués."},
    },
    "regulation": {
        "channel": {"fa": "قانون‌گذاری و ریسک حقوقی", "en": "Regulation and legal risk", "de": "Regulierung und Rechtsrisiko", "fr": "Réglementation et risque juridique"},
        "why": {"fa": "قواعد یا اقدامات حقوقی می‌توانند دسترسی، هزینه فعالیت، پذیرش نهادی و نقدشوندگی یک صنعت یا دارایی را تغییر دهند. دامنه اثر به حوزه قضایی و متن رسمی بستگی دارد.", "en": "Rules or legal actions can change access, operating costs, institutional adoption and liquidity. The scope depends on the jurisdiction and the official text.", "de": "Regeln oder rechtliche Maßnahmen können Zugang, Betriebskosten, institutionelle Akzeptanz und Liquidität verändern. Das Ausmaß hängt vom Rechtsraum und vom offiziellen Wortlaut ab.", "fr": "Les règles ou actions judiciaires peuvent modifier l'accès, les coûts d'exploitation, l'adoption institutionnelle et la liquidité. Leur portée dépend de la juridiction et du texte officiel."},
        "monitor": {"fa": "متن و مرجع رسمی، تاریخ اجرا، دارایی‌ها و کشورهایی که مشمول‌اند، و واکنش قیمت و حجم را بررسی کن.", "en": "Check the official text and authority, effective date, affected assets and jurisdictions, and price/volume reaction.", "de": "Prüfe den offiziellen Text und die zuständige Behörde, das Inkrafttreten, betroffene Assets und Rechtsräume sowie die Preis-/Volumenreaktion.", "fr": "Vérifiez le texte et l'autorité officiels, la date d'entrée en vigueur, les actifs et juridictions concernés, ainsi que la réaction des prix et volumes."},
        "education": {"fa": "ریسک مقرراتی یعنی احتمال اینکه تغییر قانون یا نحوه اجرای آن بر امکان فعالیت، هزینه یا تقاضای یک بازار اثر بگذارد.", "en": "Regulatory risk is the possibility that a rule or its enforcement changes a market's ability to operate, its costs or demand.", "de": "Regulierungsrisiko bezeichnet die Möglichkeit, dass Regeln oder ihre Durchsetzung die Geschäftstätigkeit, Kosten oder Nachfrage eines Marktes verändern.", "fr": "Le risque réglementaire désigne la possibilité qu'une règle ou son application modifie l'activité, les coûts ou la demande d'un marché."},
    },
    "security": {
        "channel": {"fa": "امنیت، طرف مقابل و اعتماد", "en": "Security, counterparty risk and trust", "de": "Sicherheit, Gegenparteirisiko und Vertrauen", "fr": "Sécurité, risque de contrepartie et confiance"},
        "why": {"fa": "رخداد امنیتی ممکن است اعتماد، دسترسی به دارایی، برداشت، نقدشوندگی و ریسک طرف مقابل را تحت تأثیر قرار دهد. شدت اثر بدون تأیید جزئیات مشخص نیست.", "en": "A security incident may affect trust, asset access, withdrawals, liquidity and counterparty risk. Its severity is unknown until details are verified.", "de": "Ein Sicherheitsvorfall kann Vertrauen, Vermögenszugang, Auszahlungen, Liquidität und Gegenparteirisiken beeinflussen. Das Ausmaß ist bis zur Bestätigung der Details unklar.", "fr": "Un incident de sécurité peut affecter la confiance, l'accès aux actifs, les retraits, la liquidité et le risque de contrepartie. Sa gravité reste inconnue tant que les détails ne sont pas vérifiés."},
        "monitor": {"fa": "اطلاعیه رسمی، وضعیت برداشت و واریز، دارایی‌های درگیر، شواهد مستقل و اختلاف قیمت/اسپرد را بررسی کن.", "en": "Check official updates, deposit/withdrawal status, affected assets, independent corroboration and price/spread dislocations.", "de": "Prüfe offizielle Meldungen, Ein- und Auszahlungsstatus, betroffene Assets, unabhängige Bestätigungen und Preis-/Spread-Verwerfungen.", "fr": "Vérifiez les annonces officielles, l'état des dépôts et retraits, les actifs concernés, les confirmations indépendantes et les anomalies de prix ou de spread."},
        "education": {"fa": "ریسک طرف مقابل یعنی احتمال اینکه نهادی که دارایی یا معامله به آن وابسته است، نتواند تعهد خود را انجام دهد.", "en": "Counterparty risk is the possibility that an institution holding assets or facilitating a transaction cannot meet its obligations.", "de": "Gegenparteirisiko ist das Risiko, dass eine Institution, bei der Vermögenswerte liegen oder die eine Transaktion ermöglicht, ihre Verpflichtungen nicht erfüllt.", "fr": "Le risque de contrepartie est la possibilité qu'un établissement qui détient des actifs ou facilite une transaction ne respecte pas ses engagements."},
    },
    "exchange": {
        "channel": {"fa": "عملیات صرافی و نقدشوندگی", "en": "Exchange operations and liquidity", "de": "Börsenbetrieb und Liquidität", "fr": "Opérations de plateforme et liquidité"},
        "why": {"fa": "توقف معامله، تغییر فهرست یا اختلال عملیاتی ممکن است دسترسی و نقدشوندگی همان پلتفرم یا دارایی مشخص را تغییر دهد؛ لزوماً جهت کل بازار را تعیین نمی‌کند.", "en": "Trading halts, listing changes or operational outages may affect access and liquidity on that venue or for that asset; they do not necessarily determine the broader market direction.", "de": "Handelsunterbrechungen, Listing-Änderungen oder Betriebsstörungen können Zugang und Liquidität auf dieser Plattform oder für dieses Asset beeinflussen; sie bestimmen nicht zwangsläufig die Richtung des Gesamtmarktes.", "fr": "Les suspensions, changements de cotation ou pannes peuvent affecter l'accès et la liquidité sur cette plateforme ou pour cet actif ; ils ne déterminent pas nécessairement la direction du marché global."},
        "monitor": {"fa": "وضعیت رسمی سامانه، بازارهای درگیر، زمان بازگشایی، عمق سفارش و اختلاف قیمت بین پلتفرم‌ها را بررسی کن.", "en": "Check official system status, affected markets, reopening time, order-book depth and cross-venue price differences.", "de": "Prüfe den offiziellen Systemstatus, betroffene Märkte, Wiedereröffnungszeit, Orderbuchtiefe und Preisunterschiede zwischen Handelsplätzen.", "fr": "Surveillez l'état officiel du système, les marchés concernés, l'heure de reprise, la profondeur du carnet et les écarts de prix entre plateformes."},
        "education": {"fa": "نقدشوندگی یعنی بتوان دارایی را با سرعت و بدون تغییر شدید قیمت خرید یا فروخت.", "en": "Liquidity is the ability to buy or sell an asset quickly without causing a large price move.", "de": "Liquidität bedeutet, einen Vermögenswert schnell zu kaufen oder zu verkaufen, ohne den Preis stark zu bewegen.", "fr": "La liquidité est la possibilité d'acheter ou de vendre rapidement un actif sans provoquer une forte variation de prix."},
    },
    "macro": {
        "channel": {"fa": "اقتصاد کلان و اشتهای ریسک", "en": "Macroeconomics and risk appetite", "de": "Makroökonomie und Risikobereitschaft", "fr": "Macroéconomie et appétit pour le risque"},
        "why": {"fa": "داده‌های رشد، اشتغال، تورم یا تنش‌های ژئوپلیتیک می‌توانند انتظارات درباره رشد، نرخ بهره، ارزها و تقاضا برای دارایی‌های پرریسک را تغییر دهند.", "en": "Growth, employment, inflation or geopolitical data can change expectations for growth, rates, currencies and demand for risk assets.", "de": "Daten zu Wachstum, Beschäftigung und Inflation sowie geopolitische Spannungen können Erwartungen zu Wachstum, Zinsen, Währungen und der Nachfrage nach Risikoanlagen verändern.", "fr": "Les données de croissance, d'emploi et d'inflation ainsi que les tensions géopolitiques peuvent modifier les anticipations de croissance, de taux, de devises et la demande d'actifs risqués."},
        "monitor": {"fa": "عدد واقعی را با پیش‌بینی و رقم قبلی مقایسه کن؛ سپس بازده اوراق، ارز مرتبط، نوسان و واکنش قیمت/حجم را بررسی کن.", "en": "Compare the actual release with consensus and the prior reading; then check yields, relevant currencies, volatility and price/volume reaction.", "de": "Vergleiche den veröffentlichten Wert mit Konsens und Vorwert; prüfe danach Renditen, relevante Währungen, Volatilität und Preis-/Volumenreaktion.", "fr": "Comparez la publication au consensus et à la valeur précédente ; examinez ensuite les rendements, les devises concernées, la volatilité et la réaction des prix et volumes."},
        "education": {"fa": "اشتهای ریسک نشان می‌دهد سرمایه‌گذاران تا چه اندازه حاضرند برای بازده احتمالی، نوسان و زیان بیشتری را بپذیرند.", "en": "Risk appetite describes how willing investors are to accept volatility and potential losses in pursuit of returns.", "de": "Risikobereitschaft beschreibt, wie stark Anleger für mögliche Renditen Schwankungen und Verluste akzeptieren.", "fr": "L'appétit pour le risque décrit la disposition des investisseurs à accepter volatilité et pertes potentielles en échange de rendements."},
    },
    "crypto_market": {
        "channel": {"fa": "عرضه، تقاضا و جریان سرمایه رمزارز", "en": "Crypto supply, demand and capital flows", "de": "Kryptoangebot, Nachfrage und Kapitalflüsse", "fr": "Offre, demande et flux de capitaux crypto"},
        "why": {"fa": "خبر مرتبط با رمزارز می‌تواند انتظارات، جریان سرمایه یا تقاضا برای دارایی مشخص را تغییر دهد؛ ارتباط آن با نماد هدف باید جداگانه تأیید شود.", "en": "Crypto news can change expectations, capital flows or demand for a specific asset; its connection to the target symbol must be verified separately.", "de": "Krypto-Nachrichten können Erwartungen, Kapitalflüsse oder die Nachfrage nach einem bestimmten Asset verändern; der Bezug zum Zielsymbol muss separat bestätigt werden.", "fr": "Une actualité crypto peut modifier les anticipations, les flux de capitaux ou la demande d'un actif précis ; son lien avec le symbole cible doit être vérifié séparément."},
        "monitor": {"fa": "دارایی دقیق خبر، جریان ورودی/خروجی، حجم، عمق بازار، همبستگی و واکنش نماد هدف را بررسی کن.", "en": "Check the exact asset named, inflows/outflows, volume, market depth, correlation and the target symbol's reaction.", "de": "Prüfe das konkret genannte Asset, Zu- und Abflüsse, Volumen, Markttiefe, Korrelation und die Reaktion des Zielsymbols.", "fr": "Vérifiez l'actif précisément cité, les flux entrants/sortants, le volume, la profondeur du marché, la corrélation et la réaction du symbole cible."},
        "education": {"fa": "جریان سرمایه یعنی ورود یا خروج پول از یک دارایی یا گروهی از دارایی‌ها؛ این جریان به‌تنهایی جهت قطعی قیمت را تضمین نمی‌کند.", "en": "Capital flows are money entering or leaving an asset or asset group; they do not guarantee a price direction on their own.", "de": "Kapitalflüsse sind Geldbewegungen in einen Vermögenswert oder aus ihm heraus; sie garantieren allein keine Kursrichtung.", "fr": "Les flux de capitaux correspondent aux entrées et sorties d'argent d'un actif ou d'un groupe d'actifs ; ils ne garantissent pas à eux seuls une direction des prix."},
    },
    "equities": {
        "channel": {"fa": "عملکرد شرکت و انتظارات سود", "en": "Company performance and earnings expectations", "de": "Unternehmensleistung und Gewinnerwartungen", "fr": "Performance de l'entreprise et anticipations de bénéfices"},
        "why": {"fa": "گزارش مالی یا تغییر راهنمایی شرکت می‌تواند انتظارات سرمایه‌گذاران درباره درآمد، سودآوری و ارزش‌گذاری همان شرکت یا صنعت را تغییر دهد.", "en": "Financial results or changed guidance can alter expectations for revenue, profitability and valuation of that company or sector.", "de": "Finanzergebnisse oder geänderte Prognosen können Erwartungen zu Umsatz, Rentabilität und Bewertung des Unternehmens oder Sektors verändern.", "fr": "Les résultats financiers ou une nouvelle prévision peuvent modifier les attentes de chiffre d'affaires, de rentabilité et de valorisation de l'entreprise ou du secteur."},
        "monitor": {"fa": "نتایج در برابر پیش‌بینی، راهنمایی آینده، حاشیه سود، بدهی و واکنش قیمت/حجم سهم را بررسی کن.", "en": "Compare results with expectations; review forward guidance, margins, debt and the share's price/volume reaction.", "de": "Vergleiche die Ergebnisse mit den Erwartungen und prüfe Ausblick, Margen, Schulden sowie die Kurs-/Volumenreaktion der Aktie.", "fr": "Comparez les résultats aux attentes ; examinez les prévisions, les marges, la dette et la réaction du cours et des volumes de l'action."},
        "education": {"fa": "راهنمایی شرکت برآورد مدیریت از عملکرد آینده است؛ بازار معمولاً آن را در کنار نتایج فعلی ارزیابی می‌کند.", "en": "Company guidance is management's outlook for future performance; markets assess it alongside current results.", "de": "Die Unternehmensprognose ist die Einschätzung des Managements zur künftigen Entwicklung; Märkte bewerten sie zusammen mit den aktuellen Ergebnissen.", "fr": "Les prévisions de l'entreprise représentent l'estimation de la direction sur les performances futures ; le marché les évalue avec les résultats actuels."},
    },
    "fx": {
        "channel": {"fa": "نرخ ارز و جریان‌های پولی", "en": "Exchange rates and monetary flows", "de": "Wechselkurse und Geldströme", "fr": "Taux de change et flux monétaires"},
        "why": {"fa": "داده یا تصمیم مرتبط با ارز می‌تواند انتظارات نرخ بهره، ارزش نسبی ارزها و هزینه واردات/صادرات را تغییر دهد.", "en": "Currency-related data or decisions can change rate expectations, relative currency values and import/export costs.", "de": "Währungsbezogene Daten oder Entscheidungen können Zinserwartungen, relative Währungswerte sowie Import- und Exportkosten verändern.", "fr": "Les données ou décisions liées aux devises peuvent modifier les anticipations de taux, la valeur relative des monnaies et les coûts d'importation ou d'exportation."},
        "monitor": {"fa": "جفت‌ارز مرتبط، اختلاف نرخ بهره، شاخص دلار، نقدینگی و زمان انتشار داده را بررسی کن.", "en": "Check the relevant currency pair, rate differentials, dollar index, liquidity and release timing.", "de": "Prüfe das betroffene Währungspaar, Zinsdifferenzen, Dollarindex, Liquidität und Veröffentlichungszeitpunkt.", "fr": "Surveillez la paire concernée, les écarts de taux, l'indice du dollar, la liquidité et l'heure de publication."},
        "education": {"fa": "جفت‌ارز ارزش یک ارز را نسبت به ارز دیگر نشان می‌دهد؛ بالا رفتن آن یعنی ارز پایه نسبت به ارز مقابل گران‌تر شده است.", "en": "A currency pair shows one currency's value against another; a rise means the base currency has strengthened relative to the quote currency.", "de": "Ein Währungspaar zeigt den Wert einer Währung gegenüber einer anderen; ein Anstieg bedeutet, dass die Basiswährung gegenüber der Kurswährung stärker wird.", "fr": "Une paire de devises exprime la valeur d'une monnaie par rapport à une autre ; une hausse signifie que la devise de base se renforce face à la devise de cotation."},
    },
    "commodities": {
        "channel": {"fa": "عرضه، تقاضا و هزینه تولید", "en": "Supply, demand and production costs", "de": "Angebot, Nachfrage und Produktionskosten", "fr": "Offre, demande et coûts de production"},
        "why": {"fa": "رویدادهای مرتبط با کالاها می‌توانند عرضه، تقاضا، هزینه حمل‌ونقل و انتظارات تورمی را تغییر دهند؛ اثر به کالای مشخص بستگی دارد.", "en": "Commodity events can change supply, demand, transport costs and inflation expectations; the effect depends on the specific commodity.", "de": "Ereignisse bei Rohstoffen können Angebot, Nachfrage, Transportkosten und Inflationserwartungen verändern; die Wirkung hängt vom jeweiligen Rohstoff ab.", "fr": "Les événements liés aux matières premières peuvent modifier l'offre, la demande, les coûts de transport et les anticipations d'inflation ; l'effet dépend du produit concerné."},
        "monitor": {"fa": "کالای دقیق، موجودی، تولید، حمل‌ونقل، قرارداد مرجع و واکنش قیمت/حجم را بررسی کن.", "en": "Check the specific commodity, inventories, production, transport, benchmark contract and price/volume reaction.", "de": "Prüfe den konkreten Rohstoff, Lagerbestände, Produktion, Transport, Referenzkontrakt und Preis-/Volumenreaktion.", "fr": "Vérifiez la matière première concernée, les stocks, la production, le transport, le contrat de référence et la réaction des prix et volumes."},
        "education": {"fa": "کالای پایه مانند نفت یا طلا دارایی فیزیکی است که قیمت آن می‌تواند بر هزینه تولید و تورم اثر بگذارد.", "en": "A commodity such as oil or gold is a physical asset whose price can influence production costs and inflation.", "de": "Ein Rohstoff wie Öl oder Gold ist ein physischer Vermögenswert, dessen Preis Produktionskosten und Inflation beeinflussen kann.", "fr": "Une matière première comme le pétrole ou l'or est un actif physique dont le prix peut influencer les coûts de production et l'inflation."},
    },
}

_LABELS = {
    "fa": {"title": "تفسیر هوش مصنوعی و آموزش اقتصادی", "what": "چه اتفاقی افتاده؟", "why": "چرا اهمیت دارد؟", "market": "بازار و دارایی مرتبط", "effect": "اثر احتمالی بر بازار", "channel": "مسیر اثرگذاری", "horizon": "افق زمانی", "monitor": "چه چیزی را دنبال کنیم؟", "education": "نکته آموزشی", "uncertainty": "ابهام‌ها و محدودیت‌ها", "disclaimer": "این تحلیل آموزشی و زمینه‌ای است؛ پیش‌بینی قطعی یا سیگنال معامله نیست."},
    "en": {"title": "AI interpretation & economic learning", "what": "What happened?", "why": "Why does it matter?", "market": "Affected market and asset", "effect": "Potential market effect", "channel": "Transmission channel", "horizon": "Time horizon", "monitor": "What to monitor", "education": "Learning point", "uncertainty": "Uncertainty and limits", "disclaimer": "Educational context only; not a certain forecast or trading signal."},
    "de": {"title": "KI-Einordnung & Wirtschaftswissen", "what": "Was ist passiert?", "why": "Warum ist das wichtig?", "market": "Betroffener Markt und Vermögenswert", "effect": "Mögliche Marktwirkung", "channel": "Wirkungskanal", "horizon": "Zeithorizont", "monitor": "Was sollte beobachtet werden?", "education": "Lernhinweis", "uncertainty": "Unsicherheiten und Grenzen", "disclaimer": "Nur zur Information und Bildung; keine sichere Prognose oder Handelssignal."},
    "fr": {"title": "Interprétation IA et pédagogie économique", "what": "Que s'est-il passé ?", "why": "Pourquoi est-ce important ?", "market": "Marché et actif concernés", "effect": "Effet potentiel sur le marché", "channel": "Mécanisme de transmission", "horizon": "Horizon temporel", "monitor": "Éléments à surveiller", "education": "Point pédagogique", "uncertainty": "Incertitudes et limites", "disclaimer": "Contexte pédagogique uniquement ; ni prévision certaine ni signal de trading."},
}


def build_news_item_interpretation_v1(
    *, title: str, context: Mapping[str, str], categories: tuple[str, ...] | list[str],
    directional_bias: str, impact: float, confidence: float, freshness: str,
    caveats: tuple[str, ...] | list[str], reasons: tuple[str, ...] | list[str],
) -> dict:
    """Build one canonical, locale-invariant interpretation with four translations."""
    market = str(context.get("market") or "unknown")
    symbol = str(context.get("symbol") or "")
    venue = str(context.get("venue") or "")
    category = next((name for name in categories if name in _CATEGORY), "")
    profile = _CATEGORY.get(category)
    direct = "symbol_keyword_match" in reasons or "explicit_market_tag" in reasons
    if direct:
        relevance_scope = "direct_symbol_or_explicit_tag"
    elif "market_keyword_match" in reasons or "market_relevant_category" in reasons:
        relevance_scope = "market_or_category_level"
    else:
        relevance_scope = "unconfirmed_relevance"
    # Headline sentiment is not a causal market-impact model. Keep the
    # potential price effect unknown until independent event/market evidence
    # establishes direction; sentiment remains upstream metadata only.
    effect = "mixed_or_unknown"
    localized_caveat_codes = list(caveats)
    if directional_bias in {"positive", "negative"}:
        localized_caveat_codes.append("headline_sentiment_not_causal")
    caveat_labels = {
        "publication_time_unverified": {"fa": "زمان انتشار تأیید نشده است.", "en": "Publication time is unverified.", "de": "Der Veröffentlichungszeitpunkt ist nicht verifiziert.", "fr": "L'heure de publication n'est pas vérifiée."},
        "publication_time_in_future": {"fa": "زمان ثبت‌شده در آینده است و باید بررسی شود.", "en": "The recorded publication time is in the future and needs review.", "de": "Der angegebene Veröffentlichungszeitpunkt liegt in der Zukunft und muss geprüft werden.", "fr": "L'heure de publication indiquée est dans le futur et doit être vérifiée."},
        "source_url_missing": {"fa": "پیوند منبع در دسترس نیست.", "en": "The source URL is missing.", "de": "Die Quellen-URL fehlt.", "fr": "L'URL de la source est absente."},
        "direction_not_established_by_rules": {"fa": "جهت اثر از قواعد موجود قابل تعیین نیست.", "en": "The direction of impact is not established by the current rules.", "de": "Die Wirkungsrichtung lässt sich mit den aktuellen Regeln nicht bestimmen.", "fr": "La direction de l'effet ne peut pas être établie par les règles actuelles."},
        "market_relevance_is_category_based": {"fa": "ارتباط فقط در سطح دسته بازار است، نه لزوماً نماد هدف.", "en": "Relevance is category-level, not necessarily specific to the target symbol.", "de": "Der Bezug besteht auf Kategorieebene und nicht zwingend zum Zielsymbol.", "fr": "La pertinence concerne la catégorie et pas nécessairement le symbole cible."},
        "source_identity_unverified": {"fa": "هویت ناشر تأیید نشده است.", "en": "The publisher identity is unverified.", "de": "Die Identität des Herausgebers ist nicht verifiziert.", "fr": "L'identité de l'éditeur n'est pas vérifiée."},
        "secondary_ai_summary": {"fa": "محتوا خلاصه ثانویه هوش مصنوعی است و باید با منبع اصلی تطبیق داده شود.", "en": "This is a secondary AI summary and should be checked against the original source.", "de": "Dies ist eine sekundäre KI-Zusammenfassung und sollte mit der Originalquelle abgeglichen werden.", "fr": "Il s'agit d'un résumé secondaire généré par IA, à vérifier auprès de la source originale."},
        "headline_sentiment_not_causal": {"fa": "بار احساسی تیتر به‌تنهایی رابطه علّی یا جهت حرکت قیمت را ثابت نمی‌کند.", "en": "Headline sentiment alone does not establish causality or price direction.", "de": "Die Stimmung einer Überschrift allein belegt weder Kausalität noch Kursrichtung.", "fr": "Le ton du titre ne suffit pas à établir un lien causal ni une direction des prix."},
    }
    impact_level = "high" if impact >= 0.75 else "medium" if impact >= 0.45 else "low"
    horizon = "not_established"
    channel = profile["channel"] if profile else {lang: {"fa": "مسیر اثرگذاری هنوز مشخص نیست", "en": "Transmission channel not established", "de": "Wirkungskanal nicht festgestellt", "fr": "Mécanisme non établi"}[lang] for lang in LOCALES}
    why = profile["why"] if profile else {lang: {"fa": "اطلاعات موجود برای توضیح رابطه اقتصادی این خبر با بازار هدف کافی نیست.", "en": "Available evidence is insufficient to explain an economic link between this item and the target market.", "de": "Die verfügbaren Belege reichen nicht aus, um einen wirtschaftlichen Zusammenhang mit dem Zielmarkt zu erklären.", "fr": "Les éléments disponibles ne suffisent pas à établir un lien économique avec le marché cible."}[lang] for lang in LOCALES}
    monitor = profile["monitor"] if profile else {lang: {"fa": "منبع رسمی، ارتباط خبر با دارایی هدف و واکنش قیمت و حجم را بررسی کن.", "en": "Check the official source, relevance to the target asset, and price/volume reaction.", "de": "Prüfe die offizielle Quelle, den Bezug zum Ziel-Asset und die Preis-/Volumenreaktion.", "fr": "Vérifiez la source officielle, le lien avec l'actif cible et la réaction des prix et volumes."}[lang] for lang in LOCALES}
    education = profile["education"] if profile else {lang: {"fa": "ارتباط یک خبر با قیمت فقط زمانی معتبرتر می‌شود که سازوکار اقتصادی و شواهد بازار آن را تأیید کنند.", "en": "A news-to-price link is more credible when both an economic mechanism and market evidence support it.", "de": "Ein Zusammenhang zwischen Nachricht und Kurs ist glaubwürdiger, wenn sowohl ein wirtschaftlicher Mechanismus als auch Marktdaten ihn stützen.", "fr": "Le lien entre une actualité et un prix est plus crédible lorsqu'un mécanisme économique et des données de marché le confirment."}[lang] for lang in LOCALES}
    localized = {}
    effect_labels = {
        "fa": {"positive": "فشار مثبت بالقوه", "negative": "فشار منفی بالقوه", "mixed_or_unknown": "مختلط یا نامشخص"},
        "en": {"positive": "Potential positive pressure", "negative": "Potential negative pressure", "mixed_or_unknown": "Mixed or unknown"},
        "de": {"positive": "Potenziell positiver Druck", "negative": "Potenziell negativer Druck", "mixed_or_unknown": "Gemischt oder unklar"},
        "fr": {"positive": "Pression potentiellement positive", "negative": "Pression potentiellement négative", "mixed_or_unknown": "Mitigé ou indéterminé"},
    }
    horizon_labels = {
        "fa": "از شواهد فعلی قابل تعیین نیست",
        "en": "Cannot be established from current evidence",
        "de": "Aus den aktuellen Belegen nicht bestimmbar",
        "fr": "Impossible à déterminer avec les éléments actuels",
    }
    scope_labels = {
        "fa": {"direct_symbol_or_explicit_tag": "ارتباط مستقیم با نماد/برچسب دارایی", "market_or_category_level": "ارتباط در سطح بازار یا دسته", "unconfirmed_relevance": "ارتباط با بازار هدف تأیید نشده"},
        "en": {"direct_symbol_or_explicit_tag": "Direct symbol or explicit asset-tag match", "market_or_category_level": "Market- or category-level relevance", "unconfirmed_relevance": "Relevance to target market is unconfirmed"},
        "de": {"direct_symbol_or_explicit_tag": "Direkter Symbol- oder Asset-Tag-Treffer", "market_or_category_level": "Relevanz auf Markt- oder Kategorieebene", "unconfirmed_relevance": "Bezug zum Zielmarkt ist nicht bestätigt"},
        "fr": {"direct_symbol_or_explicit_tag": "Correspondance directe du symbole ou du tag d'actif", "market_or_category_level": "Pertinence au niveau du marché ou de la catégorie", "unconfirmed_relevance": "Lien avec le marché cible non confirmé"},
    }
    uncertainty_map = {
        "fa": "منبع/زمان/ارتباط و کیفیت شواهد را باید جداگانه بررسی کرد. امتیازهای عددی، احتمال آماری نیستند.",
        "en": "Source, timing, relevance and evidence quality require separate checks. Numeric scores are not statistical probabilities.",
        "de": "Quelle, Zeitpunkt, Relevanz und Belegqualität müssen separat geprüft werden. Numerische Werte sind keine statistischen Wahrscheinlichkeiten.",
        "fr": "La source, le moment, la pertinence et la qualité des preuves doivent être vérifiés séparément. Les scores numériques ne sont pas des probabilités statistiques.",
    }
    for lang in LOCALES:
        labels = _LABELS[lang]
        localized[lang] = {
            "labels": labels,
            "what_happened": {
                "fa": "تیتر منبع: " + title,
                "en": "Source headline: " + title,
                "de": "Originalüberschrift: " + title,
                "fr": "Titre de la source : " + title,
            }[lang],
            "why_it_matters": why[lang],
            "affected_market": (market + ((" / " + symbol) if symbol else "") + ((" · " + venue) if venue else "")),
            "relevance_scope": scope_labels[lang][relevance_scope],
            "potential_effect": effect_labels[lang][effect],
            "impact_level": impact_level,
            "transmission_channel": channel[lang],
            "time_horizon": horizon_labels[lang],
            "what_to_monitor": monitor[lang],
            "educational_concept": education[lang],
            "uncertainty": uncertainty_map[lang] + (" " + " ".join(
                caveat_labels.get(code, {}).get(lang, {
                    "fa": "یک محدودیت شواهدی دیگر نیز نیازمند بررسی است.",
                    "en": "An additional evidence caveat requires review.",
                    "de": "Ein weiterer Belegvorbehalt muss geprüft werden.",
                    "fr": "Une réserve supplémentaire concernant les preuves doit être examinée.",
                }) for code in dict.fromkeys(localized_caveat_codes)
            ) if localized_caveat_codes else ""),
            "disclaimer": labels["disclaimer"],
        }
    return {
        "schema_version": SCHEMA_VERSION,
        "method": "deterministic_evidence_grounded_templates_v1",
        "context": {"market": market, "symbol": symbol, "venue": venue},
        "category": category or "unclassified",
        "relevance_scope": relevance_scope,
        "potential_effect": effect,
        "impact_level": impact_level,
        "impact_score": round(float(impact), 3),
        "confidence_score": round(float(confidence), 3),
        "scores_are_probabilities": False,
        "freshness": freshness,
        "time_horizon": horizon,
        "source_facts": {"headline": title},
        "evidence": {"reasons": list(reasons), "caveats": list(caveats)},
        "mother_use": {"role": "context_and_confirmation_only", "requires_independent_market_confirmation": True, "news_alone_can_authorize_trade": False},
        "localized": localized,
    }
