import requests
import json
import dataclasses
from dataclasses import dataclass

@dataclass
class Category:
    id: int
    name: str

@dataclass
class File:
    name: str
    url: str
    size: int
    creation_date: int
    downloads: int

@dataclass
class ModMetadata:
    id: str
    name: str
    desc: str
    author: str
    category: Category
    total_downloads: int
    files: list[File]
    screenshots: list[str]

GB_GAME_ID = "19773"

def fetch_all_mods() -> [str]:
    mod_ids = []
    
    # We need to index all pages until no more mods are returned
    curr_page = 0
    while True:
        curr_page += 1
        
        url = f"https://gamebanana.com/apiv11/Mod/Index?_aFilters[Generic_Game]={GB_GAME_ID}&_nPerpage=50&_nPage={curr_page}"
        print(f"Fetching {url}")
        res = requests.get(url)
        if res.status_code != 200:
            print(f"Failed to fetch! {res.text}")
            return mod_ids

        json = res.json()
              
        for mod in json["_aRecords"]:
            mod_ids.append(mod["_idRow"])

        if json["_aMetadata"]["_bIsComplete"]:
            return mod_ids


    return mod_ids


def fetch_mod_metadata(id: str) -> ModMetadata:
    url = f"https://gamebanana.com/apiv11/Mod/{id}?_csvProperties=_sName,_sDescription,_sDownloadUrl,_aFiles,_aSubmitter,_aCategory,_nDownloadCount,_aPreviewMedia"
    print(f"Fetching {url}")
    res = requests.get(url)
    if res.status_code != 200:
        print(f"Failed to fetch! {res.text}")
        return None

    json = res.json()

    files = []
    for file in json["_aFiles"]:
        files.append(File(file["_sFile"], file["_sDownloadUrl"], file["_nFilesize"], file["_tsDateAdded"], file["_nDownloadCount"]))

    screenshots = []
    for screenshot in json["_aPreviewMedia"]["_aImages"]:
        screenshots.append(f"{screenshot['_sBaseUrl']}/{screenshot['_sFile']}")

    return ModMetadata(
        id,
        json["_sName"],
        json["_sDescription"],
        json["_aSubmitter"]["_sName"],
        Category(
            json["_aCategory"]["_idRow"], 
            json["_aCategory"]["_sName"]),
        json["_nDownloadCount"],
        files,
        screenshots)

class EnhancedJSONEncoder(json.JSONEncoder):
    def default(self, o):
        if dataclasses.is_dataclass(o):
            return dataclasses.asdict(o)
        return super().default(o)

def main():
    mod_ids = fetch_all_mods()
    mod_metas = [fetch_mod_metadata(id) for id in mod_ids]

    with open("gb_index.json", "w") as f:
        json.dump(mod_metas, f, ensure_ascii=False, indent=4, cls=EnhancedJSONEncoder)

if __name__ == "__main__":
    main()
