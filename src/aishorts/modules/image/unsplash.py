import requests

ACCESS_KEY = (
    "B_Ch-l1-L_c5nAM2Xk4Q95uDr9lRDr-UKZQSj4iikcY"  # Get from unsplash.com/developers
)


def search_unsplash(query, per_page=1):
    url = "https://api.unsplash.com/search/photos"
    headers = {"Authorization": f"Client-ID {ACCESS_KEY}"}
    params = {"query": query, "per_page": per_page, "orientation": "portrait"}

    response = requests.get(url, headers=headers, params=params)
    data = response.json()

    if data["results"]:
        return data["results"][0]["urls"]["regular"]  # or "full", "small"
    return None


# Usage
image_url = search_unsplash(
    "Calvin cycle diagram with three phases: carbon fixation with Rubisco and RuBP making 3-PGA, reduction to G3P using ATP and NADPH, regeneration of RuBP using ATP, circular arrows, labeled educational chart"
)
print(image_url)
