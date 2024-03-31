import requests
import json
import zipfile
import dataclasses
import traceback
import time
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

    @classmethod
    def from_json(cls, json_data):
        return ModMetadata(
            json_data["gamebanana_id"],
            json_data["mod_id"],
            json_data["name"],
            json_data["desc"],
            json_data["version"],
            json_data["fuji_required_version"],
            json_data["dependencies"],
            json_data["author"],
            Category(**json_data["category"]),
            json_data["total_downloads"],
            [File(**file) for file in json_data["files"]],
            json_data["screenshots"]
        )

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

    @classmethod
    def from_json(cls, json_data):
        return GamebananaIndex(
            json_data["id_to_index"],
            [ModMetadata.from_json(meta) for meta in json_data["mod_metas"]]
        )

GB_GAME_ID = "19773"

MAX_RETRY_ATTEMPTS = 5
RETRY_TIMEOUT_S = 5

def fetch_all_mods() -> [str]:
    mod_ids = []
    
    # We need to index all pages until no more mods are returned
    curr_page = 0
    while True:
        curr_page += 1

        retries = 1

        json = None
        
        while True:
            try:
                url = f"https://gamebanana.com/apiv11/Mod/Index?_aFilters[Generic_Game]={GB_GAME_ID}&_nPerpage=50&_nPage={curr_page}"
                print(f"Fetching {url} (try {retries} / {MAX_RETRY_ATTEMPTS})", flush=True)
                res = requests.get(url)
                if res.status_code != 200:
                    raise Exception(res.text)
                json = res.json()
                break
            except Exception as ex:
                print(f"Failed to fetch! {ex}", flush=True)
                retries += 1
                if retries > MAX_RETRY_ATTEMPTS:
                    print("Aborting update!")
                    exit(-1)
                time.sleep(RETRY_TIMEOUT_S)
              
        for mod in json["_aRecords"]:
            mod_ids.append(mod["_idRow"])

        if json["_aMetadata"]["_bIsComplete"]:
            return mod_ids


    return mod_ids


def fetch_fuji_meta(file: File) -> FujiMetadata:
    retries = 1
    res = None
    
    while True:
        try:
            print(f"Fetching {file.url} (try {retries} / {MAX_RETRY_ATTEMPTS})", flush=True)
            res = requests.get(file.url)
            if res.status_code != 200:
                    raise Exception(res.text)
            break
        except Exception as ex:
            print(f"Failed to fetch! {ex}", flush=True)
            retries += 1
            if retries > MAX_RETRY_ATTEMPTS:
                print("Aborting fetch!")
                return None
            time.sleep(RETRY_TIMEOUT_S)

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
    return None

                 
        
def fetch_mod_metadata(old_meta: Optional[ModMetadata], id: int) -> ModMetadata:
    retries = 1

    json = None
        
    while True:
        try:
            url = f"https://gamebanana.com/apiv11/Mod/{id}?_csvProperties=_sName,_sDescription,_sDownloadUrl,_aFiles,_aSubmitter,_aCategory,_nDownloadCount,_aPreviewMedia"
            print(f"Fetching {url} (try {retries} / {MAX_RETRY_ATTEMPTS})", flush=True)
            res = requests.get(url)
            if res.status_code != 200:
                raise Exception(res.text)
            json = res.json()
            break
        except Exception as ex:
            print(f"Failed to fetch! {ex}", flush=True)
            retries += 1
            if retries > MAX_RETRY_ATTEMPTS:
                print("Aborting fetch!")
                return None
            time.sleep(RETRY_TIMEOUT_S)
    
    files = []
    for file in json["_aFiles"]:
        files.append(File(file["_sFile"], file["_sDownloadUrl"], file["_nFilesize"], file["_tsDateAdded"], file["_nDownloadCount"]))

    screenshots = []
    for screenshot in json["_aPreviewMedia"]["_aImages"]:
        screenshots.append(f"{screenshot['_sBaseUrl']}/{screenshot['_sFile']}")

    # Re-use previous data if latest file hasn't changed
    if old_meta is not None and old_meta.files[0].creation_date == files[0].creation_date:
        print(f"Skipping {files[0].url}", flush=True)
        return ModMetadata(
            id,
            old_meta.mod_id,
            json["_sName"],
            json["_sDescription"],
            old_meta.version,
            old_meta.fuji_required_version,
            old_meta.dependencies,
            json["_aSubmitter"]["_sName"],
            Category(
                json["_aCategory"]["_idRow"], 
                json["_aCategory"]["_sName"]),
            json["_nDownloadCount"],
            files,
            screenshots
        )
    
    fuji_meta = fetch_fuji_meta(files[0])
    if fuji_meta is None:
        raise Exception("Fuji.json not found")

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
        screenshots
    )

  
class EnhancedJSONEncoder(json.JSONEncoder):
    def default(self, o):
        if dataclasses.is_dataclass(o):
            return dataclasses.asdict(o)
        return super().default(o)

def main():

    old_index: Optional[GamebananaIndex] = None
    try:
        with open("gb_index.json", "r") as f:
            old_index = GamebananaIndex.from_json(json.load(f))
    except Exception:
        print("Cached previous index not found")
    
    mod_ids = fetch_all_mods()

    id_to_index = {}
    mod_metas = []

    i = 0
    for id in mod_ids:
        try:
            old_meta: Optional[ModMetadata] = None
            if old_index is not None and f"{id}" in old_index.id_to_index:
                old_meta = old_index.mod_metas[old_index.id_to_index[f"{id}"]]
            
            mod_metas.append(fetch_mod_metadata(old_meta, id))
            id_to_index[id] = i
            i += 1
        except Exception as ex:
            print(f"Failed fetching metadata: {ex}", flush=True)
    
    with open("gb_index.json", "w") as f:
        json.dump(GamebananaIndex(id_to_index, mod_metas), f, ensure_ascii=False, indent=4, cls=EnhancedJSONEncoder)
    with open("gb_index.min.json", "w") as f:
        json.dump(GamebananaIndex(id_to_index, mod_metas), f, separators=(',', ':'), cls=EnhancedJSONEncoder)

if __name__ == "__main__":
    main()
