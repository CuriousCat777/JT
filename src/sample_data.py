"""
SAMPLE DATA — The Standardized Patient
========================================
In medical school, you practice on standardized patients
before you see real ones. Same idea here.

This sample data lets you run the full Guardian pipeline
without needing internet access.
"""

SAMPLE_RESULTS = [
    # --- Should be ADMITTED (high relevance) ---
    {
        "title": "John Smith - Senior Software Engineer | LinkedIn",
        "url": "https://linkedin.com/in/john-smith-engineer",
        "snippet": "John Smith is a Senior Software Engineer at Google with 12 years "
                   "of experience in distributed systems and cloud infrastructure. "
                   "Based in Austin, TX. Previously at Amazon and Microsoft.",
        "source_query": "John Smith",
        "retrieved_at": "2026-02-22T12:00:00+00:00",
    },
    {
        "title": "John Smith (@jsmith_dev) on GitHub",
        "url": "https://github.com/jsmith-dev",
        "snippet": "John Smith has 47 repositories on GitHub. Contributions to "
                   "kubernetes, tensorflow, and several open-source CLI tools. "
                   "Active contributor since 2018.",
        "source_query": '"John Smith" linkedin OR github',
        "retrieved_at": "2026-02-22T12:00:00+00:00",
    },
    {
        "title": "John Smith - Published Research Papers",
        "url": "https://scholar.google.com/citations?user=johnsmith",
        "snippet": "John Smith, PhD. Research interests: machine learning, NLP, "
                   "information retrieval. 23 publications, 1,200 citations. "
                   "Affiliated with University of Texas at Austin.",
        "source_query": '"John Smith" profile',
        "retrieved_at": "2026-02-22T12:00:00+00:00",
    },
    {
        "title": "Building Resilient Systems - A Talk by John Smith at GopherCon",
        "url": "https://medium.com/@jsmith/building-resilient-systems",
        "snippet": "In this talk, John Smith walks through the architecture behind "
                   "Google's internal load balancing system and shares lessons "
                   "learned from running services at massive scale.",
        "source_query": "John Smith",
        "retrieved_at": "2026-02-22T12:00:00+00:00",
    },

    # --- BORDERLINE (might go either way) ---
    {
        "title": "Smith Family Reunion 2025 Photos",
        "url": "https://flickr.com/photos/smithfamily2025",
        "snippet": "Photos from the annual Smith family reunion in Lake Tahoe. "
                   "Great time with John, Mary, and the kids.",
        "source_query": "John Smith",
        "retrieved_at": "2026-02-22T12:00:00+00:00",
    },

    # --- Should be DISCHARGED (low relevance / noise) ---
    {
        "title": "Best Italian Restaurants in Austin, TX",
        "url": "https://yelp.com/search?find_desc=italian&find_loc=Austin",
        "snippet": "Top 10 Italian restaurants in Austin. Reviews, photos, and "
                   "menus for the best pasta spots downtown.",
        "source_query": "John Smith",
        "retrieved_at": "2026-02-22T12:00:00+00:00",
    },
    {
        "title": "How to Change Your Car Oil in 5 Steps",
        "url": "https://wikihow.com/Change-Your-Oil",
        "snippet": "A step-by-step guide to changing your car's engine oil at home. "
                   "Tools needed: wrench, drain pan, new oil filter.",
        "source_query": '"John Smith" profile',
        "retrieved_at": "2026-02-22T12:00:00+00:00",
    },
    {
        "title": "Weather Forecast - Austin, TX",
        "url": "https://weather.com/weather/tenday/l/Austin+TX",
        "snippet": "10-day weather forecast for Austin, Texas. High of 78F on "
                   "Tuesday. Chance of rain Wednesday afternoon.",
        "source_query": "John Smith",
        "retrieved_at": "2026-02-22T12:00:00+00:00",
    },
]
