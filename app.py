import requests
import json
import zipfile
import dataclasses
import traceback
from dataclasses import dataclass
from typing import Optional

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
    gamebanana_id: int
    mod_id: str
    name: str
    desc: str
    version: str
    fuji_required_version: str
    dependencies: dict[str,str]
    author: str
    category: Category
    total_downloads: int
    files: list[File]
    screenshots: list[str]

@dataclass
class FujiMetadata:
    id: str
    name: str
    version: str
    author: str
    description: str
    icon: str
    fuji_required_version: str
    dependencies: dict[str,str]
    asset_replacements: dict[str,str]

@dataclass
class GamebananaIndex:
    id_to_index: dict[int,int]
    mod_metas: [ModMetadata]

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


def fetch_fuji_meta(file: File) -> FujiMetadata:
    print(f"Fetching {file.url}")
    res = requests.get(file.url)
    if res.status_code != 200:
        print(f"Failed to fetch! {res.text}")
        return None

    with open("tmp.zip", "wb") as f:
        f.write(res.content)

    with zipfile.ZipFile("tmp.zip", 'r') as zip:
        for entry in zip.filelist:
            if "fuji.json" in entry.filename.lower():
                with zip.open(entry, 'r') as fuji_json_file:
                    fuji_meta = json.load(fuji_json_file)
                    return FujiMetadata(
                        fuji_meta.get("Id", None),
                        fuji_meta.get("Name", None),
                        fuji_meta.get("Version", None),
                        fuji_meta.get("ModAuthor", None),
                        fuji_meta.get("Description", None),
                        fuji_meta.get("Icon", None),
                        fuji_meta.get("FujiRequiredVersion", None),
                        fuji_meta.get("Dependencies", {}),
                        fuji_meta.get("AssetReplacements", {}))


def fetch_mod_metadata(id: int) -> ModMetadata:
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

    fuji_meta = fetch_fuji_meta(files[0])

    return ModMetadata(
        id,
        fuji_meta.id,
        json["_sName"],
        json["_sDescription"],
        fuji_meta.version,
        fuji_meta.fuji_required_version,
        fuji_meta.dependencies,
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
    print("hi main")
    mod_ids = fetch_all_mods()

    id_to_index = {}
    mod_metas = []

    for i, id in enumerate(mod_ids):
        try:
            mod_metas.append(fetch_mod_metadata(id))
            id_to_index[id] = i
        except Exception as ex:
            print(f"Failed fetching metadata: {ex}")
    
    with open("gb_index.json", "w") as f:
        json.dump(GamebananaIndex(id_to_index, mod_metas), f, ensure_ascii=False, indent=4, cls=EnhancedJSONEncoder)

print("hi")
if __name__ == "__main__":
    main()
