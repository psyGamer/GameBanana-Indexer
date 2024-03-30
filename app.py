import requests
import json
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
    creation_data: int
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

GB_GAME_ID = "19773"

def fetch_all_mods() -> [str]:
    mod_ids = []
    
    # We need to index all pages until no more mods are returned
    curr_page = 1
    while True:
        url = f"https://api.gamebanana.com/Core/List/New?page={curr_page}&gameid={GB_GAME_ID}&itemtype=Mod"
        print(f"Fetching {url}")
        res = requests.get(url)
        json = res.json()
        curr_page += 1

        if len(json) == 0:
            break
    
        for type, id in json:
            mod_ids.append(id)

    return mod_ids


def fetch_mod_metadata(id: str) -> ModMetadata:
    url = f"https://api.gamebanana.com/Core/Item/Data?itemid={id}&fields=name,description,Owner().name,catid,Category().name,downloads,Files().aFiles()&itemtype=Mod"
    print(f"Fetching {url}")
    res = requests.get(url)
    json = res.json()

    files = []
    for file_id in json[6]:
        file = json[6][file_id]
        files.append(File(file["_sFile"], file["_sDownloadUrl"], file["_nFilesize"], file["_tsDateAdded"], file["_nDownloadCount"]))

    return ModMetadata(id, json[0], json[1], json[2], Category(json[3], json[4]), json[5], files)

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
