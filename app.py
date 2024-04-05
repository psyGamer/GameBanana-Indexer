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
    modify_date: int
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
            json_data["modify_date"],
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
class ModIndexData:
    id: int
    name: str
    author: str
    modify_date: int
    screenshots: list[str]

@dataclass
class GamebananaIndex:
    id_to_index: dict[int,int]
    mod_metas: list[ModMetadata]

    # Only needed for caching
    _invalid_mods: list[ModIndexData]

    @classmethod
    def from_json(cls, json_data):
        return GamebananaIndex(
            json_data["id_to_index"],
            [ModMetadata.from_json(meta) for meta in json_data["mod_metas"]],
            [ModIndexData(**idx) for idx in json_data["_invalid_mods"]]
        )

@dataclass
class GamebananaIndexMinified:
    id_to_index: dict[int,int]
    mod_metas: list[ModMetadata]

GB_GAME_ID = "19773"

MAX_RETRY_ATTEMPTS = 5
RETRY_TIMEOUT_S = 5

def fetch_all_mods() -> list[ModIndexData]:
    mod_indices = []
    
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
            screenshots = []
            for screenshot in mod["_aPreviewMedia"]["_aImages"]:
                screenshots.append(f"{screenshot['_sBaseUrl']}/{screenshot['_sFile']}")

            mod_indices.append(ModIndexData(mod["_idRow"], mod["_sName"], mod["_aSubmitter"]["_sName"], mod["_tsDateModified"], screenshots))

        if json["_aMetadata"]["_bIsComplete"]:
            return mod_indices

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
                 
        
def fetch_mod_metadata(old_meta: Optional[ModMetadata], mod_index: ModIndexData) -> ModMetadata:
    retries = 1

    json = None
        
    while True:
        try:
            url = f"https://gamebanana.com/apiv11/Mod/{mod_index.id}?_csvProperties=_sDescription,_sDownloadUrl,_aFiles,_aCategory,_nDownloadCount"
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

    # Re-use previous data if latest file hasn't changed
    if old_meta is not None and old_meta.files[0].creation_date == files[0].creation_date:
        print(f"Skipping {files[0].url}", flush=True)
        return ModMetadata(
            mod_index.id,
            old_meta.mod_id,
            mod_index.name,
            json["_sDescription"],
            old_meta.version,
            old_meta.fuji_required_version,
            old_meta.dependencies,
            mod_index.author,
            Category(
                json["_aCategory"]["_idRow"], 
                json["_aCategory"]["_sName"]),
            mod_index.modify_date,
            json["_nDownloadCount"],
            files,
            mod_index.screenshots
        )
    
    fuji_meta = fetch_fuji_meta(files[0])
    if fuji_meta is None:
        raise Exception("Fuji.json not found")

    return ModMetadata(
        mod_index.id,
        fuji_meta.id,
        mod_index.name,
        json["_sDescription"],
        fuji_meta.version,
        fuji_meta.fuji_required_version,
        fuji_meta.dependencies,
        mod_index.author,
        Category(
            json["_aCategory"]["_idRow"], 
            json["_aCategory"]["_sName"]),
        mod_index.modify_date,
        json["_nDownloadCount"],
        files,
        mod_index.screenshots
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
        print(traceback.format_exc())
    
    mod_indices = fetch_all_mods()

    id_to_index = {}
    mod_metas = []
    invalid_mods = []

    i = 0
    for idx in mod_indices:
        old_meta: Optional[ModMetadata] = None
        if old_index is not None and f"{idx.id}" in old_index.id_to_index:
            old_meta = old_index.mod_metas[old_index.id_to_index[f"{idx.id}"]]

        # Skip fetching metadata if mod wasn't modified
        if old_meta is not None and idx.modify_date == old_meta.modify_date:
            print(f"Skipping {idx.id}")
            mod_metas.append(old_meta)
            id_to_index[idx.id] = i
            i += 1
            continue

        old_invalid: Optional[ModIndexData] = None
        if old_index is not None:
            old_invalid = next((x for x in old_index._invalid_mods if x.id == idx.id), None)

        # Skip fetching metadata if mod was invalid and still is
        if old_invalid is not None and idx.modify_date == old_invalid.modify_date:
            print(f"Still invalid {idx.id}")
            invalid_mods.append(old_invalid)
            continue
        
        try:
            mod_metas.append(fetch_mod_metadata(old_meta, idx))
            id_to_index[idx.id] = i
            i += 1
            pass
        except Exception as ex:
            print(f"Failed fetching metadata: {ex}", flush=True)
            invalid_mods.append(idx)

    with open("gb_index.json", "w") as f:
        json.dump(GamebananaIndex(id_to_index, mod_metas, invalid_mods), f, ensure_ascii=False, indent=4, cls=EnhancedJSONEncoder)
    with open("gb_index.min.json", "w") as f:
        json.dump(GamebananaIndexMinified(id_to_index, mod_metas), f, separators=(',', ':'), cls=EnhancedJSONEncoder)

if __name__ == "__main__":
    main()
