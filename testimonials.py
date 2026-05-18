"""
Отзывы клиентов (Customer Reviews).

Редактируется вручную или через /admin → Manage Reviews.
Поле visible=False скрывает отзыв на сайте и в боте.
"""

from __future__ import annotations

testimonials: list[dict] = [
    {
        "id": 1,
        "name": "Sarah M.",
        "city": "Stockholm",
        "track": "Divine sound Heart from God",
        "rating": 5,
        "visible": True,
        "text": (
            "I have been struggling with anxiety and emotional heaviness for years. After listening to the Heart track "
            "every morning for just two weeks, I noticed a remarkable shift. My chest feels lighter, my mood more balanced. "
            "This is not just music — it is medicine for the soul. I recommend it to everyone who wants to reconnect with "
            "love and inner peace."
        ),
    },
    {
        "id": 2,
        "name": "Anna K.",
        "city": "Göteborg",
        "track": "Divine sound Immunedefence from God",
        "rating": 4,
        "visible": True,
        "text": (
            "I started listening to the Immune Defence track when I felt a cold coming on. I was skeptical at first, "
            "but within days I felt stronger and more energized than usual. I have been listening daily for three months "
            "now and have not been sick since. My whole family thinks I have found some secret — and I have!"
        ),
    },
    {
        "id": 3,
        "name": "Marcus L.",
        "city": "Malmö",
        "track": "Divine sound NO Smoking from God",
        "rating": 5,
        "visible": True,
        "text": (
            "I smoked for 18 years and tried everything to quit. Patches, gum, hypnosis — nothing worked long term. "
            "A friend recommended this track and I thought why not try. After 30 days of daily listening my cravings "
            "reduced dramatically. Today I am smoke free for 4 months. I still listen every day because it keeps me "
            "calm and focused."
        ),
    },
    {
        "id": 4,
        "name": "Elena R.",
        "city": "Uppsala",
        "track": "Divine sound Crownchakra-Browchakra-Throatchakra from God",
        "rating": 5,
        "visible": True,
        "text": (
            "As a teacher I use my voice every single day and often felt blocked and nervous before important meetings. "
            "Since I started listening to the Chakra track I speak with so much more confidence and clarity. My students "
            "have noticed the difference! This track has genuinely changed how I communicate and express myself."
        ),
    },
    {
        "id": 5,
        "name": "Johan B.",
        "city": "Västerås",
        "track": "Divine sound Liver from God",
        "rating": 4,
        "visible": True,
        "text": (
            "After years of not taking care of myself I decided to make a change. The Liver track became part of my daily "
            "detox routine alongside better eating. Within weeks I felt cleaner, lighter and more clear headed. My energy "
            "levels are through the roof. Mikael has created something truly special here — ancient wisdom in modern sound."
        ),
    },
    {
        "id": 6,
        "name": "Linda S.",
        "city": "Sundsvall",
        "track": "Divine sound Estrogen from God",
        "rating": 5,
        "visible": True,
        "text": (
            "Going through perimenopause was exhausting — mood swings, poor sleep, no energy. A colleague told me about "
            "this track and I was desperate enough to try anything. After three weeks of daily listening I sleep better, "
            "feel more balanced emotionally and have my energy back. My doctor is amazed at how well I am managing. "
            "This track is now my daily ritual."
        ),
    },
    {
        "id": 7,
        "name": "Peter H.",
        "city": "Örebro",
        "track": "Divine sound Kidney from God",
        "rating": 5,
        "visible": True,
        "text": (
            "I have had kidney issues for years and my energy was always low. I added this track to my morning routine "
            "and within a month noticed significant improvement in my overall vitality. I feel more grounded and stable "
            "than I have in years. The sound frequencies in this track are unlike anything I have experienced before. "
            "Truly remarkable healing music."
        ),
    },
    {
        "id": 8,
        "name": "Maria T.",
        "city": "Linköping",
        "track": "Divine sound Rootchakra from God",
        "rating": 5,
        "visible": True,
        "text": (
            "After moving to a new city I felt completely lost and disconnected. Anxiety was constant and I could not sleep. "
            "The Root Chakra track brought me back to earth — literally. I feel safe, stable and grounded again. I listen "
            "every night before bed and wake up feeling centered and ready for the day. This music saved my mental health."
        ),
    },
    {
        "id": 9,
        "name": "Thomas A.",
        "city": "Helsingborg",
        "track": "Divine sound Testosteron from God",
        "rating": 4,
        "visible": True,
        "text": (
            "At 52 I felt my energy and drive fading. The gym sessions were getting harder and motivation was low. "
            "A friend recommended the Testosterone track and I was curious. After one month of daily listening my workouts "
            "improved dramatically, my focus sharpened and I feel like myself again at 35. My wife has also noticed the "
            "difference — she keeps asking what my secret is!"
        ),
    },
    {
        "id": 10,
        "name": "Sofia N.",
        "city": "Norrköping",
        "track": "Divine sound Vitamins from God",
        "rating": 5,
        "visible": True,
        "text": (
            "I was constantly tired, catching every cold going around and feeling depleted despite eating well. "
            "The Vitamins track felt like plugging myself into a power source. Within two weeks my energy returned, "
            "my skin started glowing and I stopped getting sick. I now listen every single morning as part of my wellness "
            "routine. Mikael has created pure magic in sound form."
        ),
    },
]
