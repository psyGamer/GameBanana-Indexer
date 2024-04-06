import requests
import json
import zipfile
import dataclasses
import traceback
import time
import os
from dataclasses import dataclass
from typing import Optional
from discord_webhook import DiscordWebhook, DiscordEmbed
from functools import partial

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
class Author:
    name: str
    icon_url: str
    profile_url: str

@dataclass
class ModMetadata:
    gamebanana_id: int
    mod_id: str
    name: str
    desc: str
    version: str
    fuji_required_version: str
    dependencies: dict[str,str]
    author: Author
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
            Author(**json_data["author"]),
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
    author: Author
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

@dataclass
class IndexUpdateStatus:
    created: list[ModMetadata]
    updated: list[(ModMetadata, ModMetadata)]

GITHUB_RUN_ID = os.getenv("GITHUB_RUN_ID")
GITHUB_RUN_URL = f"https://github.com/psyGamer/GameBanana-Indexer/actions/runs/{GITHUB_RUN_ID}" # TODO: Change URL once in Fuji org!

WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")
WEBHOOK_VERBOSE_THEAD_ID = "1225928648079446157"
WEBHOOK_COLOR_ERROR = "bb1717"
WEBHOOK_COLOR_SUCCESS = "89f556"
WEBHOOK_COLOR_BANANA = "FFF133" 
webhook = DiscordWebhook(url=WEBHOOK_URL)
webhook_verbose = DiscordWebhook(url=WEBHOOK_URL, thread_id=WEBHOOK_VERBOSE_THEAD_ID)
webhook_live_status = DiscordWebhook(url=WEBHOOK_URL, thread_id=WEBHOOK_VERBOSE_THEAD_ID)

live_status_embed = DiscordEmbed(title="Live Status", description="", url=GITHUB_RUN_URL)
webhook_live_status.add_embed(live_status_embed)
webhook_live_status.execute()

GB_GAME_ID = "19773"

MAX_RETRY_ATTEMPTS = 5
RETRY_TIMEOUT_S = 5

# The webhook library doesn't include the thread_id param when editing...
def edit_webhook(self: DiscordWebhook) -> "requests.Response":
     """
     Edit an already sent webhook with updated data.
     :return: Response of the sent webhook
     """
     assert isinstance(
         self.id, str
     ), "Webhook ID needs to be set in order to edit the webhook."
     assert isinstance(
         self.url, str
     ), "Webhook URL needs to be set in order to edit the webhook."
     url = f"{self.url}/messages/{self.id}"
     if bool(self.files) is False:
         request = partial(
             requests.patch,
             url,
             json=self.json,
             proxies=self.proxies,
             params={"wait": True, "thread_id": self.thread_id},
             timeout=self.timeout,
         )
     else:
         self.files["payload_json"] = (None, json.dumps(self.json))
         request = partial(
             requests.patch,
             url,
             files=self.files,
             proxies=self.proxies,
             timeout=self.timeout,
         )
     response = request()

   
     if response.status_code in [200, 204]:
         # logger.debug("Webhook with id {id} edited".format(id=self.id))
         pass
     elif response.status_code == 429 and self.rate_limit_retry:
         response = self.handle_rate_limit(response, request)
         # logger.debug("Webhook edited")
     else:
         # logger.error(
         #     "Webhook status code {status_code}: {content}".format(
         #         status_code=response.status_code,
         #         content=response.content.decode("utf-8"),
         #     )
         # )
         pass
     return response

def log(msg: str):
    print(msg, flush=True) # Need to flush because otherwise GitHub would buffer it
    live_status_embed.description += f"{msg}\n"
    live_status_embed.set_timestamp()
    edit_webhook(webhook_live_status)

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
                log(f"Fetching {url} (try {retries} / {MAX_RETRY_ATTEMPTS})")
                res = requests.get(url)
                if res.status_code != 200:
                    raise Exception(res.text)
                json = res.json()
                break
            except Exception as ex:
                log(f"Failed to fetch! {ex}")
                retries += 1
                if retries > MAX_RETRY_ATTEMPTS:
                    log("Aborting update!")
                    embed = DiscordEmbed(title=f"Failed to fetch '{url}' in {MAX_RETRY_ATTEMPTS} attempts: {ex}", description=traceback.format_exc(), color=WEBHOOK_COLOR_ERROR)
                    embed.set_timestamp()
                    webhook_verbose.add_embed(embed)
                    webhook_verbose.execute(remove_embeds=True)     
                    exit(-1)
                time.sleep(RETRY_TIMEOUT_S)
              
        for mod in json["_aRecords"]:
            screenshots = []
            for screenshot in mod["_aPreviewMedia"]["_aImages"]:
                screenshots.append(f"{screenshot['_sBaseUrl']}/{screenshot['_sFile']}")

            mod_indices.append(ModIndexData(
                mod["_idRow"], 
                mod["_sName"], 
                Author(mod["_aSubmitter"]["_sName"], mod["_aSubmitter"]["_sAvatarUrl"], mod["_aSubmitter"]["_sProfileUrl"]), 
                mod["_tsDateModified"], 
                screenshots))

        if json["_aMetadata"]["_bIsComplete"]:
            return mod_indices

