import requests

# http://localhost:8080/search?q=%22283%20trails%20cir,%20nashville%22&format=json
# http://localhost:8080/reverse?lat=36.147600&lon=-86.621629&format=json

def test_nominatim_search():
    base_url = "http://localhost:8080"
    endpoint = "/search"
    params = {
        'q': 'New York',
        'format': 'json'
    }

    response = requests.get(base_url + endpoint, params=params)

    if response.status_code == 200:
        print("Search API call successful!")
        data = response.json()
        print("Search Response Data:", data)
    else:
        print("Search API call failed with status code:", response.status_code)

def test_nominatim_reverse():
    base_url = "http://localhost:8080"
    endpoint = "/reverse"
    params = {
        'lat': 40.7128,
        'lon': -74.0060,
        'format': 'json'
    }

    response = requests.get(base_url + endpoint, params=params)

    if response.status_code == 200:
        print("Reverse API call successful!")
        data = response.json()
        print("Reverse Response Data:", data)
    else:
        print("Reverse API call failed with status code:", response.status_code)

def test_nominatim_lookup():
    base_url = "http://localhost:8080"
    endpoint = "/lookup"
    params = {
        'osm_ids': 'W104393803',
        'format': 'json'
    }

    response = requests.get(base_url + endpoint, params=params)

    if response.status_code == 200:
        print("Lookup API call successful!")
        data = response.json()
        print("Lookup Response Data:", data)
    else:
        print("Lookup API call failed with status code:", response.status_code)

def test_nominatim_status():
    base_url = "http://localhost:8080"
    endpoint = "/status"
    params = {
        'format': 'json'
    }

    response = requests.get(base_url + endpoint, params=params)

    if response.status_code == 200:
        print("Status API call successful!")
        data = response.json()
        print("Status Response Data:", data)
    else:
        print("Status API call failed with status code:", response.status_code)

if __name__ == "__main__":
    test_nominatim_search()
    test_nominatim_reverse()
    test_nominatim_lookup()
    test_nominatim_status()
