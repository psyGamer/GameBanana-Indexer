import requests

GB_GAME_ID = "19773"

def fetch_all_mods():
    mod_ids = []
    
    # We need to index all pages until no more mods are returned
    curr_page = 1
    while True:
        url = f"https://api.gamebanana.com/Core/List/New?page={curr_page}&gameid={GB_GAME_ID}&itemtype=Mod"
        print(f"Fetching {url}")
        res = requests.get(url)
        mods_for_page = res.json()
        curr_page += 1

        if len(mods_for_page) == 0:
            break
    
        for type, id in mods_for_page:
            mod_ids.append(id)

    return mod_ids

def main():
    print(fetch_all_mods())

if __name__ == "__main__":
    main()