def fetch_fuji_meta(file: File) -> FujiMetadata:
    retries = 1
    res = None
    
    while True:
        try:
            log(f"Fetching {file.url} (try {retries} / {MAX_RETRY_ATTEMPTS})")
            res = requests.get(file.url)
            if res.status_code != 200:
                    raise Exception(res.text)
            break
        except Exception as ex:
            log(f"Failed to fetch! {ex}")
            retries += 1
            if retries > MAX_RETRY_ATTEMPTS:
                log("Aborting fetch!")
                embed = DiscordEmbed(title=f"Failed to fetch '{url}' in {MAX_RETRY_ATTEMPTS} attempts: {ex}", description=traceback.format_exc(), color=WEBHOOK_COLOR_ERROR)
                embed.set_timestamp()
                webhook_verbose.add_embed(embed)
                webhook_verbose.execute(remove_embeds=True)     
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
            log(f"Fetching {url} (try {retries} / {MAX_RETRY_ATTEMPTS})")
            res = requests.get(url)
            if res.status_code != 200:
                raise Exception(res.text)
            json = res.json()
            break
        except Exception as ex:
            log(f"Failed to fetch! {ex}")
            retries += 1
            if retries > MAX_RETRY_ATTEMPTS:
                log("Aborting fetch!")
                embed = DiscordEmbed(title=f"Failed to fetch '{url}' in {MAX_RETRY_ATTEMPTS} attempts: {ex}", description=traceback.format_exc(), color=WEBHOOK_COLOR_ERROR)
                embed.set_timestamp()
                webhook_verbose.add_embed(embed)
                webhook_verbose.execute(remove_embeds=True)     
                return None
            time.sleep(RETRY_TIMEOUT_S)
    
    files = []
    for file in json["_aFiles"]:
        files.append(File(file["_sFile"], file["_sDownloadUrl"], file["_nFilesize"], file["_tsDateAdded"], file["_nDownloadCount"]))

    # Re-use previous data if latest file hasn't changed
    if old_meta is not None and old_meta.files[0].creation_date == files[0].creation_date:
        log(f"Skipping {files[0].url}")
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
    except Exception as ex:
        log("Cached previous index not found")
        log(traceback.format_exc())
        embed = DiscordEmbed(title=f"Invalid Cache: {ex}", description=traceback.format_exc(), color=WEBHOOK_COLOR_ERROR)
        embed.set_timestamp()
        webhook_verbose.add_embed(embed)
        webhook_verbose.execute(remove_embeds=True)     
    
    mod_indices = fetch_all_mods()

    id_to_index = {}
    mod_metas = []
    invalid_mods = []

    update_status = IndexUpdateStatus([], [])

    i = 0
    for idx in reversed(mod_indices): # Process mods from oldest to newest
        old_meta: Optional[ModMetadata] = None
        if old_index is not None and f"{idx.id}" in old_index.id_to_index:
            old_meta = old_index.mod_metas[old_index.id_to_index[f"{idx.id}"]]

        # Skip fetching metadata if mod wasn't modified
        if old_meta is not None and idx.modify_date == old_meta.modify_date:
            log(f"Skipping {idx.id}")
            mod_metas.append(old_meta)
            id_to_index[idx.id] = i
            i += 1
            continue

        old_invalid: Optional[ModIndexData] = None
        if old_index is not None:
            old_invalid = next((x for x in old_index._invalid_mods if x.id == idx.id), None)

        # Skip fetching metadata if mod was invalid and still is
        if old_invalid is not None and idx.modify_date == old_invalid.modify_date:
            log(f"Still invalid {idx.id}")
            invalid_mods.append(old_invalid)
            continue
        
        try:
            meta = fetch_mod_metadata(old_meta, idx)
            mod_metas.append(meta)
            id_to_index[idx.id] = i
            i += 1

            if old_meta is None: # New
                update_status.created.append(meta)
            else:
                update_status.updated.append((old_meta, meta))
            
            pass
        except Exception as ex:
            log(f"Failed fetching metadata: {ex}")
            invalid_mods.append(idx)

            # TODO: Handle https://gamebanana.com/tools/* URLs
            embed = DiscordEmbed(title=f"Invalid: **{idx.name}**", description=str(ex), url=f"https://gamebanana.com/mods/{idx.id}", color=WEBHOOK_COLOR_ERROR)
            embed.set_timestamp(idx.modify_date)
            embed.set_author(name=idx.author.name, url=idx.author.profile_url, icon_url=idx.author.icon_url)

            if len(idx.screenshots) > 0:
                embed.set_image(url=idx.screenshots[0])

            webhook.add_embed(embed)

            for i in range(1, len(idx.screenshots)):
                image_embed = DiscordEmbed(url=f"https://gamebanana.com/mods/{idx.id}")
                image_embed.set_image(url=idx.screenshots[i])
            
            webhook.execute(remove_embeds=True)

    with open("gb_index.json", "w") as f:
        json.dump(GamebananaIndex(id_to_index, mod_metas, invalid_mods), f, ensure_ascii=False, indent=4, cls=EnhancedJSONEncoder)
    with open("gb_index.min.json", "w") as f:
        json.dump(GamebananaIndexMinified(id_to_index, mod_metas), f, separators=(',', ':'), cls=EnhancedJSONEncoder)

    for meta in update_status.created:
        # TODO: Handle https://gamebanana.com/tools/* URLs
        embed = DiscordEmbed(title=f"New: **{meta.name}**", description=meta.desc, url=f"https://gamebanana.com/mods/{meta.gamebanana_id}", color=WEBHOOK_COLOR_BANANA)
        embed.set_timestamp(meta.files[0].creation_date)
        embed.set_author(name=meta.author.name, url=meta.author.profile_url, icon_url=meta.author.icon_url)
        
        embed.add_embed_field(name="Download Latest Version", value=f"[{meta.files[0].name}]({meta.files[0].url})")

        if len(meta.screenshots) > 0:
            embed.set_image(url=meta.screenshots[0])

        webhook.add_embed(embed)

        for i in range(1, len(meta.screenshots)):
            image_embed = DiscordEmbed(url=f"https://gamebanana.com/mods/{meta.gamebanana_id}")
            image_embed.set_image(url=meta.screenshots[i])
            webhook.add_embed(image_embed)
        
        webhook.execute(remove_embeds=True)

    for old_meta, meta in update_status.updated:
        # TODO: Handle https://gamebanana.com/tools/* URLs
        embed = DiscordEmbed(title=f"Update: **{meta.name}**", description=meta.desc, url=f"https://gamebanana.com/mods/{meta.gamebanana_id}", color=WEBHOOK_COLOR_BANANA)
        embed.set_timestamp(meta.files[0].creation_date)
        embed.set_author(name=meta.author.name, url=meta.author.profile_url, icon_url=meta.author.icon_url)
        
        embed.add_embed_field(name="Download Latest Version", value=f"[{meta.files[0].name}]({meta.files[0].url})")
        embed.add_embed_field(name="Version", value=f"**{old_meta.version}** → **{meta.version}**")

        if len(meta.screenshots) > 0:
            embed.set_image(url=meta.screenshots[0])

        webhook.add_embed(embed)

        for i in range(1, len(meta.screenshots)):
            image_embed = DiscordEmbed(url=f"https://gamebanana.com/mods/{meta.gamebanana_id}")
            image_embed.set_image(url=meta.screenshots[i])
            webhook.add_embed(image_embed)
        
        webhook.execute(remove_embeds=True)

if __name__ == "__main__":
    try:
        main()
        live_status_embed.description += "\n**Done**\n"
        live_status_embed.set_timestamp()
        live_status_embed.set_color(WEBHOOK_COLOR_SUCCESS)
        edit_webhook(webhook_live_status)
    except Exception as ex:
        log(ex)
        log(traceback.format_exc())
        embed = DiscordEmbed(title=f"Indexer Failure: {ex}", description=traceback.format_exc(), url=GITHUB_RUN_URL, color=WEBHOOK_COLOR_ERROR)
        embed.set_timestamp()
        webhook_verbose.add_embed(embed)
        webhook_verbose.execute(remove_embeds=True)     
