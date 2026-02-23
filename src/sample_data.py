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
        "page_content": (
            "John Smith Senior Software Engineer at Google Austin, Texas "
            "Experience: Google — Senior Software Engineer (2019–Present) "
            "Building distributed systems for cloud infrastructure. Led the "
            "migration of three core services to Kubernetes, reducing latency "
            "by 40%. Amazon — Software Development Engineer II (2015–2019) "
            "Worked on AWS Lambda's cold start optimization team. Microsoft — "
            "Software Engineer (2012–2015) Contributed to Azure DevOps CI/CD "
            "pipeline tooling. Education: University of Texas at Austin — "
            "MS Computer Science (2012). Skills: Go, Python, Kubernetes, "
            "Terraform, gRPC, distributed systems."
        ),
        "source_query": "John Smith",
        "retrieved_at": "2026-02-22T12:00:00+00:00",
    },
    {
        "title": "John Smith (@jsmith_dev) on GitHub",
        "url": "https://github.com/jsmith-dev",
        "snippet": "John Smith has 47 repositories on GitHub. Contributions to "
                   "kubernetes, tensorflow, and several open-source CLI tools. "
                   "Active contributor since 2018.",
        "page_content": (
            "John Smith jsmith-dev 47 repositories 312 followers Austin, TX "
            "Pinned Repositories: kube-health-checker — A lightweight CLI tool "
            "for monitoring Kubernetes cluster health. Go. 234 stars. "
            "tf-data-pipeline — TensorFlow data pipeline utilities for large "
            "datasets. Python. 89 stars. dotfiles — Personal development "
            "environment configuration. 12 stars. Contribution activity: "
            "1,247 contributions in the last year."
        ),
        "source_query": '"John Smith" linkedin OR github',
        "retrieved_at": "2026-02-22T12:00:00+00:00",
    },
    {
        "title": "John Smith - Published Research Papers",
        "url": "https://scholar.google.com/citations?user=johnsmith",
        "snippet": "John Smith, PhD. Research interests: machine learning, NLP, "
                   "information retrieval. 23 publications, 1,200 citations. "
                   "Affiliated with University of Texas at Austin.",
        "page_content": (
            "John Smith Citations: 1,200 h-index: 14 University of Texas at "
            "Austin Research Interests: machine learning, natural language "
            "processing, information retrieval. Publications: 'Efficient "
            "Attention Mechanisms for Long Documents' — EMNLP 2024 — 87 "
            "citations. 'Scaling Retrieval-Augmented Generation' — NeurIPS "
            "2023 — 142 citations. 'Low-Rank Adaptation for Domain-Specific "
            "NLP' — ACL 2023 — 203 citations. Co-authors: Sarah Chen, "
            "Michael Park, Lisa Wong."
        ),
        "source_query": '"John Smith" profile',
        "retrieved_at": "2026-02-22T12:00:00+00:00",
    },
    {
        "title": "Building Resilient Systems - A Talk by John Smith at GopherCon",
        "url": "https://medium.com/@jsmith/building-resilient-systems",
        "snippet": "In this talk, John Smith walks through the architecture behind "
                   "Google's internal load balancing system and shares lessons "
                   "learned from running services at massive scale.",
        "page_content": (
            "Building Resilient Systems by John Smith Published in Better "
            "Programming. At GopherCon 2025, I shared how our team at Google "
            "rebuilt the internal load balancer to handle 10x traffic spikes "
            "without manual intervention. Key takeaways: Circuit breakers "
            "should be adaptive, not static. Retry budgets prevent cascading "
            "failures better than exponential backoff alone. Health checks "
            "need to test actual functionality, not just connectivity. "
            "The full slide deck is available on my GitHub."
        ),
        "source_query": "John Smith",
        "retrieved_at": "2026-02-22T12:00:00+00:00",
    },

    # --- BORDERLINE (might go either way) ---
    {
        "title": "Smith Family Reunion 2025 Photos",
        "url": "https://flickr.com/photos/smithfamily2025",
        "snippet": "Photos from the annual Smith family reunion in Lake Tahoe. "
                   "Great time with John, Mary, and the kids.",
        "page_content": (
            "Smith Family Reunion 2025 Lake Tahoe, CA. 48 photos uploaded "
            "by Mary Smith. Great weekend with the whole family. John brought "
            "his famous brisket. The kids loved the kayaking."
        ),
        "source_query": "John Smith",
        "retrieved_at": "2026-02-22T12:00:00+00:00",
    },

    # --- Should be DISCHARGED (low relevance / noise) ---
    {
        "title": "Best Italian Restaurants in Austin, TX",
        "url": "https://yelp.com/search?find_desc=italian&find_loc=Austin",
        "snippet": "Top 10 Italian restaurants in Austin. Reviews, photos, and "
                   "menus for the best pasta spots downtown.",
        "page_content": (
            "Yelp Top 10 Italian Restaurants in Austin TX. 1. Bufalina — "
            "Neapolitan pizza. 4.5 stars. 2. Intero — House-made pasta. "
            "4.3 stars. 3. Juliet — Italian-inspired seasonal menu."
        ),
        "source_query": "John Smith",
        "retrieved_at": "2026-02-22T12:00:00+00:00",
    },
    {
        "title": "How to Change Your Car Oil in 5 Steps",
        "url": "https://wikihow.com/Change-Your-Oil",
        "snippet": "A step-by-step guide to changing your car's engine oil at home. "
                   "Tools needed: wrench, drain pan, new oil filter.",
        "page_content": (
            "How to Change Your Car Oil Step 1: Warm up the engine for 5 "
            "minutes. Step 2: Locate the drain plug underneath. Step 3: "
            "Drain old oil into a pan. Step 4: Replace the oil filter. "
            "Step 5: Add new oil and check the level with the dipstick."
        ),
        "source_query": '"John Smith" profile',
        "retrieved_at": "2026-02-22T12:00:00+00:00",
    },
    {
        "title": "Weather Forecast - Austin, TX",
        "url": "https://weather.com/weather/tenday/l/Austin+TX",
        "snippet": "10-day weather forecast for Austin, Texas. High of 78F on "
                   "Tuesday. Chance of rain Wednesday afternoon.",
        "page_content": None,
        "source_query": "John Smith",
        "retrieved_at": "2026-02-22T12:00:00+00:00",
    },
]
